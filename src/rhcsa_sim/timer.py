from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from rhcsa_sim.reporter import sanitize_text
from rhcsa_sim.ui import Ui, visible_len

EXAM_SECONDS = 3 * 60 * 60
_SAVE_CURSOR = "\x1b7"
_RESTORE_CURSOR = "\x1b8"
DEFAULT_EXAM_STATE = Path("/var/tmp/rhcsa-sim-exam.json")
_MAX_STATE_BYTES = 4096
# Tolerancia para relojes ligeramente desfasados antes de descartar el estado.
_FUTURE_TOLERANCE = 60.0


def format_clock(seconds: float) -> str:
    """HH:MM:SS con el tiempo redondeado hacia arriba; nunca negativo."""
    total = max(0, math.ceil(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


@dataclass(frozen=True, slots=True)
class ExamClock:
    """Cuenta regresiva del examen; `started` es una epoca (hora de pared) para
    que el tiempo con la VM apagada tambien cuente. `now` es inyectable."""

    started: float
    duration: float = EXAM_SECONDS
    now: Callable[[], float] = time.time

    def elapsed(self) -> float:
        return max(0.0, self.now() - self.started)

    def remaining(self) -> float:
        return max(0.0, self.duration - self.elapsed())

    def expired(self) -> bool:
        return self.remaining() <= 0


@dataclass(slots=True)
class ClockHolder:
    """Contenedor mutable del reloj de la sesion (el reloj en si es inmutable)."""

    clock: ExamClock | None
    path: Path | None = None
    now: Callable[[], float] = time.time

    def restart(self) -> str | None:
        """Inicia un examen nuevo ahora; devuelve un aviso si no se pudo guardar."""
        self.clock = ExamClock(started=self.now(), now=self.now)
        if self.path is None:
            return None
        try:
            save_exam(self.path, self.clock)
        except OSError:
            return save_warning(self.path)
        return None


def save_warning(path: Path) -> str:
    return (
        f"Could not save the exam timer to {sanitize_text(str(path))} "
        "(permission denied?); run with sudo consistently."
    )


def _valid_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def load_exam(path: Path, now: Callable[[], float] = time.time) -> ExamClock | None:
    """Lee el examen guardado; None si falta o no es confiable (sin seguir symlinks)."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as handle:
            raw = handle.read(_MAX_STATE_BYTES)
        data = json.loads(raw)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    started = _valid_number(data.get("started"))
    duration = _valid_number(data.get("duration"))
    if started is None or duration is None or duration <= 0:
        return None
    if started > now() + _FUTURE_TOLERANCE:
        return None
    return ExamClock(started=started, duration=duration, now=now)


def save_exam(path: Path, clock: ExamClock) -> None:
    """Guarda el examen de forma atomica; rename reemplaza un symlink, no su destino."""
    payload = json.dumps({"started": clock.started, "duration": clock.duration})
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".rhcsa-sim-exam.")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(payload)
            os.fchmod(handle.fileno(), 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def resume_or_start(
    path: Path, now: Callable[[], float] = time.time
) -> tuple[ExamClock, str | None]:
    """Reanuda el examen guardado o inicia uno nuevo; devuelve un aviso si falla guardar."""
    clock = load_exam(path, now)
    if clock is not None:
        return clock, None
    clock = ExamClock(started=now(), now=now)
    try:
        save_exam(path, clock)
    except OSError:
        return clock, save_warning(path)
    return clock, None


def render_timer(clock: ExamClock, ui: Ui) -> str:
    if clock.expired():
        return ui.red(f"TIME UP {format_clock(0)}")
    return ui.yellow(f"Time left {format_clock(clock.remaining())}")


def corner_sequence(text: str, width: int) -> str:
    """Escribe `text` en la esquina superior derecha y devuelve el cursor."""
    column = max(1, width - visible_len(text) + 1)
    return f"{_SAVE_CURSOR}\x1b[1;{column}H{text}{_RESTORE_CURSOR}"


def _terminal_width() -> int:
    return shutil.get_terminal_size().columns


class CornerTicker:
    """Hilo demonio que redibuja el reloj cada `interval` segundos."""

    def __init__(
        self,
        out: TextIO,
        lock: threading.Lock,
        render: Callable[[], str],
        width: Callable[[], int] = _terminal_width,
        interval: float = 1.0,
    ) -> None:
        self._out = out
        self._lock = lock
        self._render = render
        self._width = width
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def draw(self) -> None:
        sequence = corner_sequence(self._render(), self._width())
        with self._lock:
            self._out.write(sequence)
            self._out.flush()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self.draw()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)

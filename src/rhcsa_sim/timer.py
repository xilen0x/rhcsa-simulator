from __future__ import annotations

import math
import shutil
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TextIO

from rhcsa_sim.ui import Ui, visible_len

EXAM_SECONDS = 3 * 60 * 60
_SAVE_CURSOR = "\x1b7"
_RESTORE_CURSOR = "\x1b8"


def format_clock(seconds: float) -> str:
    """HH:MM:SS con el tiempo redondeado hacia arriba; nunca negativo."""
    total = max(0, math.ceil(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


@dataclass(frozen=True, slots=True)
class ExamClock:
    """Cuenta regresiva del examen; `now` es inyectable para los tests."""

    started: float
    duration: float = EXAM_SECONDS
    now: Callable[[], float] = time.monotonic

    def elapsed(self) -> float:
        return max(0.0, self.now() - self.started)

    def remaining(self) -> float:
        return max(0.0, self.duration - self.elapsed())

    def expired(self) -> bool:
        return self.remaining() <= 0


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

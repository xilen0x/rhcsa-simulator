from __future__ import annotations

import io
import json
import stat
import threading
import time
from pathlib import Path

import pytest

from rhcsa_sim.timer import (
    EXAM_SECONDS,
    ClockHolder,
    CornerTicker,
    ExamClock,
    corner_sequence,
    format_clock,
    load_exam,
    render_timer,
    resume_or_start,
    save_exam,
    save_warning,
)
from rhcsa_sim.ui import Ui

COLOR = Ui(unicode=False, color=True)
PLAIN = Ui(unicode=False, color=False)


class FakeNow:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def test_format_clock_values() -> None:
    assert format_clock(0) == "00:00:00"
    assert format_clock(59.2) == "00:01:00"
    assert format_clock(EXAM_SECONDS) == "03:00:00"
    assert format_clock(-5) == "00:00:00"


def test_exam_clock_with_fake_now() -> None:
    now = FakeNow()
    clock = ExamClock(started=100.0, now=now)
    assert clock.remaining() == EXAM_SECONDS
    assert clock.elapsed() == 0
    assert not clock.expired()
    now.value = 160.0
    assert clock.elapsed() == 60
    assert clock.remaining() == EXAM_SECONDS - 60
    now.value = 100.0 + EXAM_SECONDS + 50
    assert clock.remaining() == 0
    assert clock.expired()


def test_render_timer_yellow_then_red_when_expired() -> None:
    now = FakeNow()
    clock = ExamClock(started=100.0, now=now)
    assert render_timer(clock, COLOR) == COLOR.yellow("Time left 03:00:00")
    assert render_timer(clock, PLAIN) == "Time left 03:00:00"
    now.value = 100.0 + EXAM_SECONDS
    assert render_timer(clock, COLOR) == COLOR.red("TIME UP 00:00:00")
    assert render_timer(clock, PLAIN) == "TIME UP 00:00:00"


def test_corner_sequence_ignores_ansi_and_clamps() -> None:
    text = COLOR.yellow("12345")
    assert corner_sequence(text, 80) == "\x1b7\x1b[1;76H" + text + "\x1b8"
    assert "\x1b[1;1H" in corner_sequence("x" * 50, 10)


def test_corner_ticker_writes_and_stops_quickly() -> None:
    out = io.StringIO()
    written = threading.Event()

    class Out(io.StringIO):
        def flush(self) -> None:
            written.set()

    out = Out()
    ticker = CornerTicker(
        out=out,
        lock=threading.Lock(),
        render=lambda: "T",
        width=lambda: 40,
        interval=0.01,
    )
    ticker.start()
    assert written.wait(2)
    ticker.stop()
    assert "\x1b[1;40H" in out.getvalue()
    size = len(out.getvalue())
    ticker.stop()
    assert len(out.getvalue()) == size


# --- persistencia del examen ---

STATE_NAME = "exam.json"


def test_default_clock_uses_wall_time() -> None:
    assert ExamClock(started=0.0).now is time.time


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / STATE_NAME
    now = FakeNow(1000.0)
    save_exam(path, ExamClock(started=900.0, now=now))
    assert json.loads(path.read_text()) == {"started": 900.0, "duration": EXAM_SECONDS}
    assert stat.S_IMODE(path.stat().st_mode) == 0o644
    clock = load_exam(path, now)
    assert clock is not None
    assert clock.started == 900.0 and clock.elapsed() == 100.0
    assert list(tmp_path.iterdir()) == [path]


def test_resume_counts_elapsed_and_expired(tmp_path: Path) -> None:
    path = tmp_path / STATE_NAME
    save_exam(path, ExamClock(started=1000.0, now=FakeNow()))
    clock, warning = resume_or_start(path, FakeNow(1000.0 + 600))
    assert warning is None and clock.started == 1000.0
    assert render_timer(clock, PLAIN) == "Time left 02:50:00"
    late, _ = resume_or_start(path, FakeNow(1000.0 + EXAM_SECONDS + 5))
    assert late.started == 1000.0
    assert render_timer(late, PLAIN) == "TIME UP 00:00:00"


@pytest.mark.parametrize(
    "content",
    [
        None,
        "not json",
        "[1, 2]",
        '{"started": "x", "duration": 10800}',
        '{"started": 1000, "duration": true}',
        '{"started": true, "duration": 10800}',
        '{"started": NaN, "duration": 10800}',
        '{"started": 1000, "duration": Infinity}',
        '{"started": 1000, "duration": -5}',
        '{"started": 1000, "duration": 0}',
        '{"started": 1000}',
        '{"started": 99999, "duration": 10800}',
        "x" * 10000,
    ],
)
def test_invalid_state_starts_a_new_exam(tmp_path: Path, content: str | None) -> None:
    path = tmp_path / STATE_NAME
    if content is not None:
        path.write_text(content)
    now = FakeNow(5000.0)
    assert load_exam(path, now) is None
    clock, warning = resume_or_start(path, now)
    assert warning is None and clock.started == 5000.0
    assert json.loads(path.read_text())["started"] == 5000.0


def test_slightly_future_start_is_tolerated(tmp_path: Path) -> None:
    path = tmp_path / STATE_NAME
    save_exam(path, ExamClock(started=5030.0, now=FakeNow()))
    assert load_exam(path, FakeNow(5000.0)) is not None


def test_load_does_not_follow_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"started": 1000, "duration": 10800}')
    path = tmp_path / STATE_NAME
    path.symlink_to(target)
    assert load_exam(path, FakeNow(1100.0)) is None


def test_save_replaces_symlink_without_touching_target(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("precious")
    path = tmp_path / STATE_NAME
    path.symlink_to(target)
    save_exam(path, ExamClock(started=1.0, now=FakeNow()))
    assert target.read_text() == "precious"
    assert not path.is_symlink() and path.is_file()
    assert json.loads(path.read_text())["started"] == 1.0


def test_save_failure_raises_oserror_and_leaves_no_temp(tmp_path: Path) -> None:
    path = tmp_path / STATE_NAME
    path.mkdir()
    with pytest.raises(OSError):
        save_exam(path, ExamClock(started=1.0, now=FakeNow()))
    assert [p.name for p in tmp_path.iterdir()] == [STATE_NAME]


def test_resume_or_start_warns_when_save_fails(tmp_path: Path) -> None:
    path = tmp_path / "missing-dir" / STATE_NAME
    clock, warning = resume_or_start(path, FakeNow(7.0))
    assert clock.started == 7.0
    assert warning is not None and "Could not save the exam timer" in warning
    assert "sudo" in warning


def test_save_warning_sanitizes_path() -> None:
    assert "\x1b" not in save_warning(Path("/tmp/\x1b[31mx"))


def test_clock_holder_restart_replaces_clock_and_saves(tmp_path: Path) -> None:
    path = tmp_path / STATE_NAME
    now = FakeNow(100.0)
    holder = ClockHolder(ExamClock(started=0.0, now=now), path, now)
    now.value = 500.0
    assert holder.restart() is None
    assert holder.clock is not None and holder.clock.started == 500.0
    assert json.loads(path.read_text())["started"] == 500.0


def test_clock_holder_restart_without_path_does_not_save() -> None:
    now = FakeNow(100.0)
    holder = ClockHolder(ExamClock(started=0.0, now=now), None, now)
    assert holder.restart() is None
    assert holder.clock is not None and holder.clock.started == 100.0

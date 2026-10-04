from __future__ import annotations

import io
import threading

from rhcsa_sim.timer import (
    EXAM_SECONDS,
    CornerTicker,
    ExamClock,
    corner_sequence,
    format_clock,
    render_timer,
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

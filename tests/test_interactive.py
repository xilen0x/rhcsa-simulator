from __future__ import annotations

import io

from rhcsa_sim.interactive import (
    CLEAR_SCREEN,
    PROMPT,
    SessionState,
    dispatch,
    render_help,
    run_session,
)
from rhcsa_sim.models import CheckResult, ObjectiveBlock, Task
from rhcsa_sim.registry import TaskRegistry
from rhcsa_sim.timer import ExamClock
from rhcsa_sim.ui import Ui


class CountingCheck:
    def __init__(self, passed: bool, label: str = "stub check") -> None:
        self.passed = passed
        self.label = label
        self.runs = 0

    def describe(self) -> str:
        return self.label

    def run(self) -> CheckResult:
        self.runs += 1
        return CheckResult(self.passed, "detail-ok" if self.passed else "detail-bad")


def make_tasks(
    outcomes: tuple[bool, ...] = (True, False, True),
    description: str = "Create the thing",
) -> tuple[tuple[Task, ...], list[CountingCheck]]:
    checks = [CountingCheck(ok) for ok in outcomes]
    tasks = tuple(
        Task(f"t-{i + 1:02d}", ObjectiveBlock.USERS_GROUPS, description, 10, (check,))
        for i, check in enumerate(checks)
    )
    return tasks, checks


PLAIN = Ui(unicode=False, color=False)


def session(
    lines: list[str], tasks: tuple[Task, ...], ui: Ui = PLAIN
) -> tuple[int, str]:
    feed = iter(lines)

    def read() -> str:
        try:
            return next(feed)
        except StopIteration:
            raise EOFError from None

    out = io.StringIO()
    code = run_session(TaskRegistry(tasks), ui, read, out)
    return code, out.getvalue()


def send(state: SessionState, line: str, ui: Ui = PLAIN) -> tuple[str, bool]:
    reply = dispatch(state, ui, line)
    return reply.text, reply.quit


def test_start_shows_banner_and_first_task() -> None:
    tasks, _ = make_tasks()
    code, out = session([], tasks)
    assert code == 0
    assert "RHCSA EX200" in out and "3 tasks" in out and "30 points" in out
    assert "Task 1/3" in out and "t-01" in out and "Create the thing" in out
    assert "pending" in out


def test_next_prev_and_bounds() -> None:
    tasks, _ = make_tasks()
    state = SessionState(tasks)
    text, _ = send(state, "p")
    assert state.index == 0 and "first task" in text
    send(state, "")
    send(state, "n")
    assert state.index == 2
    text, _ = send(state, "N")
    assert state.index == 2 and "last task" in text
    send(state, " P ")
    assert state.index == 1


def test_jump_by_number_and_id() -> None:
    tasks, _ = make_tasks()
    state = SessionState(tasks)
    send(state, "3")
    assert state.index == 2
    send(state, "T-01")
    assert state.index == 0


def test_jump_invalid_keeps_position() -> None:
    tasks, _ = make_tasks()
    state = SessionState(tasks)
    for bad in ("0", "4", "nope-99"):
        text, quit_ = send(state, bad)
        assert state.index == 0 and not quit_
    text, _ = send(state, "9")
    assert "1-3" in text


def test_check_grades_only_current_task() -> None:
    tasks, checks = make_tasks()
    state = SessionState(tasks)
    send(state, "n")
    text, _ = send(state, "c")
    assert [c.runs for c in checks] == [0, 1, 0]
    assert "stub check" in text and "detail-bad" in text
    assert state.results["t-02"].passed is False


def test_grade_all_prints_summary_and_remembers() -> None:
    tasks, checks = make_tasks()
    state = SessionState(tasks)
    text, _ = send(state, "a")
    assert [c.runs for c in checks] == [1, 1, 1]
    assert "Score: 20/30" in text
    assert len(state.results) == 3


def test_list_shows_status_symbols_after_grading() -> None:
    tasks, _ = make_tasks()
    state = SessionState(tasks)
    before, _ = send(state, "l")
    assert "graded 0/3" in before and "OK" not in before
    send(state, "c")
    send(state, "n")
    send(state, "c")
    after, _ = send(state, "l")
    assert "graded 2/3" in after and "OK" in after and "KO" in after and ".." in after
    assert "10/30" in after


def test_unknown_command_hint_is_sanitized() -> None:
    tasks, _ = make_tasks()
    text, quit_ = send(SessionState(tasks), "\x1b[31mzz")
    assert "Unknown command" in text and "Type h for help" in text
    assert "\x1b" not in text and not quit_


def test_help_and_show() -> None:
    tasks, _ = make_tasks()
    state = SessionState(tasks)
    assert "quit" in send(state, "h")[0] and "quit" in send(state, "?")[0]
    assert "Task 1/3" in send(state, "s")[0]


def test_quit_prints_session_score() -> None:
    tasks, _ = make_tasks()
    code, out = session(["c", "q", "n"], tasks)
    assert code == 0
    assert "Bye! Session score: 10/10 (graded 1/3)." in out
    assert "Task 2/3" not in out


def test_eof_and_keyboard_interrupt_exit_zero() -> None:
    tasks, _ = make_tasks()
    assert session([], tasks)[0] == 0

    def interrupt() -> str:
        raise KeyboardInterrupt

    assert run_session(TaskRegistry(tasks), PLAIN, interrupt, io.StringIO()) == 0


def test_no_ansi_when_color_off_and_present_when_on() -> None:
    tasks, _ = make_tasks()
    _, plain = session(["c", "a", "l", "q"], tasks)
    assert "\x1b" not in plain
    _, colored = session(["c", "q"], tasks, Ui(unicode=True, color=True))
    assert "\x1b[" in colored


def test_ascii_fallback_output_is_ascii() -> None:
    tasks, _ = make_tasks()
    _, out = session(["c", "a", "l", "h", "q"], tasks, Ui(unicode=False, color=False))
    assert out.isascii()


def test_unicode_box_in_unicode_mode() -> None:
    tasks, _ = make_tasks()
    _, out = session([], tasks, Ui(unicode=True, color=False))
    assert "╭" in out


def test_description_is_sanitized_and_wrapped() -> None:
    tasks, _ = make_tasks(description="\x1b[31mred " + "word " * 40)
    _, out = session([], tasks)
    assert "\x1b" not in out
    assert max(len(line) for line in out.splitlines()) <= 78


def test_status_badge_follows_results() -> None:
    tasks, _ = make_tasks()
    state = SessionState(tasks)
    send(state, "c")
    assert "passed" in send(state, "s")[0]
    send(state, "n")
    send(state, "c")
    assert "failed" in send(state, "s")[0]




CLEAR = "\x1b[H\x1b[2J"
BAR = "[Enter] next"


def screen_session(lines: list[str], tasks: tuple[Task, ...]) -> str:
    feed = iter(lines)

    def read() -> str:
        try:
            return next(feed)
        except StopIteration:
            raise EOFError from None

    out = io.StringIO()
    run_session(TaskRegistry(tasks), PLAIN, read, out, clear_screen=True)
    return out.getvalue()


def test_navigation_clears_screen_and_shows_only_new_task_and_menu() -> None:
    tasks, _ = make_tasks()
    out = screen_session(["n"], tasks)
    last = out.split(CLEAR)[-1]
    assert "Task 2/3" in last and BAR in last
    assert "Task 1/3" not in last and "RHCSA EX200" not in last
    assert last.index("Task 2/3") < last.index(BAR)


def test_check_clears_and_shows_task_result_and_menu() -> None:
    tasks, _ = make_tasks()
    out = screen_session(["c"], tasks)
    last = out.split(CLEAR)[-1]
    assert "Task 1/3" in last and "detail-ok" in last and BAR in last
    assert last.index("Task 1/3") < last.index("detail-ok") < last.index(BAR)


def test_menu_follows_every_reply() -> None:
    tasks, _ = make_tasks()
    feed = iter(["l", "h", "zz", "p"])
    out = io.StringIO()
    before_each_read: list[str] = []

    def read() -> str:
        before_each_read.append(out.getvalue())
        try:
            return next(feed)
        except StopIteration:
            raise EOFError from None

    run_session(TaskRegistry(tasks), PLAIN, read, out, clear_screen=True)
    assert len(before_each_read) == 5
    for screen in before_each_read:
        last_line = screen.removesuffix(PROMPT).splitlines()[-1]
        assert last_line.startswith(BAR)


def test_non_navigation_replies_do_not_clear() -> None:
    tasks, _ = make_tasks()
    state = SessionState(tasks)
    for line in ("l", "h", "a", "zz", "p", "99"):
        assert dispatch(state, PLAIN, line).clear is False
    for line in ("n", "p", "3", "s", "c"):
        assert dispatch(state, PLAIN, line).clear is True


def test_no_clear_sequence_when_disabled() -> None:
    tasks, _ = make_tasks()
    _, out = session(["n", "c", "q"], tasks)
    assert CLEAR not in out
    assert out.count(BAR) == 3


def timed_session(
    lines: list[str], clear_screen: bool, clock: ExamClock | None
) -> str:
    tasks, _ = make_tasks()
    feed = iter(lines)

    def read() -> str:
        try:
            return next(feed)
        except StopIteration:
            raise EOFError from None

    out = io.StringIO()
    run_session(
        TaskRegistry(tasks), PLAIN, read, out, clear_screen=clear_screen, clock=clock
    )
    return out.getvalue()


def fixed_clock() -> ExamClock:
    return ExamClock(started=0.0, now=lambda: 0.0)


def test_timer_drawn_after_clear_with_reserved_line() -> None:
    text = timed_session(["n", "q"], True, fixed_clock())
    assert "Time left 03:00:00" in text
    assert CLEAR_SCREEN + "\n" in text
    assert "Time used 00:00:00." in text


def test_no_timer_without_clock_or_clear_screen() -> None:
    for text in (
        timed_session(["q"], True, None),
        timed_session(["q"], False, fixed_clock()),
    ):
        assert "Time left" not in text
    assert "Time used" not in timed_session(["q"], True, None)


def test_help_mentions_timer() -> None:
    assert "timer" in render_help(PLAIN)

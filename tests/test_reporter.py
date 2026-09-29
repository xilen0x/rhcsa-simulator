from __future__ import annotations

from rhcsa_sim.models import CheckResult, ObjectiveBlock, Task, TaskResult
from rhcsa_sim.reporter import (
    format_status,
    format_summary,
    format_task_result,
    sanitize_text,
    should_use_color,
)


class StubCheck:
    def describe(self) -> str:
        return "stub check"

    def run(self) -> CheckResult:
        return CheckResult(True, "")


def make_result(passed: bool, points: int = 10, detail: str = "detail") -> TaskResult:
    task = Task("t1", ObjectiveBlock.USERS_GROUPS, "Do the thing", points, (StubCheck(),))
    return TaskResult(task, (CheckResult(passed, detail),))


def test_color_disabled_by_no_color_and_dumb_term() -> None:
    assert should_use_color(True, {}) is True
    assert should_use_color(True, {"NO_COLOR": "1"}) is False
    assert should_use_color(True, {"TERM": "dumb"}) is False
    assert should_use_color(False, {}) is False


def test_empty_no_color_is_ignored() -> None:
    assert should_use_color(True, {"NO_COLOR": ""}) is True


def test_status_plain_and_colored() -> None:
    assert format_status(True, color=False) == "OK"
    assert format_status(False, color=False) == "KO"
    assert "\x1b[32m" in format_status(True, color=True)
    assert "\x1b[31m" in format_status(False, color=True)


def test_sanitize_strips_control_characters() -> None:
    assert sanitize_text("a\x1b[31mb\nc") == "a?[31mb?c"


def test_task_result_plain_output() -> None:
    text = format_task_result(make_result(True), color=False)
    assert text.startswith("[OK] t1")
    assert "(10/10)" in text
    assert "stub check: detail" in text


def test_failed_task_shows_zero_points() -> None:
    text = format_task_result(make_result(False), color=False)
    assert text.startswith("[KO] t1")
    assert "(0/10)" in text


def test_task_result_sanitizes_detail() -> None:
    text = format_task_result(make_result(True, detail="\x1b[2Jevil"), color=False)
    assert "\x1b" not in text


def test_summary_threshold_boundaries() -> None:
    seven = [make_result(True, 7), make_result(False, 3)]
    six = [make_result(True, 6), make_result(False, 4)]
    assert "PASS" in format_summary(seven, color=False)
    assert "FAIL" in format_summary(six, color=False)


def test_summary_without_tasks() -> None:
    assert format_summary([], color=False) == "No tasks evaluated."

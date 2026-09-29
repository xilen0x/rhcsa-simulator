from __future__ import annotations

import pytest

from rhcsa_sim.models import Check, CheckResult, ObjectiveBlock, Task, TaskResult

class StubCheck:
    def __init__(self, passed: bool) -> None:
        self._passed = passed

    def describe(self) -> str:
        return "stub"

    def run(self) -> CheckResult:
        return CheckResult(self._passed, "stub detail")


def make_task(
    *,
    id: str = "t1",
    description: str = "Create user alice",
    points: int = 10,
    checks: tuple[Check, ...] | None = None,
) -> Task:
    return Task(
        id=id,
        block=ObjectiveBlock.USERS_GROUPS,
        description=description,
        points=points,
        checks=(StubCheck(True),) if checks is None else checks,
    )

def test_task_rejects_empty_id() -> None:
    with pytest.raises(ValueError):
        make_task(id="  ")


def test_task_rejects_empty_description() -> None:
    with pytest.raises(ValueError):
        make_task(description="")


@pytest.mark.parametrize("points", [0, -5])
def test_task_rejects_non_positive_points(points: int) -> None:
    with pytest.raises(ValueError):
        make_task(points=points)


def test_task_rejects_no_checks() -> None:
    with pytest.raises(ValueError):
        make_task(checks=())


def test_task_result_passes_only_if_all_checks_pass() -> None:
    task = make_task()
    ok = CheckResult(True, "")
    ko = CheckResult(False, "")
    assert TaskResult(task, (ok, ok)).passed is True
    assert TaskResult(task, (ok, ko)).passed is False


def test_earned_points_is_all_or_nothing() -> None:
    task = make_task(points=10)
    assert TaskResult(task, (CheckResult(True, ""),)).earned_points == 10
    assert TaskResult(task, (CheckResult(False, ""),)).earned_points == 0

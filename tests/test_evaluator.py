from __future__ import annotations

from rhcsa_sim.evaluator import evaluate_check, evaluate_task, evaluate_tasks
from rhcsa_sim.models import Check, CheckResult, ObjectiveBlock, Task


class FixedCheck:
    def __init__(self, passed: bool) -> None:
        self._passed = passed

    def describe(self) -> str:
        return "fixed"

    def run(self) -> CheckResult:
        return CheckResult(self._passed, "detail")


class BoomCheck:
    def describe(self) -> str:
        return "boom"

    def run(self) -> CheckResult:
        raise RuntimeError("kaput")


def make_task(task_id: str, *checks: Check) -> Task:
    return Task(task_id, ObjectiveBlock.USERS_GROUPS, "desc", 10, tuple(checks))


def test_check_exception_becomes_ko() -> None:
    result = evaluate_check(BoomCheck())
    assert not result.passed
    assert "RuntimeError" in result.detail


def test_evaluate_task_runs_all_checks_without_short_circuit() -> None:
    result = evaluate_task(make_task("t", FixedCheck(False), FixedCheck(True)))
    assert len(result.check_results) == 2
    assert not result.passed


def test_evaluate_tasks_preserves_order() -> None:
    results = evaluate_tasks([make_task("a", FixedCheck(True)), make_task("b", FixedCheck(False))])
    assert [r.task.id for r in results] == ["a", "b"]
    assert [r.passed for r in results] == [True, False]

from __future__ import annotations

import pytest

from rhcsa_sim.models import CheckResult, ObjectiveBlock, Task
from rhcsa_sim.registry import TaskRegistry


class OkCheck:
    def describe(self) -> str:
        return "ok"

    def run(self) -> CheckResult:
        return CheckResult(True, "")


def make_task(task_id: str) -> Task:
    return Task(task_id, ObjectiveBlock.USERS_GROUPS, "desc", 10, (OkCheck(),))


def test_add_get_and_order() -> None:
    registry = TaskRegistry([make_task("b"), make_task("a")])
    assert [t.id for t in registry.all()] == ["b", "a"]
    task = registry.get("a")
    assert task is not None and task.id == "a"


def test_get_unknown_returns_none() -> None:
    assert TaskRegistry().get("nope") is None


def test_duplicate_id_rejected() -> None:
    with pytest.raises(ValueError):
        TaskRegistry([make_task("a"), make_task("a")])

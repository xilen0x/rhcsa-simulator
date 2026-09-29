from __future__ import annotations

from collections.abc import Iterable

from rhcsa_sim.models import Task


class TaskRegistry:
    def __init__(self, tasks: Iterable[Task] = ()) -> None:
        self._tasks: dict[str, Task] = {}
        for task in tasks:
            self.add(task)

    def add(self, task: Task) -> None:
        if task.id in self._tasks:
            raise ValueError(f"duplicate task id: {task.id}")
        self._tasks[task.id] = task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def all(self) -> tuple[Task, ...]:
        return tuple(self._tasks.values())

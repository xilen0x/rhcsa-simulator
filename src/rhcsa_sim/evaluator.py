from __future__ import annotations

from collections.abc import Iterable

from rhcsa_sim.models import Check, CheckResult, Task, TaskResult


def evaluate_check(check: Check) -> CheckResult:
    """Un check que falla por un error interno cuenta como KO, no rompe el simulador."""
    try:
        return check.run()
    except Exception as exc:
        return CheckResult(False, f"internal error in check: {type(exc).__name__}: {exc}")


def evaluate_task(task: Task) -> TaskResult:
    """Ejecuta todos los checks (sin cortocircuito) para mostrar cada fallo."""
    return TaskResult(task, tuple(evaluate_check(check) for check in task.checks))


def evaluate_tasks(tasks: Iterable[Task]) -> tuple[TaskResult, ...]:
    return tuple(evaluate_task(task) for task in tasks)

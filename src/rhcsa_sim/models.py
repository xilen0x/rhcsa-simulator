from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class ObjectiveBlock(str, Enum):
    """Bloques de objetivos del examen. Verificar contra la pagina oficial
    de EX200 (RHEL 10) y ajustar si Red Hat los cambio."""

    ESSENTIAL_TOOLS = "essential-tools"
    MANAGE_SOFTWARE = "manage-software"
    SHELL_SCRIPTS = "shell-scripts"
    RUNNING_SYSTEMS = "running-systems"
    LOCAL_STORAGE = "local-storage"
    FILE_SYSTEMS = "file-systems"
    DEPLOY_MAINTAIN = "deploy-maintain"
    NETWORKING = "networking"
    USERS_GROUPS = "users-groups"
    SECURITY = "security"


@dataclass(frozen=True, slots=True)
class CheckResult:
    passed: bool
    detail: str


class Check(Protocol):
    """Una verificacion de solo lectura sobre el estado del sistema."""

    def describe(self) -> str: ...

    def run(self) -> CheckResult: ...


@dataclass(frozen=True, slots=True)
class Task:
    id: str
    block: ObjectiveBlock
    description: str
    points: int
    checks: tuple[Check, ...]

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Task id must not be empty")
        if not self.description.strip():
            raise ValueError("Task description must not be empty")
        if self.points <= 0:
            raise ValueError("Task points must be positive")
        if not self.checks:
            raise ValueError("Task must have at least one check")


@dataclass(frozen=True, slots=True)
class TaskResult:
    task: Task
    check_results: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.check_results)

    @property
    def earned_points(self) -> int:
        return self.task.points if self.passed else 0

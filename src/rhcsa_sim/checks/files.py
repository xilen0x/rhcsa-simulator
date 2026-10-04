from __future__ import annotations

from dataclasses import dataclass

from rhcsa_sim.checks._validation import (
    parse_octal_mode,
    validate_absolute_path,
    validate_account_name,
)
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner


@dataclass(frozen=True, slots=True)
class StatInfo:
    mode: int
    owner: str
    group: str


def _stat_path(runner: CommandRunner, path: str) -> StatInfo | None:
    result = runner.run(["stat", "-c", "%a %U %G", "--", path])
    if not result.ok:
        return None
    parts = result.stdout.split()
    if len(parts) != 3:
        return None
    try:
        return StatInfo(parse_octal_mode(parts[0]), parts[1], parts[2])
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class PathHasMode:
    runner: CommandRunner
    path: str
    mode: str

    def __post_init__(self) -> None:
        validate_absolute_path(self.path)
        parse_octal_mode(self.mode)

    def describe(self) -> str:
        return f"{self.path} has mode {self.mode}"

    def run(self) -> CheckResult:
        info = _stat_path(self.runner, self.path)
        if info is None:
            return CheckResult(False, f"cannot stat '{self.path}'")
        expected = parse_octal_mode(self.mode)
        if info.mode != expected:
            return CheckResult(False, f"mode is {info.mode:o}, expected {expected:o}")
        return CheckResult(True, f"mode is {expected:o}")


@dataclass(frozen=True, slots=True)
class PathHasOwner:
    runner: CommandRunner
    path: str
    owner: str
    group: str | None = None

    def __post_init__(self) -> None:
        validate_absolute_path(self.path)
        validate_account_name(self.owner)
        if self.group is not None:
            validate_account_name(self.group)

    def describe(self) -> str:
        who = self.owner if self.group is None else f"{self.owner}:{self.group}"
        return f"{self.path} is owned by {who}"

    def run(self) -> CheckResult:
        info = _stat_path(self.runner, self.path)
        if info is None:
            return CheckResult(False, f"cannot stat '{self.path}'")
        if info.owner != self.owner:
            return CheckResult(False, f"owner is {info.owner}, expected {self.owner}")
        if self.group is not None and info.group != self.group:
            return CheckResult(False, f"group is {info.group}, expected {self.group}")
        return CheckResult(True, "ownership is correct")


@dataclass(frozen=True, slots=True)
class FilesIdentical:
    """`copy` existe y tiene exactamente el mismo contenido que `source`."""

    runner: CommandRunner
    source: str
    copy: str

    def __post_init__(self) -> None:
        validate_absolute_path(self.source)
        validate_absolute_path(self.copy)
        if self.source == self.copy:
            raise ValueError("source and copy must be different paths")

    def describe(self) -> str:
        return f"{self.copy} is identical to {self.source}"

    def run(self) -> CheckResult:
        # cmp -s no imprime nada: rc 0 iguales, 1 distintos, 2 ausente/ilegible.
        result = self.runner.run(["cmp", "-s", "--", self.source, self.copy])
        if result.returncode == 0:
            return CheckResult(True, "files are identical")
        if result.returncode == 1:
            return CheckResult(False, f"content differs from {self.source}")
        hint = " (paths under /root need sudo)" if self.copy.startswith("/root/") else ""
        return CheckResult(False, f"cannot compare: {self.copy} missing or unreadable{hint}")

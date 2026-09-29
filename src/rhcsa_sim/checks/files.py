from __future__ import annotations

from dataclasses import dataclass

from rhcsa_sim.checks._validation import validate_absolute_path, validate_account_name
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner


@dataclass(frozen=True, slots=True)
class StatInfo:
    mode: int
    owner: str
    group: str


def _parse_mode(text: str) -> int:
    """Convierte un modo octal ('640', '0640', '2770') a int. ValueError si es invalido."""
    if not text or len(text) > 4 or any(c not in "01234567" for c in text):
        raise ValueError(f"invalid octal mode: {text!r}")
    return int(text, 8)


def _stat_path(runner: CommandRunner, path: str) -> StatInfo | None:
    result = runner.run(["stat", "-c", "%a %U %G", "--", path])
    if not result.ok:
        return None
    parts = result.stdout.split()
    if len(parts) != 3:
        return None
    try:
        return StatInfo(_parse_mode(parts[0]), parts[1], parts[2])
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class PathHasMode:
    runner: CommandRunner
    path: str
    mode: str

    def __post_init__(self) -> None:
        validate_absolute_path(self.path)
        _parse_mode(self.mode)

    def describe(self) -> str:
        return f"{self.path} has mode {self.mode}"

    def run(self) -> CheckResult:
        info = _stat_path(self.runner, self.path)
        if info is None:
            return CheckResult(False, f"cannot stat '{self.path}'")
        expected = _parse_mode(self.mode)
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

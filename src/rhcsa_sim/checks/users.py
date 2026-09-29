from __future__ import annotations

from dataclasses import dataclass

from rhcsa_sim.checks._validation import validate_account_name
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner


@dataclass(frozen=True, slots=True)
class PasswdEntry:
    name: str
    uid: int
    gid: int
    home: str
    shell: str


@dataclass(frozen=True, slots=True)
class GroupEntry:
    name: str
    gid: int


def _parse_passwd(line: str) -> PasswdEntry | None:
    parts = line.strip().split(":")
    if len(parts) != 7 or not parts[2].isdigit() or not parts[3].isdigit():
        return None
    return PasswdEntry(parts[0], int(parts[2]), int(parts[3]), parts[5], parts[6])


def _parse_group(line: str) -> GroupEntry | None:
    parts = line.strip().split(":")
    if len(parts) != 4 or not parts[2].isdigit():
        return None
    return GroupEntry(parts[0], int(parts[2]))


def _lookup_user(runner: CommandRunner, name: str) -> PasswdEntry | None:
    result = runner.run(["getent", "passwd", name])
    return _parse_passwd(result.stdout) if result.ok else None


def _lookup_group(runner: CommandRunner, name: str) -> GroupEntry | None:
    result = runner.run(["getent", "group", name])
    return _parse_group(result.stdout) if result.ok else None


@dataclass(frozen=True, slots=True)
class UserExists:
    runner: CommandRunner
    name: str

    def __post_init__(self) -> None:
        validate_account_name(self.name)

    def describe(self) -> str:
        return f"user {self.name} exists"

    def run(self) -> CheckResult:
        if _lookup_user(self.runner, self.name) is None:
            return CheckResult(False, f"user '{self.name}' does not exist")
        return CheckResult(True, f"user '{self.name}' exists")


@dataclass(frozen=True, slots=True)
class UserHasUid:
    runner: CommandRunner
    name: str
    uid: int

    def __post_init__(self) -> None:
        validate_account_name(self.name)
        if self.uid < 0:
            raise ValueError("uid must not be negative")

    def describe(self) -> str:
        return f"user {self.name} has UID {self.uid}"

    def run(self) -> CheckResult:
        entry = _lookup_user(self.runner, self.name)
        if entry is None:
            return CheckResult(False, f"user '{self.name}' does not exist")
        if entry.uid != self.uid:
            return CheckResult(False, f"UID is {entry.uid}, expected {self.uid}")
        return CheckResult(True, f"UID is {self.uid}")


@dataclass(frozen=True, slots=True)
class UserHasShell:
    runner: CommandRunner
    name: str
    shell: str

    def __post_init__(self) -> None:
        validate_account_name(self.name)
        if not self.shell.startswith("/"):
            raise ValueError("shell must be an absolute path")

    def describe(self) -> str:
        return f"user {self.name} has shell {self.shell}"

    def run(self) -> CheckResult:
        entry = _lookup_user(self.runner, self.name)
        if entry is None:
            return CheckResult(False, f"user '{self.name}' does not exist")
        if entry.shell != self.shell:
            return CheckResult(False, f"shell is {entry.shell}, expected {self.shell}")
        return CheckResult(True, f"shell is {self.shell}")


@dataclass(frozen=True, slots=True)
class UserInGroup:
    """Verifica pertenencia (primaria o suplementaria) usando `id -Gn`."""

    runner: CommandRunner
    name: str
    group: str

    def __post_init__(self) -> None:
        validate_account_name(self.name)
        validate_account_name(self.group)

    def describe(self) -> str:
        return f"user {self.name} belongs to group {self.group}"

    def run(self) -> CheckResult:
        result = self.runner.run(["id", "-Gn", "--", self.name])
        if not result.ok:
            return CheckResult(False, f"user '{self.name}' does not exist")
        groups = result.stdout.split()
        if self.group not in groups:
            return CheckResult(False, f"groups are {', '.join(groups)}; missing {self.group}")
        return CheckResult(True, f"user is in group '{self.group}'")


@dataclass(frozen=True, slots=True)
class GroupExists:
    runner: CommandRunner
    name: str
    gid: int | None = None

    def __post_init__(self) -> None:
        validate_account_name(self.name)
        if self.gid is not None and self.gid < 0:
            raise ValueError("gid must not be negative")

    def describe(self) -> str:
        suffix = "" if self.gid is None else f" with GID {self.gid}"
        return f"group {self.name} exists{suffix}"

    def run(self) -> CheckResult:
        entry = _lookup_group(self.runner, self.name)
        if entry is None:
            return CheckResult(False, f"group '{self.name}' does not exist")
        if self.gid is not None and entry.gid != self.gid:
            return CheckResult(False, f"GID is {entry.gid}, expected {self.gid}")
        return CheckResult(True, f"group '{self.name}' exists")

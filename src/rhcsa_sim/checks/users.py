from __future__ import annotations

from dataclasses import dataclass

from rhcsa_sim.checks._validation import validate_account_name, validate_login_defs_key
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


_CHAGE_ROOT = "chage -l requires root for other users (run with sudo)"
_CHAGE_KEYS = {
    "max_days": "Maximum number of days between password change",
    "min_days": "Minimum number of days between password change",
    "warn_days": "Number of days of warning before password expires",
}


def _parse_chage(stdout: str) -> dict[str, str]:
    """Pares 'clave : valor' de `chage -l` (se parte en el primer ':')."""
    fields: dict[str, str] = {}
    for line in stdout.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


@dataclass(frozen=True, slots=True)
class PasswordAging:
    """Politica de caducidad de la contrasena de un usuario segun `chage -l`."""

    runner: CommandRunner
    name: str
    max_days: int | None = None
    min_days: int | None = None
    warn_days: int | None = None

    def _expected(self) -> dict[str, int]:
        values = {
            "max_days": self.max_days,
            "min_days": self.min_days,
            "warn_days": self.warn_days,
        }
        return {field: value for field, value in values.items() if value is not None}

    def __post_init__(self) -> None:
        validate_account_name(self.name)
        expected = self._expected()
        if not expected:
            raise ValueError("at least one of max_days, min_days, warn_days is required")
        if any(value < 0 for value in expected.values()):
            raise ValueError("aging values must not be negative")

    def describe(self) -> str:
        parts = ", ".join(
            f"{field.removesuffix('_days')} {value}" for field, value in self._expected().items()
        )
        return f"user {self.name} password aging: {parts} days"

    def run(self) -> CheckResult:
        result = self.runner.run(["chage", "-l", "--", self.name])
        if not result.ok:
            output = f"{result.stderr}\n{result.stdout}"
            if "Permission denied" in output:
                return CheckResult(False, _CHAGE_ROOT)
            if "does not exist" in output:
                return CheckResult(False, f"user '{self.name}' does not exist")
            return CheckResult(False, f"cannot query password aging (exit {result.returncode})")
        fields = _parse_chage(result.stdout)
        problems: list[str] = []
        for field, expected in self._expected().items():
            label = _CHAGE_KEYS[field]
            raw = fields.get(label)
            if raw is None or not raw.lstrip("-").isdigit():
                return CheckResult(False, "unexpected chage output")
            if int(raw) != expected:
                problems.append(f"{field.removesuffix('_days')} is {raw}, expected {expected}")
        if problems:
            return CheckResult(False, "; ".join(problems))
        return CheckResult(True, "password aging is correct")


@dataclass(frozen=True, slots=True)
class LoginDefsValue:
    """Valor efectivo (la ultima asignacion gana) de una clave de /etc/login.defs."""

    runner: CommandRunner
    key: str
    value: str

    def __post_init__(self) -> None:
        validate_login_defs_key(self.key)
        if not self.value or not self.value.isprintable() or self.value != self.value.strip():
            raise ValueError(f"invalid login.defs value: {self.value!r}")

    def describe(self) -> str:
        return f"/etc/login.defs sets {self.key} to {self.value}"

    def run(self) -> CheckResult:
        result = self.runner.run(["cat", "--", "/etc/login.defs"])
        if not result.ok:
            return CheckResult(False, "cannot read /etc/login.defs")
        current: str | None = None
        for line in result.stdout.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0] == self.key:
                current = parts[1].strip()
        if current is None:
            return CheckResult(False, f"{self.key} is not set in /etc/login.defs")
        if current != self.value:
            return CheckResult(False, f"{self.key} is {current}, expected {self.value}")
        return CheckResult(True, f"{self.key} is {self.value}")

from __future__ import annotations

import re
from dataclasses import dataclass

from rhcsa_sim.checks._validation import (
    validate_account_name,
    validate_package_name,
    validate_repo_id,
    validate_tuned_profile,
)
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner

_UNEXPECTED_DNF = "unexpected dnf output"
_UNEXPECTED_TUNED = "unexpected tuned-adm output"
_CRON_ROOT = "crontab -l -u requires root (run with sudo)"
_REPO_STATES = frozenset({"enabled", "disabled"})
_TUNED_PREFIX = "Current active profile:"
_TUNED_NONE = "No current active profile."
_TUNED_DOWN = "Service tuned: Not Running"
# campos de cron: numeros, '*', '/', ',' y '-' (sin nombres de mes/dia)
_CRON_FIELD_RE = re.compile(r"[0-9*/,-]+")
_CRON_MACROS = frozenset(
    {"@yearly", "@annually", "@monthly", "@weekly", "@daily", "@midnight", "@hourly", "@reboot"}
)
_CRON_ENV_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*=")


def _parse_repolist(stdout: str) -> dict[str, str] | None:
    """Estado (enabled/disabled) por id de `dnf repolist --all`; None si falta la
    cabecera o una fila no termina en un estado conocido."""
    repos: dict[str, str] = {}
    in_table = False
    for line in stdout.splitlines():
        tokens = line.split()
        if not tokens:
            continue
        if not in_table:
            in_table = tokens[:2] == ["repo", "id"]
            continue
        if len(tokens) < 2 or tokens[-1] not in _REPO_STATES:
            return None
        repos[tokens[0]] = tokens[-1]
    return repos if in_table else None


@dataclass(frozen=True, slots=True)
class RepoNotEnabled:
    """OK si el repositorio no existe o esta deshabilitado."""

    runner: CommandRunner
    repo_id: str

    def __post_init__(self) -> None:
        validate_repo_id(self.repo_id)

    def describe(self) -> str:
        return f"repository {self.repo_id} is not enabled"

    def run(self) -> CheckResult:
        result = self.runner.run(["dnf", "repolist", "--all"])
        if not result.ok:
            return CheckResult(False, f"cannot query repositories (exit {result.returncode})")
        repos = _parse_repolist(result.stdout)
        if repos is None:
            return CheckResult(False, _UNEXPECTED_DNF)
        state = repos.get(self.repo_id)
        if state == "enabled":
            return CheckResult(False, f"repository '{self.repo_id}' is enabled")
        if state is None:
            return CheckResult(True, f"repository '{self.repo_id}' is not present")
        return CheckResult(True, f"repository '{self.repo_id}' is disabled")


@dataclass(frozen=True, slots=True)
class PackageInstalled:
    runner: CommandRunner
    name: str

    def __post_init__(self) -> None:
        validate_package_name(self.name)

    def describe(self) -> str:
        return f"package {self.name} is installed"

    def run(self) -> CheckResult:
        result = self.runner.run(["rpm", "-q", "--", self.name])
        if result.ok:
            return CheckResult(True, f"package '{self.name}' is installed")
        if result.returncode == 1 and "is not installed" in result.stdout:
            return CheckResult(False, f"package '{self.name}' is not installed")
        return CheckResult(False, f"cannot query package '{self.name}' (exit {result.returncode})")


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _validate_schedule(schedule: str) -> str:
    """Cinco campos numericos de cron o una macro (@daily...), normalizados."""
    fields = schedule.split()
    if len(fields) == 1 and fields[0] in _CRON_MACROS:
        return fields[0]
    if len(fields) != 5 or not all(_CRON_FIELD_RE.fullmatch(f) for f in fields):
        raise ValueError(f"invalid cron schedule: {schedule!r}")
    return " ".join(fields)


def _validate_command(command: str) -> str:
    normalized = _normalize(command)
    if not normalized or not command.isprintable():
        raise ValueError(f"invalid cron command: {command!r}")
    return normalized


def _cron_entries(stdout: str) -> list[tuple[str, str]]:
    """Pares (schedule, command) normalizados; ignora vacias, comentarios y
    asignaciones de entorno."""
    entries: list[tuple[str, str]] = []
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or _CRON_ENV_RE.match(line):
            continue
        if line.startswith("@"):
            parts = line.split(None, 1)
            if len(parts) == 2:
                entries.append((parts[0], _normalize(parts[1])))
            continue
        parts = line.split(None, 5)
        if len(parts) == 6:
            entries.append((" ".join(parts[:5]), _normalize(parts[5])))
    return entries


@dataclass(frozen=True, slots=True)
class CronEntryExists:
    """Entrada en el crontab del usuario con el mismo schedule y comando."""

    runner: CommandRunner
    user: str
    schedule: str
    command: str

    def __post_init__(self) -> None:
        validate_account_name(self.user)
        # se valida y normaliza una sola vez; el resto de metodos usa los valores ya normalizados
        object.__setattr__(self, "schedule", _validate_schedule(self.schedule))
        object.__setattr__(self, "command", _validate_command(self.command))

    def describe(self) -> str:
        return f"{self.user} has cron entry '{self.schedule} {self.command}'"

    def run(self) -> CheckResult:
        result = self.runner.run(["crontab", "-l", "-u", self.user])
        if not result.ok:
            text = result.stderr
            if "no crontab for" in text:
                return CheckResult(False, f"user '{self.user}' has no crontab")
            if "must be privileged" in text or "Permission denied" in text:
                return CheckResult(False, _CRON_ROOT)
            return CheckResult(False, f"cannot query crontab (exit {result.returncode})")
        wanted = (self.schedule, self.command)
        if wanted in _cron_entries(result.stdout):
            return CheckResult(True, f"'{self.user}' has cron entry '{' '.join(wanted)}'")
        return CheckResult(False, f"no cron entry '{' '.join(wanted)}' for '{self.user}'")


@dataclass(frozen=True, slots=True)
class TunedProfileIs:
    runner: CommandRunner
    profile: str

    def __post_init__(self) -> None:
        validate_tuned_profile(self.profile)

    def describe(self) -> str:
        return f"tuned profile is {self.profile}"

    def run(self) -> CheckResult:
        result = self.runner.run(["tuned-adm", "active"])
        if not result.ok:
            return CheckResult(False, f"cannot query tuned (exit {result.returncode})")
        lines = [line.strip() for line in result.stdout.splitlines()]
        if _TUNED_NONE in lines:
            return CheckResult(False, "no active tuned profile")
        # solo cuenta la linea "Current active profile:"; el resto (post-loaded, preset,
        # estado del servicio) es informativo
        profiles = [
            line.removeprefix(_TUNED_PREFIX).strip()
            for line in lines
            if line.startswith(_TUNED_PREFIX)
        ]
        if len(profiles) != 1:
            return CheckResult(False, _UNEXPECTED_TUNED)
        actual = profiles[0]
        try:
            validate_tuned_profile(actual)
        except ValueError:
            return CheckResult(False, _UNEXPECTED_TUNED)
        if _TUNED_DOWN in lines:
            return CheckResult(False, "tuned service is not running (profile may not be applied)")
        if actual != self.profile:
            return CheckResult(False, f"tuned profile is {actual}, expected {self.profile}")
        return CheckResult(True, f"tuned profile is {actual}")


_AT_HINT = "(atq shows only your own jobs without sudo)"
_AT_QUEUE_RE = re.compile(r"[A-Za-z]")


def _parse_atq(stdout: str) -> list[tuple[str, str]] | None:
    """Devuelve (cola, usuario) por trabajo; None si alguna linea no se entiende."""
    jobs: list[tuple[str, str]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        job_id, sep, rest = line.partition("\t")
        fields = rest.split()
        if not sep or not job_id.strip().isdigit() or len(fields) < 2:
            return None
        jobs.append((fields[-2], fields[-1]))
    return jobs


@dataclass(frozen=True, slots=True)
class AtJobQueued:
    """Hay al menos un trabajo de at en cola para el usuario (opcionalmente en una cola)."""

    runner: CommandRunner
    user: str
    queue: str | None = None

    def __post_init__(self) -> None:
        validate_account_name(self.user)
        if self.queue is not None and not _AT_QUEUE_RE.fullmatch(self.queue):
            raise ValueError(f"at queue must be a single letter: {self.queue!r}")

    def describe(self) -> str:
        suffix = f" in queue {self.queue}" if self.queue else ""
        return f"at job queued for {self.user}{suffix}"

    def run(self) -> CheckResult:
        result = self.runner.run(["atq"])
        if result.returncode == 127:
            return CheckResult(False, "at is not installed")
        if not result.ok:
            return CheckResult(False, f"cannot query at queue (exit {result.returncode})")
        jobs = _parse_atq(result.stdout)
        if jobs is None:
            return CheckResult(False, "unexpected atq output")
        for queue, user in jobs:
            if user == self.user and (self.queue is None or queue == self.queue):
                return CheckResult(True, f"at job queued for '{self.user}'")
        return CheckResult(False, f"no at job queued for {self.user} {_AT_HINT}")

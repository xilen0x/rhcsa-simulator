from __future__ import annotations

from dataclasses import dataclass

from rhcsa_sim.checks._validation import validate_absolute_path, validate_selinux_type
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner

_MODES = frozenset({"enforcing", "permissive"})


def _parse_sestatus(stdout: str) -> dict[str, str]:
    """Pares 'Clave: valor' de sestatus; las lineas sin ':' se ignoran."""
    fields: dict[str, str] = {}
    for line in stdout.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip():
            fields[key.strip()] = value.strip()
    return fields


@dataclass(frozen=True, slots=True)
class SelinuxMode:
    runner: CommandRunner
    mode: str = "enforcing"

    def __post_init__(self) -> None:
        if self.mode not in _MODES:
            raise ValueError(f"invalid SELinux mode: {self.mode!r}")

    def describe(self) -> str:
        return f"SELinux is {self.mode} (runtime and config file)"

    def run(self) -> CheckResult:
        result = self.runner.run(["sestatus"])
        if not result.ok:
            return CheckResult(False, f"cannot query SELinux status (exit {result.returncode})")
        fields = _parse_sestatus(result.stdout)
        status = fields.get("SELinux status")
        if status == "disabled":
            return CheckResult(False, "SELinux is disabled")
        current = fields.get("Current mode")
        config = fields.get("Mode from config file")
        if not status or not current or not config:
            return CheckResult(False, "unexpected sestatus output")
        runtime_ok = current == self.mode
        config_ok = config == self.mode
        if runtime_ok and config_ok:
            return CheckResult(True, f"SELinux is {self.mode} (runtime and config file)")
        if runtime_ok:
            return CheckResult(
                False,
                f"current mode is {current} but config file has {config} "
                "(edit /etc/selinux/config)",
            )
        if config_ok:
            return CheckResult(
                False,
                f"config file has {config} but current mode is {current} "
                "(run setenforce or reboot)",
            )
        return CheckResult(
            False,
            f"current mode is {current}, config file has {config}, expected {self.mode}",
        )


def _context_type(stdout: str) -> str | None:
    """Tipo (tercer campo) de un contexto user:role:type:level; None si no es valido."""
    lines = stdout.splitlines()
    if len(lines) != 1:
        return None
    fields = lines[0].strip().split(":")
    if len(fields) < 4:
        return None
    try:
        return validate_selinux_type(fields[2])
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class PathHasSelinuxType:
    runner: CommandRunner
    path: str
    selinux_type: str

    def __post_init__(self) -> None:
        validate_absolute_path(self.path)
        validate_selinux_type(self.selinux_type)

    def describe(self) -> str:
        return (
            f"{self.path} has SELinux type {self.selinux_type} (actual and default rule)"
        )

    def run(self) -> CheckResult:
        # matchpathcon funciona aunque la ruta no exista y sin root
        rule_result = self.runner.run(["matchpathcon", "-n", "--", self.path])
        if not rule_result.ok:
            return CheckResult(
                False, f"cannot query default context (exit {rule_result.returncode})"
            )
        stat_result = self.runner.run(["stat", "-c", "%C", "--", self.path])
        if stat_result.returncode == 1:
            return CheckResult(False, f"cannot stat '{self.path}'")
        if not stat_result.ok:
            return CheckResult(
                False, f"cannot query file context (exit {stat_result.returncode})"
            )
        rule = _context_type(rule_result.stdout)
        if rule is None:
            return CheckResult(False, "unexpected matchpathcon output")
        actual = _context_type(stat_result.stdout)
        if actual is None:
            return CheckResult(False, "unexpected stat output")
        expected = self.selinux_type
        if actual == expected and rule == expected:
            return CheckResult(True, f"labeled {expected} (matches default rule)")
        if actual == expected:
            return CheckResult(
                False,
                f"labeled {actual} but the default rule is {rule} "
                "(not persistent; add a semanage fcontext rule)",
            )
        if rule == expected:
            return CheckResult(
                False,
                f"default rule is {rule} but file is labeled {actual} (run restorecon)",
            )
        return CheckResult(
            False, f"labeled {actual} and default rule is {rule}, expected {expected}"
        )

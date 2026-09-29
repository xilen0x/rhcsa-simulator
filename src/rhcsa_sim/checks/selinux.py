from __future__ import annotations

import re
from dataclasses import dataclass

from rhcsa_sim.checks._validation import (
    validate_absolute_path,
    validate_port,
    validate_protocol,
    validate_selinux_boolean,
    validate_selinux_type,
)
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandResult, CommandRunner

_MODES = frozenset({"enforcing", "permissive"})
_PROTOCOLS = frozenset({"tcp", "udp", "sctp", "dccp"})
_GETSEBOOL_RE = re.compile(r"(\S+) --> (on|off)")
# semanage boolean -l: (estado actual, valor por defecto/persistente)
_BOOL_PAIR_RE = re.compile(r"\(\s*(on|off)\s*,\s*(on|off)\s*\)")
_PORT_RANGE_RE = re.compile(r"(\d+)(?:-(\d+))?")
_UNEXPECTED_SEMANAGE = "unexpected semanage output"
_SEMANAGE_ROOT = "semanage requires root (run with sudo)"


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


def _semanage_needs_root(result: CommandResult) -> bool:
    """Sin root semanage sale con rc 1 y un ValueError sobre el store de politica."""
    return result.returncode == 1 and "not managed" in result.stderr


def _on_off(enabled: bool) -> str:
    return "on" if enabled else "off"


def _query_runtime_boolean(runner: CommandRunner, name: str) -> bool | CheckResult:
    result = runner.run(["getsebool", "--", name])
    if not result.ok:
        if result.returncode == 255 and "Error getting active value" in result.stderr:
            return CheckResult(False, f"boolean '{name}' does not exist")
        return CheckResult(False, f"cannot query SELinux boolean (exit {result.returncode})")
    match = _GETSEBOOL_RE.fullmatch(result.stdout.strip())
    if match is None or match.group(1) != name:
        return CheckResult(False, "unexpected getsebool output")
    return match.group(2) == "on"


def _query_persistent_boolean(runner: CommandRunner, name: str) -> bool | CheckResult:
    result = runner.run(["semanage", "boolean", "-l"])
    if _semanage_needs_root(result):
        return CheckResult(False, _SEMANAGE_ROOT)
    if not result.ok:
        return CheckResult(False, f"cannot query SELinux booleans (exit {result.returncode})")
    for line in result.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2 or parts[0] != name:
            continue
        match = _BOOL_PAIR_RE.match(parts[1])
        if match is None:
            return CheckResult(False, _UNEXPECTED_SEMANAGE)
        return match.group(2) == "on"
    return CheckResult(False, _UNEXPECTED_SEMANAGE)


@dataclass(frozen=True, slots=True)
class SelinuxBooleanIs:
    runner: CommandRunner
    name: str
    enabled: bool = True

    def __post_init__(self) -> None:
        validate_selinux_boolean(self.name)

    def describe(self) -> str:
        return (
            f"SELinux boolean {self.name} is {_on_off(self.enabled)} (runtime and persistent)"
        )

    def run(self) -> CheckResult:
        """Consulta runtime primero (si falla, no se consulta semanage) y luego persistente."""
        runtime = _query_runtime_boolean(self.runner, self.name)
        if isinstance(runtime, CheckResult):
            return runtime
        persistent = _query_persistent_boolean(self.runner, self.name)
        if isinstance(persistent, CheckResult):
            return persistent
        expected = _on_off(self.enabled)
        runtime_ok = runtime == self.enabled
        persistent_ok = persistent == self.enabled
        if runtime_ok and persistent_ok:
            return CheckResult(True, f"boolean is {expected} (runtime and persistent)")
        if runtime_ok:
            return CheckResult(False, "set only at runtime (use setsebool -P)")
        if persistent_ok:
            return CheckResult(
                False, "set persistently but not active (run setsebool without -P or reboot)"
            )
        return CheckResult(False, f"boolean is {_on_off(runtime)}, expected {expected}")


def _parse_ports(spec: str) -> list[tuple[int, int]] | None:
    """Lista '80, 81, 1024-32767' como rangos (inicio, fin); None si esta mal formada."""
    ranges: list[tuple[int, int]] = []
    for item in spec.split(","):
        match = _PORT_RANGE_RE.fullmatch(item.strip())
        if match is None:
            return None
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        if not 1 <= start <= end <= 65535:
            return None
        ranges.append((start, end))
    return ranges


def _parse_port_types(
    stdout: str, protocol: str
) -> list[tuple[str, list[tuple[int, int]]]] | None:
    """Entradas (tipo, rangos) de semanage port -l para un protocolo, en orden de
    aparicion. Ignora la cabecera y lineas ajenas; None si no hay ninguna entrada
    valida o una entrada tiene puertos mal formados."""
    entries: list[tuple[str, list[tuple[int, int]]]] = []
    seen_any = False
    for line in stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) != 3 or parts[1] not in _PROTOCOLS:
            continue
        ranges = _parse_ports(parts[2])
        if ranges is None:
            return None
        seen_any = True
        if parts[1] == protocol:
            entries.append((parts[0], ranges))
    return entries if seen_any else None


@dataclass(frozen=True, slots=True)
class SelinuxPortType:
    runner: CommandRunner
    port: int
    protocol: str
    selinux_type: str

    def __post_init__(self) -> None:
        validate_port(self.port)
        validate_protocol(self.protocol)
        validate_selinux_type(self.selinux_type)

    def describe(self) -> str:
        return f"port {self.port}/{self.protocol} is labeled {self.selinux_type}"

    def run(self) -> CheckResult:
        result = self.runner.run(["semanage", "port", "-l"])
        if _semanage_needs_root(result):
            return CheckResult(False, _SEMANAGE_ROOT)
        if not result.ok:
            return CheckResult(False, f"cannot query SELinux ports (exit {result.returncode})")
        entries = _parse_port_types(result.stdout, self.protocol)
        if entries is None:
            return CheckResult(False, _UNEXPECTED_SEMANAGE)
        holders = [
            name
            for name, ranges in entries
            if any(start <= self.port <= end for start, end in ranges)
        ]
        target = f"port {self.port}/{self.protocol}"
        if self.selinux_type in holders:
            return CheckResult(True, f"{target} is labeled {self.selinux_type}")
        detail = f"{target} is not labeled {self.selinux_type}"
        if holders:
            detail += f" (currently labeled {holders[0]})"
        return CheckResult(False, detail)

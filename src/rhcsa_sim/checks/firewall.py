from __future__ import annotations

from dataclasses import dataclass

from rhcsa_sim.checks._validation import (
    validate_firewall_service,
    validate_port,
    validate_protocol,
    validate_zone,
)
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner

# Codigos de salida de firewall-cmd (firewall/errors.py)
_INVALID_SERVICE = 101
_INVALID_PORT = 102
_INVALID_ZONE = 112
_NOT_RUNNING = 252
_NOT_AUTHORIZED = 253


def _query(
    runner: CommandRunner, zone: str, permanent: bool, query: str, service: str | None
) -> bool | CheckResult:
    """Ejecuta una consulta --query-*: True si esta permitido, False si no y un
    CheckResult KO ante cualquier error. rc 0 = si, rc 1 = no; la salida no cuenta."""
    argv = ["firewall-cmd"]
    if permanent:
        argv.append("--permanent")
    argv += [f"--zone={zone}", query]
    rc = runner.run(argv).returncode
    if rc == 0:
        return True
    if rc == 1:
        return False
    if rc == _NOT_AUTHORIZED:
        return CheckResult(False, "firewalld queries require root (run with sudo)")
    if rc == _NOT_RUNNING:
        return CheckResult(False, "firewalld is not running")
    if rc == _INVALID_ZONE:
        return CheckResult(False, f"zone '{zone}' does not exist")
    if rc == _INVALID_SERVICE and service is not None:
        return CheckResult(False, f"service '{service}' is not a known firewalld service")
    if rc == _INVALID_PORT and service is None:
        return CheckResult(False, "invalid port")
    return CheckResult(False, f"cannot query firewalld (exit {rc})")


def _evaluate(
    runner: CommandRunner, zone: str, query: str, service: str | None
) -> CheckResult:
    """Consulta permanente primero (si falla, no se consulta runtime) y luego runtime."""
    permanent = _query(runner, zone, True, query, service)
    if isinstance(permanent, CheckResult):
        return permanent
    runtime = _query(runner, zone, False, query, service)
    if isinstance(runtime, CheckResult):
        return runtime
    if permanent and runtime:
        return CheckResult(True, "allowed in permanent and runtime configuration")
    if permanent:
        return CheckResult(
            False, "allowed only in permanent configuration (run firewall-cmd --reload)"
        )
    if runtime:
        return CheckResult(
            False, "allowed only in runtime configuration (not persistent; use --permanent)"
        )
    return CheckResult(False, f"not allowed in zone '{zone}'")


@dataclass(frozen=True, slots=True)
class FirewallServiceAllowed:
    runner: CommandRunner
    zone: str
    service: str

    def __post_init__(self) -> None:
        validate_zone(self.zone)
        validate_firewall_service(self.service)

    def describe(self) -> str:
        return f"service {self.service} is allowed in zone {self.zone} (permanent and runtime)"

    def run(self) -> CheckResult:
        query = f"--query-service={self.service}"
        return _evaluate(self.runner, self.zone, query, self.service)


@dataclass(frozen=True, slots=True)
class FirewallPortAllowed:
    runner: CommandRunner
    zone: str
    port: int
    protocol: str = "tcp"

    def __post_init__(self) -> None:
        validate_zone(self.zone)
        validate_port(self.port)
        validate_protocol(self.protocol)

    def describe(self) -> str:
        return (
            f"port {self.port}/{self.protocol} is allowed in zone {self.zone} "
            "(permanent and runtime)"
        )

    def run(self) -> CheckResult:
        query = f"--query-port={self.port}/{self.protocol}"
        return _evaluate(self.runner, self.zone, query, None)

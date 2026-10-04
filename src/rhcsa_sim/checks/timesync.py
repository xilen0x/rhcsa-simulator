from __future__ import annotations

from dataclasses import dataclass

from rhcsa_sim.checks._validation import validate_hostname
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner

_CONF = "/etc/chrony.conf"
_SOURCE_DIRECTIVES = frozenset({"server", "pool"})


@dataclass(frozen=True, slots=True)
class ChronySource:
    """/etc/chrony.conf declara `server <host>` o `pool <host>` (cualquier linea)."""

    runner: CommandRunner
    host: str

    def __post_init__(self) -> None:
        validate_hostname(self.host)

    def describe(self) -> str:
        return f"chrony uses time source {self.host}"

    def run(self) -> CheckResult:
        result = self.runner.run(["cat", "--", _CONF])
        if not result.ok:
            return CheckResult(False, f"cannot read {_CONF} (exit {result.returncode})")
        sources: list[str] = []
        for line in result.stdout.splitlines():
            tokens = line.split()
            if len(tokens) >= 2 and tokens[0] in _SOURCE_DIRECTIVES:
                sources.append(tokens[1])
        if self.host not in sources:
            found = ", ".join(sources) if sources else "(none)"
            return CheckResult(False, f"chrony sources are {found}, expected {self.host}")
        return CheckResult(True, f"chrony uses {self.host}")

from __future__ import annotations

import re
from dataclasses import dataclass

from rhcsa_sim.checks._validation import validate_kernel_arg
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner

_NO_ENTRIES = "no boot entries visible (grubby needs root: run with sudo)"
_INDEX_RE = re.compile(r"index=\d+")
_FIELD_RE = re.compile(r'(kernel|args|title)="(.*)"')


def _parse_entries(stdout: str) -> list[dict[str, str]]:
    """Entradas de `grubby --info=ALL`: cada una empieza en `index=N`."""
    entries: list[dict[str, str]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if _INDEX_RE.fullmatch(line):
            entries.append({})
        elif entries and (match := _FIELD_RE.fullmatch(line)):
            entries[-1][match.group(1)] = match.group(2)
    return entries


@dataclass(frozen=True, slots=True)
class KernelArgPresent:
    """OK si TODAS las entradas de arranque (grubby --info=ALL) llevan el argumento."""

    runner: CommandRunner
    arg: str

    def __post_init__(self) -> None:
        validate_kernel_arg(self.arg)

    def describe(self) -> str:
        return f"all boot entries have kernel argument {self.arg}"

    def run(self) -> CheckResult:
        result = self.runner.run(["grubby", "--info=ALL"])
        if not result.ok:
            lines = result.stderr.strip().splitlines()
            reason = lines[0] if lines else f"exit {result.returncode}"
            return CheckResult(False, f"cannot read boot entries: {reason}")
        entries = _parse_entries(result.stdout)
        if not entries:
            return CheckResult(False, _NO_ENTRIES)
        missing = [
            entry.get("kernel") or entry.get("title") or "?"
            for entry in entries
            if self.arg not in entry.get("args", "").split()
        ]
        if missing:
            return CheckResult(
                False, f"kernel argument {self.arg} missing in: {', '.join(missing)}"
            )
        return CheckResult(True, f"kernel argument {self.arg} present in {len(entries)} entries")

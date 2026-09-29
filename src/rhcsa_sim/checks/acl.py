from __future__ import annotations

from dataclasses import dataclass

from rhcsa_sim.checks._validation import validate_absolute_path, validate_acl_entry
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner

_GETFACL_NOT_FOUND = 127


@dataclass(frozen=True, slots=True)
class PathHasAclEntry:
    runner: CommandRunner
    path: str
    entry: str

    def __post_init__(self) -> None:
        validate_absolute_path(self.path)
        validate_acl_entry(self.entry)

    def describe(self) -> str:
        return f"{self.path} has ACL entry {self.entry}"

    def run(self) -> CheckResult:
        argv = ["getfacl", "--omit-header", "--absolute-names", "--no-effective", "--", self.path]
        result = self.runner.run(argv)
        if result.returncode == _GETFACL_NOT_FOUND:
            return CheckResult(False, "getfacl not found (install package acl)")
        if not result.ok:
            return CheckResult(
                False, f"cannot read ACL of '{self.path}' (exit {result.returncode})"
            )
        lines = {line.strip() for line in result.stdout.splitlines()}
        if self.entry not in lines:
            return CheckResult(False, f"ACL entry {self.entry} not found on '{self.path}'")
        return CheckResult(True, f"ACL entry {self.entry} is present")

from __future__ import annotations

from dataclasses import dataclass
from posixpath import basename

from rhcsa_sim.checks._validation import validate_absolute_path
from rhcsa_sim.checks.files import _parse_mode
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner

# Solo analisis estatico: nunca se ejecuta el script del alumno (bash -n solo parsea).
_OWNER_EXEC = 0o100
_ROOT_HINT = "permission denied (run with sudo)"


def _validate_line(line: str) -> str:
    if not line or "\n" in line or "\x00" in line:
        raise ValueError(f"line must be non-empty and free of newline/NUL: {line!r}")
    return line


@dataclass(frozen=True, slots=True)
class FileIsExecutable:
    """Fichero regular con el bit de ejecucion del propietario."""

    runner: CommandRunner
    path: str

    def __post_init__(self) -> None:
        validate_absolute_path(self.path)

    def describe(self) -> str:
        return f"{self.path} is an executable file"

    def run(self) -> CheckResult:
        result = self.runner.run(["stat", "-c", "%a %F", "--", self.path])
        if not result.ok:
            return CheckResult(False, f"cannot stat '{self.path}'")
        parts = result.stdout.strip().split(None, 1)
        if len(parts) != 2:
            return CheckResult(False, "unexpected stat output")
        try:
            mode = _parse_mode(parts[0])
        except ValueError:
            return CheckResult(False, "unexpected stat output")
        if not parts[1].startswith("regular"):
            return CheckResult(False, f"'{self.path}' is not a regular file ({parts[1]})")
        if not mode & _OWNER_EXEC:
            return CheckResult(False, f"'{self.path}' is not executable (mode {mode:o})")
        return CheckResult(True, f"'{self.path}' is executable (mode {mode:o})")


@dataclass(frozen=True, slots=True)
class ScriptHasShebang:
    runner: CommandRunner
    path: str
    interpreter: str = "/bin/bash"

    def __post_init__(self) -> None:
        validate_absolute_path(self.path)
        validate_absolute_path(self.interpreter)

    def describe(self) -> str:
        return f"{self.path} starts with a {self.interpreter} shebang"

    def run(self) -> CheckResult:
        result = self.runner.run(["head", "-n", "1", "--", self.path])
        if not result.ok:
            return CheckResult(False, f"cannot read '{self.path}'")
        first = result.stdout.splitlines()[0].rstrip() if result.stdout else ""
        accepted = (
            f"#!{self.interpreter}",
            f"#!/usr/bin/env {basename(self.interpreter)}",
        )
        if first in accepted:
            return CheckResult(True, f"shebang is '{first}'")
        return CheckResult(False, f"missing shebang '#!{self.interpreter}'")


@dataclass(frozen=True, slots=True)
class ScriptSyntaxValid:
    """`bash -n` solo parsea el script; no lo ejecuta."""

    runner: CommandRunner
    path: str

    def __post_init__(self) -> None:
        validate_absolute_path(self.path)

    def describe(self) -> str:
        return f"{self.path} has valid bash syntax"

    def run(self) -> CheckResult:
        result = self.runner.run(["bash", "-n", "--", self.path])
        if result.ok:
            return CheckResult(True, "syntax is valid")
        # 126/127: bash no pudo abrir el fichero (sin permiso o no existe)
        if result.returncode in (126, 127):
            return CheckResult(False, f"cannot read '{self.path}'")
        return CheckResult(False, "syntax error")


@dataclass(frozen=True, slots=True)
class FileContainsLine:
    """Alguna linea del fichero es exactamente `line` (grep -Fx)."""

    runner: CommandRunner
    path: str
    line: str

    def __post_init__(self) -> None:
        validate_absolute_path(self.path)
        _validate_line(self.line)

    def describe(self) -> str:
        return f"{self.path} contains the line '{self.line}'"

    def run(self) -> CheckResult:
        result = self.runner.run(["grep", "-Fxq", "--", self.line, self.path])
        if result.ok:
            return CheckResult(True, "line found")
        if result.returncode == 1:
            return CheckResult(False, "line not found")
        if "Permission denied" in result.stderr:
            return CheckResult(False, f"cannot read '{self.path}': {_ROOT_HINT}")
        return CheckResult(False, f"cannot read '{self.path}'")

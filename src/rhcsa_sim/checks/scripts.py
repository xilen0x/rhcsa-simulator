from __future__ import annotations

import re
from dataclasses import dataclass
from posixpath import basename

from rhcsa_sim.checks._validation import parse_octal_mode, validate_absolute_path
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
            mode = parse_octal_mode(parts[0])
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
        # split("\n") (no splitlines) para conservar el '\r' de un fin de linea CRLF
        first = result.stdout.split("\n")[0].rstrip(" \t")
        if first.endswith("\r"):
            return CheckResult(False, "shebang line ends with CRLF (use LF line endings)")
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


# Construcciones reconocidas por ScriptUsesConstructs (regex sobre lineas sin comentarios).
_CONSTRUCT_PATTERNS: dict[str, re.Pattern[str]] = {
    "if": re.compile(r"\bif\b|\[\[|\btest\b"),
    "for": re.compile(r"\bfor\s+\w+\s+in\b|\bfor\s*\(\("),
    "args": re.compile(r"\$[1-9]|\$\{[1-9]|\$[@*#]"),
    "cmdsubst": re.compile(r"\$\((?!\()|`"),
}
# Comentario: '#' al inicio de linea o precedido de espacio (asi `$#` y `${#x}` se conservan).
_TRAILING_COMMENT_RE = re.compile(r"(?:^|\s)#.*$")


def _strip_comments(text: str) -> str:
    return "\n".join(_TRAILING_COMMENT_RE.sub("", line) for line in text.splitlines())


@dataclass(frozen=True, slots=True)
class ScriptUsesConstructs:
    """Analisis estatico (regex, nunca ejecuta el script): el script usa cada construccion
    pedida entre "if", "for", "args" y "cmdsubst".

    Limitacion: se ignoran comentarios, pero no se distinguen cadenas ni heredocs; un
    `if` dentro de un echo cuenta.
    """

    runner: CommandRunner
    path: str
    constructs: tuple[str, ...]

    def __post_init__(self) -> None:
        validate_absolute_path(self.path)
        if not self.constructs:
            raise ValueError("at least one construct is required")
        for name in self.constructs:
            if name not in _CONSTRUCT_PATTERNS:
                raise ValueError(f"unknown script construct: {name!r}")

    def describe(self) -> str:
        return f"{self.path} uses: {', '.join(self.constructs)}"

    def run(self) -> CheckResult:
        result = self.runner.run(["cat", "--", self.path])
        if not result.ok:
            if "Permission denied" in result.stderr:
                return CheckResult(False, f"cannot read '{self.path}': {_ROOT_HINT}")
            return CheckResult(False, f"cannot read '{self.path}'")
        code = _strip_comments(result.stdout)
        missing = [n for n in self.constructs if not _CONSTRUCT_PATTERNS[n].search(code)]
        if missing:
            return CheckResult(False, f"missing constructs: {', '.join(missing)}")
        return CheckResult(True, f"uses {', '.join(self.constructs)}")

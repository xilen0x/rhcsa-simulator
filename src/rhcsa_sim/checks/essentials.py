from __future__ import annotations

from dataclasses import dataclass

from rhcsa_sim.checks._validation import validate_absolute_path
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner

# Solo lectura: nunca se extrae un archivo ni se modifica nada.
_COMPRESSION_MIME = {
    "gzip": "application/gzip",
    "xz": "application/x-xz",
    "bzip2": "application/x-bzip2",
    "zstd": "application/zstd",
}
_MAX_REPORTED = 3


def _normalize_member(name: str) -> str:
    """Quita los './' iniciales y las '/' finales de un miembro de tar."""
    while name.startswith("./"):
        name = name[2:]
    return name.rstrip("/")


def _validate_member(member: str) -> str:
    if "\n" in member or "\x00" in member or member.startswith("/"):
        raise ValueError(f"invalid archive member: {member!r}")
    if not _normalize_member(member):
        raise ValueError(f"invalid archive member: {member!r}")
    return member


@dataclass(frozen=True, slots=True)
class ArchiveContains:
    """Archivo tar con la compresion indicada que incluye ciertos miembros."""

    runner: CommandRunner
    path: str
    compression: str
    members: tuple[str, ...]

    def __post_init__(self) -> None:
        validate_absolute_path(self.path)
        if self.compression not in _COMPRESSION_MIME:
            raise ValueError(f"invalid compression: {self.compression!r}")
        if not self.members:
            raise ValueError("at least one archive member is required")
        for member in self.members:
            _validate_member(member)

    def describe(self) -> str:
        return f"{self.path} is a {self.compression} tar archive containing " + ", ".join(
            self.members
        )

    def run(self) -> CheckResult:
        mime = self.runner.run(["file", "-b", "--mime-type", "--", self.path])
        if not mime.ok:
            return CheckResult(False, f"cannot inspect '{self.path}'")
        found = mime.stdout.strip()
        # `file` sale con rc 0 aunque no pueda abrir la ruta: "cannot open `p' (motivo)".
        if found.startswith("cannot open"):
            reason = found[found.rfind("(") :] if found.endswith(")") else ""
            return CheckResult(False, f"cannot open '{self.path}' {reason}".rstrip())
        expected = _COMPRESSION_MIME[self.compression]
        if found != expected:
            return CheckResult(False, f"type is {found or 'unknown'}, expected {expected}")
        listing = self.runner.run(["tar", "-tf", self.path])
        if not listing.ok:
            return CheckResult(False, f"cannot list '{self.path}' as a tar archive")
        entries = {_normalize_member(line) for line in listing.stdout.splitlines()}
        entries.discard("")
        missing = [
            m for m in self.members if not self._present(_normalize_member(m), entries)
        ]
        if missing:
            shown = ", ".join(missing[:_MAX_REPORTED])
            more = "" if len(missing) <= _MAX_REPORTED else f" (+{len(missing) - _MAX_REPORTED} more)"
            return CheckResult(
                False, f"{len(missing)} of {len(self.members)} members missing: {shown}{more}"
            )
        return CheckResult(True, f"archive contains all {len(self.members)} members")

    @staticmethod
    def _present(member: str, entries: set[str]) -> bool:
        prefix = member + "/"
        return member in entries or any(e.startswith(prefix) for e in entries)


@dataclass(frozen=True, slots=True)
class HardLinkTo:
    """`link` y `target` son ficheros regulares con el mismo dispositivo e inodo."""

    runner: CommandRunner
    link: str
    target: str

    def __post_init__(self) -> None:
        validate_absolute_path(self.link)
        validate_absolute_path(self.target)
        if self.link == self.target:
            raise ValueError("link and target must be different paths")

    def describe(self) -> str:
        return f"{self.link} is a hard link to {self.target}"

    def _identity(self, path: str) -> str | CheckResult:
        result = self.runner.run(["stat", "-c", "%d %i %F", "--", path])
        if not result.ok:
            return CheckResult(False, f"cannot stat '{path}'")
        parts = result.stdout.strip().split(None, 2)
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            return CheckResult(False, "unexpected stat output")
        if parts[2] != "regular file":
            return CheckResult(False, f"'{path}' is not a regular file ({parts[2]})")
        return parts[0] + ":" + parts[1]

    def run(self) -> CheckResult:
        link = self._identity(self.link)
        if isinstance(link, CheckResult):
            return link
        target = self._identity(self.target)
        if isinstance(target, CheckResult):
            return target
        if link != target:
            return CheckResult(False, "paths do not share the same inode")
        return CheckResult(True, "both paths share the same inode")


@dataclass(frozen=True, slots=True)
class SymlinkTo:
    """`link` es un enlace simbolico cuyo destino literal es `target`."""

    runner: CommandRunner
    link: str
    target: str

    def __post_init__(self) -> None:
        validate_absolute_path(self.link)
        validate_absolute_path(self.target)

    def describe(self) -> str:
        return f"{self.link} is a symbolic link to {self.target}"

    def run(self) -> CheckResult:
        kind = self.runner.run(["stat", "-c", "%F", "--", self.link])
        if not kind.ok:
            return CheckResult(False, f"cannot stat '{self.link}'")
        if kind.stdout.strip() != "symbolic link":
            return CheckResult(False, f"'{self.link}' is not a symbolic link")
        target = self.runner.run(["readlink", "--", self.link])
        if not target.ok:
            return CheckResult(False, f"cannot read link '{self.link}'")
        actual = target.stdout.rstrip("\n")
        if actual != self.target:
            return CheckResult(False, f"link points to {actual}, expected {self.target}")
        return CheckResult(True, f"link points to {self.target}")


@dataclass(frozen=True, slots=True)
class GrepOutputSaved:
    """`dest` contiene exactamente (y en orden) la salida de `grep pattern source`."""

    runner: CommandRunner
    source: str
    pattern: str
    dest: str

    def __post_init__(self) -> None:
        validate_absolute_path(self.source)
        validate_absolute_path(self.dest)
        if not self.pattern or "\n" in self.pattern or "\x00" in self.pattern:
            raise ValueError(f"pattern must be non-empty and free of newline/NUL: {self.pattern!r}")

    def describe(self) -> str:
        return f"{self.dest} holds the lines of {self.source} matching '{self.pattern}'"

    def run(self) -> CheckResult:
        grep = self.runner.run(["grep", "--", self.pattern, self.source])
        if grep.returncode not in (0, 1):
            return CheckResult(False, f"cannot grep '{self.source}'")
        saved = self.runner.run(["cat", "--", self.dest])
        if not saved.ok:
            return CheckResult(False, f"cannot read '{self.dest}'")
        expected = grep.stdout.splitlines()
        found = saved.stdout.splitlines()
        if expected == found:
            return CheckResult(True, f"{len(found)} lines saved correctly")
        first = next(
            (i for i, (a, b) in enumerate(zip(expected, found, strict=False)) if a != b),
            min(len(expected), len(found)),
        )
        return CheckResult(
            False,
            f"expected {len(expected)} lines, found {len(found)}; first difference at line {first + 1}",
        )

from __future__ import annotations

from dataclasses import dataclass

from rhcsa_sim.checks._validation import validate_absolute_path, validate_fstype
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner

_MASTER = "/etc/auto.master"
_MASTER_DIR = "/etc/auto.master.d"


def _validate_token(value: str, what: str) -> str:
    if not value or any(c.isspace() or c == "\0" for c in value):
        raise ValueError(f"invalid autofs {what}: {value!r}")
    return value


def _entries(text: str) -> list[list[str]]:
    """Lineas utiles (sin comentarios ni vacias) separadas en tokens."""
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            rows.append(stripped.split())
    return rows


@dataclass(frozen=True, slots=True)
class AutofsMasterEntry:
    """Linea `<punto> <mapa> [opciones]` en /etc/auto.master o /etc/auto.master.d/*.autofs."""

    runner: CommandRunner
    mount_point: str
    map_file: str

    def __post_init__(self) -> None:
        validate_absolute_path(self.mount_point)
        validate_absolute_path(self.map_file)

    def describe(self) -> str:
        return f"autofs master map maps {self.mount_point} to {self.map_file}"

    def _sources(self) -> list[str]:
        found = self.runner.run(["find", _MASTER_DIR, "-maxdepth", "1", "-name", "*.autofs"])
        # si el directorio no existe, simplemente no hay ficheros extra
        extra = sorted(found.stdout.split("\n")) if found.ok else []
        return [_MASTER, *(path for path in extra if path)]

    def run(self) -> CheckResult:
        paths = self._sources()
        for path in paths:
            result = self.runner.run(["cat", "--", path])
            if not result.ok:
                return CheckResult(False, f"cannot read {path} (exit {result.returncode})")
            for tokens in _entries(result.stdout):
                if len(tokens) >= 2 and tokens[0] == self.mount_point and tokens[1] == self.map_file:
                    return CheckResult(True, f"{path} maps {self.mount_point} to {self.map_file}")
        return CheckResult(
            False, f"no master map entry for {self.mount_point} -> {self.map_file}"
        )


@dataclass(frozen=True, slots=True)
class AutofsMapEntry:
    """Linea `<clave> [-opciones] <ubicacion>` en un fichero de mapa, con fstype opcional."""

    runner: CommandRunner
    map_file: str
    key: str
    location: str
    fstype: str | None = None

    def __post_init__(self) -> None:
        validate_absolute_path(self.map_file)
        _validate_token(self.key, "key")
        _validate_token(self.location, "location")
        if self.fstype is not None:
            validate_fstype(self.fstype)

    def describe(self) -> str:
        text = f"autofs map {self.map_file} mounts {self.location} on key '{self.key}'"
        if self.fstype is not None:
            text += f" with fstype={self.fstype}"
        return text

    def _fstype_ok(self, options: list[str]) -> bool:
        if self.fstype is None:
            return True
        for token in options:
            if token.startswith("-") and f"fstype={self.fstype}" in token[1:].split(","):
                return True
        return False

    def run(self) -> CheckResult:
        result = self.runner.run(["cat", "--", self.map_file])
        if not result.ok:
            return CheckResult(False, f"cannot read {self.map_file} (exit {result.returncode})")
        for tokens in _entries(result.stdout):
            if len(tokens) < 2 or tokens[0] != self.key or tokens[-1] != self.location:
                continue
            if self._fstype_ok(tokens[1:-1]):
                return CheckResult(True, f"{self.map_file}: {self.key} -> {self.location}")
        return CheckResult(
            False,
            f"no entry in {self.map_file} for key '{self.key}' -> {self.location}"
            + (f" with fstype={self.fstype}" if self.fstype is not None else ""),
        )

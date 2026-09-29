from __future__ import annotations

from dataclasses import dataclass

from rhcsa_sim.checks._validation import validate_unit_name
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandResult, CommandRunner

_PROPERTIES = "LoadState,ActiveState,UnitFileState"
_REQUIRED_KEYS = ("LoadState", "ActiveState", "UnitFileState")
_FILE_STATES = frozenset({"enabled", "disabled", "masked", "static"})
_ACTIVE_STATES = frozenset({"active", "inactive", "failed"})
_UNEXPECTED = "unexpected systemctl output"


def _query_failed(what: str, result: CommandResult) -> CheckResult:
    return CheckResult(False, f"cannot query {what} (exit {result.returncode})")


def _shown(value: str) -> str:
    return value or "(empty)"


def _parse_show(stdout: str) -> dict[str, str] | None:
    """Pares KEY=VALUE de systemctl show. None si falta una clave, hay lineas
    sin '=' o claves repetidas."""
    props: dict[str, str] = {}
    for line in stdout.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition("=")
        if not sep or not key or key in props:
            return None
        props[key] = value
    if any(key not in props for key in _REQUIRED_KEYS):
        return None
    return props


def _query_unit(runner: CommandRunner, unit: str) -> dict[str, str] | CheckResult:
    """Consulta el estado de una unidad. Una unidad inexistente devuelve rc 0
    con LoadState=not-found, asi que se reporta aparte de un desajuste."""
    result = runner.run(["systemctl", "show", f"--property={_PROPERTIES}", "--", unit])
    if not result.ok:
        return _query_failed(f"unit '{unit}'", result)
    props = _parse_show(result.stdout)
    if props is None:
        return CheckResult(False, f"{_UNEXPECTED} for unit '{unit}'")
    if props["LoadState"] == "not-found":
        return CheckResult(False, f"unit '{unit}' does not exist")
    return props


def _query_default_target(runner: CommandRunner) -> str | CheckResult:
    result = runner.run(["systemctl", "get-default"])
    if not result.ok:
        return _query_failed("default target", result)
    lines = result.stdout.splitlines()
    if len(lines) != 1:
        return CheckResult(False, f"{_UNEXPECTED} for default target")
    try:
        return validate_unit_name(lines[0].strip())
    except ValueError:
        return CheckResult(False, f"{_UNEXPECTED} for default target")


@dataclass(frozen=True, slots=True)
class UnitFileStateIs:
    runner: CommandRunner
    unit: str
    state: str

    def __post_init__(self) -> None:
        validate_unit_name(self.unit)
        if self.state not in _FILE_STATES:
            raise ValueError(f"invalid unit file state: {self.state!r}")

    def describe(self) -> str:
        return f"{self.unit} is {self.state}"

    def run(self) -> CheckResult:
        props = _query_unit(self.runner, self.unit)
        if isinstance(props, CheckResult):
            return props
        actual = props["UnitFileState"]
        if actual != self.state:
            return CheckResult(
                False, f"unit file state is {_shown(actual)}, expected {self.state}"
            )
        return CheckResult(True, f"'{self.unit}' is {self.state}")


@dataclass(frozen=True, slots=True)
class UnitActiveStateIs:
    runner: CommandRunner
    unit: str
    state: str

    def __post_init__(self) -> None:
        validate_unit_name(self.unit)
        if self.state not in _ACTIVE_STATES:
            raise ValueError(f"invalid unit active state: {self.state!r}")

    def describe(self) -> str:
        return f"{self.unit} is {self.state}"

    def run(self) -> CheckResult:
        props = _query_unit(self.runner, self.unit)
        if isinstance(props, CheckResult):
            return props
        actual = props["ActiveState"]
        if actual != self.state:
            return CheckResult(False, f"active state is {_shown(actual)}, expected {self.state}")
        return CheckResult(True, f"'{self.unit}' is {self.state}")


@dataclass(frozen=True, slots=True)
class DefaultTarget:
    runner: CommandRunner
    target: str

    def __post_init__(self) -> None:
        validate_unit_name(self.target)
        if not self.target.endswith(".target"):
            raise ValueError(f"not a target unit: {self.target!r}")

    def describe(self) -> str:
        return f"default target is {self.target}"

    def run(self) -> CheckResult:
        actual = _query_default_target(self.runner)
        if isinstance(actual, CheckResult):
            return actual
        if actual != self.target:
            return CheckResult(False, f"default target is {actual}, expected {self.target}")
        return CheckResult(True, f"default target is {actual}")

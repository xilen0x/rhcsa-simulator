from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

from rhcsa_sim.checks._validation import (
    validate_connection_name,
    validate_hostname,
    validate_ipv4_address,
    validate_ipv4_interface,
)
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandResult, CommandRunner

_FIELDS = "connection.id,connection.autoconnect,ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns"
_FIELDS_V6 = "connection.id,ipv6.method,ipv6.addresses,ipv6.gateway"
_NO_SUCH_PROFILE_RC = 10
_ESCAPE_RE = re.compile(r"\\([:\\])")
_UNEXPECTED = "unexpected nmcli output"


def _shown(value: str) -> str:
    return value or "(empty)"


def _query_failed(what: str, result: CommandResult) -> CheckResult:
    return CheckResult(False, f"cannot query {what} (exit {result.returncode})")


def _parse_terse(stdout: str, fields: str) -> dict[str, str] | None:
    """Pares clave:valor de nmcli -t. Se corta en el primer ':' y en el valor se
    deshacen los escapes \\: y \\\\. None si falta una clave, hay lineas sin ':'
    o claves repetidas."""
    props: dict[str, str] = {}
    for line in stdout.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or not key or key in props:
            return None
        props[key] = _ESCAPE_RE.sub(r"\1", value)
    if any(key not in props for key in fields.split(",")):
        return None
    return props


def _query_profile(
    runner: CommandRunner, name: str, fields: str = _FIELDS
) -> dict[str, str] | CheckResult:
    # 'id' obliga a leer el argumento como nombre de perfil (no usa '--')
    result = runner.run(["nmcli", "-t", "-f", fields, "connection", "show", "id", name])
    if not result.ok:
        if (
            result.returncode == _NO_SUCH_PROFILE_RC
            and "no such connection profile" in result.stderr
        ):
            return CheckResult(False, f"connection profile '{name}' does not exist")
        return _query_failed(f"connection '{name}'", result)
    props = _parse_terse(result.stdout, fields)
    if props is None:
        return CheckResult(False, f"{_UNEXPECTED} for connection '{name}'")
    return props


def _split_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _unexpected(name: str) -> CheckResult:
    return CheckResult(False, f"{_UNEXPECTED} for connection '{name}'")


@dataclass(frozen=True, slots=True)
class ConnectionStaticIpv4:
    runner: CommandRunner
    connection: str
    address: str
    gateway: str | None = None

    def __post_init__(self) -> None:
        validate_connection_name(self.connection)
        validate_ipv4_interface(self.address)
        if self.gateway is not None:
            validate_ipv4_address(self.gateway)

    def describe(self) -> str:
        via = f" via {self.gateway}" if self.gateway is not None else ""
        return f"{self.connection} has static IPv4 {self.address}{via}"

    def run(self) -> CheckResult:
        props = _query_profile(self.runner, self.connection)
        if isinstance(props, CheckResult):
            return props
        method = props["ipv4.method"]
        if method != "manual":
            return CheckResult(False, f"ipv4.method is {_shown(method)}, expected manual")
        wanted = validate_ipv4_interface(self.address)
        try:
            actual = [ipaddress.IPv4Interface(a) for a in _split_values(props["ipv4.addresses"])]
        except ValueError:
            return _unexpected(self.connection)
        if wanted not in actual:
            shown = ", ".join(str(a) for a in actual) or "(none)"
            return CheckResult(False, f"address {wanted} not configured (addresses: {shown})")
        if self.gateway is not None:
            expected_gw = validate_ipv4_address(self.gateway)
            raw_gw = props["ipv4.gateway"].strip()
            try:
                actual_gw = ipaddress.IPv4Address(raw_gw) if raw_gw else None
            except ValueError:
                return _unexpected(self.connection)
            if actual_gw != expected_gw:
                shown_gw = str(actual_gw) if actual_gw is not None else "(none)"
                return CheckResult(False, f"gateway is {shown_gw}, expected {expected_gw}")
        return CheckResult(True, f"'{self.connection}' has static IPv4 {wanted}")


def _validate_ipv6_interface(text: str) -> ipaddress.IPv6Interface:
    """Direccion IPv6 con prefijo obligatorio (addr/n), normalizada."""
    if "/" not in text:
        raise ValueError(f"IPv6 address needs a /prefix: {text!r}")
    try:
        return ipaddress.IPv6Interface(text)
    except ValueError:
        raise ValueError(f"invalid IPv6 interface: {text!r}") from None


def _validate_ipv6_address(text: str) -> ipaddress.IPv6Address:
    try:
        return ipaddress.IPv6Address(text)
    except ValueError:
        raise ValueError(f"invalid IPv6 address: {text!r}") from None


@dataclass(frozen=True, slots=True)
class ConnectionStaticIpv6:
    runner: CommandRunner
    connection: str
    address: str
    gateway: str | None = None

    def __post_init__(self) -> None:
        validate_connection_name(self.connection)
        _validate_ipv6_interface(self.address)
        if self.gateway is not None:
            _validate_ipv6_address(self.gateway)

    def describe(self) -> str:
        via = f" via {self.gateway}" if self.gateway is not None else ""
        return f"{self.connection} has static IPv6 {self.address}{via}"

    def run(self) -> CheckResult:
        props = _query_profile(self.runner, self.connection, _FIELDS_V6)
        if isinstance(props, CheckResult):
            return props
        method = props["ipv6.method"]
        if method != "manual":
            return CheckResult(False, f"ipv6.method is {_shown(method)}, expected manual")
        wanted = _validate_ipv6_interface(self.address)
        try:
            actual = [ipaddress.IPv6Interface(a) for a in _split_values(props["ipv6.addresses"])]
        except ValueError:
            return _unexpected(self.connection)
        if wanted not in actual:
            shown = ", ".join(str(a) for a in actual) or "(none)"
            return CheckResult(False, f"address {wanted} not configured (addresses: {shown})")
        if self.gateway is not None:
            expected_gw = _validate_ipv6_address(self.gateway)
            raw_gw = props["ipv6.gateway"].strip()
            try:
                actual_gw = ipaddress.IPv6Address(raw_gw) if raw_gw else None
            except ValueError:
                return _unexpected(self.connection)
            if actual_gw != expected_gw:
                shown_gw = str(actual_gw) if actual_gw is not None else "(none)"
                return CheckResult(False, f"gateway is {shown_gw}, expected {expected_gw}")
        return CheckResult(True, f"'{self.connection}' has static IPv6 {wanted}")


@dataclass(frozen=True, slots=True)
class ConnectionHasDns:
    runner: CommandRunner
    connection: str
    servers: tuple[str, ...]

    def __post_init__(self) -> None:
        validate_connection_name(self.connection)
        if not self.servers:
            raise ValueError("at least one DNS server is required")
        for server in self.servers:
            validate_ipv4_address(server)

    def describe(self) -> str:
        return f"{self.connection} uses DNS {', '.join(self.servers)}"

    def run(self) -> CheckResult:
        props = _query_profile(self.runner, self.connection)
        if isinstance(props, CheckResult):
            return props
        try:
            actual = {ipaddress.IPv4Address(s) for s in _split_values(props["ipv4.dns"])}
        except ValueError:
            return _unexpected(self.connection)
        missing = [s for s in self.servers if validate_ipv4_address(s) not in actual]
        if missing:
            return CheckResult(False, f"DNS servers missing: {', '.join(missing)}")
        return CheckResult(True, f"'{self.connection}' uses DNS {', '.join(self.servers)}")


@dataclass(frozen=True, slots=True)
class ConnectionAutoconnect:
    runner: CommandRunner
    connection: str

    def __post_init__(self) -> None:
        validate_connection_name(self.connection)

    def describe(self) -> str:
        return f"{self.connection} connects automatically at boot"

    def run(self) -> CheckResult:
        props = _query_profile(self.runner, self.connection)
        if isinstance(props, CheckResult):
            return props
        value = props["connection.autoconnect"]
        if value != "yes":
            return CheckResult(False, f"autoconnect is {_shown(value)}, expected yes")
        return CheckResult(True, f"'{self.connection}' connects automatically at boot")


def _query_hostname(
    runner: CommandRunner, argv: list[str], what: str, tool: str
) -> str | CheckResult:
    result = runner.run(argv)
    if not result.ok:
        return _query_failed(f"{what} hostname", result)
    lines = result.stdout.splitlines()
    if len(lines) > 1:
        return CheckResult(False, f"unexpected {tool} output for {what} hostname")
    return lines[0].strip() if lines else ""


def _normalize(name: str) -> str:
    return name.removesuffix(".").lower()


@dataclass(frozen=True, slots=True)
class HostnameIs:
    runner: CommandRunner
    name: str

    def __post_init__(self) -> None:
        validate_hostname(self.name)

    def describe(self) -> str:
        return f"hostname is {self.name}"

    def run(self) -> CheckResult:
        # El estatico va primero: si falla, no se consulta el runtime
        static = _query_hostname(
            self.runner, ["hostnamectl", "hostname", "--static"], "static", "hostnamectl"
        )
        if isinstance(static, CheckResult):
            return static
        runtime = _query_hostname(self.runner, ["hostname"], "running", "hostname")
        if isinstance(runtime, CheckResult):
            return runtime
        wanted = _normalize(self.name)
        static_ok = _normalize(static) == wanted
        runtime_ok = _normalize(runtime) == wanted
        if static_ok and runtime_ok:
            return CheckResult(True, f"hostname is {self.name} (static and running)")
        if static_ok:
            return CheckResult(
                False,
                f"static hostname is set but the running hostname is {_shown(runtime)} "
                "(reboot or hostnamectl)",
            )
        if runtime_ok:
            return CheckResult(
                False,
                f"running hostname is set but static hostname is {_shown(static)} "
                "(not persistent; use hostnamectl hostname)",
            )
        return CheckResult(False, f"hostname is {_shown(static)}, expected {self.name}")

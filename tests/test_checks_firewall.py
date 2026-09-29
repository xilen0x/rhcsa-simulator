from __future__ import annotations

import pytest

from rhcsa_sim.checks.firewall import FirewallPortAllowed, FirewallServiceAllowed
from rhcsa_sim.models import Check
from rhcsa_sim.testing import FakeCommandRunner, make_result

SVC_PERM = ("firewall-cmd", "--permanent", "--zone=public", "--query-service=http")
SVC_RUN = ("firewall-cmd", "--zone=public", "--query-service=http")
PORT_PERM = ("firewall-cmd", "--permanent", "--zone=public", "--query-port=8080/tcp")
PORT_RUN = ("firewall-cmd", "--zone=public", "--query-port=8080/tcp")

SERVICE_ARGV = (SVC_PERM, SVC_RUN)
PORT_ARGV = (PORT_PERM, PORT_RUN)


def fake(perm: tuple[str, ...], run: tuple[str, ...], perm_rc: int, run_rc: int | None = None,
         stdout: str | None = None) -> FakeCommandRunner:  # fmt: skip
    """Fake con las dos consultas; run_rc None omite la consulta runtime."""

    def out(rc: int) -> str:
        if stdout is not None:
            return stdout
        return "yes\n" if rc == 0 else "no\n" if rc == 1 else ""

    responses = {perm: make_result(perm, returncode=perm_rc, stdout=out(perm_rc))}
    if run_rc is not None:
        responses[run] = make_result(run, returncode=run_rc, stdout=out(run_rc))
    return FakeCommandRunner(responses)


def service_check(runner: FakeCommandRunner) -> FirewallServiceAllowed:
    return FirewallServiceAllowed(runner, "public", "http")


def port_check(runner: FakeCommandRunner) -> FirewallPortAllowed:
    return FirewallPortAllowed(runner, "public", 8080, "tcp")


def test_checks_satisfy_protocol() -> None:
    runner = FakeCommandRunner({})
    checks: list[Check] = [service_check(runner), port_check(runner)]
    assert all(c.describe() for c in checks)


def test_describe() -> None:
    runner = FakeCommandRunner({})
    assert service_check(runner).describe() == (
        "service http is allowed in zone public (permanent and runtime)"
    )
    assert port_check(runner).describe() == (
        "port 8080/tcp is allowed in zone public (permanent and runtime)"
    )


def test_port_protocol_defaults_to_tcp() -> None:
    check = FirewallPortAllowed(FakeCommandRunner({}), "public", 8080)
    assert check.protocol == "tcp"


def test_port_udp_uses_protocol_in_query() -> None:
    perm = ("firewall-cmd", "--permanent", "--zone=dmz", "--query-port=53/udp")
    run = ("firewall-cmd", "--zone=dmz", "--query-port=53/udp")
    runner = fake(perm, run, 0, 0)
    assert FirewallPortAllowed(runner, "dmz", 53, "udp").run().passed
    assert runner.calls == [perm, run]


# --- resultados: los cuatro casos, servicio y puerto ---


@pytest.mark.parametrize("argv", [SERVICE_ARGV, PORT_ARGV], ids=["service", "port"])
def test_allowed_in_both_is_ok(argv: tuple[tuple[str, ...], tuple[str, ...]]) -> None:
    runner = fake(argv[0], argv[1], 0, 0)
    check = service_check(runner) if argv is SERVICE_ARGV else port_check(runner)
    result = check.run()
    assert result.passed
    assert result.detail == "allowed in permanent and runtime configuration"
    assert runner.calls == [argv[0], argv[1]]


@pytest.mark.parametrize("argv", [SERVICE_ARGV, PORT_ARGV], ids=["service", "port"])
def test_permanent_only_is_ko(argv: tuple[tuple[str, ...], tuple[str, ...]]) -> None:
    runner = fake(argv[0], argv[1], 0, 1)
    check = service_check(runner) if argv is SERVICE_ARGV else port_check(runner)
    result = check.run()
    assert not result.passed
    assert result.detail == "allowed only in permanent configuration (run firewall-cmd --reload)"


@pytest.mark.parametrize("argv", [SERVICE_ARGV, PORT_ARGV], ids=["service", "port"])
def test_runtime_only_is_ko(argv: tuple[tuple[str, ...], tuple[str, ...]]) -> None:
    runner = fake(argv[0], argv[1], 1, 0)
    check = service_check(runner) if argv is SERVICE_ARGV else port_check(runner)
    result = check.run()
    assert not result.passed
    assert result.detail == (
        "allowed only in runtime configuration (not persistent; use --permanent)"
    )


@pytest.mark.parametrize("argv", [SERVICE_ARGV, PORT_ARGV], ids=["service", "port"])
def test_neither_is_ko(argv: tuple[tuple[str, ...], tuple[str, ...]]) -> None:
    runner = fake(argv[0], argv[1], 1, 1)
    check = service_check(runner) if argv is SERVICE_ARGV else port_check(runner)
    result = check.run()
    assert not result.passed
    assert result.detail == "not allowed in zone 'public'"


@pytest.mark.parametrize("stdout", ["", "garbage\n", "\x1b[31mno\n"])
def test_return_code_decides_regardless_of_stdout(stdout: str) -> None:
    ok = fake(SVC_PERM, SVC_RUN, 0, 0, stdout=stdout)
    assert service_check(ok).run().passed
    ko = fake(SVC_PERM, SVC_RUN, 1, 1, stdout=stdout)
    assert service_check(ko).run().detail == "not allowed in zone 'public'"


# --- errores ---

ERROR_DETAILS = [
    (253, "firewalld queries require root (run with sudo)"),
    (252, "firewalld is not running"),
    (112, "zone 'public' does not exist"),
    (124, "cannot query firewalld (exit 124)"),
    (126, "cannot query firewalld (exit 126)"),
    (127, "cannot query firewalld (exit 127)"),
    (2, "cannot query firewalld (exit 2)"),
]


@pytest.mark.parametrize(("rc", "detail"), ERROR_DETAILS)
def test_service_permanent_error_skips_runtime(rc: int, detail: str) -> None:
    runner = fake(SVC_PERM, SVC_RUN, rc)
    result = service_check(runner).run()
    assert not result.passed and result.detail == detail
    assert runner.calls == [SVC_PERM]


@pytest.mark.parametrize(("rc", "detail"), ERROR_DETAILS)
def test_port_permanent_error_skips_runtime(rc: int, detail: str) -> None:
    runner = fake(PORT_PERM, PORT_RUN, rc)
    result = port_check(runner).run()
    assert not result.passed and result.detail == detail
    assert runner.calls == [PORT_PERM]


def test_service_unknown_is_ko() -> None:
    result = service_check(fake(SVC_PERM, SVC_RUN, 101)).run()
    assert not result.passed
    assert result.detail == "service 'http' is not a known firewalld service"


def test_port_invalid_is_ko() -> None:
    result = port_check(fake(PORT_PERM, PORT_RUN, 102)).run()
    assert not result.passed and result.detail == "invalid port"


@pytest.mark.parametrize(("rc", "detail"), ERROR_DETAILS)
def test_service_runtime_error_after_permanent_ok(rc: int, detail: str) -> None:
    runner = fake(SVC_PERM, SVC_RUN, 0, rc)
    result = service_check(runner).run()
    assert not result.passed and result.detail == detail
    assert runner.calls == [SVC_PERM, SVC_RUN]


@pytest.mark.parametrize(("rc", "detail"), ERROR_DETAILS)
def test_port_runtime_error_after_permanent_ok(rc: int, detail: str) -> None:
    runner = fake(PORT_PERM, PORT_RUN, 0, rc)
    result = port_check(runner).run()
    assert not result.passed and result.detail == detail


def test_runtime_error_after_permanent_no() -> None:
    result = service_check(fake(SVC_PERM, SVC_RUN, 1, 253)).run()
    assert not result.passed
    assert result.detail == "firewalld queries require root (run with sudo)"


# --- parametros invalidos ---


@pytest.mark.parametrize("zone", ["", "-public", "a b", "z;x", "z" * 18])
def test_invalid_zone(zone: str) -> None:
    runner = FakeCommandRunner({})
    with pytest.raises(ValueError):
        FirewallServiceAllowed(runner, zone, "http")
    with pytest.raises(ValueError):
        FirewallPortAllowed(runner, zone, 80)


@pytest.mark.parametrize("service", ["", "-http", "HTTP", "a b", "x;y"])
def test_invalid_service(service: str) -> None:
    with pytest.raises(ValueError):
        FirewallServiceAllowed(FakeCommandRunner({}), "public", service)


@pytest.mark.parametrize("port", [0, -1, 65536, True])
def test_invalid_port(port: int) -> None:
    with pytest.raises(ValueError):
        FirewallPortAllowed(FakeCommandRunner({}), "public", port)


@pytest.mark.parametrize("protocol", ["", "TCP", "icmp", "tcp\n"])
def test_invalid_protocol(protocol: str) -> None:
    with pytest.raises(ValueError):
        FirewallPortAllowed(FakeCommandRunner({}), "public", 80, protocol)

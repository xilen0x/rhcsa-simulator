from __future__ import annotations

import pytest

from rhcsa_sim.checks.network import (
    ConnectionAutoconnect,
    ConnectionHasDns,
    ConnectionStaticIpv4,
    ConnectionStaticIpv6,
    HostnameIs,
)
from rhcsa_sim.models import Check
from rhcsa_sim.testing import FakeCommandRunner, make_result

FIELDS = (
    "connection.id,connection.autoconnect,ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns"
)
SHOW = ("nmcli", "-t", "-f", FIELDS, "connection", "show", "id", "exam-static")
STATIC = ("hostnamectl", "hostname", "--static")
RUNTIME = ("hostname",)
NAME = "servera.lab.example.com"


def profile_out(
    method: str = "manual",
    addresses: str = "192.168.122.50/24",
    gateway: str = "192.168.122.1",
    dns: str = "192.168.122.1",
    autoconnect: str = "yes",
) -> str:
    return (
        "connection.id:exam-static\n"
        f"connection.autoconnect:{autoconnect}\n"
        f"ipv4.method:{method}\n"
        f"ipv4.addresses:{addresses}\n"
        f"ipv4.gateway:{gateway}\n"
        f"ipv4.dns:{dns}\n"
    )


def fake_profile(
    stdout: str, returncode: int = 0, stderr: str = ""
) -> FakeCommandRunner:
    result = make_result(SHOW, returncode=returncode, stdout=stdout, stderr=stderr)
    return FakeCommandRunner({SHOW: result})


def fake_hostname(static: str, runtime: str, static_rc: int = 0) -> FakeCommandRunner:
    return FakeCommandRunner(
        {
            STATIC: make_result(STATIC, returncode=static_rc, stdout=static),
            RUNTIME: make_result(RUNTIME, stdout=runtime),
        }
    )


def static_check(runner: FakeCommandRunner, gateway: str | None = "192.168.122.1") -> Check:
    return ConnectionStaticIpv4(runner, "exam-static", "192.168.122.50/24", gateway)


BAD_OUTPUTS = [
    "",
    "\n",
    "garbage\n",
    "connection.id exam-static\n",
    profile_out().replace("ipv4.method:manual\n", ""),
    profile_out().replace("ipv4.dns:192.168.122.1\n", ""),
    profile_out() + "ipv4.dns:8.8.8.8\n",
]


def all_checks(runner: FakeCommandRunner) -> list[Check]:
    return [
        static_check(runner),
        ConnectionHasDns(runner, "exam-static", ("192.168.122.1",)),
        ConnectionAutoconnect(runner, "exam-static"),
    ]


def test_checks_satisfy_protocol() -> None:
    runner = fake_profile(profile_out())
    checks: list[Check] = [*all_checks(runner), HostnameIs(runner, NAME)]
    assert all(c.describe() for c in checks)


def test_describe() -> None:
    runner = fake_profile(profile_out())
    assert static_check(runner).describe() == (
        "exam-static has static IPv4 192.168.122.50/24 via 192.168.122.1"
    )
    assert ConnectionStaticIpv4(runner, "exam-static", "192.168.122.50/24").describe() == (
        "exam-static has static IPv4 192.168.122.50/24"
    )
    assert ConnectionHasDns(runner, "exam-static", ("1.1.1.1", "8.8.8.8")).describe() == (
        "exam-static uses DNS 1.1.1.1, 8.8.8.8"
    )
    assert ConnectionAutoconnect(runner, "exam-static").describe() == (
        "exam-static connects automatically at boot"
    )
    assert HostnameIs(runner, NAME).describe() == f"hostname is {NAME}"


def test_all_profile_checks_ok() -> None:
    runner = fake_profile(profile_out())
    results = [c.run() for c in all_checks(runner)]
    assert all(r.passed for r in results)
    assert runner.calls == [SHOW] * 3


def test_static_ok_without_gateway_and_extra_addresses() -> None:
    runner = fake_profile(profile_out(addresses="10.0.0.5/8,192.168.122.50/24", gateway=""))
    assert static_check(runner, gateway=None).run().passed


def test_static_address_compared_as_interface() -> None:
    runner = fake_profile(profile_out(addresses="192.168.122.50/24"))
    check = ConnectionStaticIpv4(runner, "exam-static", "192.168.122.50/255.255.255.0")
    assert check.run().passed


def test_static_method_auto() -> None:
    result = static_check(fake_profile(profile_out(method="auto"))).run()
    assert not result.passed
    assert "ipv4.method is auto, expected manual" in result.detail


def test_static_address_missing() -> None:
    result = static_check(fake_profile(profile_out(addresses="10.0.0.5/8"))).run()
    assert not result.passed
    assert "192.168.122.50/24" in result.detail and "10.0.0.5/8" in result.detail
    result = static_check(fake_profile(profile_out(addresses=""))).run()
    assert not result.passed and "(none)" in result.detail


def test_static_address_with_other_prefix_fails() -> None:
    result = static_check(fake_profile(profile_out(addresses="192.168.122.50/16"))).run()
    assert not result.passed and "192.168.122.50/16" in result.detail


def test_static_gateway_mismatch_and_empty() -> None:
    result = static_check(fake_profile(profile_out(gateway="192.168.122.2"))).run()
    assert not result.passed
    assert "gateway is 192.168.122.2, expected 192.168.122.1" in result.detail
    result = static_check(fake_profile(profile_out(gateway=""))).run()
    assert not result.passed
    assert "gateway is (none), expected 192.168.122.1" in result.detail


def test_dns_multi_values_order_insensitive() -> None:
    runner = fake_profile(profile_out(dns="1.1.1.1,8.8.8.8"))
    assert ConnectionHasDns(runner, "exam-static", ("8.8.8.8", "1.1.1.1")).run().passed


def test_dns_missing_names_missing_servers() -> None:
    runner = fake_profile(profile_out(dns="1.1.1.1"))
    result = ConnectionHasDns(runner, "exam-static", ("1.1.1.1", "8.8.8.8", "9.9.9.9")).run()
    assert not result.passed
    assert "8.8.8.8" in result.detail and "9.9.9.9" in result.detail
    assert "missing" in result.detail


def test_dns_empty() -> None:
    runner = fake_profile(profile_out(dns=""))
    result = ConnectionHasDns(runner, "exam-static", ("1.1.1.1",)).run()
    assert not result.passed and "1.1.1.1" in result.detail


def test_autoconnect_ok_and_ko() -> None:
    assert ConnectionAutoconnect(fake_profile(profile_out()), "exam-static").run().passed
    result = ConnectionAutoconnect(
        fake_profile(profile_out(autoconnect="no")), "exam-static"
    ).run()
    assert not result.passed and "autoconnect is no" in result.detail


def test_escaped_values_are_unescaped() -> None:
    out = profile_out().replace("connection.id:exam-static", r"connection.id:a\:b\\c")
    runner = fake_profile(out)
    assert all(r.passed for r in (c.run() for c in all_checks(runner)))


def test_value_split_on_first_colon_only() -> None:
    out = profile_out(gateway="192.168.122.1") + "extra:x:y\n"
    assert static_check(fake_profile(out)).run().passed


def test_unknown_profile() -> None:
    runner = fake_profile("", 10, "Error: exam-static - no such connection profile.\n")
    for check in all_checks(runner):
        result = check.run()
        assert not result.passed
        assert "connection profile 'exam-static' does not exist" in result.detail


@pytest.mark.parametrize("rc", [1, 124, 127])
def test_other_exit_codes(rc: int) -> None:
    runner = fake_profile("", rc)
    for check in all_checks(runner):
        result = check.run()
        assert not result.passed
        assert f"cannot query connection 'exam-static' (exit {rc})" in result.detail


def test_unparseable_values_are_unexpected_output() -> None:
    for out in (profile_out(addresses="not-an-ip"), profile_out(gateway="not-an-ip")):
        result = static_check(fake_profile(out)).run()
        assert not result.passed and "unexpected nmcli output" in result.detail
    runner = fake_profile(profile_out(dns="not-an-ip"))
    result = ConnectionHasDns(runner, "exam-static", ("1.1.1.1",)).run()
    assert not result.passed and "unexpected nmcli output" in result.detail


def test_rc_10_without_known_stderr_is_generic() -> None:
    result = ConnectionAutoconnect(fake_profile("", 10, "other\n"), "exam-static").run()
    assert not result.passed and "exit 10" in result.detail


@pytest.mark.parametrize("stdout", BAD_OUTPUTS)
def test_malformed_output(stdout: str) -> None:
    runner = fake_profile(stdout)
    for check in all_checks(runner):
        result = check.run()
        assert not result.passed
        assert "unexpected nmcli output" in result.detail


def test_hostname_both_match() -> None:
    runner = fake_hostname(f"{NAME}\n", f"{NAME}\n")
    result = HostnameIs(runner, NAME).run()
    assert result.passed
    assert runner.calls == [STATIC, RUNTIME]


def test_hostname_case_insensitive_and_trailing_dot() -> None:
    runner = fake_hostname("ServerA.Lab.Example.Com\n", f"{NAME}.\n")
    assert HostnameIs(runner, NAME).run().passed


def test_hostname_static_only() -> None:
    result = HostnameIs(fake_hostname(f"{NAME}\n", "localhost\n"), NAME).run()
    assert not result.passed
    assert result.detail == (
        "static hostname is set but the running hostname is localhost "
        "(reboot or hostnamectl)"
    )


def test_hostname_runtime_only() -> None:
    result = HostnameIs(fake_hostname("localhost.localdomain\n", f"{NAME}\n"), NAME).run()
    assert not result.passed
    assert result.detail == (
        "running hostname is set but static hostname is localhost.localdomain "
        "(not persistent; use hostnamectl hostname)"
    )


def test_hostname_neither() -> None:
    result = HostnameIs(fake_hostname("localhost.localdomain\n", "localhost\n"), NAME).run()
    assert not result.passed
    assert result.detail == f"hostname is localhost.localdomain, expected {NAME}"


def test_hostname_static_query_failure_stops() -> None:
    runner = fake_hostname("", "", static_rc=127)
    result = HostnameIs(runner, NAME).run()
    assert not result.passed and "cannot query static hostname (exit 127)" in result.detail
    assert runner.calls == [STATIC]


def test_hostname_runtime_query_failure() -> None:
    runner = FakeCommandRunner(
        {
            STATIC: make_result(STATIC, stdout=f"{NAME}\n"),
            RUNTIME: make_result(RUNTIME, returncode=124),
        }
    )
    result = HostnameIs(runner, NAME).run()
    assert not result.passed and "cannot query running hostname (exit 124)" in result.detail


@pytest.mark.parametrize("stdout", ["a\nb\n"])
def test_hostname_unexpected_output(stdout: str) -> None:
    result = HostnameIs(fake_hostname(stdout, "x\n"), NAME).run()
    assert not result.passed and "unexpected hostnamectl output" in result.detail
    result = HostnameIs(fake_hostname("x\n", stdout), NAME).run()
    assert not result.passed and "unexpected hostname output" in result.detail


def test_hostname_unset_static_is_a_mismatch() -> None:
    result = HostnameIs(fake_hostname("\n", f"{NAME}\n"), NAME).run()
    assert not result.passed and "static hostname is (empty)" in result.detail


def test_invalid_parameters() -> None:
    runner = fake_profile(profile_out())
    for bad in ("", "-x", " x", "a\nb"):
        with pytest.raises(ValueError):
            ConnectionAutoconnect(runner, bad)
        with pytest.raises(ValueError):
            ConnectionHasDns(runner, bad, ("1.1.1.1",))
    for addr in ("192.168.122.50", "x/24", ""):
        with pytest.raises(ValueError):
            ConnectionStaticIpv4(runner, "exam-static", addr)
    with pytest.raises(ValueError):
        ConnectionStaticIpv4(runner, "exam-static", "192.168.122.50/24", "300.1.1.1")
    with pytest.raises(ValueError):
        ConnectionStaticIpv4(runner, "exam-static", "192.168.122.50/24", "")
    with pytest.raises(ValueError):
        ConnectionHasDns(runner, "exam-static", ())
    with pytest.raises(ValueError):
        ConnectionHasDns(runner, "exam-static", ("nope",))
    for host in ("", "Servera", "a..b", "-a"):
        with pytest.raises(ValueError):
            HostnameIs(runner, host)


# --- IPv6 ---
# Los ':' de los valores van escapados como '\:' (regla de nmcli -t; fixture derivado
# de esa regla, no observado: la VM de pruebas no tiene IPv6 manual).
FIELDS6 = "connection.id,ipv6.method,ipv6.addresses,ipv6.gateway"
SHOW6 = ("nmcli", "-t", "-f", FIELDS6, "connection", "show", "id", "exam-static")
ADDR6 = "2001:db8:10::50/64"
GW6 = "2001:db8:10::1"


def esc6(text: str) -> str:
    return text.replace(":", "\\:")


def profile6_out(
    method: str = "manual", addresses: str = esc6(ADDR6), gateway: str = esc6(GW6)
) -> str:
    return (
        "connection.id:exam-static\n"
        f"ipv6.method:{method}\n"
        f"ipv6.addresses:{addresses}\n"
        f"ipv6.gateway:{gateway}\n"
    )


def fake6(stdout: str, returncode: int = 0, stderr: str = "") -> FakeCommandRunner:
    return FakeCommandRunner(
        {SHOW6: make_result(SHOW6, returncode=returncode, stdout=stdout, stderr=stderr)}
    )


def test_ipv6_passes_with_escaped_colons() -> None:
    check = ConnectionStaticIpv6(fake6(profile6_out()), "exam-static", ADDR6, GW6)
    assert check.run().passed
    assert check.describe() == f"exam-static has static IPv6 {ADDR6} via {GW6}"


def test_ipv6_matches_compressed_and_expanded_forms() -> None:
    out = profile6_out(addresses=esc6("2001:0db8:0010:0000:0000:0000:0000:0050/64"))
    assert ConnectionStaticIpv6(fake6(out), "exam-static", ADDR6).run().passed


def test_ipv6_accepts_several_addresses_and_no_gateway_check() -> None:
    out = profile6_out(addresses=esc6(f"fd00::5/64, {ADDR6}"), gateway="")
    assert ConnectionStaticIpv6(fake6(out), "exam-static", ADDR6).run().passed


@pytest.mark.parametrize(
    ("out", "text"),
    [
        (profile6_out(method="auto"), "ipv6.method is auto, expected manual"),
        (profile6_out(addresses=""), "not configured"),
        (profile6_out(addresses=esc6("2001:db8:10::51/64")), "not configured"),
        (profile6_out(addresses=esc6("2001:db8:10::50/48")), "not configured"),
        (profile6_out(gateway=""), "gateway is (none)"),
        (profile6_out(gateway=esc6("2001:db8:10::2")), "gateway is 2001:db8:10::2"),
        (profile6_out(addresses="nonsense"), "unexpected nmcli output"),
        (profile6_out().replace("ipv6.method:manual\n", ""), "unexpected nmcli output"),
    ],
)
def test_ipv6_failures(out: str, text: str) -> None:
    result = ConnectionStaticIpv6(fake6(out), "exam-static", ADDR6, GW6).run()
    assert not result.passed and text in result.detail


def test_ipv6_missing_profile_and_query_failure() -> None:
    runner = fake6("", 10, "Error: no such connection profile.\n")
    result = ConnectionStaticIpv6(runner, "exam-static", ADDR6).run()
    assert not result.passed and "does not exist" in result.detail
    result = ConnectionStaticIpv6(fake6("", 1), "exam-static", ADDR6).run()
    assert not result.passed and "exit 1" in result.detail


@pytest.mark.parametrize("addr", ["2001:db8::50", "2001:db8::50/129", "192.168.1.1/24", "", "zz::1/64"])
def test_ipv6_rejects_invalid_address(addr: str) -> None:
    with pytest.raises(ValueError):
        ConnectionStaticIpv6(FakeCommandRunner({}), "exam-static", addr)


@pytest.mark.parametrize("gw", ["", "192.168.1.1", "2001:db8::1/64", "zz"])
def test_ipv6_rejects_invalid_gateway(gw: str) -> None:
    with pytest.raises(ValueError):
        ConnectionStaticIpv6(FakeCommandRunner({}), "exam-static", ADDR6, gw)

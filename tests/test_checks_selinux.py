from __future__ import annotations

import pytest

from rhcsa_sim.checks.selinux import (
    PathHasSelinuxType,
    SelinuxBooleanIs,
    SelinuxMode,
    SelinuxPortType,
)
from rhcsa_sim.models import Check
from rhcsa_sim.runner import CommandResult
from rhcsa_sim.testing import FakeCommandRunner, make_result

SESTATUS = ("sestatus",)
STAT = ("stat", "-c", "%C", "--", "/srv/web")
RULE = ("matchpathcon", "-n", "--", "/srv/web")
GETSEBOOL = ("getsebool", "httpd_can_network_connect")
SEMANAGE_BOOL = ("semanage", "boolean", "-l")
SEMANAGE_PORT = ("semanage", "port", "-l")
SEMANAGE_ROOT_ERR = "ValueError: SELinux policy is not managed or store cannot be accessed.\n"


def sestatus_out(status: str = "enabled", current: str | None = "enforcing",
                 config: str | None = "enforcing") -> str:  # fmt: skip
    lines = [f"SELinux status:                 {status}"]
    if current is not None:
        lines.append("SELinuxfs mount:                /sys/fs/selinux")
        lines.append(f"Current mode:                   {current}")
    if config is not None:
        lines.append(f"Mode from config file:          {config}")
    return "\n".join(lines) + "\n"


def mode_runner(stdout: str, rc: int = 0) -> FakeCommandRunner:
    return FakeCommandRunner({SESTATUS: make_result(SESTATUS, returncode=rc, stdout=stdout)})


def context(selinux_type: str) -> str:
    return f"system_u:object_r:{selinux_type}:s0\n"


def path_runner(rule: str, actual: str, rule_rc: int = 0, stat_rc: int = 0) -> FakeCommandRunner:
    return FakeCommandRunner(
        {
            RULE: make_result(RULE, returncode=rule_rc, stdout=rule),
            STAT: make_result(STAT, returncode=stat_rc, stdout=actual),
        }
    )


def path_check(runner: FakeCommandRunner) -> PathHasSelinuxType:
    return PathHasSelinuxType(runner, "/srv/web", "httpd_sys_content_t")


def test_checks_satisfy_protocol() -> None:
    runner = FakeCommandRunner({})
    checks: list[Check] = [SelinuxMode(runner), path_check(runner)]
    assert all(c.describe() for c in checks)


def test_describe() -> None:
    runner = FakeCommandRunner({})
    assert SelinuxMode(runner, "permissive").describe() == (
        "SELinux is permissive (runtime and config file)"
    )
    assert path_check(runner).describe() == (
        "/srv/web has SELinux type httpd_sys_content_t (actual and default rule)"
    )


def test_mode_defaults_to_enforcing() -> None:
    assert SelinuxMode(FakeCommandRunner({})).mode == "enforcing"


# --- SelinuxMode ---


def test_mode_both_match_is_ok() -> None:
    runner = mode_runner(sestatus_out())
    result = SelinuxMode(runner, "enforcing").run()
    assert result.passed and result.detail == "SELinux is enforcing (runtime and config file)"
    assert runner.calls == [SESTATUS]


def test_mode_permissive_expected_ok() -> None:
    runner = mode_runner(sestatus_out(current="permissive", config="permissive"))
    assert SelinuxMode(runner, "permissive").run().passed


def test_mode_runtime_only_is_ko() -> None:
    runner = mode_runner(sestatus_out(current="enforcing", config="permissive"))
    result = SelinuxMode(runner, "enforcing").run()
    assert not result.passed
    assert result.detail == (
        "current mode is enforcing but config file has permissive (edit /etc/selinux/config)"
    )


def test_mode_config_only_is_ko() -> None:
    runner = mode_runner(sestatus_out(current="permissive", config="enforcing"))
    result = SelinuxMode(runner, "enforcing").run()
    assert not result.passed
    assert result.detail == (
        "config file has enforcing but current mode is permissive "
        "(run setenforce or reboot)"
    )


def test_mode_neither_is_ko() -> None:
    runner = mode_runner(sestatus_out(current="permissive", config="permissive"))
    result = SelinuxMode(runner, "enforcing").run()
    assert not result.passed
    assert result.detail == (
        "current mode is permissive, config file has permissive, expected enforcing"
    )


def test_mode_disabled_is_ko() -> None:
    runner = mode_runner(sestatus_out(status="disabled", current=None, config=None))
    result = SelinuxMode(runner).run()
    assert not result.passed and result.detail == "SELinux is disabled"


@pytest.mark.parametrize("rc", [1, 124, 126, 127])
def test_mode_command_error(rc: int) -> None:
    result = SelinuxMode(mode_runner("", rc)).run()
    assert not result.passed
    assert result.detail == f"cannot query SELinux status (exit {rc})"


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "garbage\n",
        "SELinux status:                 enabled\n",
        sestatus_out(current=None),
        sestatus_out(config=None),
        sestatus_out(current=""),
        "Current mode: enforcing\nMode from config file: enforcing\n",
    ],
)
def test_mode_unexpected_output(stdout: str) -> None:
    result = SelinuxMode(mode_runner(stdout)).run()
    assert not result.passed and result.detail == "unexpected sestatus output"


@pytest.mark.parametrize("mode", ["", "Enforcing", "disabled", "on"])
def test_mode_invalid(mode: str) -> None:
    with pytest.raises(ValueError):
        SelinuxMode(FakeCommandRunner({}), mode)


# --- PathHasSelinuxType ---


def test_path_both_ok() -> None:
    runner = path_runner(context("httpd_sys_content_t"), context("httpd_sys_content_t"))
    result = path_check(runner).run()
    assert result.passed and result.detail == "labeled httpd_sys_content_t (matches default rule)"
    assert runner.calls == [RULE, STAT]


def test_path_actual_ok_rule_differs_is_ko() -> None:
    runner = path_runner(context("default_t"), context("httpd_sys_content_t"))
    result = path_check(runner).run()
    assert not result.passed
    assert result.detail == (
        "labeled httpd_sys_content_t but the default rule is default_t "
        "(not persistent; add a semanage fcontext rule)"
    )


def test_path_rule_ok_actual_differs_is_ko() -> None:
    runner = path_runner(context("httpd_sys_content_t"), context("unlabeled_t"))
    result = path_check(runner).run()
    assert not result.passed
    assert result.detail == (
        "default rule is httpd_sys_content_t but file is labeled unlabeled_t (run restorecon)"
    )


def test_path_neither_is_ko() -> None:
    runner = path_runner(context("default_t"), context("unlabeled_t"))
    result = path_check(runner).run()
    assert not result.passed
    assert result.detail == (
        "labeled unlabeled_t and default rule is default_t, expected httpd_sys_content_t"
    )


def test_path_stat_failure_is_ko() -> None:
    runner = path_runner(context("httpd_sys_content_t"), "", stat_rc=1)
    result = path_check(runner).run()
    assert not result.passed and result.detail == "cannot stat '/srv/web'"


@pytest.mark.parametrize("rc", [124, 126, 127])
def test_path_stat_other_error(rc: int) -> None:
    runner = path_runner(context("httpd_sys_content_t"), "", stat_rc=rc)
    result = path_check(runner).run()
    assert not result.passed and result.detail == f"cannot query file context (exit {rc})"


@pytest.mark.parametrize("rc", [1, 124, 127])
def test_path_rule_error_skips_stat(rc: int) -> None:
    runner = path_runner("", "", rule_rc=rc)
    result = path_check(runner).run()
    assert not result.passed
    assert result.detail == f"cannot query default context (exit {rc})"
    assert runner.calls == [RULE]


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "garbage\n",
        "system_u:object_r:httpd_sys_content_t\n",
        "system_u:object_r:Bad-Type:s0\n",
        "system_u:object_r:notatype:s0\n",
        "system_u:object_r:a_t:s0\nsystem_u:object_r:b_t:s0\n",
        "(null)\n",
    ],
)
def test_path_unexpected_output(stdout: str) -> None:
    good = context("httpd_sys_content_t")
    result = path_check(path_runner(stdout, good)).run()
    assert not result.passed and result.detail == "unexpected matchpathcon output"
    result = path_check(path_runner(good, stdout)).run()
    assert not result.passed and result.detail == "unexpected stat output"


def test_path_context_with_mcs_categories() -> None:
    full = "system_u:object_r:httpd_sys_content_t:s0:c0.c1023\n"
    assert path_check(path_runner(full, full)).run().passed


@pytest.mark.parametrize("path", ["", "srv/web", "/srv\nweb", "/srv\x00web"])
def test_path_invalid_path(path: str) -> None:
    with pytest.raises(ValueError):
        PathHasSelinuxType(FakeCommandRunner({}), path, "httpd_sys_content_t")


@pytest.mark.parametrize("selinux_type", ["", "httpd", "Httpd_t", "a b_t"])
def test_path_invalid_type(selinux_type: str) -> None:
    with pytest.raises(ValueError):
        PathHasSelinuxType(FakeCommandRunner({}), "/srv/web", selinux_type)


# --- SelinuxBooleanIs ---

BOOL_HEADER = "SELinux boolean                State  Default Description\n\n"


def bool_line(name: str, current: str, default: str) -> str:
    return f"{name:<30} ({current:<4},  {default:<4})  Allow httpd to can network connect\n"


def bool_runner(runtime: str | None, persistent: str | None = None, *, sebool_rc: int = 0,
                sebool_err: str = "", semanage_rc: int = 0,
                semanage_out: str | None = None) -> FakeCommandRunner:  # fmt: skip
    """Fake de getsebool y semanage boolean -l; persistent None omite semanage."""
    out = "" if runtime is None else f"httpd_can_network_connect --> {runtime}\n"
    responses: dict[tuple[str, ...], CommandResult] = {
        GETSEBOOL: make_result(GETSEBOOL, returncode=sebool_rc, stdout=out, stderr=sebool_err)
    }
    if persistent is not None or semanage_out is not None:
        listing = semanage_out
        if listing is None:
            listing = (
                BOOL_HEADER
                + bool_line("allow_ftpd_anon_write", "off", "off")
                + bool_line("httpd_can_network_connect", "on", persistent or "off")
            )
        err = SEMANAGE_ROOT_ERR if semanage_rc == 1 else ""
        responses[SEMANAGE_BOOL] = make_result(
            SEMANAGE_BOOL, returncode=semanage_rc, stdout=listing, stderr=err
        )
    return FakeCommandRunner(responses)


def bool_check(runner: FakeCommandRunner, enabled: bool = True) -> SelinuxBooleanIs:
    return SelinuxBooleanIs(runner, "httpd_can_network_connect", enabled)


def test_boolean_describe_and_default() -> None:
    runner = FakeCommandRunner({})
    assert SelinuxBooleanIs(runner, "httpd_can_network_connect").enabled is True
    assert bool_check(runner).describe() == (
        "SELinux boolean httpd_can_network_connect is on (runtime and persistent)"
    )
    assert bool_check(runner, False).describe() == (
        "SELinux boolean httpd_can_network_connect is off (runtime and persistent)"
    )


def test_boolean_satisfies_protocol() -> None:
    check: Check = bool_check(FakeCommandRunner({}))
    assert check.describe()


@pytest.mark.parametrize("enabled", [True, False])
def test_boolean_both_is_ok(enabled: bool) -> None:
    state = "on" if enabled else "off"
    runner = bool_runner(state, state)
    result = bool_check(runner, enabled).run()
    assert result.passed and result.detail == f"boolean is {state} (runtime and persistent)"
    assert runner.calls == [GETSEBOOL, SEMANAGE_BOOL]


def test_boolean_runtime_only_is_ko() -> None:
    result = bool_check(bool_runner("on", "off")).run()
    assert not result.passed
    assert result.detail == "set only at runtime (use setsebool -P)"


def test_boolean_persistent_only_is_ko() -> None:
    result = bool_check(bool_runner("off", "on")).run()
    assert not result.passed
    assert result.detail == (
        "set persistently but not active (run setsebool without -P or reboot)"
    )


def test_boolean_neither_is_ko() -> None:
    result = bool_check(bool_runner("off", "off")).run()
    assert not result.passed and result.detail == "boolean is off, expected on"
    result = bool_check(bool_runner("on", "on"), False).run()
    assert not result.passed and result.detail == "boolean is on, expected off"


def test_boolean_off_expected_runtime_only() -> None:
    result = bool_check(bool_runner("off", "on"), False).run()
    assert not result.passed
    assert result.detail == "set only at runtime (use setsebool -P)"


def test_boolean_unknown_is_ko_and_stops() -> None:
    runner = bool_runner(
        None, sebool_rc=255, sebool_err="Error getting active value for httpd_can_network_connect\n"
    )
    result = bool_check(runner).run()
    assert not result.passed
    assert result.detail == "boolean 'httpd_can_network_connect' does not exist"
    assert runner.calls == [GETSEBOOL]


@pytest.mark.parametrize("rc", [1, 124, 126, 127])
def test_boolean_runtime_error_stops(rc: int) -> None:
    runner = bool_runner(None, sebool_rc=rc)
    result = bool_check(runner).run()
    assert not result.passed
    assert result.detail == f"cannot query SELinux boolean (exit {rc})"
    assert runner.calls == [GETSEBOOL]


def test_boolean_semanage_needs_root() -> None:
    result = bool_check(bool_runner("on", semanage_rc=1, semanage_out="")).run()
    assert not result.passed
    assert result.detail == "semanage requires root (run with sudo)"


@pytest.mark.parametrize("rc", [2, 124, 127])
def test_boolean_semanage_other_error(rc: int) -> None:
    result = bool_check(bool_runner("on", semanage_rc=rc, semanage_out="")).run()
    assert not result.passed
    assert result.detail == f"cannot query SELinux booleans (exit {rc})"


@pytest.mark.parametrize("stdout", ["", "garbage\n", "no --> maybe\n", "other --> on\n"])
def test_boolean_runtime_unexpected_output(stdout: str) -> None:
    runner = FakeCommandRunner({GETSEBOOL: make_result(GETSEBOOL, stdout=stdout)})
    result = bool_check(runner).run()
    assert not result.passed and result.detail == "unexpected getsebool output"
    assert runner.calls == [GETSEBOOL]


@pytest.mark.parametrize(
    "listing",
    [
        "",
        BOOL_HEADER,
        BOOL_HEADER + bool_line("allow_ftpd_anon_write", "off", "off"),
        "httpd_can_network_connect      broken line\n",
        "httpd_can_network_connect      (on  ,  maybe)  desc\n",
        "httpd_can_network_connect_db   (on  ,  on)  desc\n",
    ],
)
def test_boolean_semanage_unexpected_output(listing: str) -> None:
    result = bool_check(bool_runner("on", semanage_out=listing)).run()
    assert not result.passed and result.detail == "unexpected semanage output"


def test_boolean_exact_name_match_only() -> None:
    listing = (
        BOOL_HEADER
        + bool_line("httpd_can_network_connect_db", "off", "off")
        + bool_line("httpd_can_network_connect", "on", "on")
    )
    assert bool_check(bool_runner("on", semanage_out=listing)).run().passed


@pytest.mark.parametrize("name", ["", "HTTPD", "a b", "-x", "a;b"])
def test_boolean_invalid_name(name: str) -> None:
    with pytest.raises(ValueError):
        SelinuxBooleanIs(FakeCommandRunner({}), name)


# --- SelinuxPortType ---

PORT_HEADER = "SELinux Port Type              Proto    Port Number\n\n"
PORT_LISTING = (
    PORT_HEADER
    + "http_cache_port_t              tcp      8080, 8118, 8123, 10001-10010\n"
    + "http_port_t                    tcp      80, 81, 443, 488, 8008, 8009, 8443, 9000\n"
    + "http_port_t                    udp      80\n"
    + "unreserved_port_t              tcp      61000-65535, 1024-32767\n"
)


def port_runner(listing: str, rc: int = 0, stderr: str = "") -> FakeCommandRunner:
    return FakeCommandRunner(
        {SEMANAGE_PORT: make_result(SEMANAGE_PORT, returncode=rc, stdout=listing, stderr=stderr)}
    )


def port_check(runner: FakeCommandRunner, port: int = 80, protocol: str = "tcp",
               selinux_type: str = "http_port_t") -> SelinuxPortType:  # fmt: skip
    return SelinuxPortType(runner, port, protocol, selinux_type)


def test_port_describe_and_satisfies_protocol() -> None:
    check: Check = port_check(FakeCommandRunner({}), 82)
    assert check.describe() == "port 82/tcp is labeled http_port_t"


@pytest.mark.parametrize(
    ("port", "protocol", "selinux_type"),
    [
        (80, "tcp", "http_port_t"),
        (9000, "tcp", "http_port_t"),
        (80, "udp", "http_port_t"),
        (30000, "tcp", "unreserved_port_t"),
        (1024, "tcp", "unreserved_port_t"),
        (32767, "tcp", "unreserved_port_t"),
        (61000, "tcp", "unreserved_port_t"),
        (65535, "tcp", "unreserved_port_t"),
        (10005, "tcp", "http_cache_port_t"),
    ],
)
def test_port_labeled_is_ok(port: int, protocol: str, selinux_type: str) -> None:
    runner = port_runner(PORT_LISTING)
    result = port_check(runner, port, protocol, selinux_type).run()
    assert result.passed
    assert result.detail == f"port {port}/{protocol} is labeled {selinux_type}"
    assert runner.calls == [SEMANAGE_PORT]


def test_port_not_labeled_mentions_current_type() -> None:
    result = port_check(port_runner(PORT_LISTING), 8080, "tcp", "http_port_t").run()
    assert not result.passed
    assert result.detail == (
        "port 8080/tcp is not labeled http_port_t (currently labeled http_cache_port_t)"
    )


def test_port_multiple_other_types_uses_first() -> None:
    listing = (
        "a_port_t                       tcp      82\n"
        "b_port_t                       tcp      82\n"
    )
    result = port_check(port_runner(listing), 82).run()
    assert result.detail == "port 82/tcp is not labeled http_port_t (currently labeled a_port_t)"


def test_port_unlabeled_is_ko() -> None:
    result = port_check(port_runner(PORT_LISTING), 82).run()
    assert not result.passed and result.detail == "port 82/tcp is not labeled http_port_t"


def test_port_protocol_is_respected() -> None:
    result = port_check(port_runner(PORT_LISTING), 443, "udp").run()
    assert not result.passed and result.detail == "port 443/udp is not labeled http_port_t"


def test_port_type_seen_only_under_other_protocol() -> None:
    result = port_check(port_runner(PORT_LISTING), 8443, "udp").run()
    assert not result.passed and result.detail == "port 8443/udp is not labeled http_port_t"


def test_port_header_is_ignored() -> None:
    listing = PORT_HEADER + "http_port_t                    tcp      82\n"
    assert port_check(port_runner(listing), 82).run().passed


def test_port_semanage_needs_root() -> None:
    result = port_check(port_runner("", 1, SEMANAGE_ROOT_ERR)).run()
    assert not result.passed and result.detail == "semanage requires root (run with sudo)"


@pytest.mark.parametrize("rc", [2, 124, 126, 127])
def test_port_other_error(rc: int) -> None:
    result = port_check(port_runner("", rc)).run()
    assert not result.passed and result.detail == f"cannot query SELinux ports (exit {rc})"


@pytest.mark.parametrize(
    "listing",
    [
        "",
        PORT_HEADER,
        "garbage\n",
        "http_port_t                    tcp      80, abc\n",
        "http_port_t                    tcp      80,\n",
        "http_port_t                    tcp      90-80\n",
        "http_port_t                    tcp      1-2-3\n",
        "http_port_t                    tcp      0\n",
        "http_port_t                    tcp      70000\n",
    ],
)
def test_port_unexpected_output(listing: str) -> None:
    result = port_check(port_runner(listing), 80).run()
    assert not result.passed and result.detail == "unexpected semanage output"


@pytest.mark.parametrize("port", [0, -1, 65536, True])
def test_port_invalid_port(port: int) -> None:
    with pytest.raises(ValueError):
        SelinuxPortType(FakeCommandRunner({}), port, "tcp", "http_port_t")


@pytest.mark.parametrize("protocol", ["", "TCP", "icmp"])
def test_port_invalid_protocol(protocol: str) -> None:
    with pytest.raises(ValueError):
        SelinuxPortType(FakeCommandRunner({}), 80, protocol, "http_port_t")


@pytest.mark.parametrize("selinux_type", ["", "http_port", "HTTP_t", "a b_t"])
def test_port_invalid_type(selinux_type: str) -> None:
    with pytest.raises(ValueError):
        SelinuxPortType(FakeCommandRunner({}), 80, "tcp", selinux_type)

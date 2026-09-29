from __future__ import annotations

import pytest

from rhcsa_sim.checks.selinux import PathHasSelinuxType, SelinuxMode
from rhcsa_sim.models import Check
from rhcsa_sim.testing import FakeCommandRunner, make_result

SESTATUS = ("sestatus",)
STAT = ("stat", "-c", "%C", "--", "/srv/web")
RULE = ("matchpathcon", "-n", "--", "/srv/web")


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

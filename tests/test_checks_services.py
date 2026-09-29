from __future__ import annotations

import pytest

from rhcsa_sim.checks.services import DefaultTarget, UnitActiveStateIs, UnitFileStateIs
from rhcsa_sim.models import Check
from rhcsa_sim.runner import CommandRunner
from rhcsa_sim.testing import FakeCommandRunner, make_result

SHOW = (
    "systemctl", "show", "--property=LoadState,ActiveState,UnitFileState", "--", "httpd.service",
)  # fmt: skip
GET_DEFAULT = ("systemctl", "get-default")


def show_out(load: str = "loaded", active: str = "active", file_state: str = "enabled") -> str:
    return f"LoadState={load}\nActiveState={active}\nUnitFileState={file_state}\n"


def fake_show(stdout: str, returncode: int = 0) -> FakeCommandRunner:
    return FakeCommandRunner({SHOW: make_result(SHOW, returncode=returncode, stdout=stdout)})


def fake_default(stdout: str, returncode: int = 0) -> FakeCommandRunner:
    result = make_result(GET_DEFAULT, returncode=returncode, stdout=stdout)
    return FakeCommandRunner({GET_DEFAULT: result})


BAD_SHOW_OUTPUTS = [
    "",
    "\n",
    "garbage\n",
    "LoadState=loaded\nActiveState=active\n",
    "LoadState=loaded\nUnitFileState=enabled\n",
    "ActiveState=active\nUnitFileState=enabled\n",
    "LoadState=loaded\nActiveState=active\nUnitFileState=enabled\nnope\n",
    "LoadState=loaded\nActiveState=active\nActiveState=failed\nUnitFileState=enabled\n",
]


def unit_checks(runner: CommandRunner) -> list[Check]:
    return [
        UnitFileStateIs(runner, "httpd.service", "enabled"),
        UnitActiveStateIs(runner, "httpd.service", "active"),
    ]


def test_checks_satisfy_protocol() -> None:
    runner = fake_show(show_out())
    checks: list[Check] = [*unit_checks(runner), DefaultTarget(runner, "multi-user.target")]
    assert all(c.describe() for c in checks)


def test_describe() -> None:
    runner = fake_show(show_out())
    assert UnitFileStateIs(runner, "httpd.service", "enabled").describe() == (
        "httpd.service is enabled"
    )
    assert UnitActiveStateIs(runner, "httpd.service", "active").describe() == (
        "httpd.service is active"
    )
    assert DefaultTarget(runner, "multi-user.target").describe() == (
        "default target is multi-user.target"
    )


# --- UnitFileStateIs ---


def test_unit_file_state_ok() -> None:
    assert UnitFileStateIs(fake_show(show_out()), "httpd.service", "enabled").run().passed


def test_unit_file_state_accepts_any_key_order() -> None:
    out = "UnitFileState=masked\nLoadState=masked\nActiveState=inactive\n"
    assert UnitFileStateIs(fake_show(out), "httpd.service", "masked").run().passed


def test_unit_file_state_mismatch_is_ko() -> None:
    check = UnitFileStateIs(fake_show(show_out(file_state="disabled")), "httpd.service", "enabled")
    result = check.run()
    assert not result.passed
    assert result.detail == "unit file state is disabled, expected enabled"


def test_unit_file_state_empty_value_is_shown() -> None:
    check = UnitFileStateIs(fake_show(show_out(file_state="")), "httpd.service", "enabled")
    assert "(empty)" in check.run().detail


def test_unit_file_state_not_found_is_ko() -> None:
    out = show_out(load="not-found", active="inactive", file_state="")
    result = UnitFileStateIs(fake_show(out), "httpd.service", "disabled").run()
    assert not result.passed
    assert result.detail == "unit 'httpd.service' does not exist"


@pytest.mark.parametrize("returncode", [1, 124, 126, 127])
def test_unit_file_state_failed_command_is_ko(returncode: int) -> None:
    check = UnitFileStateIs(fake_show("", returncode), "httpd.service", "enabled")
    result = check.run()
    assert not result.passed
    assert result.detail == f"cannot query unit 'httpd.service' (exit {returncode})"


@pytest.mark.parametrize("stdout", BAD_SHOW_OUTPUTS)
def test_unit_file_state_malformed_output_is_ko(stdout: str) -> None:
    result = UnitFileStateIs(fake_show(stdout), "httpd.service", "enabled").run()
    assert not result.passed and "unexpected systemctl output" in result.detail


@pytest.mark.parametrize("state", ["", "active", "ENABLED", "enabled\n", "linked"])
def test_unit_file_state_invalid_state(state: str) -> None:
    with pytest.raises(ValueError):
        UnitFileStateIs(fake_show(""), "httpd.service", state)


@pytest.mark.parametrize("unit", ["httpd", "-x.service", "a b.service", "x;y.service"])
def test_unit_file_state_invalid_unit(unit: str) -> None:
    with pytest.raises(ValueError):
        UnitFileStateIs(fake_show(""), unit, "enabled")


# --- UnitActiveStateIs ---


def test_active_state_ok() -> None:
    assert UnitActiveStateIs(fake_show(show_out()), "httpd.service", "active").run().passed
    out = show_out(active="failed")
    assert UnitActiveStateIs(fake_show(out), "httpd.service", "failed").run().passed


def test_active_state_mismatch_is_ko() -> None:
    check = UnitActiveStateIs(fake_show(show_out(active="inactive")), "httpd.service", "active")
    result = check.run()
    assert not result.passed
    assert result.detail == "active state is inactive, expected active"


def test_active_state_empty_value_is_shown() -> None:
    check = UnitActiveStateIs(fake_show(show_out(active="")), "httpd.service", "active")
    assert "(empty)" in check.run().detail


def test_active_state_not_found_is_ko() -> None:
    out = show_out(load="not-found", active="inactive", file_state="")
    result = UnitActiveStateIs(fake_show(out), "httpd.service", "inactive").run()
    assert not result.passed
    assert result.detail == "unit 'httpd.service' does not exist"


@pytest.mark.parametrize("returncode", [1, 124, 126, 127])
def test_active_state_failed_command_is_ko(returncode: int) -> None:
    check = UnitActiveStateIs(fake_show("", returncode), "httpd.service", "active")
    result = check.run()
    assert not result.passed
    assert result.detail == f"cannot query unit 'httpd.service' (exit {returncode})"


@pytest.mark.parametrize("stdout", BAD_SHOW_OUTPUTS)
def test_active_state_malformed_output_is_ko(stdout: str) -> None:
    result = UnitActiveStateIs(fake_show(stdout), "httpd.service", "active").run()
    assert not result.passed and "unexpected systemctl output" in result.detail


@pytest.mark.parametrize("state", ["", "enabled", "activating", "ACTIVE", "active\n"])
def test_active_state_invalid_state(state: str) -> None:
    with pytest.raises(ValueError):
        UnitActiveStateIs(fake_show(""), "httpd.service", state)


@pytest.mark.parametrize("unit", ["httpd", "-x.service", "a b.service", "x;y.service"])
def test_active_state_invalid_unit(unit: str) -> None:
    with pytest.raises(ValueError):
        UnitActiveStateIs(fake_show(""), unit, "active")


# --- DefaultTarget ---


def test_default_target_ok() -> None:
    check = DefaultTarget(fake_default("multi-user.target\n"), "multi-user.target")
    assert check.run().passed


def test_default_target_mismatch_is_ko() -> None:
    result = DefaultTarget(fake_default("graphical.target\n"), "multi-user.target").run()
    assert not result.passed
    assert result.detail == "default target is graphical.target, expected multi-user.target"


@pytest.mark.parametrize("returncode", [1, 124, 126, 127])
def test_default_target_failed_command_is_ko(returncode: int) -> None:
    result = DefaultTarget(fake_default("", returncode), "multi-user.target").run()
    assert not result.passed
    assert result.detail == f"cannot query default target (exit {returncode})"


@pytest.mark.parametrize("stdout", ["", "\n", "a.target\nb.target\n", "not a unit\n"])
def test_default_target_malformed_output_is_ko(stdout: str) -> None:
    result = DefaultTarget(fake_default(stdout), "multi-user.target").run()
    assert not result.passed and "unexpected systemctl output" in result.detail


@pytest.mark.parametrize("target", ["multi-user", "sshd.service", "-x.target", "a b.target", ""])
def test_default_target_invalid_target(target: str) -> None:
    with pytest.raises(ValueError):
        DefaultTarget(fake_default(""), target)

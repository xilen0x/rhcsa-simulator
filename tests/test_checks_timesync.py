from __future__ import annotations

import pytest

from rhcsa_sim.checks.services import TimerOnCalendar
from rhcsa_sim.checks.timesync import ChronySource
from rhcsa_sim.models import Check
from rhcsa_sim.testing import FakeCommandRunner, make_result

TIMERS = ("systemctl", "show", "--property=TimersCalendar", "--value", "--", "backup.timer")
CHRONY = ("cat", "--", "/etc/chrony.conf")
DAILY = "{ OnCalendar=*-*-* 00:00:00 ; next_elapse=Mon 2026-10-05 00:00:00 UTC }\n"
TWO = (
    "{ OnCalendar=*-*-* 00:00:00 ; next_elapse=Mon 2026-10-05 00:00:00 UTC }\n"
    "{ OnCalendar=Mon *-*-* 12:00:00 ; next_elapse=Mon 2026-10-05 12:00:00 UTC }\n"
)


def fake_timer(stdout: str, returncode: int = 0) -> FakeCommandRunner:
    return FakeCommandRunner({TIMERS: make_result(TIMERS, returncode=returncode, stdout=stdout)})


def fake_chrony(stdout: str, returncode: int = 0) -> FakeCommandRunner:
    return FakeCommandRunner({CHRONY: make_result(CHRONY, returncode=returncode, stdout=stdout)})


def timer(runner: FakeCommandRunner, expected: str = "*-*-* 00:00:00") -> TimerOnCalendar:
    return TimerOnCalendar(runner, "backup.timer", expected)


def test_checks_satisfy_protocol() -> None:
    checks: list[Check] = [timer(fake_timer(DAILY)), ChronySource(fake_chrony(""), "a.example.com")]
    assert all(c.describe() for c in checks)


def test_timer_passes_on_match() -> None:
    result = timer(fake_timer(DAILY)).run()
    assert result.passed and "backup.timer" in result.detail


def test_timer_passes_when_any_group_matches() -> None:
    assert timer(fake_timer(TWO), "Mon *-*-* 12:00:00").run().passed


def test_timer_mismatch_reports_found_expressions() -> None:
    result = timer(fake_timer(TWO), "hourly").run()
    assert not result.passed
    assert "*-*-* 00:00:00" in result.detail and "Mon *-*-* 12:00:00" in result.detail


@pytest.mark.parametrize("out", ["", "\n"])
def test_timer_without_calendar_fails(out: str) -> None:
    result = timer(fake_timer(out)).run()
    assert not result.passed
    assert "backup.timer has no OnCalendar trigger (unit missing or monotonic-only)" in result.detail


def test_timer_unparseable_output_fails() -> None:
    result = timer(fake_timer("garbage\n")).run()
    assert not result.passed and "unexpected systemctl output" in result.detail


def test_timer_command_failure() -> None:
    result = timer(fake_timer("", returncode=1)).run()
    assert not result.passed and "exit 1" in result.detail


@pytest.mark.parametrize("name", ["backup.service", "-x.timer", "backup", ""])
def test_timer_rejects_bad_name(name: str) -> None:
    with pytest.raises(ValueError):
        TimerOnCalendar(fake_timer(DAILY), name, "daily")


def test_timer_rejects_empty_expected() -> None:
    with pytest.raises(ValueError):
        timer(fake_timer(DAILY), "")


CONF = (
    "# server ignored.example.com\n\n"
    "server 192.0.2.1 iburst\n"
    "pool classroom.example.com iburst\n"
    "driftfile /var/lib/chrony/drift\n"
)


def test_chrony_pass_server_and_pool() -> None:
    assert ChronySource(fake_chrony(CONF), "192.0.2.1").run().passed
    assert ChronySource(fake_chrony(CONF), "classroom.example.com").run().passed


def test_chrony_ignores_comments() -> None:
    result = ChronySource(fake_chrony(CONF), "ignored.example.com").run()
    assert not result.passed


def test_chrony_mismatch_lists_sources() -> None:
    result = ChronySource(fake_chrony(CONF), "other.example.com").run()
    assert not result.passed
    assert "192.0.2.1" in result.detail and "classroom.example.com" in result.detail


def test_chrony_no_sources() -> None:
    result = ChronySource(fake_chrony("driftfile /x\n"), "a.example.com").run()
    assert not result.passed and "(none)" in result.detail


def test_chrony_prefix_host_not_matched() -> None:
    assert not ChronySource(fake_chrony("server a.example.com.evil\n"), "a.example.com").run().passed


def test_chrony_read_failure() -> None:
    result = ChronySource(fake_chrony("", returncode=1), "a.example.com").run()
    assert not result.passed and "exit 1" in result.detail


@pytest.mark.parametrize("host", ["", "-h", "a b", "a.example.com\n"])
def test_chrony_rejects_bad_host(host: str) -> None:
    with pytest.raises(ValueError):
        ChronySource(fake_chrony(""), host)

from __future__ import annotations

import pytest

from rhcsa_sim.checks._validation import (
    validate_package_name,
    validate_repo_id,
    validate_tuned_profile,
)
from rhcsa_sim.checks.maintenance import (
    CronEntryExists,
    PackageInstalled,
    RepoNotEnabled,
    TunedProfileIs,
)
from rhcsa_sim.models import Check
from rhcsa_sim.testing import FakeCommandRunner, make_result

REPOLIST = ("dnf", "repolist", "--all")
RPM_AT = ("rpm", "-q", "--", "at")
CRON_ALICE = ("crontab", "-l", "-u", "alice")
TUNED = ("tuned-adm", "active")

# salida real de `dnf repolist --all` (recortada)
REPOLIST_OUT = (
    "repo id                      repo name                                  status\n"
    "appstream                    AlmaLinux 10 - AppStream                   enabled\n"
    "baseos                       AlmaLinux 10 - BaseOS                      enabled\n"
    "exam-internal                Exam Internal Repository                   disabled\n"
    "extras                       AlmaLinux 10 - Extras                      enabled\n"
)
CRON_OUT = (
    "# comentario\n"
    "MAILTO=root\n"
    "\n"
    "0 1 * * * /usr/bin/true\n"
    "30 14 * * * /usr/bin/date\n"
)


def fake(
    args: tuple[str, ...], stdout: str = "", returncode: int = 0, stderr: str = ""
) -> FakeCommandRunner:
    return FakeCommandRunner(
        {args: make_result(args, returncode=returncode, stdout=stdout, stderr=stderr)}
    )


def test_checks_satisfy_protocol() -> None:
    runner = FakeCommandRunner({})
    checks: list[Check] = [
        RepoNotEnabled(runner, "exam-internal"),
        PackageInstalled(runner, "at"),
        CronEntryExists(runner, "alice", "30 14 * * *", "/usr/bin/date"),
        TunedProfileIs(runner, "virtual-guest"),
    ]
    assert all(c.describe() for c in checks)


def test_describe() -> None:
    runner = FakeCommandRunner({})
    assert RepoNotEnabled(runner, "exam-internal").describe() == "repository exam-internal is not enabled"
    assert PackageInstalled(runner, "at").describe() == "package at is installed"
    assert CronEntryExists(runner, "alice", "30  14 * * *", "/usr/bin/date").describe() == (
        "alice has cron entry '30 14 * * * /usr/bin/date'"
    )
    assert TunedProfileIs(runner, "virtual-guest").describe() == "tuned profile is virtual-guest"


def test_validators_accept_and_reject() -> None:
    assert validate_repo_id("exam-internal") == "exam-internal"
    assert validate_repo_id("rhel-10:baseos_1.x") == "rhel-10:baseos_1.x"
    assert validate_package_name("libstdc++-devel") == "libstdc++-devel"
    assert validate_tuned_profile("virtual-guest") == "virtual-guest"
    for bad in ("", "-x", "a b", "a/b", "a\n", "x" * 101):
        with pytest.raises(ValueError):
            validate_repo_id(bad)
    for bad in ("", "-x", "a b", "a:b", "a\n", "x" * 129):
        with pytest.raises(ValueError):
            validate_package_name(bad)
    for bad in ("", "-x", "_x", "Virtual", "a b", "a\n", "x" * 65):
        with pytest.raises(ValueError):
            validate_tuned_profile(bad)


def test_invalid_parameters_rejected() -> None:
    runner = FakeCommandRunner({})
    with pytest.raises(ValueError):
        RepoNotEnabled(runner, "-bad")
    with pytest.raises(ValueError):
        PackageInstalled(runner, "--all")
    with pytest.raises(ValueError):
        TunedProfileIs(runner, "Bad Profile")
    with pytest.raises(ValueError):
        CronEntryExists(runner, "Bad User", "30 14 * * *", "/usr/bin/date")
    for schedule in ("", "30 14 * *", "30 14 * * * *", "a b c d e", "@nothing", "30 14 * * *;"):
        with pytest.raises(ValueError):
            CronEntryExists(runner, "alice", schedule, "/usr/bin/date")
    for command in ("", "  ", "a\nb", "a\x00b"):
        with pytest.raises(ValueError):
            CronEntryExists(runner, "alice", "30 14 * * *", command)


def test_repo_disabled_ok() -> None:
    result = RepoNotEnabled(fake(REPOLIST, REPOLIST_OUT), "exam-internal").run()
    assert result.passed and "disabled" in result.detail


def test_repo_enabled_ko() -> None:
    result = RepoNotEnabled(fake(REPOLIST, REPOLIST_OUT), "extras").run()
    assert not result.passed and "enabled" in result.detail


def test_repo_absent_ok() -> None:
    result = RepoNotEnabled(fake(REPOLIST, REPOLIST_OUT), "gone").run()
    assert result.passed and "not present" in result.detail


def test_repo_id_is_matched_exactly() -> None:
    result = RepoNotEnabled(fake(REPOLIST, REPOLIST_OUT), "base").run()
    assert result.passed and "not present" in result.detail


def test_repo_command_failure_and_malformed() -> None:
    result = RepoNotEnabled(fake(REPOLIST, "", 1, "boom"), "extras").run()
    assert not result.passed and "cannot query" in result.detail and "exit 1" in result.detail
    result = RepoNotEnabled(fake(REPOLIST, "nothing useful\n"), "extras").run()
    assert not result.passed and "unexpected dnf output" in result.detail
    result = RepoNotEnabled(fake(REPOLIST, "repo id  repo name  status\nextras only\n"), "extras").run()
    assert not result.passed and "unexpected dnf output" in result.detail


def test_package_installed_ok() -> None:
    runner = fake(RPM_AT, "at-3.2.5-13.el10.x86_64\n")
    assert PackageInstalled(runner, "at").run().passed


def test_package_missing_ko() -> None:
    runner = fake(RPM_AT, "package at is not installed\n", 1)
    result = PackageInstalled(runner, "at").run()
    assert not result.passed and "not installed" in result.detail


def test_package_query_failure() -> None:
    result = PackageInstalled(fake(RPM_AT, "", 127), "at").run()
    assert not result.passed and "cannot query" in result.detail and "127" in result.detail
    result = PackageInstalled(fake(RPM_AT, "error: db open\n", 1), "at").run()
    assert not result.passed and "cannot query" in result.detail


def cron(
    stdout: str, returncode: int = 0, stderr: str = "", schedule: str = "30 14 * * *",
    command: str = "/usr/bin/date",
) -> CronEntryExists:
    return CronEntryExists(fake(CRON_ALICE, stdout, returncode, stderr), "alice", schedule, command)


def test_cron_ok() -> None:
    assert cron(CRON_OUT).run().passed


def test_cron_ok_with_whitespace_and_macro() -> None:
    assert cron("30   14 *\t* *   /usr/bin/date \n").run().passed
    assert cron("@daily /usr/bin/date\n", schedule="@daily").run().passed
    assert cron("30 14 * * * /usr/bin/echo  a   b\n", command="/usr/bin/echo a b").run().passed


def test_cron_ko_wrong_schedule_or_command() -> None:
    result = cron(CRON_OUT, schedule="0 2 * * *").run()
    assert not result.passed and "no cron entry" in result.detail
    result = cron(CRON_OUT, command="/usr/bin/id").run()
    assert not result.passed and "no cron entry" in result.detail
    assert not cron("30 14 * * * /usr/bin/date -u\n").run().passed
    assert not cron("# 30 14 * * * /usr/bin/date\n").run().passed
    assert not cron("MAILTO=30 14 * * * /usr/bin/date\n").run().passed
    assert not cron("@daily /usr/bin/date\n").run().passed


def test_cron_no_crontab() -> None:
    result = cron("", 1, "no crontab for alice\n").run()
    assert not result.passed and "user 'alice' has no crontab" in result.detail


def test_cron_permission_hint() -> None:
    result = cron("", 1, "must be privileged to use -u\n").run()
    assert not result.passed and "sudo" in result.detail
    result = cron("", 1, "crontab: Permission denied\n").run()
    assert not result.passed and "sudo" in result.detail


def test_cron_other_failure() -> None:
    result = cron("", 127).run()
    assert not result.passed and "cannot query" in result.detail and "127" in result.detail


def test_cron_malformed_lines_ignored() -> None:
    assert not cron("garbage\n30 14\n").run().passed


def test_tuned_ok_and_ko() -> None:
    out = "Current active profile: virtual-guest\n"
    assert TunedProfileIs(fake(TUNED, out), "virtual-guest").run().passed
    out = "Current active profile: throughput-performance\n"
    result = TunedProfileIs(fake(TUNED, out), "virtual-guest").run()
    assert not result.passed and "throughput-performance" in result.detail
    assert "virtual-guest" in result.detail


def test_tuned_no_profile() -> None:
    result = TunedProfileIs(fake(TUNED, "No current active profile.\n"), "virtual-guest").run()
    assert not result.passed and "no active tuned profile" in result.detail


def test_tuned_errors() -> None:
    err = "Cannot talk to Tuned daemon via DBus. Is Tuned daemon running?\n"
    result = TunedProfileIs(fake(TUNED, "", 1, err), "virtual-guest").run()
    assert not result.passed and "cannot query" in result.detail and "exit 1" in result.detail
    result = TunedProfileIs(fake(TUNED, "", 127), "virtual-guest").run()
    assert not result.passed and "cannot query" in result.detail
    result = TunedProfileIs(fake(TUNED, "hello\n"), "virtual-guest").run()
    assert not result.passed and "unexpected tuned-adm output" in result.detail
    result = TunedProfileIs(fake(TUNED, "Current active profile: Bad Name\n"), "virtual-guest").run()
    assert not result.passed and "unexpected tuned-adm output" in result.detail


def test_tuned_multiline_output_parses_only_profile_line() -> None:
    out = "Current active profile: virtual-guest\nPreset profile: balanced\n"
    assert TunedProfileIs(fake(TUNED, out), "virtual-guest").run().passed
    out = "Current active profile: virtual-guest\nCurrent post-loaded profile: my-post\n"
    assert TunedProfileIs(fake(TUNED, out), "virtual-guest").run().passed
    out = "Preset profile: balanced\nCurrent active profile: virtual-guest\n"
    assert TunedProfileIs(fake(TUNED, out), "virtual-guest").run().passed


def test_tuned_multiline_mismatch_reports_actual() -> None:
    out = "Current active profile: balanced\nCurrent post-loaded profile: virtual-guest\n"
    result = TunedProfileIs(fake(TUNED, out), "virtual-guest").run()
    assert not result.passed and "balanced" in result.detail


def test_tuned_daemon_down_fails_clearly() -> None:
    out = "No current active profile.\nService tuned: Not Running\n"
    result = TunedProfileIs(fake(TUNED, out), "virtual-guest").run()
    assert not result.passed and "no active tuned profile" in result.detail
    out = "Current active profile: virtual-guest\nService tuned: Not Running\n"
    result = TunedProfileIs(fake(TUNED, out), "virtual-guest").run()
    assert not result.passed and "not running" in result.detail


def test_tuned_duplicate_profile_lines_are_unexpected() -> None:
    out = "Current active profile: virtual-guest\nCurrent active profile: balanced\n"
    result = TunedProfileIs(fake(TUNED, out), "virtual-guest").run()
    assert not result.passed and "unexpected tuned-adm output" in result.detail

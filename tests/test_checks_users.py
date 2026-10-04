from __future__ import annotations

import pytest

from rhcsa_sim.checks.users import (
    GroupExists,
    LoginDefsValue,
    PasswordAging,
    UserExists,
    UserHasShell,
    UserHasUid,
    UserInGroup,
)
from rhcsa_sim.models import Check
from rhcsa_sim.testing import FakeCommandRunner, make_result

PASSWD = "alice:x:1234:1234:Alice:/home/alice:/bin/bash\n"
PASSWD_CMD = ("getent", "passwd", "alice")
GROUP_CMD = ("getent", "group", "devs")
ID_CMD = ("id", "-Gn", "--", "alice")


def user_runner(stdout: str = PASSWD, returncode: int = 0) -> FakeCommandRunner:
    return FakeCommandRunner(
        {PASSWD_CMD: make_result(PASSWD_CMD, returncode=returncode, stdout=stdout)}
    )


def test_checks_satisfy_protocol() -> None:
    check: Check = UserExists(user_runner(), "alice")
    assert check.describe()


def test_user_exists_ok_and_ko() -> None:
    assert UserExists(user_runner(), "alice").run().passed
    assert not UserExists(user_runner("", 2), "alice").run().passed


def test_user_exists_rejects_malformed_output() -> None:
    assert not UserExists(user_runner("garbage\n"), "alice").run().passed


@pytest.mark.parametrize("name", ["", "-r", "Alice", "a b", "../x", "a;b"])
def test_invalid_names_are_rejected(name: str) -> None:
    with pytest.raises(ValueError):
        UserExists(user_runner(), name)


def test_uid_check() -> None:
    assert UserHasUid(user_runner(), "alice", 1234).run().passed
    assert not UserHasUid(user_runner(), "alice", 1000).run().passed
    assert not UserHasUid(user_runner("", 2), "alice", 1234).run().passed


def test_uid_rejects_negative() -> None:
    with pytest.raises(ValueError):
        UserHasUid(user_runner(), "alice", -1)


def test_shell_check() -> None:
    assert UserHasShell(user_runner(), "alice", "/bin/bash").run().passed
    assert not UserHasShell(user_runner(), "alice", "/sbin/nologin").run().passed


def test_shell_rejects_relative_path() -> None:
    with pytest.raises(ValueError):
        UserHasShell(user_runner(), "alice", "bash")


def test_user_in_group() -> None:
    def runner(stdout: str, rc: int = 0) -> FakeCommandRunner:
        return FakeCommandRunner({ID_CMD: make_result(ID_CMD, returncode=rc, stdout=stdout)})

    assert UserInGroup(runner("alice devs wheel\n"), "alice", "devs").run().passed
    assert not UserInGroup(runner("alice wheel\n"), "alice", "devs").run().passed
    assert not UserInGroup(runner("", 1), "alice", "devs").run().passed


def test_user_in_group_does_not_match_substrings() -> None:
    fake = FakeCommandRunner({ID_CMD: make_result(ID_CMD, stdout="alice devsops\n")})
    assert not UserInGroup(fake, "alice", "devs").run().passed


def test_group_exists_with_and_without_gid() -> None:
    fake = FakeCommandRunner({GROUP_CMD: make_result(GROUP_CMD, stdout="devs:x:5000:alice\n")})
    assert GroupExists(fake, "devs").run().passed
    assert GroupExists(fake, "devs", 5000).run().passed
    assert not GroupExists(fake, "devs", 6000).run().passed


def test_group_missing() -> None:
    fake = FakeCommandRunner({GROUP_CMD: make_result(GROUP_CMD, returncode=2)})
    assert not GroupExists(fake, "devs").run().passed


CHAGE_CMD = ("chage", "-l", "--", "alice")
CHAGE_OUT = (
    "Last password change\t\t\t\t\t: Oct 04, 2026\n"
    "Password expires\t\t\t\t\t: Jan 02, 2027\n"
    "Password inactive\t\t\t\t\t: never\n"
    "Account expires\t\t\t\t\t\t: never\n"
    "Minimum number of days between password change\t\t: 1\n"
    "Maximum number of days between password change\t\t: 90\n"
    "Number of days of warning before password expires\t: 7\n"
)


def chage_runner(
    stdout: str = CHAGE_OUT, returncode: int = 0, stderr: str = ""
) -> FakeCommandRunner:
    return FakeCommandRunner(
        {CHAGE_CMD: make_result(CHAGE_CMD, returncode=returncode, stdout=stdout, stderr=stderr)}
    )


def test_password_aging_ok() -> None:
    check = PasswordAging(chage_runner(), "alice", max_days=90, min_days=1, warn_days=7)
    assert check.run().passed
    assert "alice" in check.describe() and "90" in check.describe()


def test_password_aging_only_requested_fields_are_compared() -> None:
    assert PasswordAging(chage_runner(), "alice", warn_days=7).run().passed


def test_password_aging_mismatch_names_field() -> None:
    result = PasswordAging(chage_runner(), "alice", max_days=60).run()
    assert not result.passed
    assert "90" in result.detail and "60" in result.detail


def test_password_aging_reports_every_mismatch() -> None:
    result = PasswordAging(chage_runner(), "alice", max_days=60, warn_days=14).run()
    assert not result.passed
    assert "60" in result.detail and "14" in result.detail


def test_password_aging_requires_one_value_and_valid_input() -> None:
    with pytest.raises(ValueError):
        PasswordAging(chage_runner(), "alice")
    with pytest.raises(ValueError):
        PasswordAging(chage_runner(), "alice", max_days=-2)
    with pytest.raises(ValueError):
        PasswordAging(chage_runner(), "bad name", max_days=1)


def test_password_aging_permission_denied_shows_root_hint() -> None:
    runner = chage_runner("", 1, "chage: Permission denied.\n")
    result = PasswordAging(runner, "alice", max_days=90).run()
    assert not result.passed and "sudo" in result.detail


def test_password_aging_unknown_user() -> None:
    runner = chage_runner("", 1, "chage: user 'alice' does not exist in /etc/passwd\n")
    result = PasswordAging(runner, "alice", max_days=90).run()
    assert not result.passed and "user 'alice' does not exist" in result.detail


def test_password_aging_unparseable_output() -> None:
    assert not PasswordAging(chage_runner("garbage\n"), "alice", max_days=90).run().passed
    assert not PasswordAging(chage_runner("", 2), "alice", max_days=90).run().passed


LOGIN_DEFS_CMD = ("cat", "--", "/etc/login.defs")
LOGIN_DEFS = (
    "# comment\n\n"
    "PASS_MAX_DAYS\t99999\n"
    "PASS_MIN_DAYS\t0\n"
    "#PASS_WARN_AGE\t7\n"
    "PASS_MAX_DAYS   60\n"
)


def defs_runner(stdout: str = LOGIN_DEFS, returncode: int = 0) -> FakeCommandRunner:
    return FakeCommandRunner(
        {LOGIN_DEFS_CMD: make_result(LOGIN_DEFS_CMD, returncode=returncode, stdout=stdout)}
    )


def test_login_defs_last_assignment_wins() -> None:
    assert LoginDefsValue(defs_runner(), "PASS_MAX_DAYS", "60").run().passed
    result = LoginDefsValue(defs_runner(), "PASS_MAX_DAYS", "99999").run()
    assert not result.passed and "60" in result.detail


def test_login_defs_ignores_comments_and_missing_key() -> None:
    assert LoginDefsValue(defs_runner(), "PASS_MIN_DAYS", "0").run().passed
    result = LoginDefsValue(defs_runner(), "PASS_WARN_AGE", "7").run()
    assert not result.passed and "not set" in result.detail


def test_login_defs_unreadable_file() -> None:
    assert not LoginDefsValue(defs_runner("", 1), "PASS_MAX_DAYS", "60").run().passed


def test_login_defs_validates_input() -> None:
    for key in ("pass_max_days", "PASS MAX", "", "1ABC"):
        with pytest.raises(ValueError):
            LoginDefsValue(defs_runner(), key, "1")
    with pytest.raises(ValueError):
        LoginDefsValue(defs_runner(), "PASS_MAX_DAYS", "")

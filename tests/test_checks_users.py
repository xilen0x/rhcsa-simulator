from __future__ import annotations

import pytest

from rhcsa_sim.checks.users import (
    GroupExists,
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

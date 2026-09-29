from __future__ import annotations

import pytest

from rhcsa_sim.checks.acl import PathHasAclEntry
from rhcsa_sim.models import Check
from rhcsa_sim.testing import FakeCommandRunner, make_result

CMD = ("getfacl", "--omit-header", "--absolute-names", "--no-effective", "--", "/data")
ACL_OUT = """user::rwx
user:alice:rwx
group::r-x
group:devs:r--
mask::rwx
other::---
default:user::rwx
default:user:bob:r-x
default:mask::rwx
"""


def fake(stdout: str = ACL_OUT, returncode: int = 0, stderr: str = "") -> FakeCommandRunner:
    result = make_result(CMD, returncode=returncode, stdout=stdout, stderr=stderr)
    return FakeCommandRunner({CMD: result})


def test_check_satisfies_protocol() -> None:
    check: Check = PathHasAclEntry(fake(), "/data", "user:alice:rwx")
    assert check.describe()


@pytest.mark.parametrize(
    "entry", ["user:alice:rwx", "group:devs:r--", "mask::rwx", "other::---", "default:user:bob:r-x"]
)
def test_entry_present_is_ok(entry: str) -> None:
    assert PathHasAclEntry(fake(), "/data", entry).run().passed


def test_ignores_comments_blank_lines_and_surrounding_whitespace() -> None:
    stdout = "# file: data\n\n  user:alice:rwx  \n"
    assert PathHasAclEntry(fake(stdout), "/data", "user:alice:rwx").run().passed


def test_missing_entry_is_ko() -> None:
    result = PathHasAclEntry(fake(), "/data", "user:carol:rwx").run()
    assert not result.passed and "user:carol:rwx" in result.detail


def test_different_perms_is_ko() -> None:
    stdout = "user::rwx\nuser:alice:r-x\n"
    result = PathHasAclEntry(fake(stdout), "/data", "user:alice:rwx").run()
    assert not result.passed and "user:alice:rwx" in result.detail


def test_default_entry_is_not_confused_with_access_entry() -> None:
    stdout = "default:user:alice:rwx\n"
    assert not PathHasAclEntry(fake(stdout), "/data", "user:alice:rwx").run().passed
    stdout = "user:alice:rwx\n"
    assert not PathHasAclEntry(fake(stdout), "/data", "default:user:alice:rwx").run().passed


def test_entry_must_match_whole_line() -> None:
    stdout = "user:alice:rwx-extra\nxuser:alice:rwx\n"
    assert not PathHasAclEntry(fake(stdout), "/data", "user:alice:rwx").run().passed


def test_empty_output_is_ko() -> None:
    assert not PathHasAclEntry(fake(""), "/data", "user:alice:rwx").run().passed


def test_getfacl_not_installed_hints_package() -> None:
    result = PathHasAclEntry(fake("", 127), "/data", "user:alice:rwx").run()
    assert not result.passed
    assert result.detail == "getfacl not found (install package acl)"


@pytest.mark.parametrize("rc", [1, 2, 124, 126])
def test_other_failure_reports_exit_code(rc: int) -> None:
    result = PathHasAclEntry(fake("", rc, "boom"), "/data", "user:alice:rwx").run()
    assert not result.passed
    assert result.detail == f"cannot read ACL of '/data' (exit {rc})"


@pytest.mark.parametrize(
    ("path", "entry"),
    [
        ("data", "user:alice:rwx"),
        ("", "user:alice:rwx"),
        ("/d\na", "user:alice:rwx"),
        ("/data", "user:alice:rwz"),
        ("/data", "user:Alice:rwx"),
        ("/data", ""),
    ],
)
def test_invalid_parameters(path: str, entry: str) -> None:
    with pytest.raises(ValueError):
        PathHasAclEntry(fake(), path, entry)

from __future__ import annotations

import pytest

from rhcsa_sim.checks.files import FilesIdentical, PathHasMode, PathHasOwner
from rhcsa_sim.testing import FakeCommandRunner, make_result

PATH = "/srv/shared"
STAT_CMD = ("stat", "-c", "%a %U %G", "--", PATH)


def stat_runner(stdout: str, returncode: int = 0) -> FakeCommandRunner:
    return FakeCommandRunner(
        {STAT_CMD: make_result(STAT_CMD, returncode=returncode, stdout=stdout)}
    )


def test_mode_matches_with_and_without_leading_zero() -> None:
    assert PathHasMode(stat_runner("640 root root\n"), PATH, "0640").run().passed
    assert PathHasMode(stat_runner("640 root root\n"), PATH, "640").run().passed


def test_mode_supports_setgid() -> None:
    assert PathHasMode(stat_runner("2770 root devs\n"), PATH, "2770").run().passed


def test_mode_mismatch_and_missing_path() -> None:
    assert not PathHasMode(stat_runner("644 root root\n"), PATH, "640").run().passed
    assert not PathHasMode(stat_runner("", 1), PATH, "640").run().passed


def test_mode_rejects_malformed_stat_output() -> None:
    assert not PathHasMode(stat_runner("zzz root\n"), PATH, "640").run().passed


@pytest.mark.parametrize("mode", ["", "9", "12345", "rw-r--r--"])
def test_invalid_expected_mode_rejected(mode: str) -> None:
    with pytest.raises(ValueError):
        PathHasMode(stat_runner(""), PATH, mode)


@pytest.mark.parametrize("path", ["relative/path", "", "/a\nb"])
def test_invalid_path_rejected(path: str) -> None:
    with pytest.raises(ValueError):
        PathHasMode(stat_runner(""), path, "640")


def test_owner_only_and_owner_group() -> None:
    fake = stat_runner("2770 root devs\n")
    assert PathHasOwner(fake, PATH, "root").run().passed
    assert PathHasOwner(fake, PATH, "root", "devs").run().passed
    assert not PathHasOwner(fake, PATH, "alice").run().passed
    assert not PathHasOwner(fake, PATH, "root", "wheel").run().passed


def test_owner_missing_path() -> None:
    assert not PathHasOwner(stat_runner("", 1), PATH, "root").run().passed


SRC = "/etc/services"
COPY = "/root/services.bak"
CMP_CMD = ("cmp", "-s", "--", SRC, COPY)


def cmp_runner(returncode: int) -> FakeCommandRunner:
    return FakeCommandRunner({CMP_CMD: make_result(CMP_CMD, returncode=returncode)})


def test_files_identical_pass() -> None:
    result = FilesIdentical(cmp_runner(0), SRC, COPY).run()
    assert result.passed and "identical" in result.detail


def test_files_identical_differs() -> None:
    result = FilesIdentical(cmp_runner(1), SRC, COPY).run()
    assert not result.passed and f"content differs from {SRC}" in result.detail


def test_files_identical_missing_or_unreadable() -> None:
    for rc in (2, 127):
        result = FilesIdentical(cmp_runner(rc), SRC, COPY).run()
        assert not result.passed
        assert f"cannot compare: {COPY} missing or unreadable" in result.detail
        assert "sudo" in result.detail


def test_files_identical_describe_and_validation() -> None:
    assert FilesIdentical(cmp_runner(0), SRC, COPY).describe() == f"{COPY} is identical to {SRC}"
    with pytest.raises(ValueError):
        FilesIdentical(cmp_runner(0), "etc/services", COPY)
    with pytest.raises(ValueError):
        FilesIdentical(cmp_runner(0), SRC, "services.bak")
    with pytest.raises(ValueError):
        FilesIdentical(cmp_runner(0), SRC, SRC)

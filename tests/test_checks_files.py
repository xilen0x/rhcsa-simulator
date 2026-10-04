from __future__ import annotations

import pytest

from rhcsa_sim.checks.files import FilesIdentical, PathHasMode, PathHasOwner, UmaskConfigured
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


def test_files_identical_no_sudo_hint_outside_root() -> None:
    other = "/srv/services.bak"
    runner = FakeCommandRunner({("cmp", "-s", "--", SRC, other): make_result(
        ("cmp", "-s", "--", SRC, other), returncode=2
    )})
    result = FilesIdentical(runner, SRC, other).run()
    assert result.detail == f"cannot compare: {other} missing or unreadable"


def test_files_identical_describe_and_validation() -> None:
    assert FilesIdentical(cmp_runner(0), SRC, COPY).describe() == f"{COPY} is identical to {SRC}"
    with pytest.raises(ValueError):
        FilesIdentical(cmp_runner(0), "etc/services", COPY)
    with pytest.raises(ValueError):
        FilesIdentical(cmp_runner(0), SRC, "services.bak")
    with pytest.raises(ValueError):
        FilesIdentical(cmp_runner(0), SRC, SRC)


# --- UmaskConfigured ---
BASHRC = "/home/alice/.bashrc"
CAT_BASHRC = ("cat", "--", BASHRC)


def cat_runner(stdout: str, returncode: int = 0, stderr: str = "") -> FakeCommandRunner:
    return FakeCommandRunner(
        {CAT_BASHRC: make_result(CAT_BASHRC, returncode=returncode, stdout=stdout, stderr=stderr)}
    )


@pytest.mark.parametrize(
    "content",
    [
        "umask 027\n",
        "umask 0027\n",
        "# .bashrc\nalias ll='ls -l'\n  umask   027   # restrictivo\n",
        "umask 022\numask 027\n",
        "\tumask 0027",
    ],
)
def test_umask_found(content: str) -> None:
    assert UmaskConfigured(cat_runner(content), BASHRC, "027").run().passed
    assert UmaskConfigured(cat_runner(content), BASHRC, "0027").run().passed


@pytest.mark.parametrize(
    "content",
    [
        "",
        "# umask 027\n",
        "umask 022\n",
        "umask 27\n",
        "umask -S\n",
        "umask 0270\n",
        "echo umask 027\n",
        "umask 027 && true\n",
        "umaskx 027\n",
    ],
)
def test_umask_not_found(content: str) -> None:
    result = UmaskConfigured(cat_runner(content), BASHRC, "027").run()
    assert not result.passed and "umask 027" in result.detail


def test_umask_unreadable_and_root_hint() -> None:
    result = UmaskConfigured(cat_runner("", 1, "cat: x: No such file or directory\n"), BASHRC, "027").run()
    assert not result.passed and "cannot read" in result.detail and "sudo" not in result.detail
    err = "cat: x: Permission denied\n"
    assert "sudo" in UmaskConfigured(cat_runner("", 1, err), BASHRC, "027").run().detail


def test_umask_describe_and_validation() -> None:
    assert UmaskConfigured(cat_runner(""), BASHRC, "027").describe() == (
        "/home/alice/.bashrc sets umask 027"
    )
    for bad in ("", "02", "00027", "028", "u=rwx", "-S"):
        with pytest.raises(ValueError):
            UmaskConfigured(cat_runner(""), BASHRC, bad)
    with pytest.raises(ValueError):
        UmaskConfigured(cat_runner(""), "relative", "027")

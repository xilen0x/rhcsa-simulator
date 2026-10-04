from __future__ import annotations

import pytest

from rhcsa_sim.checks.essentials import (
    ArchiveContains,
    GrepOutputSaved,
    HardLinkTo,
    SymlinkTo,
)
from rhcsa_sim.testing import FakeCommandRunner, make_result

ARCHIVE = "/root/etc-backup.tar.gz"
FILE_CMD = ("file", "-b", "--mime-type", "--", ARCHIVE)
TAR_CMD = ("tar", "-tf", ARCHIVE)


def archive_runner(
    mime: str = "application/gzip\n",
    listing: str = "etc/\netc/fstab\netc/hosts\n",
    file_rc: int = 0,
    tar_rc: int = 0,
) -> FakeCommandRunner:
    return FakeCommandRunner(
        {
            FILE_CMD: make_result(FILE_CMD, returncode=file_rc, stdout=mime),
            TAR_CMD: make_result(TAR_CMD, returncode=tar_rc, stdout=listing),
        }
    )


def test_archive_ok() -> None:
    check = ArchiveContains(archive_runner(), ARCHIVE, "gzip", ("etc/fstab", "etc/hosts"))
    assert check.run().passed


def test_archive_normalizes_dot_slash_and_trailing_slash() -> None:
    fake = archive_runner(listing="./etc/\n./etc/fstab\n./etc/hosts\n")
    assert ArchiveContains(fake, ARCHIVE, "gzip", ("etc/fstab", "etc/", "etc")).run().passed


def test_archive_directory_member_counts_via_children() -> None:
    fake = archive_runner(listing="etc/fstab\netc/hosts\n")
    assert ArchiveContains(fake, ARCHIVE, "gzip", ("etc",)).run().passed


def test_archive_prefix_is_not_a_directory_match() -> None:
    fake = archive_runner(listing="etcetera/file\n")
    assert not ArchiveContains(fake, ARCHIVE, "gzip", ("etc",)).run().passed


def test_archive_reports_missing_members() -> None:
    fake = archive_runner(listing="etc/fstab\n")
    result = ArchiveContains(fake, ARCHIVE, "gzip", ("etc/fstab", "etc/hosts")).run()
    assert not result.passed and "etc/hosts" in result.detail
    assert "etc/fstab" not in result.detail


def test_archive_missing_members_message_is_truncated() -> None:
    members = tuple(f"etc/f{i}" for i in range(10))
    result = ArchiveContains(archive_runner(listing=""), ARCHIVE, "gzip", members).run()
    assert not result.passed and "etc/f0" in result.detail
    assert "etc/f9" not in result.detail and "10" in result.detail


@pytest.mark.parametrize(
    ("compression", "mime"),
    [
        ("gzip", "application/gzip"),
        ("xz", "application/x-xz"),
        ("bzip2", "application/x-bzip2"),
        ("zstd", "application/zstd"),
    ],
)
def test_archive_compression_mime_mapping(compression: str, mime: str) -> None:
    fake = archive_runner(mime=mime + "\n")
    assert ArchiveContains(fake, ARCHIVE, compression, ("etc/fstab",)).run().passed


def test_archive_wrong_compression() -> None:
    fake = archive_runner(mime="application/x-xz\n")
    result = ArchiveContains(fake, ARCHIVE, "gzip", ("etc/fstab",)).run()
    assert not result.passed and "application/x-xz" in result.detail
    assert fake.calls == [FILE_CMD]


def test_archive_missing_file_and_bad_tar() -> None:
    missing = archive_runner(file_rc=1, mime="")
    assert not ArchiveContains(missing, ARCHIVE, "gzip", ("etc/fstab",)).run().passed
    bad = archive_runner(tar_rc=2, listing="")
    assert not ArchiveContains(bad, ARCHIVE, "gzip", ("etc/fstab",)).run().passed


def test_archive_unreadable_file_reports_cannot_open() -> None:
    # `file` sale con rc 0 aunque no pueda abrir la ruta: lo indica en stdout.
    fake = archive_runner(
        mime=f"cannot open `{ARCHIVE}' (Permission denied)\n", tar_rc=2, listing=""
    )
    result = ArchiveContains(fake, ARCHIVE, "gzip", ("etc/fstab",)).run()
    assert not result.passed
    assert result.detail == f"cannot open '{ARCHIVE}' (Permission denied)"


def test_archive_empty_file_mime() -> None:
    fake = archive_runner(mime="inode/x-empty\n")
    assert not ArchiveContains(fake, ARCHIVE, "gzip", ("etc/fstab",)).run().passed


@pytest.mark.parametrize(
    ("path", "compression", "members"),
    [
        ("relative.tgz", "gzip", ("a",)),
        (ARCHIVE, "lzma", ("a",)),
        (ARCHIVE, "gzip", ()),
        (ARCHIVE, "gzip", ("",)),
        (ARCHIVE, "gzip", ("a\nb",)),
        (ARCHIVE, "gzip", ("a\x00b",)),
        (ARCHIVE, "gzip", ("/",)),
    ],
)
def test_archive_invalid_arguments_rejected(
    path: str, compression: str, members: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError):
        ArchiveContains(archive_runner(), path, compression, members)


LINK = "/root/notes.hard"
TARGET = "/root/notes.txt"
LINK_STAT = ("stat", "-c", "%d %i %F", "--", LINK)
TARGET_STAT = ("stat", "-c", "%d %i %F", "--", TARGET)


def hard_runner(link_out: str, target_out: str, link_rc: int = 0, target_rc: int = 0) -> FakeCommandRunner:
    return FakeCommandRunner(
        {
            LINK_STAT: make_result(LINK_STAT, returncode=link_rc, stdout=link_out),
            TARGET_STAT: make_result(TARGET_STAT, returncode=target_rc, stdout=target_out),
        }
    )


def test_hard_link_ok() -> None:
    fake = hard_runner("64768 1034 regular file\n", "64768 1034 regular file\n")
    assert HardLinkTo(fake, LINK, TARGET).run().passed


def test_hard_link_different_inode() -> None:
    fake = hard_runner("64768 1035 regular file\n", "64768 1034 regular file\n")
    assert not HardLinkTo(fake, LINK, TARGET).run().passed


def test_hard_link_same_inode_other_device() -> None:
    fake = hard_runner("64769 1034 regular file\n", "64768 1034 regular file\n")
    assert not HardLinkTo(fake, LINK, TARGET).run().passed


def test_hard_link_not_regular_file() -> None:
    fake = hard_runner("64768 1034 symbolic link\n", "64768 1034 regular file\n")
    assert not HardLinkTo(fake, LINK, TARGET).run().passed
    fake = hard_runner("64768 1034 regular file\n", "64768 1034 directory\n")
    assert not HardLinkTo(fake, LINK, TARGET).run().passed


def test_hard_link_missing_or_malformed() -> None:
    assert not HardLinkTo(hard_runner("", "64768 1034 regular file\n", link_rc=1), LINK, TARGET).run().passed
    assert not HardLinkTo(hard_runner("64768 1034 regular file\n", "", target_rc=1), LINK, TARGET).run().passed
    assert not HardLinkTo(hard_runner("zzz\n", "64768 1034 regular file\n"), LINK, TARGET).run().passed


def test_hard_link_same_path_rejected() -> None:
    with pytest.raises(ValueError):
        HardLinkTo(hard_runner("", ""), TARGET, TARGET)


def test_hard_link_invalid_paths() -> None:
    with pytest.raises(ValueError):
        HardLinkTo(hard_runner("", ""), "rel", TARGET)
    with pytest.raises(ValueError):
        HardLinkTo(hard_runner("", ""), LINK, "rel")


SYM = "/root/hosts-link"
SYM_STAT = ("stat", "-c", "%F", "--", SYM)
READLINK = ("readlink", "--", SYM)


def sym_runner(kind: str = "symbolic link\n", target: str = "/etc/hosts\n", stat_rc: int = 0, rl_rc: int = 0) -> FakeCommandRunner:
    return FakeCommandRunner(
        {
            SYM_STAT: make_result(SYM_STAT, returncode=stat_rc, stdout=kind),
            READLINK: make_result(READLINK, returncode=rl_rc, stdout=target),
        }
    )


def test_symlink_ok() -> None:
    assert SymlinkTo(sym_runner(), SYM, "/etc/hosts").run().passed


def test_symlink_wrong_target_reports_actual() -> None:
    result = SymlinkTo(sym_runner(target="/etc/passwd\n"), SYM, "/etc/hosts").run()
    assert not result.passed and "/etc/passwd" in result.detail


def test_symlink_not_a_link_or_missing() -> None:
    fake = sym_runner(kind="regular file\n")
    assert not SymlinkTo(fake, SYM, "/etc/hosts").run().passed
    assert fake.calls == [SYM_STAT]
    assert not SymlinkTo(sym_runner(kind="", stat_rc=1), SYM, "/etc/hosts").run().passed


def test_symlink_readlink_failure() -> None:
    assert not SymlinkTo(sym_runner(target="", rl_rc=1), SYM, "/etc/hosts").run().passed


def test_symlink_invalid_paths() -> None:
    with pytest.raises(ValueError):
        SymlinkTo(sym_runner(), "rel", "/etc/hosts")
    with pytest.raises(ValueError):
        SymlinkTo(sym_runner(), SYM, "")


SRC = "/etc/passwd"
DEST = "/root/nologin.txt"
GREP = ("grep", "--", "nologin", SRC)
CAT = ("cat", "--", DEST)


def grep_runner(
    grep_out: str = "a:nologin\nb:nologin\n",
    dest_out: str = "a:nologin\nb:nologin\n",
    grep_rc: int = 0,
    cat_rc: int = 0,
) -> FakeCommandRunner:
    return FakeCommandRunner(
        {
            GREP: make_result(GREP, returncode=grep_rc, stdout=grep_out),
            CAT: make_result(CAT, returncode=cat_rc, stdout=dest_out),
        }
    )


def test_grep_saved_ok_ignores_trailing_newline() -> None:
    assert GrepOutputSaved(grep_runner(dest_out="a:nologin\nb:nologin"), SRC, "nologin", DEST).run().passed
    assert GrepOutputSaved(grep_runner(), SRC, "nologin", DEST).run().passed


def test_grep_saved_order_matters() -> None:
    fake = grep_runner(dest_out="b:nologin\na:nologin\n")
    result = GrepOutputSaved(fake, SRC, "nologin", DEST).run()
    assert not result.passed and "line 1" in result.detail


def test_grep_saved_count_mismatch() -> None:
    fake = grep_runner(dest_out="a:nologin\n")
    result = GrepOutputSaved(fake, SRC, "nologin", DEST).run()
    assert not result.passed
    assert "expected 2" in result.detail and "found 1" in result.detail


def test_grep_saved_extra_line_reports_first_difference() -> None:
    fake = grep_runner(dest_out="a:nologin\nb:nologin\nc:extra\n")
    result = GrepOutputSaved(fake, SRC, "nologin", DEST).run()
    assert not result.passed and "line 3" in result.detail


def test_grep_saved_no_matches_requires_empty_dest() -> None:
    assert GrepOutputSaved(grep_runner("", "", grep_rc=1), SRC, "nologin", DEST).run().passed
    assert not GrepOutputSaved(grep_runner("", "x\n", grep_rc=1), SRC, "nologin", DEST).run().passed


def test_grep_saved_source_unreadable() -> None:
    result = GrepOutputSaved(grep_runner("", "", grep_rc=2), SRC, "nologin", DEST).run()
    assert not result.passed and "cannot grep" in result.detail


def test_grep_saved_dest_missing() -> None:
    result = GrepOutputSaved(grep_runner(cat_rc=1, dest_out=""), SRC, "nologin", DEST).run()
    assert not result.passed and "cannot read" in result.detail


def test_grep_saved_pattern_starting_with_dash_uses_double_dash() -> None:
    cmd = ("grep", "--", "-x", SRC)
    cat = CAT
    fake = FakeCommandRunner(
        {cmd: make_result(cmd, stdout="-x\n"), cat: make_result(cat, stdout="-x\n")}
    )
    assert GrepOutputSaved(fake, SRC, "-x", DEST).run().passed


@pytest.mark.parametrize("pattern", ["", "a\nb", "a\x00b"])
def test_grep_saved_invalid_pattern(pattern: str) -> None:
    with pytest.raises(ValueError):
        GrepOutputSaved(grep_runner(), SRC, pattern, DEST)


def test_grep_saved_invalid_paths() -> None:
    with pytest.raises(ValueError):
        GrepOutputSaved(grep_runner(), "rel", "nologin", DEST)
    with pytest.raises(ValueError):
        GrepOutputSaved(grep_runner(), SRC, "nologin", "rel")

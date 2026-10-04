from __future__ import annotations

import json

import pytest

from rhcsa_sim.checks.filesystems import (
    FstabMountByUuid,
    FstabNfsEntry,
    FstabUuidMatchesMount,
    MountedAt,
    NfsMountedAt,
)
from rhcsa_sim.models import Check
from rhcsa_sim.runner import CommandResult
from rhcsa_sim.testing import FakeCommandRunner, make_result

UUID = "476c00b7-0000-45fe-a368-d4b5f25a5ee1"
OTHER_UUID = "deadbeef-0000-45fe-a368-d4b5f25a5ee1"
DEVICE = "/dev/mapper/examvg-datalv"

MOUNT_CMD = ("findmnt", "-J", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS", "--mountpoint=/data")
FSTAB_CMD = (
    "findmnt", "-J", "--fstab", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS", "--mountpoint=/data",
)  # fmt: skip
BLKID_CMD = ("blkid", "-o", "value", "-s", "UUID", "--", DEVICE)


def table(source: str, fstype: str = "xfs", target: str = "/data") -> str:
    row = {"target": target, "source": source, "fstype": fstype, "options": "rw,relatime"}
    return json.dumps({"filesystems": [row]})


MOUNT_OK = table(DEVICE)
FSTAB_OK = table(f"UUID={UUID}")


def fake(
    mount: tuple[str, int] | None = (MOUNT_OK, 0),
    fstab: tuple[str, int] | None = (FSTAB_OK, 0),
    blkid: tuple[str, int] | None = (f"{UUID}\n", 0),
) -> FakeCommandRunner:
    """Runner con las respuestas indicadas (None = comando no esperado)."""
    responses: dict[tuple[str, ...], CommandResult] = {}
    for cmd, item in ((MOUNT_CMD, mount), (FSTAB_CMD, fstab), (BLKID_CMD, blkid)):
        if item is not None:
            responses[cmd] = make_result(cmd, returncode=item[1], stdout=item[0])
    return FakeCommandRunner(responses)


NOT_FOUND = ("", 1)
BAD_OUTPUTS = [
    "not json",
    "[]",
    "{}",
    '{"filesystems": "x"}',
    '{"filesystems": [1]}',
    '{"filesystems": [{"target": "/data", "source": 1}]}',
    '{"filesystems": [{"target": "/data", "source": null}]}',
    '{"filesystems": [{"target": "/data"}]}',
]


def test_checks_satisfy_protocol() -> None:
    runner = fake()
    checks: list[Check] = [
        MountedAt(runner, "/data", "xfs"),
        FstabMountByUuid(runner, "/data", "xfs"),
        FstabUuidMatchesMount(runner, "/data"),
    ]
    assert all(c.describe() for c in checks)


# --- MountedAt ---


def test_mounted_ok_without_and_with_fstype() -> None:
    assert MountedAt(fake(), "/data").run().passed
    assert MountedAt(fake(), "/data", "xfs").run().passed


def test_mounted_not_mounted_is_ko() -> None:
    result = MountedAt(fake(mount=NOT_FOUND), "/data").run()
    assert not result.passed and "not mounted" in result.detail


def test_mounted_fstype_mismatch_reports_both() -> None:
    result = MountedAt(fake(mount=(table(DEVICE, "ext4"), 0)), "/data", "xfs").run()
    assert not result.passed
    assert "ext4" in result.detail and "xfs" in result.detail


@pytest.mark.parametrize("rc", [2, 124, 126, 127])
def test_mounted_failed_command_is_ko(rc: int) -> None:
    result = MountedAt(fake(mount=("", rc)), "/data").run()
    assert not result.passed and f"exit {rc}" in result.detail


def test_mounted_rc1_with_output_is_a_failure_not_unmounted() -> None:
    result = MountedAt(fake(mount=("boom", 1)), "/data").run()
    assert not result.passed and "exit 1" in result.detail


@pytest.mark.parametrize("stdout", BAD_OUTPUTS)
def test_mounted_malformed_output_is_ko(stdout: str) -> None:
    result = MountedAt(fake(mount=(stdout, 0)), "/data", "xfs").run()
    assert not result.passed and "unexpected" in result.detail


def test_mounted_empty_list_is_not_mounted() -> None:
    result = MountedAt(fake(mount=('{"filesystems": []}', 0)), "/data").run()
    assert not result.passed and "not mounted" in result.detail


@pytest.mark.parametrize(("target", "fstype"), [("data", None), ("", None), ("/d\na", None)])
def test_mounted_invalid_target(target: str, fstype: str | None) -> None:
    with pytest.raises(ValueError):
        MountedAt(fake(), target, fstype)


@pytest.mark.parametrize("fstype", ["", "XFS", "-x", "a b"])
def test_mounted_invalid_fstype(fstype: str) -> None:
    with pytest.raises(ValueError):
        MountedAt(fake(), "/data", fstype)


def test_mounted_source_matches_ok() -> None:
    assert MountedAt(fake(), "/data", "xfs", DEVICE).run().passed


def test_mounted_source_mismatch_reports_both() -> None:
    result = MountedAt(fake(mount=(table("/dev/sdb2"), 0)), "/data", "xfs", DEVICE).run()
    assert not result.passed
    assert "/dev/sdb2" in result.detail and DEVICE in result.detail


def test_mounted_source_is_compared_exactly() -> None:
    result = MountedAt(fake(mount=(table(f"{DEVICE}x"), 0)), "/data", None, DEVICE).run()
    assert not result.passed


@pytest.mark.parametrize("source", ["", "sdb1", "/dev/../x", "/etc/passwd"])
def test_mounted_invalid_source(source: str) -> None:
    with pytest.raises(ValueError):
        MountedAt(fake(), "/data", "xfs", source)


def test_mounted_describe_mentions_source() -> None:
    assert DEVICE in MountedAt(fake(), "/data", "xfs", DEVICE).describe()
    assert DEVICE in MountedAt(fake(), "/data", None, DEVICE).describe()


def test_mounted_null_options_still_parses() -> None:
    row = '{"filesystems": [{"target": "/data", "source": "%s", "fstype": "xfs", "options": null}]}'
    assert MountedAt(fake(mount=(row % DEVICE, 0)), "/data", "xfs", DEVICE).run().passed


@pytest.mark.parametrize("column", ["source", "fstype"])
def test_mounted_null_required_column_is_unexpected(column: str) -> None:
    row: dict[str, object] = {"target": "/data", "source": DEVICE, "fstype": "xfs"}
    row[column] = None
    stdout = json.dumps({"filesystems": [row]})
    result = MountedAt(fake(mount=(stdout, 0)), "/data").run()
    assert not result.passed and "unexpected" in result.detail


# --- FstabMountByUuid ---


def test_fstab_by_uuid_ok_without_and_with_fstype() -> None:
    assert FstabMountByUuid(fake(), "/data").run().passed
    assert FstabMountByUuid(fake(), "/data", "xfs").run().passed


def test_fstab_by_uuid_no_entry() -> None:
    result = FstabMountByUuid(fake(fstab=NOT_FOUND), "/data").run()
    assert not result.passed and "no fstab entry" in result.detail


@pytest.mark.parametrize("source", ["/dev/sdb1", "LABEL=data", f"PARTUUID={UUID}", ""])
def test_fstab_by_uuid_source_not_uuid(source: str) -> None:
    result = FstabMountByUuid(fake(fstab=(table(source), 0)), "/data").run()
    assert not result.passed and "does not use UUID=" in result.detail


@pytest.mark.parametrize("value", ["", "xyz", "deadbeef", f"{UUID}\n", "1234-56"])
def test_fstab_by_uuid_malformed_uuid(value: str) -> None:
    result = FstabMountByUuid(fake(fstab=(table(f"UUID={value}"), 0)), "/data").run()
    assert not result.passed and "malformed" in result.detail


def test_fstab_by_uuid_accepts_short_vfat_uuid() -> None:
    assert FstabMountByUuid(fake(fstab=(table("UUID=1A2B-3C4D", "vfat"), 0)), "/data").run().passed


def test_fstab_by_uuid_fstype_mismatch() -> None:
    result = FstabMountByUuid(fake(fstab=(table(f"UUID={UUID}", "ext4"), 0)), "/data", "xfs").run()
    assert not result.passed and "ext4" in result.detail and "xfs" in result.detail


@pytest.mark.parametrize("rc", [2, 124, 126, 127])
def test_fstab_by_uuid_failed_command_is_ko(rc: int) -> None:
    result = FstabMountByUuid(fake(fstab=("", rc)), "/data").run()
    assert not result.passed and f"exit {rc}" in result.detail


@pytest.mark.parametrize("stdout", BAD_OUTPUTS)
def test_fstab_by_uuid_malformed_output_is_ko(stdout: str) -> None:
    result = FstabMountByUuid(fake(fstab=(stdout, 0)), "/data").run()
    assert not result.passed and "unexpected" in result.detail


def test_fstab_by_uuid_invalid_parameters() -> None:
    with pytest.raises(ValueError):
        FstabMountByUuid(fake(), "data")
    with pytest.raises(ValueError):
        FstabMountByUuid(fake(), "/data", "XFS")


# --- FstabUuidMatchesMount ---


def test_matches_ok_and_case_insensitive() -> None:
    assert FstabUuidMatchesMount(fake(), "/data").run().passed
    upper = fake(blkid=(f"{UUID.upper()}\n", 0))
    assert FstabUuidMatchesMount(upper, "/data").run().passed


def test_matches_mismatch_shows_both_uuids() -> None:
    result = FstabUuidMatchesMount(fake(blkid=(f"{OTHER_UUID}\n", 0)), "/data").run()
    assert not result.passed
    assert UUID in result.detail and OTHER_UUID in result.detail


def test_matches_no_fstab_entry_skips_other_commands() -> None:
    runner = fake(fstab=NOT_FOUND)
    result = FstabUuidMatchesMount(runner, "/data").run()
    assert not result.passed and "no fstab entry" in result.detail
    assert BLKID_CMD not in runner.calls


def test_matches_fstab_not_by_uuid() -> None:
    runner = fake(fstab=(table("/dev/sdb1"), 0))
    result = FstabUuidMatchesMount(runner, "/data").run()
    assert not result.passed and "does not use UUID=" in result.detail
    assert BLKID_CMD not in runner.calls


def test_matches_not_mounted() -> None:
    runner = fake(mount=NOT_FOUND)
    result = FstabUuidMatchesMount(runner, "/data").run()
    assert not result.passed and "not mounted" in result.detail
    assert BLKID_CMD not in runner.calls


@pytest.mark.parametrize("source", ["tmpfs", "/dev/../x", "/etc/passwd", "/dev/sdb1[/sub]", ""])
def test_matches_unsafe_mounted_source_never_reaches_blkid(source: str) -> None:
    runner = fake(mount=(table(source), 0), blkid=None)
    result = FstabUuidMatchesMount(runner, "/data").run()
    assert not result.passed and "block device" in result.detail
    assert all(call[0] != "blkid" for call in runner.calls)


def test_matches_device_without_uuid() -> None:
    result = FstabUuidMatchesMount(fake(blkid=("", 2)), "/data").run()
    assert not result.passed and "no UUID" in result.detail
    assert "retry with sudo" in result.detail


@pytest.mark.parametrize("rc", [1, 3, 124, 126, 127])
def test_matches_blkid_failure_is_ko(rc: int) -> None:
    result = FstabUuidMatchesMount(fake(blkid=("", rc)), "/data").run()
    assert not result.passed and f"exit {rc}" in result.detail


@pytest.mark.parametrize("stdout", ["", "\n", "garbage\n", f"{UUID}\n{UUID}\n"])
def test_matches_unexpected_blkid_output_is_ko(stdout: str) -> None:
    result = FstabUuidMatchesMount(fake(blkid=(stdout, 0)), "/data").run()
    assert not result.passed and "unexpected" in result.detail


@pytest.mark.parametrize("rc", [124, 127])
def test_matches_failed_findmnt_is_ko(rc: int) -> None:
    assert not FstabUuidMatchesMount(fake(fstab=("", rc)), "/data").run().passed
    assert not FstabUuidMatchesMount(fake(mount=("", rc)), "/data").run().passed


@pytest.mark.parametrize("stdout", BAD_OUTPUTS)
def test_matches_malformed_findmnt_output_is_ko(stdout: str) -> None:
    assert not FstabUuidMatchesMount(fake(fstab=(stdout, 0)), "/data").run().passed
    assert not FstabUuidMatchesMount(fake(mount=(stdout, 0)), "/data").run().passed


def test_matches_invalid_target() -> None:
    with pytest.raises(ValueError):
        FstabUuidMatchesMount(fake(), "data")


NFS_SOURCE = "localhost:/srv/nfsexport"
NFS_MOUNT_CMD = (
    "findmnt", "-J", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS", "--mountpoint=/mnt/nfs",
)  # fmt: skip
NFS_FSTAB_CMD = (
    "findmnt", "-J", "--fstab", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS", "--mountpoint=/mnt/nfs",
)  # fmt: skip


def nfs_fake(
    mount: tuple[str, int] | None = None, fstab: tuple[str, int] | None = None
) -> FakeCommandRunner:
    responses: dict[tuple[str, ...], CommandResult] = {}
    for cmd, item in ((NFS_MOUNT_CMD, mount), (NFS_FSTAB_CMD, fstab)):
        if item is not None:
            responses[cmd] = make_result(cmd, returncode=item[1], stdout=item[0])
    return FakeCommandRunner(responses)


def nfs_table(source: str = NFS_SOURCE, fstype: str = "nfs4") -> str:
    return table(source, fstype, "/mnt/nfs")


def test_nfs_checks_satisfy_protocol() -> None:
    checks: list[Check] = [
        NfsMountedAt(nfs_fake(), "/mnt/nfs", NFS_SOURCE),
        FstabNfsEntry(nfs_fake(), "/mnt/nfs", NFS_SOURCE),
    ]
    assert all(c.describe() and NFS_SOURCE in c.describe() for c in checks)


@pytest.mark.parametrize("fstype", ["nfs", "nfs4"])
def test_nfs_mounted_passes(fstype: str) -> None:
    runner = nfs_fake(mount=(nfs_table(fstype=fstype), 0))
    assert NfsMountedAt(runner, "/mnt/nfs", NFS_SOURCE).run().passed


def test_nfs_mounted_fails_when_not_mounted() -> None:
    result = NfsMountedAt(nfs_fake(mount=NOT_FOUND), "/mnt/nfs", NFS_SOURCE).run()
    assert not result.passed and "not mounted" in result.detail


def test_nfs_mounted_fails_on_wrong_fstype() -> None:
    runner = nfs_fake(mount=(nfs_table("/dev/sdb3", "xfs"), 0))
    result = NfsMountedAt(runner, "/mnt/nfs", NFS_SOURCE).run()
    assert not result.passed and "xfs" in result.detail


def test_nfs_mounted_fails_on_wrong_source() -> None:
    runner = nfs_fake(mount=(nfs_table("other:/srv/x"), 0))
    result = NfsMountedAt(runner, "/mnt/nfs", NFS_SOURCE).run()
    assert not result.passed and "other:/srv/x" in result.detail


@pytest.mark.parametrize("fstype", ["nfs", "nfs4"])
def test_fstab_nfs_entry_passes(fstype: str) -> None:
    runner = nfs_fake(fstab=(nfs_table(fstype=fstype), 0))
    assert FstabNfsEntry(runner, "/mnt/nfs", NFS_SOURCE).run().passed


def test_fstab_nfs_entry_fails_without_entry() -> None:
    result = FstabNfsEntry(nfs_fake(fstab=NOT_FOUND), "/mnt/nfs", NFS_SOURCE).run()
    assert not result.passed and "no fstab entry" in result.detail


def test_fstab_nfs_entry_fails_on_wrong_source_or_type() -> None:
    wrong_source = nfs_fake(fstab=(nfs_table("other:/srv/x"), 0))
    assert not FstabNfsEntry(wrong_source, "/mnt/nfs", NFS_SOURCE).run().passed
    wrong_type = nfs_fake(fstab=(nfs_table(fstype="cifs"), 0))
    result = FstabNfsEntry(wrong_type, "/mnt/nfs", NFS_SOURCE).run()
    assert not result.passed and "cifs" in result.detail


def test_nfs_checks_fail_on_query_error() -> None:
    assert not NfsMountedAt(nfs_fake(mount=("", 2)), "/mnt/nfs", NFS_SOURCE).run().passed
    assert not FstabNfsEntry(nfs_fake(fstab=("junk", 0)), "/mnt/nfs", NFS_SOURCE).run().passed


@pytest.mark.parametrize("source", ["", "localhost", "localhost:srv", "host :/x", "/srv:", ":/x\n"])
def test_nfs_checks_reject_bad_source(source: str) -> None:
    with pytest.raises(ValueError):
        NfsMountedAt(nfs_fake(), "/mnt/nfs", source)
    with pytest.raises(ValueError):
        FstabNfsEntry(nfs_fake(), "/mnt/nfs", source)


def test_nfs_checks_reject_relative_target() -> None:
    with pytest.raises(ValueError):
        NfsMountedAt(nfs_fake(), "mnt/nfs", NFS_SOURCE)
    with pytest.raises(ValueError):
        FstabNfsEntry(nfs_fake(), "mnt/nfs", NFS_SOURCE)

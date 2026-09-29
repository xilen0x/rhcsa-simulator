from __future__ import annotations

import json

import pytest

from rhcsa_sim.checks.blockdev import PartitionExists, SwapActive, SwapInFstabByUuid
from rhcsa_sim.models import Check
from rhcsa_sim.runner import CommandResult
from rhcsa_sim.testing import FakeCommandRunner, make_result

MIB = 1024 * 1024
DEVICE = "/dev/sdb2"
LSBLK_COLUMNS = "PATH,KNAME,SIZE,TYPE,FSTYPE,UUID,PARTTYPENAME"


def lsblk_cmd(device: str = DEVICE) -> tuple[str, ...]:
    return ("lsblk", "-J", "-l", "-b", "-o", LSBLK_COLUMNS, "--", device)


def row(
    path: str = DEVICE,
    kname: object = "sdb2",
    size: object = 512 * MIB,
    type_: object = "part",
    fstype: object = None,
    uuid: object = None,
    parttypename: object = "Linux filesystem",
) -> dict[str, object]:
    return {
        "path": path,
        "kname": kname,
        "size": size,
        "type": type_,
        "fstype": fstype,
        "uuid": uuid,
        "parttypename": parttypename,
    }


def lsblk_out(*rows: dict[str, object]) -> str:
    return json.dumps({"blockdevices": list(rows)})


def runner_for(stdout: str, rc: int = 0, stderr: str = "") -> FakeCommandRunner:
    cmd = lsblk_cmd()
    return FakeCommandRunner({cmd: make_result(cmd, returncode=rc, stdout=stdout, stderr=stderr)})


def make_check(runner: FakeCommandRunner) -> PartitionExists:
    return PartitionExists(runner, DEVICE, 480 * MIB, 560 * MIB)


def test_partition_ok() -> None:
    result = make_check(runner_for(lsblk_out(row()))).run()
    assert result.passed and "512 MiB" in result.detail


def test_partition_satisfies_check_protocol() -> None:
    check: Check = make_check(runner_for(lsblk_out(row())))
    assert DEVICE in check.describe()


def test_partition_bounds_are_inclusive() -> None:
    for size in (480 * MIB, 560 * MIB):
        assert make_check(runner_for(lsblk_out(row(size=size)))).run().passed


@pytest.mark.parametrize("size", [480 * MIB - 1, 560 * MIB + 1, 2048 * MIB])
def test_partition_size_out_of_range(size: int) -> None:
    result = make_check(runner_for(lsblk_out(row(size=size)))).run()
    assert not result.passed and "size" in result.detail
    assert "480 MiB" in result.detail and "560 MiB" in result.detail


def test_partition_size_not_mib_multiple_is_shown_in_bytes() -> None:
    result = make_check(runner_for(lsblk_out(row(size=100)))).run()
    assert not result.passed and "100 bytes" in result.detail


def test_partition_picks_row_matching_path_ignoring_children() -> None:
    child = row(path="/dev/mapper/examvg-datalv", kname="dm-2", size=1 * MIB, type_="lvm")
    assert make_check(runner_for(lsblk_out(child, row()))).run().passed


def test_partition_wrong_type() -> None:
    result = make_check(runner_for(lsblk_out(row(type_="disk")))).run()
    assert not result.passed
    assert result.detail == f"'{DEVICE}' is a disk, not a partition"


def test_partition_missing_device_by_returncode() -> None:
    result = make_check(runner_for("", rc=32)).run()
    assert not result.passed and result.detail == f"'{DEVICE}' does not exist"


def test_partition_missing_device_by_stderr() -> None:
    err = f"lsblk: {DEVICE}: not a block device\n"
    result = make_check(runner_for("", rc=1, stderr=err)).run()
    assert not result.passed and "does not exist" in result.detail


@pytest.mark.parametrize("rc", [1, 124, 127])
def test_partition_query_failure(rc: int) -> None:
    result = make_check(runner_for("", rc=rc)).run()
    assert not result.passed
    assert result.detail == f"cannot query block device '{DEVICE}' (exit {rc})"


@pytest.mark.parametrize(
    "stdout",
    [
        "not json",
        "[]",
        "{}",
        '{"blockdevices": "x"}',
        '{"blockdevices": ["x"]}',
        lsblk_out(),
        lsblk_out(row(path="/dev/sdc1")),
        lsblk_out(row(size="512")),
        lsblk_out(row(size=True)),
        lsblk_out(row(size=-1)),
        lsblk_out(row(size=1.5)),
        lsblk_out(row(type_=None)),
        lsblk_out(row(kname=3)),
        lsblk_out(row(fstype=5)),
        lsblk_out(row(uuid=5)),
        lsblk_out(row(parttypename=5)),
    ],
)
def test_partition_unexpected_output(stdout: str) -> None:
    result = make_check(runner_for(stdout)).run()
    assert not result.passed and "unexpected lsblk output" in result.detail


@pytest.mark.parametrize("device", ["sdb2", "/dev/../etc", "/dev/sd b", ""])
def test_partition_rejects_bad_device(device: str) -> None:
    with pytest.raises(ValueError):
        PartitionExists(FakeCommandRunner({}), device, 1, 2)


@pytest.mark.parametrize("bounds", [(0, 5), (-1, 5), (10, 5), (True, 5), (1, True)])
def test_partition_rejects_bad_bounds(bounds: tuple[int, int]) -> None:
    with pytest.raises(ValueError):
        PartitionExists(FakeCommandRunner({}), DEVICE, *bounds)


# --- swap ---

UUID = "995e11a3-0000-45fe-a368-d4b5f25a5ee1"
SWAPON_CMD = ("swapon", "--show=NAME,SIZE", "--bytes", "--noheadings", "--raw")
FSTAB_SWAP_CMD = (
    "findmnt", "-J", "--fstab", "-t", "swap", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS",
)  # fmt: skip
SWAP_ROW = row(fstype="swap", uuid=UUID, parttypename="Linux swap")
LVM_SWAP_ROW = row(
    path="/dev/mapper/almalinux-swap", kname="dm-1", size=2 * 1024 * MIB, type_="lvm",
    fstype="swap", uuid=UUID, parttypename=None,
)  # fmt: skip


def fstab_out(*sources: str, fstype: str = "swap") -> str:
    entries = [
        {"target": "none", "source": src, "fstype": fstype, "options": "defaults"}
        for src in sources
    ]
    return json.dumps({"filesystems": entries})


def swap_runner(
    lsblk: str | None,
    swapon: tuple[str, int] | None = None,
    fstab: tuple[str, int] | None = None,
    device: str = DEVICE,
) -> FakeCommandRunner:
    """Runner con las respuestas indicadas (None = comando no esperado)."""
    responses: dict[tuple[str, ...], CommandResult] = {}
    if lsblk is not None:
        cmd = lsblk_cmd(device)
        responses[cmd] = make_result(cmd, stdout=lsblk)
    if swapon is not None:
        responses[SWAPON_CMD] = make_result(SWAPON_CMD, returncode=swapon[1], stdout=swapon[0])
    if fstab is not None:
        responses[FSTAB_SWAP_CMD] = make_result(
            FSTAB_SWAP_CMD, returncode=fstab[1], stdout=fstab[0]
        )
    return FakeCommandRunner(responses)


def test_swap_active_ok() -> None:
    runner = swap_runner(lsblk_out(SWAP_ROW), ("/dev/sdb2 536866816\n", 0))
    result = SwapActive(runner, DEVICE).run()
    assert result.passed and DEVICE in result.detail


def test_swap_active_ok_with_other_swaps_listed() -> None:
    out = "/dev/dm-1 2147479552\n/dev/sdb2 536866816\n"
    assert SwapActive(swap_runner(lsblk_out(SWAP_ROW), (out, 0)), DEVICE).run().passed


def test_swap_active_matches_kernel_name_of_mapper_device() -> None:
    dev = "/dev/mapper/almalinux-swap"
    runner = swap_runner(lsblk_out(LVM_SWAP_ROW), ("/dev/dm-1 2147479552\n", 0), device=dev)
    assert SwapActive(runner, dev).run().passed


def test_swap_active_ignores_children_rows() -> None:
    child = row(path="/dev/mapper/x", kname="dm-9", type_="lvm", fstype="swap")
    runner = swap_runner(lsblk_out(child, SWAP_ROW), ("/dev/sdb2 1\n", 0))
    assert SwapActive(runner, DEVICE).run().passed


def test_swap_active_ko_when_not_listed() -> None:
    runner = swap_runner(lsblk_out(SWAP_ROW), ("/dev/dm-1 2147479552\n", 0))
    result = SwapActive(runner, DEVICE).run()
    assert not result.passed
    assert result.detail == f"'{DEVICE}' is not an active swap (run swapon)"


def test_swap_active_empty_swapon_is_a_normal_ko() -> None:
    result = SwapActive(swap_runner(lsblk_out(SWAP_ROW), ("", 0)), DEVICE).run()
    assert not result.passed and "not an active swap" in result.detail


def test_swap_active_does_not_match_name_prefixes() -> None:
    runner = swap_runner(lsblk_out(SWAP_ROW), ("/dev/sdb22 1\n", 0))
    assert not SwapActive(runner, DEVICE).run().passed


@pytest.mark.parametrize("fstype", [None, "xfs"])
def test_swap_active_requires_swap_fstype(fstype: str | None) -> None:
    runner = swap_runner(lsblk_out(row(fstype=fstype)))
    result = SwapActive(runner, DEVICE).run()
    assert not result.passed
    assert result.detail == f"'{DEVICE}' is not formatted as swap (fstype: {fstype})"


def test_swap_active_missing_device() -> None:
    cmd = lsblk_cmd()
    runner = FakeCommandRunner({cmd: make_result(cmd, returncode=32)})
    result = SwapActive(runner, DEVICE).run()
    assert not result.passed and result.detail == f"'{DEVICE}' does not exist"


def test_swap_active_swapon_failure() -> None:
    runner = swap_runner(lsblk_out(SWAP_ROW), ("", 1))
    result = SwapActive(runner, DEVICE).run()
    assert not result.passed and result.detail == "cannot query active swap (exit 1)"


@pytest.mark.parametrize("bad", ["garbage\n", "/dev/sdb2\n", "/dev/sdb2 abc\n", "a b c\n"])
def test_swap_active_unexpected_swapon_output(bad: str) -> None:
    result = SwapActive(swap_runner(lsblk_out(SWAP_ROW), (bad, 0)), DEVICE).run()
    assert not result.passed and "unexpected swapon output" in result.detail


@pytest.mark.parametrize("rc", [124, 127])
def test_swap_active_lsblk_failure(rc: int) -> None:
    cmd = lsblk_cmd()
    runner = FakeCommandRunner({cmd: make_result(cmd, returncode=rc)})
    result = SwapActive(runner, DEVICE).run()
    assert not result.passed and f"(exit {rc})" in result.detail


def test_swap_active_bad_device() -> None:
    with pytest.raises(ValueError):
        SwapActive(FakeCommandRunner({}), "sdb2")


def test_swap_active_describe() -> None:
    check: Check = SwapActive(FakeCommandRunner({}), DEVICE)
    assert DEVICE in check.describe()


def test_fstab_swap_ok() -> None:
    runner = swap_runner(lsblk_out(SWAP_ROW), fstab=(fstab_out(f"UUID={UUID}"), 0))
    result = SwapInFstabByUuid(runner, DEVICE).run()
    assert result.passed and UUID in result.detail


def test_fstab_swap_ok_among_other_entries_and_case_insensitive() -> None:
    fstab = fstab_out("UUID=aaaaaaaa-0000-0000-0000-000000000000", f"UUID={UUID.upper()}")
    runner = swap_runner(lsblk_out(SWAP_ROW), fstab=(fstab, 0))
    assert SwapInFstabByUuid(runner, DEVICE).run().passed


def test_fstab_swap_ko_no_entries() -> None:
    runner = swap_runner(lsblk_out(SWAP_ROW), fstab=("", 1))
    result = SwapInFstabByUuid(runner, DEVICE).run()
    assert not result.passed and result.detail == "no swap entries in /etc/fstab"


def test_fstab_swap_ko_empty_list() -> None:
    runner = swap_runner(lsblk_out(SWAP_ROW), fstab=(fstab_out(), 0))
    assert not SwapInFstabByUuid(runner, DEVICE).run().passed


def test_fstab_swap_ko_by_path() -> None:
    runner = swap_runner(lsblk_out(SWAP_ROW), fstab=(fstab_out(DEVICE), 0))
    result = SwapInFstabByUuid(runner, DEVICE).run()
    assert not result.passed
    assert result.detail == f"fstab references '{DEVICE}' by path; use UUID={UUID}"


def test_fstab_swap_ko_other_uuid() -> None:
    other = "UUID=aaaaaaaa-0000-0000-0000-000000000000"
    runner = swap_runner(lsblk_out(SWAP_ROW), fstab=(fstab_out(other), 0))
    result = SwapInFstabByUuid(runner, DEVICE).run()
    assert not result.passed and result.detail == f"no fstab swap entry for UUID={UUID}"


def test_fstab_swap_ignores_non_swap_fstype_entries() -> None:
    runner = swap_runner(lsblk_out(SWAP_ROW), fstab=(fstab_out(f"UUID={UUID}", fstype="xfs"), 0))
    assert not SwapInFstabByUuid(runner, DEVICE).run().passed


def test_fstab_swap_null_uuid() -> None:
    runner = swap_runner(lsblk_out(row(uuid=None)))
    result = SwapInFstabByUuid(runner, DEVICE).run()
    assert not result.passed and result.detail == f"'{DEVICE}' has no UUID"


def test_fstab_swap_malformed_device_uuid() -> None:
    runner = swap_runner(lsblk_out(row(uuid="not a uuid")))
    result = SwapInFstabByUuid(runner, DEVICE).run()
    assert not result.passed and "malformed UUID" in result.detail


def test_fstab_swap_missing_device() -> None:
    cmd = lsblk_cmd()
    runner = FakeCommandRunner({cmd: make_result(cmd, returncode=32)})
    result = SwapInFstabByUuid(runner, DEVICE).run()
    assert not result.passed and result.detail == f"'{DEVICE}' does not exist"


@pytest.mark.parametrize("rc", [2, 124, 127])
def test_fstab_swap_findmnt_failure(rc: int) -> None:
    runner = swap_runner(lsblk_out(SWAP_ROW), fstab=("", rc))
    result = SwapInFstabByUuid(runner, DEVICE).run()
    assert not result.passed and result.detail == f"cannot query /etc/fstab (exit {rc})"


@pytest.mark.parametrize("bad", ["not json", "[]", "{}", '{"filesystems": [1]}'])
def test_fstab_swap_unexpected_findmnt_output(bad: str) -> None:
    runner = swap_runner(lsblk_out(SWAP_ROW), fstab=(bad, 0))
    result = SwapInFstabByUuid(runner, DEVICE).run()
    assert not result.passed and "unexpected findmnt output" in result.detail


def test_fstab_swap_bad_device_and_describe() -> None:
    with pytest.raises(ValueError):
        SwapInFstabByUuid(FakeCommandRunner({}), "/dev/../x")
    check: Check = SwapInFstabByUuid(FakeCommandRunner({}), DEVICE)
    assert DEVICE in check.describe()

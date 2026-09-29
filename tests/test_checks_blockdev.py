from __future__ import annotations

import json

import pytest

from rhcsa_sim.checks.blockdev import PartitionExists
from rhcsa_sim.models import Check
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

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from rhcsa_sim.checks.storage import (
    MIB,
    LogicalVolumeExists,
    LogicalVolumeSizeInRange,
    PhysicalVolumeInGroup,
    VolumeGroupExists,
)
from rhcsa_sim.models import Check
from rhcsa_sim.testing import FakeCommandRunner, make_result

VG_CMD = (
    "vgs", "--reportformat", "json", "--units", "b", "--nosuffix",
    "-o", "vg_name,vg_extent_size", "--", "examvg",
)  # fmt: skip
PV_CMD = ("pvs", "--reportformat", "json", "-o", "pv_name,vg_name", "--", "/dev/sdb1")
LV_CMD = (
    "lvs", "--reportformat", "json", "--units", "b", "--nosuffix",
    "-o", "vg_name,lv_name,lv_size", "--", "examvg/datalv",
)  # fmt: skip


def report(section: str, rows: list[dict[str, str]]) -> str:
    return json.dumps({"report": [{section: rows}]})


def runner_for(
    cmd: tuple[str, ...], stdout: str = "", returncode: int = 0, stderr: str = ""
) -> FakeCommandRunner:
    result = make_result(cmd, returncode=returncode, stdout=stdout, stderr=stderr)
    return FakeCommandRunner({cmd: result})


def vg_runner(stdout: str, returncode: int = 0, stderr: str = "") -> FakeCommandRunner:
    return runner_for(VG_CMD, stdout, returncode, stderr)


def pv_runner(stdout: str, returncode: int = 0, stderr: str = "") -> FakeCommandRunner:
    return runner_for(PV_CMD, stdout, returncode, stderr)


def lv_runner(stdout: str, returncode: int = 0, stderr: str = "") -> FakeCommandRunner:
    return runner_for(LV_CMD, stdout, returncode, stderr)


VG_OK = report("vg", [{"vg_name": "examvg", "vg_extent_size": str(16 * MIB)}])
PV_OK = report("pv", [{"pv_name": "/dev/sdb1", "vg_name": "examvg"}])
LV_OK = report("lv", [{"vg_name": "examvg", "lv_name": "datalv", "lv_size": str(1024 * MIB)}])


def failure(*messages: str) -> str:
    """JSON de LVM con solo la lista de log, como en una consulta fallida."""
    log = [{"log_type": "error", "log_message": m, "log_ret_code": "0"} for m in messages]
    log.append({"log_type": "status", "log_message": "failure", "log_ret_code": "5"})
    return json.dumps({"log": log})


DENIED = "/dev/mapper/control: open failed: Permission denied"


def vg_check(stdout: str, stderr: str = "", rc: int = 5) -> Check:
    return VolumeGroupExists(vg_runner(stdout, rc, stderr), "examvg")


def pv_check(stdout: str, stderr: str = "", rc: int = 5) -> Check:
    return PhysicalVolumeInGroup(pv_runner(stdout, rc, stderr), "/dev/sdb1", "examvg")


def lv_check(stdout: str, stderr: str = "", rc: int = 5) -> Check:
    return LogicalVolumeExists(lv_runner(stdout, rc, stderr), "examvg", "datalv")


def lv_size_check(stdout: str, stderr: str = "", rc: int = 5) -> Check:
    return LogicalVolumeSizeInRange(lv_runner(stdout, rc, stderr), "examvg", "datalv", 1, 2)


# (fabrica del check, mensaje de LVM cuando falta el objeto, texto esperado en el detalle)
FAILING_CHECKS = [
    pytest.param(vg_check, 'Volume group "examvg" not found', "'examvg' does not exist", id="vg"),
    pytest.param(
        pv_check,
        'Failed to find physical volume "/dev/sdb1".',
        "'/dev/sdb1' is not a physical volume",
        id="pv",
    ),
    pytest.param(
        lv_check,
        'Failed to find logical volume "examvg/datalv"',
        "'examvg/datalv' does not exist",
        id="lv",
    ),
    pytest.param(
        lv_size_check,
        'Failed to find logical volume "examvg/datalv"',
        "'examvg/datalv' does not exist",
        id="lv-size",
    ),
]

CheckFactory = Callable[..., Check]


@pytest.mark.parametrize(("make", "missing", "expected"), FAILING_CHECKS)
def test_failed_query_permission_denied_in_log_hints_root(
    make: CheckFactory, missing: str, expected: str
) -> None:
    result = make(failure(DENIED)).run()
    assert not result.passed
    assert "exit 5" in result.detail and "sudo" in result.detail


@pytest.mark.parametrize(("make", "missing", "expected"), FAILING_CHECKS)
def test_failed_query_non_root_warning_in_stderr_hints_root(
    make: CheckFactory, missing: str, expected: str
) -> None:
    result = make("", "WARNING: Running as a non-root user.").run()
    assert "sudo" in result.detail


@pytest.mark.parametrize(("make", "missing", "expected"), FAILING_CHECKS)
def test_failed_query_not_found_in_log_says_missing(
    make: CheckFactory, missing: str, expected: str
) -> None:
    result = make(failure(missing)).run()
    assert not result.passed
    assert expected in result.detail and "sudo" not in result.detail


@pytest.mark.parametrize(("make", "missing", "expected"), FAILING_CHECKS)
def test_failed_query_not_found_only_in_stderr_says_missing(
    make: CheckFactory, missing: str, expected: str
) -> None:
    result = make("not json", missing.upper()).run()
    assert not result.passed
    assert expected in result.detail and "sudo" not in result.detail


@pytest.mark.parametrize(("make", "missing", "expected"), FAILING_CHECKS)
def test_failed_query_unknown_failure_reports_exit_only(
    make: CheckFactory, missing: str, expected: str
) -> None:
    result = make(failure("something odd happened"), "", 3).run()
    assert not result.passed
    assert "exit 3" in result.detail and "sudo" not in result.detail
    assert "does not exist" not in result.detail


@pytest.mark.parametrize(("make", "missing", "expected"), FAILING_CHECKS)
def test_failed_query_permission_wins_over_not_found(
    make: CheckFactory, missing: str, expected: str
) -> None:
    result = make(failure(missing, DENIED)).run()
    assert "sudo" in result.detail


@pytest.mark.parametrize(
    "stdout",
    ["[]", "null", '{"log": "x"}', '{"log": [1, {"log_message": 2}, "x"]}', '{"log": {}}'],
)
def test_failed_query_malformed_log_falls_back_to_stderr(stdout: str) -> None:
    result = vg_check(stdout, 'Volume group "examvg" not found').run()
    assert "does not exist" in result.detail
    assert "exit 5" in vg_check(stdout).run().detail


def test_failed_query_detail_does_not_embed_log_text() -> None:
    result = vg_check(failure("weird\x1b[31m text")).run()
    assert "weird" not in result.detail


def test_mib_constant() -> None:
    assert MIB == 1024 * 1024


def test_checks_satisfy_protocol() -> None:
    checks: list[Check] = [
        VolumeGroupExists(vg_runner(VG_OK), "examvg"),
        PhysicalVolumeInGroup(pv_runner(PV_OK), "/dev/sdb1", "examvg"),
        LogicalVolumeExists(lv_runner(LV_OK), "examvg", "datalv"),
        LogicalVolumeSizeInRange(lv_runner(LV_OK), "examvg", "datalv", 1, 2),
    ]
    assert all(c.describe() for c in checks)


# --- VolumeGroupExists ---


def test_vg_exists_ok() -> None:
    assert VolumeGroupExists(vg_runner(VG_OK), "examvg").run().passed


def test_vg_exists_ok_with_extent_size() -> None:
    assert VolumeGroupExists(vg_runner(VG_OK), "examvg", 16 * MIB).run().passed


def test_vg_extent_size_mismatch_reports_mib() -> None:
    result = VolumeGroupExists(vg_runner(VG_OK), "examvg", 32 * MIB).run()
    assert not result.passed
    assert "16 MiB" in result.detail and "32 MiB" in result.detail


def test_vg_extent_size_mismatch_reports_bytes_when_not_divisible() -> None:
    result = VolumeGroupExists(vg_runner(VG_OK), "examvg", 1000).run()
    assert not result.passed
    assert "1000 bytes" in result.detail


def test_vg_missing_when_no_rows() -> None:
    result = VolumeGroupExists(vg_runner(report("vg", [])), "examvg").run()
    assert not result.passed
    assert "does not exist" in result.detail


def test_vg_failed_command_hints_root() -> None:
    result = VolumeGroupExists(vg_runner(failure(DENIED), 5), "examvg").run()
    assert not result.passed
    assert "exit 5" in result.detail and "sudo" in result.detail


@pytest.mark.parametrize(
    "stdout",
    [
        "not json",
        "[]",
        '{"report": []}',
        '{"report": "x"}',
        '{"report": [{}]}',
        '{"report": [{"vg": "x"}]}',
        '{"report": [{"vg": ["x"]}]}',
        '{"report": [{"vg": [{"vg_name": 1}]}]}',
        report("vg", [{"vg_name": "examvg", "vg_extent_size": "16MiB"}]),
        report("vg", [{"vg_name": "examvg"}]),
    ],
)
def test_vg_malformed_output_is_ko(stdout: str) -> None:
    assert not VolumeGroupExists(vg_runner(stdout), "examvg", 16 * MIB).run().passed


def test_vg_extra_log_key_is_ignored() -> None:
    stdout = json.dumps(
        {
            "report": [{"vg": [{"vg_name": "examvg", "vg_extent_size": str(4 * MIB)}]}],
            "log": [{"log_type": "warning", "log_message": "x"}],
        }
    )
    assert VolumeGroupExists(vg_runner(stdout), "examvg", 4 * MIB).run().passed


@pytest.mark.parametrize("name", ["", "-vg", "..", "a b"])
def test_vg_invalid_name(name: str) -> None:
    with pytest.raises(ValueError):
        VolumeGroupExists(vg_runner(VG_OK), name)


@pytest.mark.parametrize("extent", [0, -1])
def test_vg_invalid_extent_size(extent: int) -> None:
    with pytest.raises(ValueError):
        VolumeGroupExists(vg_runner(VG_OK), "examvg", extent)


# --- PhysicalVolumeInGroup ---


def test_pv_in_group_ok() -> None:
    assert PhysicalVolumeInGroup(pv_runner(PV_OK), "/dev/sdb1", "examvg").run().passed


def test_pv_in_other_group() -> None:
    stdout = report("pv", [{"pv_name": "/dev/sdb1", "vg_name": "othervg"}])
    result = PhysicalVolumeInGroup(pv_runner(stdout), "/dev/sdb1", "examvg").run()
    assert not result.passed and "othervg" in result.detail


def test_pv_without_group() -> None:
    stdout = report("pv", [{"pv_name": "/dev/sdb1", "vg_name": ""}])
    result = PhysicalVolumeInGroup(pv_runner(stdout), "/dev/sdb1", "examvg").run()
    assert not result.passed and "not in any volume group" in result.detail


def test_pv_missing_and_wrong_device() -> None:
    check = PhysicalVolumeInGroup(pv_runner(report("pv", [])), "/dev/sdb1", "examvg")
    assert "is not a physical volume" in check.run().detail
    stdout = report("pv", [{"pv_name": "/dev/sdc1", "vg_name": "examvg"}])
    assert not PhysicalVolumeInGroup(pv_runner(stdout), "/dev/sdb1", "examvg").run().passed


def test_pv_failed_command_hints_root() -> None:
    result = PhysicalVolumeInGroup(pv_runner(failure(DENIED), 5), "/dev/sdb1", "examvg").run()
    assert not result.passed
    assert "exit 5" in result.detail and "sudo" in result.detail


@pytest.mark.parametrize("stdout", ["nope", '{"report": [{"pv": [{"pv_name": "x"}]}]}', "{}"])
def test_pv_malformed_output_is_ko(stdout: str) -> None:
    assert not PhysicalVolumeInGroup(pv_runner(stdout), "/dev/sdb1", "examvg").run().passed


@pytest.mark.parametrize(
    ("device", "vg"),
    [("/etc/sdb1", "examvg"), ("/dev/../x", "examvg"), ("/dev/sdb1", "-vg"), ("", "examvg")],
)
def test_pv_invalid_parameters(device: str, vg: str) -> None:
    with pytest.raises(ValueError):
        PhysicalVolumeInGroup(pv_runner(PV_OK), device, vg)


# --- LogicalVolumeExists ---


def test_lv_exists_ok_and_missing() -> None:
    assert LogicalVolumeExists(lv_runner(LV_OK), "examvg", "datalv").run().passed
    missing = LogicalVolumeExists(lv_runner(report("lv", [])), "examvg", "datalv").run()
    assert not missing.passed and "does not exist" in missing.detail


def test_lv_wrong_row_is_ko() -> None:
    stdout = report("lv", [{"vg_name": "examvg", "lv_name": "other", "lv_size": "1"}])
    assert not LogicalVolumeExists(lv_runner(stdout), "examvg", "datalv").run().passed


def test_lv_failed_command_hints_root() -> None:
    result = LogicalVolumeExists(lv_runner(failure(DENIED), 5), "examvg", "datalv").run()
    assert not result.passed
    assert "exit 5" in result.detail and "sudo" in result.detail


@pytest.mark.parametrize("stdout", ["nope", "[]", '{"report": [{"lv": 3}]}'])
def test_lv_malformed_output_is_ko(stdout: str) -> None:
    assert not LogicalVolumeExists(lv_runner(stdout), "examvg", "datalv").run().passed


@pytest.mark.parametrize(("vg", "lv"), [("-vg", "datalv"), ("examvg", ".."), ("examvg", "a b")])
def test_lv_invalid_parameters(vg: str, lv: str) -> None:
    with pytest.raises(ValueError):
        LogicalVolumeExists(lv_runner(LV_OK), vg, lv)


# --- LogicalVolumeSizeInRange ---


def size_check(
    size: str, min_bytes: int = 960 * MIB, max_bytes: int = 1088 * MIB
) -> LogicalVolumeSizeInRange:
    stdout = report("lv", [{"vg_name": "examvg", "lv_name": "datalv", "lv_size": size}])
    return LogicalVolumeSizeInRange(lv_runner(stdout), "examvg", "datalv", min_bytes, max_bytes)


@pytest.mark.parametrize("size", [960 * MIB, 1024 * MIB, 1088 * MIB])
def test_lv_size_in_range_ok(size: int) -> None:
    assert size_check(str(size)).run().passed


@pytest.mark.parametrize("size", [960 * MIB - 1, 1088 * MIB + 1])
def test_lv_size_out_of_range(size: int) -> None:
    result = size_check(str(size)).run()
    assert not result.passed and "outside" in result.detail


def test_lv_size_missing_lv() -> None:
    check = LogicalVolumeSizeInRange(
        lv_runner(report("lv", [])), "examvg", "datalv", 1, 2
    )
    assert "does not exist" in check.run().detail


def test_lv_size_failed_command_hints_root() -> None:
    check = LogicalVolumeSizeInRange(lv_runner(failure(DENIED), 5), "examvg", "datalv", 1, 2)
    result = check.run()
    assert not result.passed and "exit 5" in result.detail and "sudo" in result.detail


@pytest.mark.parametrize("size", ["", "abc", "1.5", "-5", "1024B", "12 "])
def test_lv_size_non_numeric_is_ko(size: str) -> None:
    assert not size_check(size).run().passed


def test_lv_size_malformed_output_is_ko() -> None:
    check = LogicalVolumeSizeInRange(lv_runner("nope"), "examvg", "datalv", 1, 2)
    assert not check.run().passed


@pytest.mark.parametrize(("low", "high"), [(0, 5), (-1, 5), (10, 5)])
def test_lv_size_invalid_bounds(low: int, high: int) -> None:
    with pytest.raises(ValueError):
        LogicalVolumeSizeInRange(lv_runner(LV_OK), "examvg", "datalv", low, high)


def test_lv_size_invalid_names() -> None:
    with pytest.raises(ValueError):
        LogicalVolumeSizeInRange(lv_runner(LV_OK), "-vg", "datalv", 1, 2)

from __future__ import annotations

import json
from dataclasses import dataclass

from rhcsa_sim.checks._validation import validate_block_device, validate_lvm_name
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandResult, CommandRunner

MIB = 1024 * 1024

Row = dict[str, str]


def _parse_report(stdout: str, section: str) -> list[Row] | None:
    """Extrae las filas de una seccion del JSON de LVM. None si la forma es inesperada."""
    try:
        data = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    reports = data.get("report")
    if not isinstance(reports, list) or not reports:
        return None
    first = reports[0]
    if not isinstance(first, dict):
        return None
    rows = first.get(section)
    if not isinstance(rows, list):
        return None
    parsed: list[Row] = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        clean: Row = {}
        for key, value in row.items():
            if not isinstance(key, str) or not isinstance(value, str):
                return None
            clean[key] = value
        parsed.append(clean)
    return parsed


def _parse_bytes(text: str) -> int | None:
    if not text or not text.isascii() or not text.isdigit():
        return None
    return int(text)


def _format_size(value: int) -> str:
    if value % MIB == 0:
        return f"{value // MIB} MiB"
    return f"{value} bytes"


def _query_failed(what: str, result: CommandResult) -> CheckResult:
    return CheckResult(
        False,
        f"cannot query {what} (exit {result.returncode}); LVM checks require root (run with sudo)",
    )


def _query(
    runner: CommandRunner, argv: list[str], section: str, what: str
) -> list[Row] | CheckResult:
    """Ejecuta una consulta LVM; devuelve las filas o un CheckResult KO."""
    result = runner.run(argv)
    if not result.ok:
        return _query_failed(what, result)
    rows = _parse_report(result.stdout, section)
    if rows is None:
        return CheckResult(False, f"unexpected LVM output while querying {what}")
    return rows


def _query_vg(runner: CommandRunner, vg: str) -> list[Row] | CheckResult:
    argv = [
        "vgs", "--reportformat", "json", "--units", "b", "--nosuffix",
        "-o", "vg_name,vg_extent_size", "--", vg,
    ]  # fmt: skip
    return _query(runner, argv, "vg", f"volume group '{vg}'")


def _query_pv(runner: CommandRunner, device: str) -> list[Row] | CheckResult:
    argv = ["pvs", "--reportformat", "json", "-o", "pv_name,vg_name", "--", device]
    return _query(runner, argv, "pv", f"physical volume '{device}'")


def _query_lv(runner: CommandRunner, vg: str, lv: str) -> list[Row] | CheckResult:
    argv = [
        "lvs", "--reportformat", "json", "--units", "b", "--nosuffix",
        "-o", "vg_name,lv_name,lv_size", "--", f"{vg}/{lv}",
    ]  # fmt: skip
    return _query(runner, argv, "lv", f"logical volume '{vg}/{lv}'")


@dataclass(frozen=True, slots=True)
class VolumeGroupExists:
    runner: CommandRunner
    name: str
    extent_size: int | None = None

    def __post_init__(self) -> None:
        validate_lvm_name(self.name)
        if self.extent_size is not None and self.extent_size <= 0:
            raise ValueError("extent_size must be positive")

    def describe(self) -> str:
        if self.extent_size is None:
            return f"volume group {self.name} exists"
        return f"volume group {self.name} exists with {_format_size(self.extent_size)} extents"

    def run(self) -> CheckResult:
        rows = _query_vg(self.runner, self.name)
        if isinstance(rows, CheckResult):
            return rows
        if not rows or rows[0].get("vg_name") != self.name:
            return CheckResult(False, f"volume group '{self.name}' does not exist")
        if self.extent_size is None:
            return CheckResult(True, f"volume group '{self.name}' exists")
        actual = _parse_bytes(rows[0].get("vg_extent_size", ""))
        if actual is None:
            return CheckResult(False, "unexpected extent size in LVM output")
        if actual != self.extent_size:
            return CheckResult(
                False,
                f"extent size is {_format_size(actual)}, expected {_format_size(self.extent_size)}",
            )
        return CheckResult(True, f"extent size is {_format_size(actual)}")


@dataclass(frozen=True, slots=True)
class PhysicalVolumeInGroup:
    runner: CommandRunner
    device: str
    vg: str

    def __post_init__(self) -> None:
        validate_block_device(self.device)
        validate_lvm_name(self.vg)

    def describe(self) -> str:
        return f"{self.device} is a physical volume in {self.vg}"

    def run(self) -> CheckResult:
        rows = _query_pv(self.runner, self.device)
        if isinstance(rows, CheckResult):
            return rows
        if not rows or rows[0].get("pv_name") != self.device:
            return CheckResult(False, f"'{self.device}' is not a physical volume")
        actual = rows[0].get("vg_name", "")
        if not actual:
            return CheckResult(False, f"'{self.device}' is not in any volume group")
        if actual != self.vg:
            return CheckResult(False, f"volume group is '{actual}', expected '{self.vg}'")
        return CheckResult(True, f"'{self.device}' is in volume group '{self.vg}'")


@dataclass(frozen=True, slots=True)
class LogicalVolumeExists:
    runner: CommandRunner
    vg: str
    lv: str

    def __post_init__(self) -> None:
        validate_lvm_name(self.vg)
        validate_lvm_name(self.lv)

    def describe(self) -> str:
        return f"logical volume {self.vg}/{self.lv} exists"

    def run(self) -> CheckResult:
        rows = _query_lv(self.runner, self.vg, self.lv)
        if isinstance(rows, CheckResult):
            return rows
        if not rows or rows[0].get("lv_name") != self.lv:
            return CheckResult(False, f"logical volume '{self.vg}/{self.lv}' does not exist")
        return CheckResult(True, f"logical volume '{self.vg}/{self.lv}' exists")


@dataclass(frozen=True, slots=True)
class LogicalVolumeSizeInRange:
    runner: CommandRunner
    vg: str
    lv: str
    min_bytes: int
    max_bytes: int

    def __post_init__(self) -> None:
        validate_lvm_name(self.vg)
        validate_lvm_name(self.lv)
        if not 0 < self.min_bytes <= self.max_bytes:
            raise ValueError("size bounds must satisfy 0 < min_bytes <= max_bytes")

    def describe(self) -> str:
        low, high = _format_size(self.min_bytes), _format_size(self.max_bytes)
        return f"logical volume {self.vg}/{self.lv} size is between {low} and {high}"

    def run(self) -> CheckResult:
        rows = _query_lv(self.runner, self.vg, self.lv)
        if isinstance(rows, CheckResult):
            return rows
        if not rows or rows[0].get("lv_name") != self.lv:
            return CheckResult(False, f"logical volume '{self.vg}/{self.lv}' does not exist")
        size = _parse_bytes(rows[0].get("lv_size", ""))
        if size is None:
            return CheckResult(False, "unexpected logical volume size in LVM output")
        if not self.min_bytes <= size <= self.max_bytes:
            low, high = _format_size(self.min_bytes), _format_size(self.max_bytes)
            return CheckResult(
                False, f"size is {_format_size(size)}, outside {low} - {high}"
            )
        return CheckResult(True, f"size is {_format_size(size)}")

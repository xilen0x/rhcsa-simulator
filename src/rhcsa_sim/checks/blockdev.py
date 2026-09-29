from __future__ import annotations

import json
from dataclasses import dataclass

from rhcsa_sim.checks._units import format_size
from rhcsa_sim.checks._findmnt import COLUMNS, parse_findmnt
from rhcsa_sim.checks._validation import validate_block_device, validate_uuid
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner

_LSBLK_COLUMNS = "PATH,KNAME,SIZE,TYPE,FSTYPE,UUID,PARTTYPENAME"
_NOT_A_BLOCK_DEVICE = "not a block device"
_LSBLK_MISSING_RC = 32
_SWAPON_ARGV = ["swapon", "--show=NAME,SIZE", "--bytes", "--noheadings", "--raw"]
_UUID_PREFIX = "UUID="


@dataclass(frozen=True, slots=True)
class BlockDevice:
    path: str
    kname: str
    size: int
    type: str
    fstype: str | None
    uuid: str | None
    parttypename: str | None


def _opt_str(value: object) -> tuple[bool, str | None]:
    """(valido, valor): null es valido y vale None."""
    if value is None or isinstance(value, str):
        return True, value
    return False, None


def _parse_row(entry: object) -> BlockDevice | None:
    if not isinstance(entry, dict):
        return None
    path, kname, kind, size = (entry.get(k) for k in ("path", "kname", "type", "size"))
    if not isinstance(path, str) or not isinstance(kname, str) or not isinstance(kind, str):
        return None
    # bool es subclase de int: se rechaza a mano
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        return None
    optional: list[str | None] = []
    for key in ("fstype", "uuid", "parttypename"):
        valid, value = _opt_str(entry.get(key))
        if not valid:
            return None
        optional.append(value)
    return BlockDevice(path, kname, size, kind, optional[0], optional[1], optional[2])


def _parse_lsblk(stdout: str, device: str) -> BlockDevice | None:
    """Fila cuyo path es el dispositivo pedido (lsblk incluye tambien los hijos)."""
    try:
        data = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    entries = data.get("blockdevices")
    if not isinstance(entries, list):
        return None
    rows = [_parse_row(entry) for entry in entries]
    if any(row is None for row in rows):
        return None
    for row in rows:
        if row is not None and row.path == device:
            return row
    return None


def _query_device(runner: CommandRunner, device: str) -> BlockDevice | CheckResult:
    argv = ["lsblk", "-J", "-l", "-b", "-o", _LSBLK_COLUMNS, "--", device]
    result = runner.run(argv)
    if result.returncode == _LSBLK_MISSING_RC or _NOT_A_BLOCK_DEVICE in result.stderr:
        return CheckResult(False, f"'{device}' does not exist")
    if not result.ok:
        return CheckResult(
            False, f"cannot query block device '{device}' (exit {result.returncode})"
        )
    row = _parse_lsblk(result.stdout, device)
    if row is None:
        return CheckResult(False, f"unexpected lsblk output for '{device}'")
    return row


@dataclass(frozen=True, slots=True)
class PartitionExists:
    runner: CommandRunner
    device: str
    min_bytes: int
    max_bytes: int

    def __post_init__(self) -> None:
        validate_block_device(self.device)
        for value in (self.min_bytes, self.max_bytes):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"size bounds must be integers: {value!r}")
        if not 0 < self.min_bytes <= self.max_bytes:
            raise ValueError(f"invalid size range: {self.min_bytes!r}-{self.max_bytes!r}")

    def describe(self) -> str:
        low, high = format_size(self.min_bytes), format_size(self.max_bytes)
        return f"{self.device} is a partition between {low} and {high}"

    def run(self) -> CheckResult:
        row = _query_device(self.runner, self.device)
        if isinstance(row, CheckResult):
            return row
        if row.type != "part":
            return CheckResult(False, f"'{self.device}' is a {row.type}, not a partition")
        if not self.min_bytes <= row.size <= self.max_bytes:
            low, high = format_size(self.min_bytes), format_size(self.max_bytes)
            return CheckResult(
                False, f"size is {format_size(row.size)}, outside {low} - {high}"
            )
        return CheckResult(True, f"'{self.device}' is a partition of {format_size(row.size)}")


def _query_swaps(runner: CommandRunner) -> set[str] | CheckResult:
    """Nombres (/dev/...) de los swaps activos; salida vacia = ninguno."""
    result = runner.run(_SWAPON_ARGV)
    if not result.ok:
        return CheckResult(False, f"cannot query active swap (exit {result.returncode})")
    names: set[str] = set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2 or not fields[1].isascii() or not fields[1].isdigit():
            return CheckResult(False, "unexpected swapon output while querying active swap")
        names.add(fields[0])
    return names


@dataclass(frozen=True, slots=True)
class SwapActive:
    runner: CommandRunner
    device: str

    def __post_init__(self) -> None:
        validate_block_device(self.device)

    def describe(self) -> str:
        return f"{self.device} is formatted as swap and active"

    def run(self) -> CheckResult:
        row = _query_device(self.runner, self.device)
        if isinstance(row, CheckResult):
            return row
        if row.fstype != "swap":
            return CheckResult(
                False, f"'{self.device}' is not formatted as swap (fstype: {row.fstype})"
            )
        active = _query_swaps(self.runner)
        if isinstance(active, CheckResult):
            return active
        # swapon lista nombres del kernel (/dev/dm-1), no rutas de /dev/mapper
        if f"/dev/{row.kname}" not in active:
            return CheckResult(False, f"'{self.device}' is not an active swap (run swapon)")
        return CheckResult(True, f"'{self.device}' is an active swap")


@dataclass(frozen=True, slots=True)
class SwapInFstabByUuid:
    runner: CommandRunner
    device: str

    def __post_init__(self) -> None:
        validate_block_device(self.device)

    def describe(self) -> str:
        return f"{self.device} has a persistent swap entry by UUID in /etc/fstab"

    def run(self) -> CheckResult:
        row = _query_device(self.runner, self.device)
        if isinstance(row, CheckResult):
            return row
        if row.uuid is None:
            return CheckResult(False, f"'{self.device}' has no UUID")
        try:
            uuid = validate_uuid(row.uuid)
        except ValueError:
            return CheckResult(False, f"'{self.device}' has a malformed UUID")
        argv = ["findmnt", "-J", "--fstab", "-t", "swap", "-o", COLUMNS]
        result = self.runner.run(argv)
        if result.returncode == 1 and not result.stdout.strip():
            return CheckResult(False, "no swap entries in /etc/fstab")
        if not result.ok:
            return CheckResult(False, f"cannot query /etc/fstab (exit {result.returncode})")
        entries = parse_findmnt(result.stdout)
        if entries is None:
            return CheckResult(False, "unexpected findmnt output while querying /etc/fstab")
        swaps = [entry["source"] for entry in entries if entry["fstype"] == "swap"]
        if not swaps:
            return CheckResult(False, "no swap entries in /etc/fstab")
        wanted = f"{_UUID_PREFIX}{uuid}".lower()
        if any(source.lower() == wanted for source in swaps):
            return CheckResult(True, f"fstab has a swap entry for {_UUID_PREFIX}{uuid}")
        if self.device in swaps:
            return CheckResult(
                False, f"fstab references '{self.device}' by path; use {_UUID_PREFIX}{uuid}"
            )
        return CheckResult(False, f"no fstab swap entry for {_UUID_PREFIX}{uuid}")

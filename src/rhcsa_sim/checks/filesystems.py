from __future__ import annotations

from dataclasses import dataclass

from rhcsa_sim.checks._findmnt import COLUMNS, Row, parse_findmnt
from rhcsa_sim.checks._validation import (
    validate_absolute_path,
    validate_block_device,
    validate_fstype,
    validate_uuid,
)
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandResult, CommandRunner

_UUID_PREFIX = "UUID="


def _query_failed(what: str, result: CommandResult) -> CheckResult:
    return CheckResult(False, f"cannot query {what} (exit {result.returncode})")


def _findmnt(
    runner: CommandRunner, target: str, fstab: bool, absent: str
) -> Row | CheckResult:
    """Consulta findmnt; rc 1 sin salida significa "no hay entrada" (KO normal)."""
    argv = ["findmnt", "-J"]
    if fstab:
        argv.append("--fstab")
    argv += ["-o", COLUMNS, f"--mountpoint={target}"]
    what = "/etc/fstab" if fstab else f"mount of '{target}'"
    result = runner.run(argv)
    if result.returncode == 1 and not result.stdout.strip():
        return CheckResult(False, absent)
    if not result.ok:
        return _query_failed(what, result)
    rows = parse_findmnt(result.stdout)
    if rows is None:
        return CheckResult(False, f"unexpected findmnt output while querying {what}")
    if not rows:
        return CheckResult(False, absent)
    # con montajes apilados o entradas repetidas manda la ultima
    return rows[-1]


def _query_mount(runner: CommandRunner, target: str) -> Row | CheckResult:
    return _findmnt(runner, target, False, f"'{target}' is not mounted")


def _query_fstab(runner: CommandRunner, target: str) -> Row | CheckResult:
    return _findmnt(runner, target, True, f"no fstab entry for '{target}'")


def _fstab_uuid(target: str, row: Row) -> str | CheckResult:
    """UUID escrito en la entrada de fstab, o un KO si no usa UUID= valido."""
    source = row["source"]
    if not source.startswith(_UUID_PREFIX):
        return CheckResult(False, f"fstab entry for '{target}' does not use UUID=")
    value = source[len(_UUID_PREFIX) :]
    try:
        return validate_uuid(value)
    except ValueError:
        return CheckResult(False, f"fstab entry for '{target}' has a malformed UUID")


def _fstype_mismatch(row: Row, expected: str | None) -> CheckResult | None:
    if expected is not None and row["fstype"] != expected:
        return CheckResult(False, f"filesystem type is {row['fstype']}, expected {expected}")
    return None


def _query_device_uuid(runner: CommandRunner, device: str) -> str | CheckResult:
    argv = ["blkid", "-o", "value", "-s", "UUID", "--", device]
    result = runner.run(argv)
    if result.returncode == 2 and not result.stdout.strip():
        return CheckResult(
            False, f"'{device}' has no UUID (if not running as root, retry with sudo)"
        )
    if not result.ok:
        return _query_failed(f"UUID of '{device}'", result)
    try:
        return validate_uuid(result.stdout.strip())
    except ValueError:
        return CheckResult(False, f"unexpected blkid output for '{device}'")


@dataclass(frozen=True, slots=True)
class MountedAt:
    runner: CommandRunner
    target: str
    fstype: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        validate_absolute_path(self.target)
        if self.fstype is not None:
            validate_fstype(self.fstype)
        if self.source is not None:
            validate_block_device(self.source)

    def describe(self) -> str:
        text = f"{self.target} is mounted"
        if self.fstype is not None:
            text += f" as {self.fstype}"
        if self.source is not None:
            text += f" from {self.source}"
        return text

    def run(self) -> CheckResult:
        row = _query_mount(self.runner, self.target)
        if isinstance(row, CheckResult):
            return row
        mismatch = _fstype_mismatch(row, self.fstype)
        if mismatch is not None:
            return mismatch
        if self.source is not None and row["source"] != self.source:
            return CheckResult(
                False, f"mounted source is {row['source']}, expected {self.source}"
            )
        return CheckResult(True, f"'{self.target}' is mounted ({row['fstype']})")


@dataclass(frozen=True, slots=True)
class FstabMountByUuid:
    runner: CommandRunner
    target: str
    fstype: str | None = None

    def __post_init__(self) -> None:
        validate_absolute_path(self.target)
        if self.fstype is not None:
            validate_fstype(self.fstype)

    def describe(self) -> str:
        return f"{self.target} has a persistent mount by UUID in /etc/fstab"

    def run(self) -> CheckResult:
        row = _query_fstab(self.runner, self.target)
        if isinstance(row, CheckResult):
            return row
        uuid = _fstab_uuid(self.target, row)
        if isinstance(uuid, CheckResult):
            return uuid
        mismatch = _fstype_mismatch(row, self.fstype)
        if mismatch is not None:
            return mismatch
        return CheckResult(True, f"fstab entry for '{self.target}' uses UUID={uuid}")


@dataclass(frozen=True, slots=True)
class FstabUuidMatchesMount:
    runner: CommandRunner
    target: str

    def __post_init__(self) -> None:
        validate_absolute_path(self.target)

    def describe(self) -> str:
        return f"the fstab UUID for {self.target} matches the mounted device"

    def run(self) -> CheckResult:
        fstab_row = _query_fstab(self.runner, self.target)
        if isinstance(fstab_row, CheckResult):
            return fstab_row
        expected = _fstab_uuid(self.target, fstab_row)
        if isinstance(expected, CheckResult):
            return expected
        mount_row = _query_mount(self.runner, self.target)
        if isinstance(mount_row, CheckResult):
            return mount_row
        device = mount_row["source"]
        try:
            validate_block_device(device)
        except ValueError:
            return CheckResult(False, f"mounted source of '{self.target}' is not a block device")
        actual = _query_device_uuid(self.runner, device)
        if isinstance(actual, CheckResult):
            return actual
        if actual.lower() != expected.lower():
            return CheckResult(
                False, f"fstab UUID is {expected}, but the mounted device has {actual}"
            )
        return CheckResult(True, f"fstab UUID matches the mounted device ({actual})")

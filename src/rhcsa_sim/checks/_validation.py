from __future__ import annotations

import re

_ACCOUNT_NAME_RE = re.compile(r"[a-z_][a-z0-9_-]{0,31}")
_LVM_NAME_RE = re.compile(r"[A-Za-z0-9+_.][A-Za-z0-9+_.-]{0,126}")
_BLOCK_DEVICE_RE = re.compile(r"/dev/[A-Za-z0-9_][A-Za-z0-9_./:-]*")
_FSTYPE_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,31}")
_UUID_RE = re.compile(
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
    r"|[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}"
)
_ACL_PERMS = r"[r-][w-][x-]"
_ACL_ENTRY_RE = re.compile(
    rf"(?:default:)?(?:(?:user|group):(?:[a-z_][a-z0-9_-]{{0,31}})?|(?:mask|other):):"
    rf"{_ACL_PERMS}"
)


def validate_account_name(name: str) -> str:
    if not _ACCOUNT_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid user/group name: {name!r}")
    return name


def validate_absolute_path(path: str) -> str:
    if not path.startswith("/") or "\x00" in path or "\n" in path:
        raise ValueError(f"path must be absolute and free of control chars: {path!r}")
    return path


def validate_lvm_name(name: str) -> str:
    """Nombres de VG/LV: sin '-' inicial y distintos de '.' y '..'."""
    if not _LVM_NAME_RE.fullmatch(name) or name in {".", ".."}:
        raise ValueError(f"invalid LVM name: {name!r}")
    return name


def validate_block_device(path: str) -> str:
    if not _BLOCK_DEVICE_RE.fullmatch(path) or ".." in path.split("/"):
        raise ValueError(f"invalid block device path: {path!r}")
    return path


def validate_fstype(name: str) -> str:
    if not _FSTYPE_RE.fullmatch(name):
        raise ValueError(f"invalid filesystem type: {name!r}")
    return name


def validate_uuid(value: str) -> str:
    """UUID de sistema de archivos: forma larga o corta de vfat (XXXX-XXXX)."""
    if not _UUID_RE.fullmatch(value):
        raise ValueError(f"invalid filesystem UUID: {value!r}")
    return value


def validate_acl_entry(entry: str) -> str:
    """Entrada ACL en formato getfacl: [default:]user|group:<nombre>:rwx o mask|other::rwx."""
    if not _ACL_ENTRY_RE.fullmatch(entry):
        raise ValueError(f"invalid ACL entry: {entry!r}")
    return entry

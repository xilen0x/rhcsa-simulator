from __future__ import annotations

import re

_ACCOUNT_NAME_RE = re.compile(r"[a-z_][a-z0-9_-]{0,31}")


def validate_account_name(name: str) -> str:
    if not _ACCOUNT_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid user/group name: {name!r}")
    return name


def validate_absolute_path(path: str) -> str:
    if not path.startswith("/") or "\x00" in path or "\n" in path:
        raise ValueError(f"path must be absolute and free of control chars: {path!r}")
    return path

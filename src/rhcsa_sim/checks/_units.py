from __future__ import annotations

MIB = 1024 * 1024


def format_size(value: int) -> str:
    """Tamano legible: MiB exactos o bytes."""
    if value % MIB == 0:
        return f"{value // MIB} MiB"
    return f"{value} bytes"

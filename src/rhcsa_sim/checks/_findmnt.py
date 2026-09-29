from __future__ import annotations

import json

Row = dict[str, str]

COLUMNS = "TARGET,SOURCE,FSTYPE,OPTIONS"
_REQUIRED_COLUMNS = ("source", "fstype")


def parse_findmnt(stdout: str) -> list[Row] | None:
    """Extrae las filas del JSON de findmnt. None si la forma es inesperada."""
    try:
        data = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    entries = data.get("filesystems")
    if not isinstance(entries, list):
        return None
    rows: list[Row] = []
    for entry in entries:
        if not isinstance(entry, dict):
            return None
        # solo se exigen strings en las columnas que usan los checks;
        # el resto puede venir null o faltar segun la version de util-linux
        row: Row = {}
        for key in _REQUIRED_COLUMNS:
            value = entry.get(key)
            if not isinstance(value, str):
                return None
            row[key] = value
        rows.append(row)
    return rows

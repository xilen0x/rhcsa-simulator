from __future__ import annotations

import re
from dataclasses import dataclass

from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner

_NOT_FOUND = 127
_NO_FLATPAK = "flatpak is not installed"
# id de aplicacion en notacion DNS inversa (org.gnome.TextEditor); sin '-' inicial
_APP_ID_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+)+")
_REMOTE_NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")


def _validate_remote_name(name: str) -> str:
    if not _REMOTE_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid flatpak remote name: {name!r}")
    return name


def _validate_url(url: str) -> str:
    if not url or any(c.isspace() or c == "\x00" for c in url):
        raise ValueError(f"invalid remote url: {url!r}")
    return url


def _validate_app_id(app_id: str) -> str:
    if not _APP_ID_RE.fullmatch(app_id):
        raise ValueError(f"invalid flatpak application id: {app_id!r}")
    return app_id


def _same_url(a: str, b: str) -> bool:
    return a.rstrip("/") == b.rstrip("/")


@dataclass(frozen=True, slots=True)
class FlatpakRemote:
    """Remoto Flatpak a nivel de sistema; con `url`, ademas debe apuntar a esa URL
    (se ignora una '/' final)."""

    runner: CommandRunner
    name: str
    url: str | None = None

    def __post_init__(self) -> None:
        _validate_remote_name(self.name)
        if self.url is not None:
            _validate_url(self.url)

    def describe(self) -> str:
        suffix = f" with url {self.url}" if self.url is not None else ""
        return f"flatpak system remote {self.name} is configured{suffix}"

    def run(self) -> CheckResult:
        result = self.runner.run(["flatpak", "remotes", "--system", "--columns=name,url"])
        if result.returncode == _NOT_FOUND:
            return CheckResult(False, _NO_FLATPAK)
        if not result.ok:
            return CheckResult(False, "cannot list flatpak remotes")
        for line in result.stdout.splitlines():
            columns = line.split("\t")
            if columns[0] != self.name:
                continue
            if self.url is None:
                return CheckResult(True, f"remote '{self.name}' is configured")
            actual = columns[1].strip() if len(columns) > 1 else ""
            if _same_url(actual, self.url):
                return CheckResult(True, f"remote '{self.name}' points to {actual}")
            return CheckResult(
                False, f"remote '{self.name}' url is '{actual}', expected '{self.url}'"
            )
        return CheckResult(False, f"remote '{self.name}' is not configured")


@dataclass(frozen=True, slots=True)
class FlatpakAppInstalled:
    """Aplicacion Flatpak instalada a nivel de sistema (`flatpak info` rc 0 / 1)."""

    runner: CommandRunner
    app_id: str

    def __post_init__(self) -> None:
        _validate_app_id(self.app_id)

    def describe(self) -> str:
        return f"flatpak application {self.app_id} is installed system-wide"

    def run(self) -> CheckResult:
        result = self.runner.run(["flatpak", "info", "--system", "--", self.app_id])
        if result.returncode == _NOT_FOUND:
            return CheckResult(False, _NO_FLATPAK)
        if result.ok:
            return CheckResult(True, f"'{self.app_id}' is installed")
        return CheckResult(False, f"'{self.app_id}' is not installed")

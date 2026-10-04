from __future__ import annotations

import pytest

from rhcsa_sim.checks.flatpak import FlatpakAppInstalled, FlatpakRemote
from rhcsa_sim.models import Check
from rhcsa_sim.testing import FakeCommandRunner, make_result

REMOTES = ("flatpak", "remotes", "--system", "--columns=name,url")
# salida real observada: "flathub<TAB>https://dl.flathub.org/repo/"
REMOTES_OUT = "flathub\thttps://dl.flathub.org/repo/\n"
APP = "org.gnome.TextEditor"
INFO = ("flatpak", "info", "--system", "--", APP)
INFO_OUT = "Text Editor - Edit text files\n\n          ID: org.gnome.TextEditor\n"
# stderr real observado con rc 1
NOT_INSTALLED = "error: org.gnome.TextEditor/*unspecified*/*unspecified* not installed\n"


def fake(cmd: tuple[str, ...], returncode: int = 0, stdout: str = "", stderr: str = "") -> FakeCommandRunner:
    return FakeCommandRunner(
        {cmd: make_result(cmd, returncode=returncode, stdout=stdout, stderr=stderr)}
    )


def test_checks_satisfy_protocol() -> None:
    checks: list[Check] = [FlatpakRemote(fake(REMOTES), "flathub"), FlatpakAppInstalled(fake(INFO), APP)]
    assert [c.describe() for c in checks]


# --- FlatpakRemote ---


def test_remote_ok_by_name_only() -> None:
    assert FlatpakRemote(fake(REMOTES, stdout=REMOTES_OUT), "flathub").run().passed


def test_remote_ok_with_url_ignoring_trailing_slash() -> None:
    runner = fake(REMOTES, stdout=REMOTES_OUT)
    assert FlatpakRemote(runner, "flathub", "https://dl.flathub.org/repo/").run().passed
    assert FlatpakRemote(runner, "flathub", "https://dl.flathub.org/repo").run().passed
    other = fake(REMOTES, stdout="flathub\thttps://dl.flathub.org/repo\n")
    assert FlatpakRemote(other, "flathub", "https://dl.flathub.org/repo/").run().passed


def test_remote_ko_wrong_url() -> None:
    result = FlatpakRemote(
        fake(REMOTES, stdout="flathub\thttps://evil.example.com/repo/\n"),
        "flathub",
        "https://dl.flathub.org/repo/",
    ).run()
    assert not result.passed and "evil.example.com" in result.detail


def test_remote_ko_missing() -> None:
    result = FlatpakRemote(fake(REMOTES, stdout="other\thttps://x.example/\n"), "flathub").run()
    assert not result.passed and "not configured" in result.detail
    assert not FlatpakRemote(fake(REMOTES, stdout=""), "flathub").run().passed


def test_remote_ko_flatpak_missing() -> None:
    result = FlatpakRemote(fake(REMOTES, 127), "flathub").run()
    assert not result.passed and "flatpak is not installed" in result.detail


def test_remote_ko_command_failed() -> None:
    assert not FlatpakRemote(fake(REMOTES, 1, stderr="boom"), "flathub").run().passed


@pytest.mark.parametrize("name", ["", "a b", "-x", "a\tb", "a\nb"])
def test_remote_rejects_invalid_name(name: str) -> None:
    with pytest.raises(ValueError):
        FlatpakRemote(fake(REMOTES), name)


def test_remote_rejects_invalid_url() -> None:
    with pytest.raises(ValueError):
        FlatpakRemote(fake(REMOTES), "flathub", "")
    with pytest.raises(ValueError):
        FlatpakRemote(fake(REMOTES), "flathub", "a\tb")


# --- FlatpakAppInstalled ---


def test_app_ok() -> None:
    assert FlatpakAppInstalled(fake(INFO, stdout=INFO_OUT), APP).run().passed


def test_app_ko_not_installed() -> None:
    result = FlatpakAppInstalled(fake(INFO, 1, stderr=NOT_INSTALLED), APP).run()
    assert not result.passed and "not installed" in result.detail


def test_app_ko_flatpak_missing() -> None:
    result = FlatpakAppInstalled(fake(INFO, 127), APP).run()
    assert not result.passed and "flatpak is not installed" in result.detail


@pytest.mark.parametrize(
    "app_id", ["", "-bad", "--help", "nodots", "a..b", "a b.c", "org.x;rm", "org.x\n"]
)
def test_app_rejects_invalid_id(app_id: str) -> None:
    with pytest.raises(ValueError):
        FlatpakAppInstalled(fake(INFO), app_id)

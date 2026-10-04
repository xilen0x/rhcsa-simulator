from __future__ import annotations

import pytest

from rhcsa_sim.checks.autofs import AutofsMapEntry, AutofsMasterEntry
from rhcsa_sim.models import Check
from rhcsa_sim.runner import CommandResult
from rhcsa_sim.testing import FakeCommandRunner, make_result

MASTER = ("cat", "--", "/etc/auto.master")
FIND = ("find", "/etc/auto.master.d", "-maxdepth", "1", "-name", "*.autofs")
REMOTE_AUTOFS = "/etc/auto.master.d/remote.autofs"
CAT_REMOTE = ("cat", "--", REMOTE_AUTOFS)
MAP = ("cat", "--", "/etc/auto.remote")

# /etc/auto.master real de RHEL 10 (recortado)
STOCK_MASTER = (
    "#\n# Sample auto.master file\n#\n/misc\t/etc/auto.misc\n#\n/net\t-hosts\n#\n"
    "+dir:/etc/auto.master.d\n#\n+auto.master\n"
)


def res(cmd: tuple[str, ...], out: str, rc: int = 0) -> CommandResult:
    return make_result(cmd, returncode=rc, stdout=out)


def master_runner(
    master: str = STOCK_MASTER,
    found: str = "",
    files: dict[str, str] | None = None,
    master_rc: int = 0,
    find_rc: int = 0,
) -> FakeCommandRunner:
    responses = {MASTER: res(MASTER, master, master_rc), FIND: res(FIND, found, find_rc)}
    for path, text in (files or {}).items():
        cmd = ("cat", "--", path)
        responses[cmd] = res(cmd, text)
    return FakeCommandRunner(responses)


def entry(runner: FakeCommandRunner) -> AutofsMasterEntry:
    return AutofsMasterEntry(runner, "/remote", "/etc/auto.remote")


def test_autofs_checks_satisfy_protocol() -> None:
    checks: list[Check] = [
        entry(master_runner()),
        AutofsMapEntry(master_runner(), "/etc/auto.remote", "data", "h:/x", "nfs4"),
    ]
    assert all(c.describe() for c in checks)


def test_master_entry_in_auto_master() -> None:
    runner = master_runner(STOCK_MASTER + "/remote\t/etc/auto.remote\t--timeout=60\n")
    assert entry(runner).run().passed


def test_master_entry_in_master_d_file() -> None:
    runner = master_runner(
        found=REMOTE_AUTOFS + "\n",
        files={REMOTE_AUTOFS: "/remote /etc/auto.remote\n"},
    )
    assert entry(runner).run().passed


def test_master_entry_missing() -> None:
    result = entry(master_runner()).run()
    assert not result.passed and "/remote" in result.detail


def test_master_entry_ignores_comments_and_wrong_map() -> None:
    assert not entry(master_runner("#/remote /etc/auto.remote\n")).run().passed
    assert not entry(master_runner("/remote /etc/auto.other\n")).run().passed
    assert not entry(master_runner("/remote2 /etc/auto.remote\n")).run().passed


def test_master_entry_tolerates_missing_master_d() -> None:
    runner = master_runner("/remote /etc/auto.remote\n", find_rc=1)
    assert entry(runner).run().passed


def test_master_entry_fails_when_master_unreadable() -> None:
    result = entry(master_runner(master_rc=1)).run()
    assert not result.passed and "/etc/auto.master" in result.detail


def test_master_entry_skips_unreadable_extra_file() -> None:
    # el fichero listado por find no tiene respuesta cat -> error de lectura, KO sin crash
    runner = FakeCommandRunner(
        {
            MASTER: res(MASTER, STOCK_MASTER),
            FIND: res(FIND, REMOTE_AUTOFS + "\n"),
            CAT_REMOTE: res(CAT_REMOTE, "", 1),
        }
    )
    assert not entry(runner).run().passed


@pytest.mark.parametrize(
    ("mount_point", "map_file"), [("remote", "/etc/auto.remote"), ("/remote", "auto.remote")]
)
def test_master_entry_rejects_relative_paths(mount_point: str, map_file: str) -> None:
    with pytest.raises(ValueError):
        AutofsMasterEntry(master_runner(), mount_point, map_file)


MAP_TEXT = "# comment\ndata\t-fstype=nfs4,rw\tlocalhost:/srv/nfsexport\n"


def map_runner(text: str, rc: int = 0) -> FakeCommandRunner:
    return FakeCommandRunner({MAP: res(MAP, text, rc)})


def map_entry(runner: FakeCommandRunner, fstype: str | None = "nfs4") -> AutofsMapEntry:
    return AutofsMapEntry(runner, "/etc/auto.remote", "data", "localhost:/srv/nfsexport", fstype)


def test_map_entry_passes() -> None:
    assert map_entry(map_runner(MAP_TEXT)).run().passed


def test_map_entry_without_fstype_requirement() -> None:
    assert map_entry(map_runner("data localhost:/srv/nfsexport\n"), None).run().passed


def test_map_entry_fstype_among_other_options() -> None:
    assert map_entry(map_runner("data -rw,fstype=nfs4,soft localhost:/srv/nfsexport\n")).run().passed


@pytest.mark.parametrize(
    "text",
    [
        "",
        "#data -fstype=nfs4,rw localhost:/srv/nfsexport\n",
        "other -fstype=nfs4,rw localhost:/srv/nfsexport\n",
        "data -fstype=nfs4,rw otherhost:/srv/nfsexport\n",
        "data -fstype=nfs,rw localhost:/srv/nfsexport\n",
        "data -rw localhost:/srv/nfsexport\n",
        "data localhost:/srv/nfsexport\n",
        "data\n",
    ],
)
def test_map_entry_fails(text: str) -> None:
    assert not map_entry(map_runner(text)).run().passed


def test_map_entry_fails_when_unreadable() -> None:
    result = map_entry(map_runner("", rc=1)).run()
    assert not result.passed and "/etc/auto.remote" in result.detail


@pytest.mark.parametrize(
    ("key", "location", "fstype"),
    [("", "h:/x", None), ("a b", "h:/x", None), ("data", "", None), ("data", "h :/x", None),
     ("data", "h:/x", "NFS"), ("data", "h:/x", "")],
)  # fmt: skip
def test_map_entry_rejects_bad_input(key: str, location: str, fstype: str | None) -> None:
    with pytest.raises(ValueError):
        AutofsMapEntry(map_runner(""), "/etc/auto.remote", key, location, fstype)


def test_map_entry_rejects_relative_map_file() -> None:
    with pytest.raises(ValueError):
        AutofsMapEntry(map_runner(""), "auto.remote", "data", "h:/x")

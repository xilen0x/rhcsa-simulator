from __future__ import annotations

from rhcsa_sim.catalog import build_catalog
from rhcsa_sim.testing import FakeCommandRunner


def test_catalog_has_expected_well_formed_tasks() -> None:
    tasks = build_catalog(FakeCommandRunner({})).all()
    ids = ["users-01", "users-02", "users-03", "users-04", "users-05", "users-06", "files-01", "storage-01", "storage-02", "part-01", "swap-01", "fs-01", "fs-02"]
    ids += ["svc-01", "svc-02", "fw-01", "fw-02", "net-01", "net-02", "se-01", "se-02", "se-03", "se-04", "sec-01", "sec-02"]
    ids += ["dnf-01", "pkg-01", "cron-01", "tuned-01"]
    ids += ["scr-01", "scr-02"]
    ids += ["prc-01", "log-01", "run-01"]
    ids += ["ess-01", "ess-02", "ess-03"]
    assert [t.id for t in tasks] == ids
    assert all(t.points > 0 and t.checks for t in tasks)
    assert len({t.id for t in tasks}) == len(tasks)


def test_running_systems_and_scripts_blocks() -> None:
    from rhcsa_sim.models import ObjectiveBlock

    tasks = {t.id: t for t in build_catalog(FakeCommandRunner({})).all()}
    running = {i for i, t in tasks.items() if t.block is ObjectiveBlock.RUNNING_SYSTEMS}
    assert running == {"prc-01", "log-01", "tuned-01", "run-01"}
    scripts = {i for i, t in tasks.items() if t.block is ObjectiveBlock.SHELL_SCRIPTS}
    assert scripts == {"scr-01", "scr-02"}
    assert len(tasks["scr-02"].checks) == 4


def test_manage_software_block_and_no_containers() -> None:
    from rhcsa_sim.models import ObjectiveBlock

    tasks = {t.id: t for t in build_catalog(FakeCommandRunner({})).all()}
    software = {i for i, t in tasks.items() if t.block is ObjectiveBlock.MANAGE_SOFTWARE}
    assert software == {"dnf-01", "pkg-01"}
    assert not hasattr(ObjectiveBlock, "CONTAINERS")
    assert [b.name for b in ObjectiveBlock] == [
        "ESSENTIAL_TOOLS", "MANAGE_SOFTWARE", "SHELL_SCRIPTS", "RUNNING_SYSTEMS",
        "LOCAL_STORAGE", "FILE_SYSTEMS", "DEPLOY_MAINTAIN", "NETWORKING",
        "USERS_GROUPS", "SECURITY",
    ]  # fmt: skip
    assert ObjectiveBlock.MANAGE_SOFTWARE.value == "manage-software"


def test_catalog_totals() -> None:
    tasks = build_catalog(FakeCommandRunner({})).all()
    assert (len(tasks), sum(t.points for t in tasks)) == (37, 370)

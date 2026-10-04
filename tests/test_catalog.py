from __future__ import annotations

from rhcsa_sim.catalog import build_catalog
from rhcsa_sim.testing import FakeCommandRunner


def test_catalog_has_expected_well_formed_tasks() -> None:
    tasks = build_catalog(FakeCommandRunner({})).all()
    ids = ["users-01", "users-02", "users-03", "users-04", "users-05", "files-01", "storage-01", "storage-02", "part-01", "swap-01", "fs-01", "fs-02", "fs-03", "fs-04", "fs-05"]
    ids += ["svc-01", "svc-02", "fw-01", "fw-02", "net-01", "net-02", "net-03", "se-01", "se-02", "se-03", "se-04", "sec-01", "sec-02", "sec-03", "sec-04"]
    ids += ["dnf-01", "pkg-01", "sw-01", "sw-02", "cron-01", "tuned-01"]
    ids += ["scr-01", "scr-02", "scr-03"]
    ids += ["prc-01", "log-01", "run-01"]
    ids += ["ess-01", "ess-02", "ess-03"]
    ids += ["dep-01", "dep-02", "dep-03"]
    assert [t.id for t in tasks] == ids
    assert all(t.points > 0 and t.checks for t in tasks)
    assert len({t.id for t in tasks}) == len(tasks)


def test_running_systems_and_scripts_blocks() -> None:
    from rhcsa_sim.models import ObjectiveBlock

    tasks = {t.id: t for t in build_catalog(FakeCommandRunner({})).all()}
    running = {i for i, t in tasks.items() if t.block is ObjectiveBlock.RUNNING_SYSTEMS}
    assert running == {"prc-01", "log-01", "tuned-01", "run-01"}
    scripts = {i for i, t in tasks.items() if t.block is ObjectiveBlock.SHELL_SCRIPTS}
    assert scripts == {"scr-01", "scr-02", "scr-03"}
    assert len(tasks["scr-02"].checks) == 4
    assert len(tasks["scr-03"].checks) == 4
    assert "estatica" in tasks["scr-03"].description


def test_manage_software_block_and_no_containers() -> None:
    from rhcsa_sim.models import ObjectiveBlock

    tasks = {t.id: t for t in build_catalog(FakeCommandRunner({})).all()}
    software = {i for i, t in tasks.items() if t.block is ObjectiveBlock.MANAGE_SOFTWARE}
    assert software == {"dnf-01", "pkg-01", "sw-01", "sw-02"}
    assert not hasattr(ObjectiveBlock, "CONTAINERS")
    assert [b.name for b in ObjectiveBlock] == [
        "ESSENTIAL_TOOLS", "MANAGE_SOFTWARE", "SHELL_SCRIPTS", "RUNNING_SYSTEMS",
        "LOCAL_STORAGE", "FILE_SYSTEMS", "DEPLOY_MAINTAIN", "NETWORKING",
        "USERS_GROUPS", "SECURITY",
    ]  # fmt: skip
    assert ObjectiveBlock.MANAGE_SOFTWARE.value == "manage-software"


def test_catalog_totals() -> None:
    tasks = build_catalog(FakeCommandRunner({})).all()
    assert (len(tasks), sum(t.points for t in tasks)) == (48, 480)


def test_deploy_timer_and_time_service_tasks() -> None:
    from rhcsa_sim.models import ObjectiveBlock

    tasks = {t.id: t for t in build_catalog(FakeCommandRunner({})).all()}
    for task_id in ("dep-01", "dep-02"):
        assert tasks[task_id].block is ObjectiveBlock.DEPLOY_MAINTAIN
        assert tasks[task_id].points == 10
    assert "OnCalendar=daily" in tasks["dep-01"].description
    assert "classroom.example.com" in tasks["dep-02"].description
    assert len(tasks["dep-01"].checks) == 3 and len(tasks["dep-02"].checks) == 3


def test_deploy_bootloader_task() -> None:
    from rhcsa_sim.models import ObjectiveBlock

    task = {t.id: t for t in build_catalog(FakeCommandRunner({})).all()}["dep-03"]
    assert task.block is ObjectiveBlock.DEPLOY_MAINTAIN and task.points == 10
    assert "systemd.show_status=1" in task.description and "grubby" in task.description
    assert len(task.checks) == 1


def test_vfat_nfs_autofs_tasks() -> None:
    from rhcsa_sim.models import ObjectiveBlock

    tasks = {t.id: t for t in build_catalog(FakeCommandRunner({})).all()}
    for task_id in ("fs-03", "fs-04", "fs-05"):
        assert tasks[task_id].block is ObjectiveBlock.FILE_SYSTEMS
        assert tasks[task_id].points == 10
    assert "/dev/sdb3" in tasks["fs-03"].description and "VFAT" in tasks["fs-03"].description
    assert "localhost:/srv/nfsexport" in tasks["fs-04"].description
    assert "/etc/auto.remote" in tasks["fs-05"].description
    assert len(tasks["fs-03"].checks) == 4 and len(tasks["fs-04"].checks) == 2
    assert len(tasks["fs-05"].checks) == 4


def test_ipv6_umask_and_ssh_key_tasks() -> None:
    from rhcsa_sim.models import ObjectiveBlock

    tasks = {t.id: t for t in build_catalog(FakeCommandRunner({})).all()}
    assert "users-06" not in tasks
    assert tasks["net-03"].block is ObjectiveBlock.NETWORKING
    for task_id in ("sec-03", "sec-04"):
        assert tasks[task_id].block is ObjectiveBlock.SECURITY
    for task_id in ("net-03", "sec-03", "sec-04"):
        assert tasks[task_id].points == 10
    assert "2001:db8:10::50/64" in tasks["net-03"].description
    assert "2001:db8:10::1" in tasks["net-03"].description
    assert "0027" in tasks["sec-03"].description and "/home/alice/.bashrc" in tasks["sec-03"].description
    assert "ed25519" in tasks["sec-04"].description
    assert [len(tasks[i].checks) for i in ("net-03", "sec-03", "sec-04")] == [1, 1, 5]

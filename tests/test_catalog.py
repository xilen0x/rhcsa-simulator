from __future__ import annotations

from rhcsa_sim.catalog import build_catalog
from rhcsa_sim.testing import FakeCommandRunner


def test_catalog_has_expected_well_formed_tasks() -> None:
    tasks = build_catalog(FakeCommandRunner({})).all()
    ids = ["users-01", "users-02", "files-01", "storage-01", "storage-02", "part-01", "swap-01", "fs-01", "fs-02"]
    ids += ["svc-01", "svc-02", "fw-01", "fw-02", "net-01", "net-02", "se-01", "se-02", "se-03", "se-04", "sec-01", "sec-02"]
    ids += ["dnf-01", "pkg-01", "cron-01", "tuned-01"]
    ids += ["scr-01"]
    assert [t.id for t in tasks] == ids
    assert all(t.points > 0 and t.checks for t in tasks)
    assert len({t.id for t in tasks}) == len(tasks)

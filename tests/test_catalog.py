from __future__ import annotations

from rhcsa_sim.catalog import build_catalog
from rhcsa_sim.testing import FakeCommandRunner


def test_catalog_has_expected_well_formed_tasks() -> None:
    tasks = build_catalog(FakeCommandRunner({})).all()
    ids = ["users-01", "users-02", "files-01", "storage-01", "storage-02", "fs-01", "fs-02"]
    ids += ["svc-01", "svc-02", "fw-01", "fw-02"]
    assert [t.id for t in tasks] == ids
    assert all(t.points > 0 and t.checks for t in tasks)
    assert len({t.id for t in tasks}) == len(tasks)

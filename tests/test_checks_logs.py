from __future__ import annotations

from rhcsa_sim.checks.logs import JournalPersistent
from rhcsa_sim.models import Check
from rhcsa_sim.testing import FakeCommandRunner, make_result

CAT = ("systemd-analyze", "cat-config", "systemd/journald.conf")
STAT = ("stat", "-L", "-c", "%F", "--", "/var/log/journal")

MAIN = "# /etc/systemd/journald.conf\n#  Storage=auto\n[Journal]\n#Storage=auto\n"
DROPIN = "\n# /etc/systemd/journald.conf.d/99-persistent.conf\n[Journal]\nStorage=persistent\nSystemMaxUse=200MB\n"


def runner(
    conf: str = MAIN + DROPIN,
    cat_rc: int = 0,
    stat_out: str = "directory\n",
    stat_rc: int = 0,
    cat_err: str = "",
) -> FakeCommandRunner:
    return FakeCommandRunner(
        {
            CAT: make_result(CAT, stdout=conf, returncode=cat_rc, stderr=cat_err),
            STAT: make_result(STAT, stdout=stat_out, returncode=stat_rc),
        }
    )


def test_satisfies_protocol() -> None:
    check: Check = JournalPersistent(FakeCommandRunner({}))
    assert check.describe()


def test_persistent_ok() -> None:
    assert JournalPersistent(runner()).run().passed


def test_last_assignment_wins() -> None:
    conf = "[Journal]\nStorage=persistent\n\n[Journal]\nStorage=volatile\n"
    result = JournalPersistent(runner(conf)).run()
    assert not result.passed and "Storage=volatile (expected persistent)" in result.detail
    conf = "[Journal]\nStorage=volatile\n[Journal]\nStorage = persistent\n"
    assert JournalPersistent(runner(conf)).run().passed


def test_comments_ignored() -> None:
    conf = "[Journal]\n#Storage=persistent\n;Storage=persistent\n"
    result = JournalPersistent(runner(conf)).run()
    assert not result.passed and "Storage not set (default auto)" in result.detail


def test_storage_auto() -> None:
    result = JournalPersistent(runner("[Journal]\nStorage=auto\n")).run()
    assert not result.passed and "Storage=auto (expected persistent)" in result.detail


def test_storage_in_other_section_does_not_count() -> None:
    conf = "[Other]\nStorage=persistent\n[Journal]\nSystemMaxUse=1M\n"
    assert not JournalPersistent(runner(conf)).run().passed


def test_storage_before_any_section_does_not_count() -> None:
    assert not JournalPersistent(runner("Storage=persistent\n")).run().passed


def test_directory_missing() -> None:
    result = JournalPersistent(runner(stat_rc=1, stat_out="")).run()
    assert not result.passed and "/var/log/journal" in result.detail


def test_directory_wrong_type() -> None:
    result = JournalPersistent(runner(stat_out="regular file\n")).run()
    assert not result.passed and "regular file" in result.detail


def test_both_failures_reported() -> None:
    result = JournalPersistent(runner("[Journal]\n", stat_rc=1, stat_out="")).run()
    assert not result.passed
    assert "Storage not set" in result.detail and "/var/log/journal" in result.detail


def test_cat_config_failure() -> None:
    result = JournalPersistent(runner(cat_rc=127, cat_err="no such command\n")).run()
    assert not result.passed and "cannot read journald configuration" in result.detail

from __future__ import annotations

import pytest

from rhcsa_sim.checks.processes import ProcessNotRunning, ProcessRunning
from rhcsa_sim.models import Check
from rhcsa_sim.testing import FakeCommandRunner, make_result


def ps_cmd(comm: str = "sshd") -> tuple[str, ...]:
    return ("ps", "-C", comm, "-o", "pid=,ni=,user:32=,comm=")


def runner(
    stdout: str = "", returncode: int = 0, comm: str = "sshd", stderr: str = ""
) -> FakeCommandRunner:
    args = ps_cmd(comm)
    return FakeCommandRunner(
        {args: make_result(args, stdout=stdout, returncode=returncode, stderr=stderr)}
    )


ONE = "    899   0 root     sshd\n"
TWO = "    899   0 root     sshd\n   1500   5 alice    sshd\n"


def test_checks_satisfy_protocol() -> None:
    r = FakeCommandRunner({})
    checks: list[Check] = [ProcessRunning(r, "sshd"), ProcessNotRunning(r, "sshd")]
    assert all(c.describe() for c in checks)


@pytest.mark.parametrize(
    "comm", ["", "a" * 16, "a/b", "a b", "-x", "a\x00b", "a\tb"]
)
def test_comm_validation(comm: str) -> None:
    with pytest.raises(ValueError):
        ProcessRunning(FakeCommandRunner({}), comm)
    with pytest.raises(ValueError):
        ProcessNotRunning(FakeCommandRunner({}), comm)


def test_other_validation() -> None:
    r = FakeCommandRunner({})
    for nice in (-21, 20):
        with pytest.raises(ValueError):
            ProcessRunning(r, "sshd", nice=nice)
    with pytest.raises(ValueError):
        ProcessRunning(r, "sshd", user="Bad User")
    assert ProcessRunning(r, "a" * 15, nice=-20).nice == -20
    assert ProcessRunning(r, "sshd", nice=19).nice == 19


def test_running_ok() -> None:
    assert ProcessRunning(runner(ONE), "sshd").run().passed


def test_running_not_running() -> None:
    result = ProcessRunning(runner(returncode=1), "sshd").run()
    assert not result.passed and "not running" in result.detail


def test_running_empty_output_rc0_is_not_running() -> None:
    assert not ProcessRunning(runner(""), "sshd").run().passed


def test_running_with_nice_and_user_ok() -> None:
    assert ProcessRunning(runner(ONE), "sshd", nice=0, user="root").run().passed


def test_running_negative_nice() -> None:
    out = "  10 -5 root     sshd\n"
    assert ProcessRunning(runner(out), "sshd", nice=-5).run().passed


def test_running_wrong_nice_reports_pid() -> None:
    result = ProcessRunning(runner(TWO), "sshd", nice=0).run()
    assert not result.passed
    assert "1500" in result.detail and "nice 5" in result.detail and "expected 0" in result.detail


def test_running_wrong_user_reports_pid() -> None:
    result = ProcessRunning(runner(TWO), "sshd", user="root").run()
    assert not result.passed
    assert "1500" in result.detail and "alice" in result.detail and "root" in result.detail


def test_running_all_matching_must_satisfy() -> None:
    assert not ProcessRunning(runner(TWO), "sshd", nice=0).run().passed
    assert ProcessRunning(runner(ONE + ONE), "sshd", nice=0).run().passed


@pytest.mark.parametrize("out", ["garbage\n", "1 2 3\n", "x 0 root sshd\n", "1 - root sshd\n"])
def test_running_unexpected_output(out: str) -> None:
    result = ProcessRunning(runner(out), "sshd", nice=0).run()
    assert not result.passed and "unexpected" in result.detail


def test_running_ps_failure() -> None:
    result = ProcessRunning(runner(returncode=2, stderr="ps: boom\n"), "sshd").run()
    assert not result.passed and "exit 2" in result.detail and "boom" in result.detail


def test_not_running_ok() -> None:
    assert ProcessNotRunning(runner(returncode=1, comm="yes"), "yes").run().passed


def test_not_running_lists_pids() -> None:
    result = ProcessNotRunning(runner(TWO), "sshd").run()
    assert not result.passed and "899" in result.detail and "1500" in result.detail


def test_not_running_ps_failure() -> None:
    result = ProcessNotRunning(runner(returncode=2, stderr="ps: boom\n"), "sshd").run()
    assert not result.passed and "boom" in result.detail


def test_not_running_rc0_empty_passes() -> None:
    assert ProcessNotRunning(runner(""), "sshd").run().passed

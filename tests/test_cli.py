from __future__ import annotations

import io
from collections.abc import Sequence

import pytest

from rhcsa_sim.cli import main
from rhcsa_sim.testing import FakeCommandRunner, make_result

GROUP = ("getent", "group", "devs")
PASSWD = ("getent", "passwd", "alice")
IDG = ("id", "-Gn", "--", "alice")
STAT = ("stat", "-c", "%a %U %G", "--", "/srv/shared")


def make_runner(group_rc: int = 0) -> FakeCommandRunner:
    group_out = "devs:x:5000:alice\n" if group_rc == 0 else ""
    return FakeCommandRunner(
        {
            GROUP: make_result(GROUP, returncode=group_rc, stdout=group_out),
            PASSWD: make_result(PASSWD, stdout="alice:x:1234:1234:A:/home/alice:/bin/bash\n"),
            IDG: make_result(IDG, stdout="alice devs\n"),
            STAT: make_result(STAT, stdout="2770 root devs\n"),
        }
    )


def run_cli(argv: Sequence[str], runner: FakeCommandRunner) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, runner=runner, stdout=out, stderr=err, env={})
    return code, out.getvalue(), err.getvalue()


def test_list() -> None:
    code, out, _ = run_cli(["list"], make_runner())
    assert code == 0
    assert "users-01" in out and "files-01" in out


def test_show_and_unknown() -> None:
    code, out, _ = run_cli(["show", "users-01"], make_runner())
    assert code == 0 and "devs" in out
    code, _, err = run_cli(["show", "nope"], make_runner())
    assert code == 2 and "unknown task" in err


def test_check_single_ok_and_ko() -> None:
    code, out, _ = run_cli(["check", "users-01"], make_runner())
    assert code == 0 and "[OK] users-01" in out
    code, out, _ = run_cli(["check", "users-01"], make_runner(group_rc=2))
    assert code == 1 and "[KO] users-01" in out


def test_check_all_pass() -> None:
    code, out, _ = run_cli(["check", "--all"], make_runner())
    assert code == 0
    assert "30/30" in out and "PASS" in out


def test_check_all_with_failure() -> None:
    code, out, _ = run_cli(["check", "--all"], make_runner(group_rc=2))
    assert code == 1
    assert "20/30" in out and "FAIL" in out


def test_check_requires_exactly_one_selector() -> None:
    code, _, err = run_cli(["check"], make_runner())
    assert code == 2 and "exactly one" in err
    code, _, _ = run_cli(["check", "users-01", "--all"], make_runner())
    assert code == 2


def test_unknown_task_id_is_sanitized() -> None:
    _, _, err = run_cli(["check", "\x1b[31mx"], make_runner())
    assert "\x1b" not in err


def test_missing_command_returns_usage_code(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    capsys.readouterr()

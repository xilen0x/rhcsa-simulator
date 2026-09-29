from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import cast

import pytest

from rhcsa_sim.runner import (
    EXIT_NOT_FOUND,
    EXIT_TIMEOUT,
    CommandRunner,
    SubprocessRunner,
)
from rhcsa_sim.testing import FakeCommandRunner, make_result


def test_runs_command_and_captures_stdout() -> None:
    result = SubprocessRunner().run(["echo", "hello"])
    assert result.ok
    assert result.stdout == "hello\n"


def test_nonzero_exit_is_reported_not_raised() -> None:
    result = SubprocessRunner().run([sys.executable, "-c", "raise SystemExit(3)"])
    assert result.returncode == 3
    assert not result.ok


def test_shell_metacharacters_are_not_interpreted() -> None:
    result = SubprocessRunner().run(["echo", "a; echo b"])
    assert result.stdout == "a; echo b\n"


def test_missing_command_returns_not_found() -> None:
    result = SubprocessRunner().run(["definitely-not-a-command-xyz"])
    assert result.returncode == EXIT_NOT_FOUND
    assert "not found" in result.stderr


def test_timeout_returns_timeout_code() -> None:
    result = SubprocessRunner().run(
        [sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2
    )
    assert result.returncode == EXIT_TIMEOUT


def test_locale_is_forced_to_c() -> None:
    code = "import os; print(os.environ['LC_ALL'])"
    result = SubprocessRunner().run([sys.executable, "-c", code])
    assert result.stdout.strip() == "C"


def test_rejects_single_string() -> None:
    with pytest.raises(ValueError):
        SubprocessRunner().run("ls -l")


def test_rejects_empty_args() -> None:
    with pytest.raises(ValueError):
        SubprocessRunner().run([])


def test_rejects_blank_command_name() -> None:
    with pytest.raises(ValueError):
        SubprocessRunner().run(["  "])


def test_rejects_non_string_args() -> None:
    with pytest.raises(ValueError):
        SubprocessRunner().run(cast(Sequence[str], ["echo", 1]))


def test_rejects_nul_bytes() -> None:
    with pytest.raises(ValueError):
        SubprocessRunner().run(["echo", "a\x00b"])


@pytest.mark.parametrize("timeout", [0.0, -1.0])
def test_rejects_non_positive_timeout(timeout: float) -> None:
    with pytest.raises(ValueError):
        SubprocessRunner().run(["echo", "x"], timeout=timeout)


def test_fake_runner_returns_configured_result_and_records_calls() -> None:
    cmd = ("id", "alice")
    fake = FakeCommandRunner({cmd: make_result(cmd, stdout="uid=1000(alice)\n")})
    runner: CommandRunner = fake
    assert runner.run(cmd).stdout == "uid=1000(alice)\n"
    assert fake.calls == [cmd]


def test_fake_runner_fails_on_unexpected_command() -> None:
    with pytest.raises(AssertionError):
        FakeCommandRunner({}).run(["id", "bob"])

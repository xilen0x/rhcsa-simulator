from __future__ import annotations

import pytest

from rhcsa_sim.checks.scripts import (
    FileContainsLine,
    FileIsExecutable,
    ScriptHasShebang,
    ScriptSyntaxValid,
)
from rhcsa_sim.models import Check
from rhcsa_sim.testing import FakeCommandRunner, make_result

PATH = "/usr/local/bin/sysinfo.sh"
STAT_CMD = ("stat", "-c", "%a %F", "--", PATH)
HEAD_CMD = ("head", "-n", "1", "--", PATH)
SYNTAX_CMD = ("bash", "-n", "--", PATH)
LINE = "servera.lab.example.com"
GREP_CMD = ("grep", "-Fxq", "--", LINE, PATH)


def fake(cmd: tuple[str, ...], returncode: int = 0, stdout: str = "", stderr: str = "") -> FakeCommandRunner:
    return FakeCommandRunner(
        {cmd: make_result(cmd, returncode=returncode, stdout=stdout, stderr=stderr)}
    )


# --- FileIsExecutable (probe: "755 regular file", rc 1 si no existe) ---


def test_executable_ok() -> None:
    assert FileIsExecutable(fake(STAT_CMD, stdout="755 regular file\n"), PATH).run().passed
    assert FileIsExecutable(fake(STAT_CMD, stdout="700 regular file\n"), PATH).run().passed


def test_executable_ko_missing() -> None:
    result = FileIsExecutable(fake(STAT_CMD, 1, stderr="stat: cannot statx"), PATH).run()
    assert not result.passed and "cannot stat" in result.detail


def test_executable_ko_not_regular() -> None:
    result = FileIsExecutable(fake(STAT_CMD, stdout="755 directory\n"), PATH).run()
    assert not result.passed and "not a regular file" in result.detail


def test_executable_ko_mode_shown() -> None:
    result = FileIsExecutable(fake(STAT_CMD, stdout="644 regular file\n"), PATH).run()
    assert not result.passed and "644" in result.detail


def test_executable_requires_owner_bit() -> None:
    result = FileIsExecutable(fake(STAT_CMD, stdout="611 regular file\n"), PATH).run()
    assert not result.passed


def test_executable_accepts_empty_regular_file_type() -> None:
    result = FileIsExecutable(fake(STAT_CMD, stdout="755 regular empty file\n"), PATH).run()
    assert result.passed


def test_executable_malformed_output() -> None:
    assert not FileIsExecutable(fake(STAT_CMD, stdout="zzz\n"), PATH).run().passed
    assert not FileIsExecutable(fake(STAT_CMD, stdout="rwx regular file\n"), PATH).run().passed


# --- ScriptHasShebang (probe: head devuelve la primera linea tal cual) ---


@pytest.mark.parametrize(
    "first", ["#!/bin/bash", "#!/bin/bash  ", "#!/usr/bin/env bash", "#!/usr/bin/env bash \t"]
)
def test_shebang_ok(first: str) -> None:
    assert ScriptHasShebang(fake(HEAD_CMD, stdout=first + "\n"), PATH).run().passed


def test_shebang_custom_interpreter() -> None:
    fk = fake(HEAD_CMD, stdout="#!/usr/bin/python3\n")
    assert ScriptHasShebang(fk, PATH, "/usr/bin/python3").run().passed
    assert not ScriptHasShebang(fk, PATH).run().passed


@pytest.mark.parametrize("first", ["", "#!/bin/sh", "/bin/bash", "#! /bin/bash", "#!/usr/bin/env zsh"])
def test_shebang_ko(first: str) -> None:
    result = ScriptHasShebang(fake(HEAD_CMD, stdout=first), PATH).run()
    assert not result.passed and "shebang" in result.detail


def test_shebang_ko_unreadable() -> None:
    result = ScriptHasShebang(fake(HEAD_CMD, 1, stderr="Permission denied"), PATH).run()
    assert not result.passed and "cannot read" in result.detail


# --- ScriptSyntaxValid (probe: rc 0 ok, 2 sintaxis, 126 sin permiso, 127 no existe) ---


def test_syntax_ok() -> None:
    assert ScriptSyntaxValid(fake(SYNTAX_CMD), PATH).run().passed


def test_syntax_error_rc2() -> None:
    err = "x.sh: line 2: syntax error near unexpected token `then'\n"
    result = ScriptSyntaxValid(fake(SYNTAX_CMD, 2, stderr=err), PATH).run()
    assert not result.passed and "syntax error" in result.detail


@pytest.mark.parametrize("rc", [126, 127])
def test_syntax_unreadable_or_missing(rc: int) -> None:
    result = ScriptSyntaxValid(fake(SYNTAX_CMD, rc, stderr="No such file"), PATH).run()
    assert not result.passed and "cannot read" in result.detail


# --- FileContainsLine (probe: grep rc 0 / 1 / 2) ---


def test_line_found() -> None:
    assert FileContainsLine(fake(GREP_CMD), "/usr/local/bin/sysinfo.sh", LINE).run().passed


def test_line_not_found() -> None:
    result = FileContainsLine(fake(GREP_CMD, 1), PATH, LINE).run()
    assert not result.passed and "line not found" in result.detail


def test_line_missing_file() -> None:
    result = FileContainsLine(fake(GREP_CMD, 2, stderr="No such file or directory"), PATH, LINE).run()
    assert not result.passed and "cannot read" in result.detail and "sudo" not in result.detail


def test_line_permission_denied_hints_root() -> None:
    result = FileContainsLine(fake(GREP_CMD, 2, stderr="grep: x: Permission denied"), PATH, LINE).run()
    assert not result.passed and "sudo" in result.detail


@pytest.mark.parametrize("line", ["", "a\nb", "a\x00b"])
def test_invalid_line_rejected(line: str) -> None:
    with pytest.raises(ValueError):
        FileContainsLine(fake(GREP_CMD), PATH, line)


# --- validacion comun y proteccion ---


@pytest.mark.parametrize("path", ["relative.sh", "", "/a\nb"])
def test_invalid_path_rejected(path: str) -> None:
    runner = fake(STAT_CMD)
    for build in (
        lambda: FileIsExecutable(runner, path),
        lambda: ScriptHasShebang(runner, path),
        lambda: ScriptSyntaxValid(runner, path),
        lambda: FileContainsLine(runner, path, LINE),
    ):
        with pytest.raises(ValueError):
            build()


@pytest.mark.parametrize("interpreter", ["bash", "", "/bin/ba\nsh"])
def test_invalid_interpreter_rejected(interpreter: str) -> None:
    with pytest.raises(ValueError):
        ScriptHasShebang(fake(HEAD_CMD), PATH, interpreter)


def test_describe_and_protocol() -> None:
    runner = fake(STAT_CMD)
    checks: list[Check] = [
        FileIsExecutable(runner, PATH),
        ScriptHasShebang(runner, PATH),
        ScriptSyntaxValid(runner, PATH),
        FileContainsLine(runner, PATH, LINE),
    ]
    assert all(c.describe() for c in checks)


def test_never_executes_the_script() -> None:
    cmds = {STAT_CMD: "755 regular file\n", HEAD_CMD: "#!/bin/bash\n", SYNTAX_CMD: "", GREP_CMD: ""}
    runner = FakeCommandRunner({c: make_result(c, stdout=out) for c, out in cmds.items()})
    for check in (
        FileIsExecutable(runner, PATH),
        ScriptHasShebang(runner, PATH),
        ScriptSyntaxValid(runner, PATH),
        FileContainsLine(runner, PATH, LINE),
    ):
        assert check.run().passed
    assert runner.calls
    for argv in runner.calls:
        assert argv[0] != PATH
        assert argv[0] in {"stat", "head", "bash", "grep"}
        if argv[0] == "bash":
            assert argv[1:3] == ("-n", "--")

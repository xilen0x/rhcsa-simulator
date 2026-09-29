from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

DEFAULT_TIMEOUT_SECONDS = 10.0

EXIT_TIMEOUT = 124
EXIT_NOT_EXECUTABLE = 126
EXIT_NOT_FOUND = 127


@dataclass(frozen=True, slots=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class CommandRunner(Protocol):
    def run(
        self, args: Sequence[str], *, timeout: float | None = None
    ) -> CommandResult: ...


def _validate_args(args: Sequence[str]) -> tuple[str, ...]:
    if isinstance(args, str):
        raise ValueError("args must be a sequence of strings, not a single string")
    argv = tuple(args)
    if not argv:
        raise ValueError("args must not be empty")
    if not all(isinstance(a, str) for a in argv):
        raise ValueError("all args must be strings")
    if not argv[0].strip():
        raise ValueError("the command name must not be empty")
    if any("\x00" in a for a in argv):
        raise ValueError("args must not contain NUL bytes")
    return argv


def _validate_timeout(timeout: float) -> float:
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    return timeout


def _stable_env() -> dict[str, str]:
    """Locale fija para que la salida de los comandos sea parseable."""
    return {**os.environ, "LC_ALL": "C", "LANG": "C"}


class SubprocessRunner:
    def __init__(self, default_timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._default_timeout = _validate_timeout(default_timeout)

    def run(
        self, args: Sequence[str], *, timeout: float | None = None
    ) -> CommandResult:
        argv = _validate_args(args)
        effective = (
            self._default_timeout if timeout is None else _validate_timeout(timeout)
        )
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=effective,
                check=False,
                shell=False,
                stdin=subprocess.DEVNULL,
                env=_stable_env(),
            )
        except FileNotFoundError:
            return CommandResult(argv, EXIT_NOT_FOUND, "", f"command not found: {argv[0]}")
        except PermissionError:
            return CommandResult(argv, EXIT_NOT_EXECUTABLE, "", f"not executable: {argv[0]}")
        except subprocess.TimeoutExpired:
            return CommandResult(argv, EXIT_TIMEOUT, "", f"timeout after {effective}s")
        return CommandResult(argv, completed.returncode, completed.stdout, completed.stderr)

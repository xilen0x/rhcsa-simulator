from __future__ import annotations

from dataclasses import dataclass

from rhcsa_sim.checks._validation import validate_account_name
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner

_COMM_MAX = 15  # el kernel trunca comm a 15 caracteres (TASK_COMM_LEN - 1)
_NICE_MIN = -20
_NICE_MAX = 19
_UNEXPECTED = "unexpected ps output"


def _validate_comm(comm: str) -> str:
    if (
        not comm
        or len(comm) > _COMM_MAX
        or comm.startswith("-")
        or "/" in comm
        or any(c.isspace() or c == "\x00" for c in comm)
    ):
        raise ValueError(f"invalid process name: {comm!r}")
    return comm


def _validate_nice(nice: int) -> int:
    if not _NICE_MIN <= nice <= _NICE_MAX:
        raise ValueError(f"invalid nice value: {nice!r}")
    return nice


@dataclass(frozen=True, slots=True)
class _Proc:
    pid: str
    nice: int
    user: str


def _list_processes(runner: CommandRunner, comm: str) -> list[_Proc] | CheckResult:
    """Procesos vivos con ese `comm` exacto (los zombies se ignoran). rc 1 y
    salida vacia = ninguno."""
    # user:32 evita que ps sustituya nombres largos por el uid
    result = runner.run(["ps", "-C", comm, "-o", "pid=,ni=,user:32=,stat=,comm="])
    if result.returncode == 1 and not result.stdout.strip():
        return []
    if not result.ok:
        lines = result.stderr.strip().splitlines()
        detail = f": {lines[0]}" if lines else ""
        return CheckResult(False, f"cannot list processes (exit {result.returncode}){detail}")
    procs: list[_Proc] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        # comm puede contener espacios (un zombie sale como "sshd <defunct>")
        fields = line.split(maxsplit=4)
        if len(fields) != 5:
            return CheckResult(False, _UNEXPECTED)
        pid, ni, user, state, _comm = fields
        if state.startswith("Z"):
            continue  # zombie: ya termino, solo espera a que su padre lo recoja
        try:
            procs.append(_Proc(str(int(pid)), int(ni), user))
        except ValueError:
            return CheckResult(False, _UNEXPECTED)
    return procs


@dataclass(frozen=True, slots=True)
class ProcessRunning:
    """Hay al menos un proceso `comm` y TODOS cumplen `nice` y `user` si se indican."""

    runner: CommandRunner
    comm: str
    nice: int | None = None
    user: str | None = None

    def __post_init__(self) -> None:
        _validate_comm(self.comm)
        if self.nice is not None:
            _validate_nice(self.nice)
        if self.user is not None:
            validate_account_name(self.user)

    def describe(self) -> str:
        extra = ""
        if self.nice is not None:
            extra += f" with nice {self.nice}"
        if self.user is not None:
            extra += f" as {self.user}"
        return f"process {self.comm} is running{extra}"

    def run(self) -> CheckResult:
        procs = _list_processes(self.runner, self.comm)
        if isinstance(procs, CheckResult):
            return procs
        if not procs:
            return CheckResult(False, f"process '{self.comm}' is not running")
        for proc in procs:
            if self.nice is not None and proc.nice != self.nice:
                return CheckResult(
                    False,
                    f"process '{self.comm}' (pid {proc.pid}) has nice {proc.nice}, "
                    f"expected {self.nice}",
                )
            if self.user is not None and proc.user != self.user:
                return CheckResult(
                    False,
                    f"process '{self.comm}' (pid {proc.pid}) runs as {proc.user}, "
                    f"expected {self.user}",
                )
        return CheckResult(True, f"process '{self.comm}' is running ({len(procs)} found)")


@dataclass(frozen=True, slots=True)
class ProcessNotRunning:
    runner: CommandRunner
    comm: str

    def __post_init__(self) -> None:
        _validate_comm(self.comm)

    def describe(self) -> str:
        return f"process {self.comm} is not running"

    def run(self) -> CheckResult:
        procs = _list_processes(self.runner, self.comm)
        if isinstance(procs, CheckResult):
            return procs
        if procs:
            pids = ", ".join(p.pid for p in procs)
            return CheckResult(False, f"process '{self.comm}' is still running (pid {pids})")
        return CheckResult(True, f"process '{self.comm}' is not running")

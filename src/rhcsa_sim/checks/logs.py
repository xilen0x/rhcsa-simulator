from __future__ import annotations

from dataclasses import dataclass

from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandRunner

_JOURNAL_DIR = "/var/log/journal"


def _journal_storage(text: str) -> str | None:
    """Ultimo `Storage=` de la seccion [Journal] (la configuracion efectiva: el
    fichero principal y los drop-ins llegan concatenados y gana el ultimo)."""
    in_journal = False
    storage: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            in_journal = line[1:-1] == "Journal"
            continue
        key, sep, value = line.partition("=")
        if in_journal and sep and key.strip() == "Storage":
            storage = value.strip()
    return storage


@dataclass(frozen=True, slots=True)
class JournalPersistent:
    """journald con almacenamiento persistente: `Storage=persistent` efectivo y
    /var/log/journal como directorio. `Storage=auto` con el directorio creado
    tambien persiste, pero el examen pide persistencia explicita."""

    runner: CommandRunner

    def describe(self) -> str:
        return "journald stores logs persistently"

    def run(self) -> CheckResult:
        conf = self.runner.run(["systemd-analyze", "cat-config", "systemd/journald.conf"])
        if not conf.ok:
            return CheckResult(
                False, f"cannot read journald configuration (exit {conf.returncode})"
            )
        problems: list[str] = []
        storage = _journal_storage(conf.stdout)
        if storage is None:
            problems.append("Storage not set (default auto)")
        elif storage != "persistent":
            problems.append(f"Storage={storage} (expected persistent)")
        stat = self.runner.run(["stat", "-L", "-c", "%F", "--", _JOURNAL_DIR])
        kind = stat.stdout.strip()
        if not stat.ok:
            problems.append(f"{_JOURNAL_DIR} does not exist")
        elif kind != "directory":
            problems.append(f"{_JOURNAL_DIR} is a {kind}, expected a directory")
        if problems:
            return CheckResult(False, "; ".join(problems))
        return CheckResult(True, "Storage=persistent and /var/log/journal exists")

from __future__ import annotations

import re
from dataclasses import dataclass

from rhcsa_sim.checks._validation import (
    validate_absolute_path,
    validate_account_name,
    validate_sshd_keyword,
)
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandResult, CommandRunner

_SSHD_ROOT = "sshd -T requires root (run with sudo)"
_SUDO_ROOT = "sudo -l -U requires root (run with sudo)"
_VISUDO_ROOT = "visudo -c requires root (run with sudo)"
_UNEXPECTED_SUDO = "unexpected sudo output"
_SUDO_HEADER = "may run the following commands"
_RULE_RE = re.compile(r"\(([^()]*)\)\s*(.*)")
_TAG_RE = re.compile(r"([A-Z_]+):\s*")


def _validate_text(value: str, what: str) -> str:
    """Texto no vacio, sin caracteres de control."""
    if not value or not value.isprintable():
        raise ValueError(f"invalid {what}: {value!r}")
    return value


def _parse_sshd(stdout: str) -> dict[str, list[str]] | None:
    """Valores por keyword de sshd -T (una keyword puede repetirse); None si no hay
    ninguna linea 'keyword valor'."""
    options: dict[str, list[str]] = {}
    for line in stdout.splitlines():
        keyword, _, value = line.strip().partition(" ")
        if keyword and value.strip():
            options.setdefault(keyword, []).append(" ".join(value.split()))
    return options or None


@dataclass(frozen=True, slots=True)
class SshdOptionIs:
    runner: CommandRunner
    keyword: str
    value: str

    def __post_init__(self) -> None:
        validate_sshd_keyword(self.keyword)
        _validate_text(self.value, "sshd value")

    def describe(self) -> str:
        return f"sshd {self.keyword} is {self.value}"

    def run(self) -> CheckResult:
        result = self.runner.run(["sshd", "-T"])
        if not result.ok:
            if "Permission denied" in result.stderr:
                return CheckResult(False, _SSHD_ROOT)
            # stderr puede traer errores de configuracion: solo se informa el codigo
            return CheckResult(
                False, f"cannot query sshd configuration (exit {result.returncode})"
            )
        options = _parse_sshd(result.stdout)
        if options is None:
            return CheckResult(False, "unexpected sshd -T output")
        values = options.get(self.keyword)
        if values is None:
            return CheckResult(False, f"{self.keyword} not present in sshd -T output")
        expected = " ".join(self.value.split()).lower()
        if any(v.lower() == expected for v in values):
            return CheckResult(True, f"{self.keyword} is {self.value}")
        return CheckResult(
            False, f"{self.keyword} is {', '.join(values)}, expected {self.value}"
        )


@dataclass(frozen=True, slots=True)
class SudoersValid:
    runner: CommandRunner

    def describe(self) -> str:
        return "sudoers configuration is valid"

    def run(self) -> CheckResult:
        result = self.runner.run(["visudo", "-c"])
        if result.ok:
            return CheckResult(True, "sudoers configuration is valid")
        if "Permission denied" in result.stderr or "Permission denied" in result.stdout:
            return CheckResult(False, _VISUDO_ROOT)
        return CheckResult(
            False, f"sudoers has syntax errors (visudo -c exit {result.returncode})"
        )


def _runas_includes_all(runas: str) -> bool:
    """El grupo '(runas)' de sudo incluye ALL (puede ejecutar como cualquier usuario/grupo)."""
    return "ALL" in re.split(r"[\s:,]+", runas.strip())


def _parse_rule(line: str) -> list[tuple[str, bool]] | None:
    """Rule '(runas) [TAG:] cmd, ...' como [(comando, nopasswd)]; None si el runas
    no incluye ALL o la linea no es una regla."""
    match = _RULE_RE.fullmatch(line)
    if match is None:
        return None
    if not _runas_includes_all(match.group(1)):
        return None
    nopasswd = False
    grants: list[tuple[str, bool]] = []
    for item in match.group(2).split(","):
        item = item.strip()
        # los tags (NOPASSWD:, PASSWD:, SETENV:...) persisten hasta que otro los cambie
        while (tag := _TAG_RE.match(item)) is not None:
            if tag.group(1) in {"NOPASSWD", "PASSWD"}:
                nopasswd = tag.group(1) == "NOPASSWD"
            item = item[tag.end() :]
        if item:
            grants.append((item, nopasswd))
    return grants


def _sudo_rules(stdout: str) -> list[list[tuple[str, bool]]] | None:
    """Reglas indentadas tras la cabecera 'may run the following commands'; None si
    no hay cabecera."""
    lines = stdout.splitlines()
    for index, line in enumerate(lines):
        if _SUDO_HEADER in line:
            break
    else:
        return None
    rules: list[list[tuple[str, bool]]] = []
    for line in lines[index + 1 :]:
        if not line.strip() or not line[0].isspace():
            break
        rule = _parse_rule(line.strip())
        if rule is not None:
            rules.append(rule)
    return rules


@dataclass(frozen=True, slots=True)
class UserHasSudoRule:
    runner: CommandRunner
    user: str
    command: str = "ALL"
    nopasswd: bool = False

    def __post_init__(self) -> None:
        validate_account_name(self.user)
        _validate_text(self.command, "sudo command")
        if self.command != self.command.strip() or "," in self.command:
            raise ValueError(f"invalid sudo command: {self.command!r}")

    def describe(self) -> str:
        suffix = " without password" if self.nopasswd else ""
        return f"{self.user} may run {self.command} with sudo{suffix}"

    def _failure(self, result: CommandResult) -> CheckResult | None:
        if result.ok:
            return None
        text = result.stderr
        if "unknown user" in text:
            return CheckResult(False, f"user '{self.user}' does not exist")
        if "a password is required" in text or "Permission denied" in text:
            return CheckResult(False, _SUDO_ROOT)
        return CheckResult(False, f"cannot query sudo rules (exit {result.returncode})")

    def run(self) -> CheckResult:
        # -n evita que sudo pida contrasena; sin root falla con "a password is required"
        result = self.runner.run(["sudo", "-n", "-l", "-U", self.user])
        failure = self._failure(result)
        if failure is not None:
            return failure
        if "is not allowed to run sudo" in result.stdout:
            return CheckResult(False, f"user '{self.user}' is not allowed to run sudo")
        rules = _sudo_rules(result.stdout)
        if rules is None:
            return CheckResult(False, _UNEXPECTED_SUDO)
        grants = [g for rule in rules for g in rule if g[0] == self.command]
        if not grants:
            return CheckResult(
                False, f"no sudo rule grants {self.command} to '{self.user}'"
            )
        if self.nopasswd and not any(nopasswd for _, nopasswd in grants):
            return CheckResult(False, "rule requires a password; expected NOPASSWD")
        return CheckResult(True, f"{self.user} may run {self.command} with sudo")


def _read_file(runner: CommandRunner, path: str) -> str | CheckResult:
    result = runner.run(["cat", "--", path])
    if result.ok:
        return result.stdout
    if "Permission denied" in result.stderr:
        hint = " (permission denied; run with sudo)"
    elif path.startswith(("/root/", "/home/")):
        hint = " (paths under /root and /home may need sudo)"
    else:
        hint = ""
    return CheckResult(False, f"cannot read '{path}'{hint}")


@dataclass(frozen=True, slots=True)
class AuthorizedKeyPresent:
    """El tipo y blob base64 de `pubkey_file` figuran en una linea no comentada de
    `authorized_keys` (se admite un prefijo de opciones). Solo lectura de ficheros."""

    runner: CommandRunner
    authorized_keys: str
    pubkey_file: str

    def __post_init__(self) -> None:
        validate_absolute_path(self.authorized_keys)
        validate_absolute_path(self.pubkey_file)

    def describe(self) -> str:
        return f"{self.authorized_keys} authorizes the key in {self.pubkey_file}"

    def run(self) -> CheckResult:
        pub = _read_file(self.runner, self.pubkey_file)
        if isinstance(pub, CheckResult):
            return pub
        pair = _key_pair(pub)
        if pair is None:
            return CheckResult(False, f"'{self.pubkey_file}' is not a valid public key")
        keys = _read_file(self.runner, self.authorized_keys)
        if isinstance(keys, CheckResult):
            return keys
        for line in keys.splitlines():
            tokens = line.split()
            if not tokens or tokens[0].startswith("#"):
                continue
            if any(tokens[i : i + 2] == list(pair) for i in range(len(tokens) - 1)):
                return CheckResult(True, f"key {pair[0]} found in {self.authorized_keys}")
        return CheckResult(False, f"key from {self.pubkey_file} not found in {self.authorized_keys}")


def _key_pair(text: str) -> tuple[str, str] | None:
    """(tipo, blob) de la primera linea no comentaria con al menos dos campos."""
    for line in text.splitlines():
        tokens = line.split()
        if not tokens or tokens[0].startswith("#"):
            continue
        return (tokens[0], tokens[1]) if len(tokens) >= 2 else None
    return None

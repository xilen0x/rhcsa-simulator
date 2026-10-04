from __future__ import annotations

import pytest

from rhcsa_sim.checks.security import (
    AuthorizedKeyPresent,
    SshdOptionIs,
    SudoersValid,
    UserHasSudoRule,
)
from rhcsa_sim.models import Check
from rhcsa_sim.testing import FakeCommandRunner, make_result

SSHD = ("sshd", "-T")
VISUDO = ("visudo", "-c")
SUDO_L = ("sudo", "-n", "-l", "-U", "alice")
SSHD_OUT = "port 22\npermitrootlogin no\npasswordauthentication yes\nlistenaddress 0.0.0.0:22\n"
HEADER = "User alice may run the following commands on localhost:\n"
DEFAULTS = "Matching Defaults entries for alice on localhost:\n    !visiblepw, always_set_home\n\n"


def sudo_out(*rules: str) -> str:
    return DEFAULTS + HEADER + "".join(f"    {rule}\n" for rule in rules)


def fake(
    args: tuple[str, ...], stdout: str = "", returncode: int = 0, stderr: str = ""
) -> FakeCommandRunner:
    result = make_result(args, returncode=returncode, stdout=stdout, stderr=stderr)
    return FakeCommandRunner({args: result})


def sudo_check(
    stdout: str,
    command: str = "ALL",
    nopasswd: bool = False,
    returncode: int = 0,
    stderr: str = "",
) -> Check:
    runner = fake(SUDO_L, stdout, returncode, stderr)
    return UserHasSudoRule(runner, "alice", command, nopasswd)


def test_checks_satisfy_protocol() -> None:
    runner = FakeCommandRunner({})
    checks: list[Check] = [
        SshdOptionIs(runner, "permitrootlogin", "no"),
        SudoersValid(runner),
        UserHasSudoRule(runner, "alice"),
    ]
    assert all(c.describe() for c in checks)


def test_describe() -> None:
    runner = FakeCommandRunner({})
    assert SshdOptionIs(runner, "permitrootlogin", "no").describe() == "sshd permitrootlogin is no"
    assert SudoersValid(runner).describe() == "sudoers configuration is valid"
    assert UserHasSudoRule(runner, "alice").describe() == "alice may run ALL with sudo"
    assert UserHasSudoRule(runner, "alice", "/bin/ls", True).describe() == (
        "alice may run /bin/ls with sudo without password"
    )


def test_sshd_ok_and_case_insensitive() -> None:
    runner = fake(SSHD, SSHD_OUT)
    assert SshdOptionIs(runner, "permitrootlogin", "no").run().passed
    assert SshdOptionIs(runner, "permitrootlogin", "NO").run().passed
    assert runner.calls == [SSHD, SSHD]


def test_sshd_value_mismatch() -> None:
    result = SshdOptionIs(fake(SSHD, SSHD_OUT), "passwordauthentication", "no").run()
    assert not result.passed
    assert result.detail == "passwordauthentication is yes, expected no"


def test_sshd_keyword_missing() -> None:
    result = SshdOptionIs(fake(SSHD, SSHD_OUT), "x11forwarding", "no").run()
    assert not result.passed
    assert result.detail == "x11forwarding not present in sshd -T output"


def test_sshd_repeated_keyword_any_value_matches() -> None:
    runner = fake(SSHD, "port 22\nport 2222\n")
    assert SshdOptionIs(runner, "port", "2222").run().passed
    result = SshdOptionIs(runner, "port", "80").run()
    assert not result.passed and "22, 2222" in result.detail


def test_sshd_multi_word_value_matches_whole() -> None:
    runner = fake(SSHD, "authorizedkeysfile .ssh/authorized_keys .ssh/authorized_keys2\n")
    check = SshdOptionIs(runner, "authorizedkeysfile", ".ssh/authorized_keys .ssh/authorized_keys2")
    assert check.run().passed


def test_sshd_requires_root() -> None:
    runner = fake(SSHD, returncode=255, stderr="/etc/ssh/sshd_config: Permission denied\n")
    result = SshdOptionIs(runner, "permitrootlogin", "no").run()
    assert not result.passed and result.detail == "sshd -T requires root (run with sudo)"


def test_sshd_other_exit_code_hides_stderr() -> None:
    runner = fake(SSHD, returncode=255, stderr="/etc/ssh/sshd_config line 3: bad option\n")
    result = SshdOptionIs(runner, "permitrootlogin", "no").run()
    assert not result.passed
    assert result.detail == "cannot query sshd configuration (exit 255)"


@pytest.mark.parametrize("stdout", ["", "\n", "   \n\n", "garbage\n"])
def test_sshd_malformed_output(stdout: str) -> None:
    result = SshdOptionIs(fake(SSHD, stdout), "permitrootlogin", "no").run()
    assert not result.passed


@pytest.mark.parametrize("keyword", ["", "PermitRootLogin", "1abc", "a b", "a;b", "a" * 65, "-x"])
def test_sshd_invalid_keyword(keyword: str) -> None:
    with pytest.raises(ValueError):
        SshdOptionIs(FakeCommandRunner({}), keyword, "no")


@pytest.mark.parametrize("value", ["", "a\nb", "a\x00b"])
def test_sshd_invalid_value(value: str) -> None:
    with pytest.raises(ValueError):
        SshdOptionIs(FakeCommandRunner({}), "permitrootlogin", value)


def test_sudoers_ok() -> None:
    out = "/etc/sudoers: parsed OK\n/etc/sudoers.d/alice: parsed OK\n"
    runner = fake(VISUDO, out)
    assert SudoersValid(runner).run().passed
    assert runner.calls == [VISUDO]


def test_sudoers_syntax_error() -> None:
    runner = fake(VISUDO, "", 1, "/etc/sudoers.d/x:1:5: syntax error\n")
    result = SudoersValid(runner).run()
    assert not result.passed
    assert result.detail == "sudoers has syntax errors (visudo -c exit 1)"


@pytest.mark.parametrize("where", ["stderr", "stdout"])
def test_sudoers_requires_root(where: str) -> None:
    text = "visudo: unable to open /etc/sudoers: Permission denied\n"
    runner = fake(
        VISUDO,
        stdout=text if where == "stdout" else "",
        returncode=1,
        stderr=text if where == "stderr" else "",
    )
    result = SudoersValid(runner).run()
    assert not result.passed and result.detail == "visudo -c requires root (run with sudo)"


def test_sudo_nopasswd_all_ok() -> None:
    assert sudo_check(sudo_out("(ALL) NOPASSWD: ALL"), nopasswd=True).run().passed
    assert sudo_check(sudo_out("(ALL) NOPASSWD: ALL")).run().passed


def test_sudo_all_all_form_ok() -> None:
    assert sudo_check(sudo_out("(ALL : ALL) ALL")).run().passed
    assert sudo_check(sudo_out("(ALL:ALL) NOPASSWD: ALL"), nopasswd=True).run().passed


def test_sudo_requires_password() -> None:
    result = sudo_check(sudo_out("(ALL) ALL"), nopasswd=True).run()
    assert not result.passed
    assert result.detail == "rule requires a password; expected NOPASSWD"


def test_sudo_explicit_passwd_tag() -> None:
    result = sudo_check(sudo_out("(ALL) PASSWD: ALL"), nopasswd=True).run()
    assert not result.passed and "requires a password" in result.detail


def test_sudo_not_allowed() -> None:
    out = "User alice is not allowed to run sudo on localhost.\n"
    result = sudo_check(out).run()
    assert not result.passed
    assert result.detail == "user 'alice' is not allowed to run sudo"


def test_sudo_command_not_granted() -> None:
    result = sudo_check(sudo_out("(ALL) NOPASSWD: /usr/bin/systemctl")).run()
    assert not result.passed
    assert result.detail == "no sudo rule grants ALL to 'alice'"


def test_sudo_specific_command_in_list_with_tags() -> None:
    out = sudo_out("(ALL) PASSWD: /bin/cat, NOPASSWD: /bin/ls, /bin/id")
    assert sudo_check(out, "/bin/ls", nopasswd=True).run().passed
    assert sudo_check(out, "/bin/id", nopasswd=True).run().passed
    result = sudo_check(out, "/bin/cat", nopasswd=True).run()
    assert not result.passed and "requires a password" in result.detail


def test_sudo_runas_must_include_all() -> None:
    result = sudo_check(sudo_out("(root) NOPASSWD: ALL")).run()
    assert not result.passed


def test_sudo_multiple_rules_any_matches() -> None:
    out = sudo_out("(root) /bin/ls", "(ALL) ALL", "(ALL) NOPASSWD: ALL")
    assert sudo_check(out, nopasswd=True).run().passed
    out = sudo_out("(ALL) ALL", "(ALL) NOPASSWD: /bin/ls")
    assert not sudo_check(out, nopasswd=True).run().passed


def test_sudo_negated_command_is_not_a_grant() -> None:
    assert not sudo_check(sudo_out("(ALL) !ALL")).run().passed


def test_sudo_parses_only_rules_after_header() -> None:
    out = "Matching Defaults entries for alice on x:\n    (ALL) NOPASSWD: ALL\n\n" + HEADER
    result = sudo_check(out).run()
    assert not result.passed


def test_sudo_stops_at_blank_or_unindented_line() -> None:
    out = HEADER + "    (root) /bin/ls\n\nsomething\n    (ALL) NOPASSWD: ALL\n"
    assert not sudo_check(out).run().passed
    out = HEADER + "    (root) /bin/ls\nRunas and Command-specific defaults:\n    (ALL) ALL\n"
    assert not sudo_check(out).run().passed


@pytest.mark.parametrize("stdout", ["", "\n", "garbage\n", "    (ALL) ALL\n"])
def test_sudo_malformed_output(stdout: str) -> None:
    result = sudo_check(stdout).run()
    assert not result.passed and result.detail == "unexpected sudo output"


def test_sudo_garbage_rule_lines_ignored() -> None:
    out = sudo_out("not a rule", "(ALL", "(ALL) NOPASSWD: ALL")
    assert sudo_check(out).run().passed


def test_sudo_unknown_user() -> None:
    result = sudo_check("", returncode=1, stderr="sudo: unknown user alice\n").run()
    assert not result.passed and result.detail == "user 'alice' does not exist"


@pytest.mark.parametrize("stderr", ["sudo: a password is required\n", "sudo: Permission denied\n"])
def test_sudo_requires_root(stderr: str) -> None:
    result = sudo_check("", returncode=1, stderr=stderr).run()
    assert not result.passed
    assert result.detail == "sudo -l -U requires root (run with sudo)"


def test_sudo_other_exit_code() -> None:
    result = sudo_check("", returncode=2, stderr="boom\n").run()
    assert not result.passed and result.detail == "cannot query sudo rules (exit 2)"


@pytest.mark.parametrize("user", ["", "Alice", "a b", "-x", "a;b"])
def test_sudo_invalid_user(user: str) -> None:
    with pytest.raises(ValueError):
        UserHasSudoRule(FakeCommandRunner({}), user)


@pytest.mark.parametrize("command", ["", "a\nb", "a,b", "a\x00b", " ALL"])
def test_sudo_invalid_command(command: str) -> None:
    with pytest.raises(ValueError):
        UserHasSudoRule(FakeCommandRunner({}), "alice", command)


# --- AuthorizedKeyPresent ---
AK = "/home/alice/.ssh/authorized_keys"
PUB = "/root/.ssh/id_ed25519.pub"
CAT_AK = ("cat", "--", AK)
CAT_PUB = ("cat", "--", PUB)
BLOB = "AAAAC3NzaC1lZDI1NTE5AAAAIKd0xqF7cR9mJp2hQ8vYw3tLz5nB1uXoE6sDgVfHiMkA"
OTHER = "AAAAC3NzaC1lZDI1NTE5AAAAIOtherOtherOtherOtherOtherOtherOtherOtherOth"
PUB_LINE = f"ssh-ed25519 {BLOB} root@servera\n"


def ak_runner(
    ak_out: str,
    pub_out: str = PUB_LINE,
    ak_rc: int = 0,
    pub_rc: int = 0,
    ak_err: str = "",
    pub_err: str = "",
) -> FakeCommandRunner:
    return FakeCommandRunner(
        {
            CAT_AK: make_result(CAT_AK, returncode=ak_rc, stdout=ak_out, stderr=ak_err),
            CAT_PUB: make_result(CAT_PUB, returncode=pub_rc, stdout=pub_out, stderr=pub_err),
        }
    )


def key_check(runner: FakeCommandRunner) -> Check:
    return AuthorizedKeyPresent(runner, AK, PUB)


@pytest.mark.parametrize(
    "ak",
    [
        f"ssh-ed25519 {BLOB} root@servera\n",
        f"ssh-ed25519 {BLOB}\n",
        f"# comentario\nssh-ed25519 {OTHER} x\nssh-ed25519 {BLOB} y\n",
        f'command="/bin/true",no-pty ssh-ed25519 {BLOB} root@servera\n',
        f"from=\"10.0.0.0/8\" ssh-ed25519 {BLOB}",
        f"ssh-ed25519\t{BLOB}\troot@servera\n",
    ],
)
def test_key_present(ak: str) -> None:
    assert key_check(ak_runner(ak)).run().passed


@pytest.mark.parametrize(
    "ak",
    [
        "",
        f"# ssh-ed25519 {BLOB} root@servera\n",
        f"ssh-ed25519 {OTHER} root@servera\n",
        f"ssh-rsa {BLOB} root@servera\n",
        f"ssh-ed25519 {BLOB}extra root@servera\n",
        f"ssh-ed25519 {BLOB[:-4]}\n",
    ],
)
def test_key_absent(ak: str) -> None:
    result = key_check(ak_runner(ak)).run()
    assert not result.passed and "not found" in result.detail


def test_key_unreadable_files_and_hints() -> None:
    result = key_check(ak_runner("", ak_rc=1, ak_err="cat: x: No such file or directory\n")).run()
    assert not result.passed and "cannot read" in result.detail and "may need sudo" in result.detail
    result = key_check(ak_runner("", ak_rc=1, ak_err="cat: x: Permission denied\n")).run()
    assert not result.passed and "sudo" in result.detail
    result = key_check(ak_runner(PUB_LINE, pub_rc=1, pub_err="cat: x: Permission denied\n")).run()
    assert not result.passed and PUB in result.detail and "sudo" in result.detail
    result = key_check(ak_runner(PUB_LINE, pub_out="", pub_rc=1)).run()
    assert not result.passed and PUB in result.detail and "sudo" in result.detail


@pytest.mark.parametrize("pub", ["", "# only a comment\n", "ssh-ed25519\n", "\n"])
def test_key_malformed_pubkey(pub: str) -> None:
    result = key_check(ak_runner(f"ssh-ed25519 {BLOB}\n", pub_out=pub)).run()
    assert not result.passed and "not a valid public key" in result.detail


def test_key_describe_and_validation() -> None:
    assert key_check(ak_runner("")).describe() == f"{AK} authorizes the key in {PUB}"
    with pytest.raises(ValueError):
        AuthorizedKeyPresent(ak_runner(""), "relative", PUB)
    with pytest.raises(ValueError):
        AuthorizedKeyPresent(ak_runner(""), AK, "relative.pub")

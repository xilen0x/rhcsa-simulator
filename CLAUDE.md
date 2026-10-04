# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`rhcsa-sim` is an RHCSA (EX200) exam simulator: a CLI that checks whether the *live system* matches a set of exam tasks (users, groups, file permissions, ...) and scores the result. Python 3.12+, no runtime dependencies (stdlib only).

## Commands

A virtualenv already exists at `.venv` with the package installed in editable mode (`pip install -e '.[dev]'`).

```bash
.venv/bin/pytest                                   # all tests
.venv/bin/pytest tests/test_checks_users.py        # one file
.venv/bin/pytest tests/test_cli.py::test_name      # one test
.venv/bin/mypy src tests                           # strict type check (must stay clean)
.venv/bin/rhcsa-sim list | show <id> | check <id> | check --all
```

Storage (LVM), firewalld, `semanage` (SELinux booleans/ports), sshd/sudo (`sshd -T`, `visudo -c`, `sudo -n -l -U`), `chage -l` for other users, `crontab -l -u` for other users, and any check on /root paths (scripts, archives, links, saved grep output) need root: in the VM run `sudo .venv/bin/rhcsa-sim check ...`. They stay read-only (`vgs`/`pvs`/`lvs`, `firewall-cmd --query-*`); without root the check fails with a hint (e.g. LVM tools exit 5, `file` reports "cannot open") and the CLI exits 1 like any failed task.

CLI exit codes: `0` all checked tasks passed, `1` at least one failed, `2` usage error / unknown task.

## Architecture

Flow: `cli.main` → `catalog.build_catalog(runner)` → `TaskRegistry` → `evaluator.evaluate_tasks` → `reporter` formatting.

- **`models.py`** — the core types. `Task` (validated in `__post_init__`: non-empty id/description, positive points, ≥1 check) holds a tuple of `Check`s. `Check` is a `Protocol` (`describe()`, `run() -> CheckResult`), so checks are plain classes, not subclasses. `TaskResult` gives all-or-nothing points: a task earns its points only if every check passes.
- **`runner.py`** — the only place that touches the OS. `CommandRunner` is a Protocol; `SubprocessRunner` runs argv lists with `shell=False`, stdin closed, forced `LC_ALL=C` locale (so output is parseable), and a timeout. It never raises for command failures: missing command / not executable / timeout map to `CommandResult` with return codes 127 / 126 / 124. It does validate argv (no single string, no empty, no NUL bytes) and raises `ValueError` for that.
- **`checks/`** — concrete read-only checks grouped by exam domain (`users.py` (passwd/group via `getent`, password aging via `chage -l`, which needs root for other users, and `/etc/login.defs` values), `files.py` (mode/owner via `stat`, identical copies via `cmp -s`), `storage.py` for LVM via `vgs`/`pvs`/`lvs --reportformat json`, `filesystems.py` for mounts/fstab via `findmnt`/`blkid`, `blockdev.py` for partitions and swap via `lsblk`/`swapon`/`findmnt`, `acl.py` via `getfacl`, which needs package `acl`, `services.py` via `systemctl show`/`get-default`; unknown units return rc 0 with `LoadState=not-found`, `firewall.py` via `firewall-cmd --query-*` for service/port in a zone, permanent + runtime, needs root, `network.py` via `nmcli -t ... connection show id <name>` (static IPv4, gateway, DNS, autoconnect) and `hostnamectl hostname --static`/`hostname`, `selinux.py` via `sestatus`, `stat`/`matchpathcon`, `getsebool` and `semanage`, which needs root, `security.py` via `sshd -T`, `visudo -c` and `sudo -n -l -U <user>`, all need root, `maintenance.py` via `dnf repolist --all`, `rpm -q`, `crontab -l -u` (root for other users) and `tuned-adm active`, `scripts.py` static only via `stat`/`head`/`bash -n`/`grep`: it never executes student scripts, and /root paths need root, `processes.py` via `ps -C <comm> -o pid=,ni=,user:32=,stat=,comm=` (running with optional nice/owner, or not running; zombies are ignored; comm max 15 chars) and `logs.py` for persistent journald via `systemd-analyze cat-config systemd/journald.conf` (effective `Storage=persistent`) plus `stat -L` of `/var/log/journal`) and `essentials.py` for compressed tar archives (`file -b --mime-type` + `tar -tf`, never extracted; needs package `file`), hard/symbolic links (`stat -c '%d %i %F'`, `readlink`) and saved grep output (re-runs `grep` and compares with `cat`); /root paths need root. Each is a frozen, slotted dataclass that receives the `runner` as its first field, validates inputs in `__post_init__` (via `checks/_validation.py`: account-name regex, absolute path), and inspects the system through commands like `getent`, `id -Gn --`, `stat -c`. Parse failures return a failing `CheckResult`, not an exception.
- **`catalog.py`** — the task bank. Tasks are declared here, wiring checks to the injected runner. Adding an exam task = add a `Task` here (plus new check classes in `checks/` if needed).
- **`evaluator.py`** — runs every check with no short-circuit (so all failures are shown) and converts any exception raised by a check into a failed `CheckResult`, so one broken check never crashes the simulator.
- **`reporter.py`** — output formatting. All system-derived text goes through `sanitize_text` (strips control chars to prevent terminal escape injection). Color respects `NO_COLOR`, `TERM=dumb`, and TTY detection. `PASS_THRESHOLD_PERCENT = 70` mirrors the official exam threshold.
- **`testing.py`** — shipped test helpers: `FakeCommandRunner` maps exact argv tuples to canned `CommandResult`s (via `make_result`) and raises `AssertionError` on any unexpected command. Tests for checks must use it rather than touching the real system.

`cli.main` accepts injectable `runner`, `stdout`, `stderr`, and `env` for testing; argparse `SystemExit` is converted to a return code instead of propagating.

## Conventions

- Dependency injection through Protocols (`Check`, `CommandRunner`); no global state.
- Frozen, slotted dataclasses for values and checks; `from __future__ import annotations` in every module.
- Code identifiers and CLI output are in English; docstrings/comments and task descriptions in `catalog.py` are in Spanish.
- When passing user-supplied names/paths to commands, validate them first and use `--` before positional arguments.
- `ObjectiveBlock` values and `PASS_THRESHOLD_PERCENT` are meant to track the official EX200 (RHEL 10) objectives (verified against the official page on 2026-10-04); adjust if Red Hat changes them.

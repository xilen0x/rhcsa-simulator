# rhcsa-sim

A practice checker for the **RHCSA exam (EX200, RHEL 10)**. You solve the tasks on a lab VM yourself, then `rhcsa-sim` inspects the **live system** and scores the result the way the exam does: a task scores only if all its checks pass, and 70% is a pass.

The checks never change the system, never run your scripts, and only use the Python standard library.

## Quick start

```bash
git clone git@github.com:xilen0x/rhcsa-simulator.git
cd rhcsa-simulator
python3 -m venv .venv
.venv/bin/pip install -e .

.venv/bin/rhcsa-sim list              # see every task
.venv/bin/rhcsa-sim show net-01       # read one task and its checks
sudo .venv/bin/rhcsa-sim check --all  # grade everything
```

Example output:

```text
[KO] net-02  Configura de forma persistente el hostname servera.lab.example.com.  (0/10)
     [KO] hostname is servera.lab.example.com: hostname is localhost.localdomain, expected servera.lab.example.com
```

> **Run checks with `sudo`.** Many checks read root-only state (LVM, firewalld, SELinux, sudoers, `/root`, other users' files, `grubby`, `atq`). Without root they fail with a hint telling you to use sudo, and the task does not score.

## Requirements

| What | Why |
|------|-----|
| RHEL 10 or a rebuild (AlmaLinux, Rocky) | the tasks and commands target EX200 on RHEL 10 |
| Python 3.12+ | no runtime dependencies |
| A spare disk at `/dev/sdb` | storage tasks create partitions, LVM, swap and VFAT on it |
| Packages used by the checks: `acl`, `file`, `autofs`, `nfs-utils`, `flatpak`, `chrony`, `at` | a missing tool makes its checks fail, not crash |

Task text (descriptions) is in Spanish; command output is in English.

## Commands

| Command | Does |
|---------|------|
| `rhcsa-sim list` | lists task id, objective block, points and description |
| `rhcsa-sim show <id>` | shows one task and the checks that grade it |
| `rhcsa-sim check <id>` | grades one task |
| `rhcsa-sim check --all` | grades every task and prints the total score |

Exit codes: `0` every checked task passed, `1` at least one failed, `2` usage error or unknown task.

## What is covered

Tasks are grouped by the official EX200 RHEL 10 objective blocks:

| Block | Examples |
|-------|----------|
| Essential tools | tar + gzip archives, hard and soft links, saving `grep` output |
| Manage software | dnf repositories, packages, Flatpak remote and apps |
| Shell scripts | executable bash scripts with `if`, `for`, `$1`, `$(...)` (checked statically) |
| Operate running systems | nice values, persistent journal, tuned profile, copying files with `scp` |
| Local storage | GPT partitions, LVM volume group and logical volume, swap by UUID |
| File systems | XFS and VFAT mounts by UUID, NFS, autofs, ACLs, setgid directories |
| Deploy and maintain | services, default target, cron, `at`, systemd timers, chrony, `grubby` |
| Networking | static IPv4/IPv6 profiles, hostname, firewalld services and ports |
| Users and groups | users, groups, password aging, `login.defs` defaults |
| Security | SELinux modes, contexts, booleans and ports, sshd and sudo, umask, SSH keys |

Run `rhcsa-sim list` for the exact task list.

## Development

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest                # all tests (they never touch the real system)
.venv/bin/mypy src tests        # strict type check, must stay clean
```

Adding a task:

1. Add a check class in `src/rhcsa_sim/checks/` if no existing check fits. Checks are frozen dataclasses that receive a `CommandRunner` and return a `CheckResult`.
2. Declare the `Task` in `src/rhcsa_sim/catalog.py`.
3. Test it with `rhcsa_sim.testing.FakeCommandRunner`, using real command output captured on a RHEL 10 machine as fixtures.

`CLAUDE.md` describes the architecture and conventions in more detail.

## Contributing

Issues and pull requests are welcome. Before opening a PR:

- [ ] `.venv/bin/pytest` passes and `.venv/bin/mypy src tests` is clean.
- [ ] New checks are read-only and tested with `FakeCommandRunner`.
- [ ] Test fixtures come from real command output on RHEL 10 (say so in the PR if you could only derive them).
- [ ] New tasks map to an objective on the [official EX200 page](https://www.redhat.com/en/services/training/ex200-red-hat-certified-system-administrator-rhcsa-exam).

## License

[MIT](LICENSE).

## Disclaimer

This is an independent, unofficial study tool. It is not affiliated with, endorsed by or sponsored by Red Hat, Inc. Red Hat, RHEL, RHCSA and EX200 are trademarks or registered trademarks of Red Hat, Inc. The tasks are original practice exercises based on the public exam objectives; they are not real exam questions. Passing here does not guarantee passing the real exam.

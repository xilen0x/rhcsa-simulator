from __future__ import annotations

import pytest

from rhcsa_sim.checks.boot import KernelArgPresent
from rhcsa_sim.models import Check
from rhcsa_sim.testing import FakeCommandRunner, make_result

GRUBBY = ("grubby", "--info=ALL")
ARGS = "ro crashkernel=2G-64G:256M,64G-:512M resume=UUID=995e11a3-d8d0-47b1-b098-623b4b1039a1 rd.lvm.lv=almalinux/root rd.lvm.lv=almalinux/swap audit=0"


def _entry(index: int, kernel: str, args: str, title: str, entry_id: str) -> str:
    return (
        f"index={index}\n"
        f'kernel="{kernel}"\n'
        f'args="{args}"\n'
        'root="/dev/mapper/almalinux-root"\n'
        f'initrd="{kernel.replace("vmlinuz", "initramfs")}.img"\n'
        f'title="{title}"\n'
        f'id="{entry_id}"\n'
    )


# formato real de `sudo grubby --info=ALL` (3 entradas: 2 kernels + rescue)
def _grubby_out(extra: str = "") -> str:
    suffix = f" {extra}" if extra else ""
    return (
        _entry(0, "/boot/vmlinuz-6.12.0-211.49.1.el10_2.x86_64", ARGS + suffix,
               "AlmaLinux (6.12.0-211.49.1.el10_2.x86_64) 10.2", "abc-6.12.0-211.49.1.el10_2.x86_64")
        + _entry(1, "/boot/vmlinuz-6.12.0-124.8.1.el10_1.x86_64", ARGS + suffix,
                 "AlmaLinux (6.12.0-124.8.1.el10_1.x86_64) 10.1", "abc-6.12.0-124.8.1.el10_1.x86_64")
        + _entry(2, "/boot/vmlinuz-0-rescue-abc", ARGS + suffix,
                 "AlmaLinux (0-rescue-abc) 10.2", "abc-0-rescue")
    )


def _check(stdout: str = "", rc: int = 0, stderr: str = "", arg: str = "audit=0") -> Check:
    runner = FakeCommandRunner({GRUBBY: make_result(GRUBBY, returncode=rc, stdout=stdout, stderr=stderr)})
    return KernelArgPresent(runner, arg)


# salida literal de `sudo grubby --info=ALL` en la VM de laboratorio (2026-10-04)
REAL_GRUBBY = """\
index=0
kernel="/boot/vmlinuz-6.12.0-211.49.1.el10_2.x86_64"
args="ro crashkernel=2G-64G:256M,64G-:512M resume=UUID=995e11a3-d8d0-47b1-b098-623b4b1039a1 rd.lvm.lv=almalinux/root rd.lvm.lv=almalinux/swap audit=0"
root="/dev/mapper/almalinux-root"
initrd="/boot/initramfs-6.12.0-211.49.1.el10_2.x86_64.img"
title="AlmaLinux (6.12.0-211.49.1.el10_2.x86_64) 10.2 (Lavender Lion)"
id="e84779d92877485c97471ca85acc19f6-6.12.0-211.49.1.el10_2.x86_64"
index=1
kernel="/boot/vmlinuz-6.12.0-211.7.3.el10_2.x86_64"
args="ro crashkernel=2G-64G:256M,64G-:512M resume=UUID=995e11a3-d8d0-47b1-b098-623b4b1039a1 rd.lvm.lv=almalinux/root rd.lvm.lv=almalinux/swap audit=0"
root="/dev/mapper/almalinux-root"
initrd="/boot/initramfs-6.12.0-211.7.3.el10_2.x86_64.img"
title="AlmaLinux (6.12.0-211.7.3.el10_2.x86_64) 10.2 (Lavender Lion)"
id="e84779d92877485c97471ca85acc19f6-6.12.0-211.7.3.el10_2.x86_64"
index=2
kernel="/boot/vmlinuz-0-rescue-e84779d92877485c97471ca85acc19f6"
args="ro crashkernel=2G-64G:256M,64G-:512M resume=UUID=995e11a3-d8d0-47b1-b098-623b4b1039a1 rd.lvm.lv=almalinux/root rd.lvm.lv=almalinux/swap audit=0"
root="/dev/mapper/almalinux-root"
initrd="/boot/initramfs-0-rescue-e84779d92877485c97471ca85acc19f6.img"
title="AlmaLinux (0-rescue-e84779d92877485c97471ca85acc19f6) 10.2 (Lavender Lion)"
id="e84779d92877485c97471ca85acc19f6-0-rescue"
"""


def test_real_output_present_and_missing() -> None:
    assert _check(REAL_GRUBBY, arg="audit=0").run().passed
    result = _check(REAL_GRUBBY, arg="systemd.show_status=1").run()
    assert not result.passed
    assert "vmlinuz-0-rescue-e84779d92877485c97471ca85acc19f6" in result.detail


def test_present_in_every_entry() -> None:
    result = _check(_grubby_out()).run()
    assert result.passed
    assert "audit=0" in result.detail


def test_key_value_arg_added_to_all() -> None:
    assert _check(_grubby_out("systemd.show_status=1"), arg="systemd.show_status=1").run().passed


def test_missing_everywhere_lists_entries() -> None:
    result = _check(_grubby_out(), arg="systemd.show_status=1").run()
    assert not result.passed
    assert "/boot/vmlinuz-0-rescue-abc" in result.detail
    assert "/boot/vmlinuz-6.12.0-211.49.1.el10_2.x86_64" in result.detail


def test_missing_in_one_entry_only() -> None:
    out = _grubby_out("quiet").replace('audit=0 quiet"', 'audit=0"', 1)
    result = _check(out, arg="quiet").run()
    assert not result.passed
    assert "vmlinuz-6.12.0-211.49.1.el10_2" in result.detail
    assert "vmlinuz-0-rescue-abc" not in result.detail


def test_exact_token_match_only() -> None:
    out = _grubby_out("audit=01")
    assert not _check(out.replace("audit=0 ", "", 3), arg="audit=0").run().passed
    assert not _check(_grubby_out(), arg="audit").run().passed


def test_empty_stdout_fails_with_sudo_hint() -> None:
    result = _check("", stderr="grep: /boot/grub2/grubenv: Permission denied\n").run()
    assert not result.passed
    assert "no boot entries visible" in result.detail and "sudo" in result.detail


def test_nonzero_rc_reports_first_stderr_line() -> None:
    result = _check("", rc=1, stderr="grubby: boom\nsecond\n").run()
    assert not result.passed
    assert "grubby: boom" in result.detail and "second" not in result.detail


def test_entry_without_args_fails() -> None:
    out = 'index=0\nkernel="/boot/vmlinuz-x"\ntitle="x"\n'
    result = _check(out).run()
    assert not result.passed and "/boot/vmlinuz-x" in result.detail


def test_describe() -> None:
    assert "audit=0" in _check().describe()


@pytest.mark.parametrize("bad", ["", "a b", "-x", "a\0b", "a\tb"])
def test_invalid_arg_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        KernelArgPresent(FakeCommandRunner({}), bad)

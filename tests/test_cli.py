from __future__ import annotations

import io
from collections.abc import Sequence

import pytest

from rhcsa_sim.cli import main
from rhcsa_sim.testing import FakeCommandRunner, make_result

GROUP = ("getent", "group", "devs")
PASSWD = ("getent", "passwd", "alice")
IDG = ("id", "-Gn", "--", "alice")
STAT = ("stat", "-c", "%a %U %G", "--", "/srv/shared")
VGS = (
    "vgs", "--reportformat", "json", "--units", "b", "--nosuffix",
    "-o", "vg_name,vg_extent_size", "--", "examvg",
)  # fmt: skip
PVS = ("pvs", "--reportformat", "json", "-o", "pv_name,vg_name", "--", "/dev/sdb1")
LVS = (
    "lvs", "--reportformat", "json", "--units", "b", "--nosuffix",
    "-o", "vg_name,lv_name,lv_size", "--", "examvg/datalv",
)  # fmt: skip
VGS_OUT = '{"report": [{"vg": [{"vg_name": "examvg", "vg_extent_size": "16777216"}]}]}'
PVS_OUT = '{"report": [{"pv": [{"pv_name": "/dev/sdb1", "vg_name": "examvg"}]}]}'
LVS_OUT = (
    '{"report": [{"lv": [{"vg_name": "examvg", "lv_name": "datalv", '
    '"lv_size": "1073741824"}]}]}'
)
DEVICE = "/dev/mapper/examvg-datalv"
UUID = "476c00b7-0000-45fe-a368-d4b5f25a5ee1"
MOUNT = ("findmnt", "-J", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS", "--mountpoint=/data")
FSTAB = (
    "findmnt", "-J", "--fstab", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS", "--mountpoint=/data",
)  # fmt: skip
GETFACL = ("getfacl", "--omit-header", "--absolute-names", "--no-effective", "--", "/data")
MOUNT_OUT = (
    f'{{"filesystems": [{{"target": "/data", "source": "{DEVICE}", '
    '"fstype": "xfs", "options": "rw,relatime"}]}'
)
FSTAB_OUT = (
    f'{{"filesystems": [{{"target": "/data", "source": "UUID={UUID}", '
    '"fstype": "xfs", "options": "defaults"}]}'
)
SHOW = (
    "systemctl", "show", "--property=LoadState,ActiveState,UnitFileState", "--", "httpd.service",
)  # fmt: skip
GET_DEFAULT = ("systemctl", "get-default")
SHOW_OUT = "LoadState=loaded\nActiveState=active\nUnitFileState=enabled\n"
FW_SVC_PERM = ("firewall-cmd", "--permanent", "--zone=public", "--query-service=http")
FW_SVC_RUN = ("firewall-cmd", "--zone=public", "--query-service=http")
FW_PORT_PERM = ("firewall-cmd", "--permanent", "--zone=public", "--query-port=8080/tcp")
FW_PORT_RUN = ("firewall-cmd", "--zone=public", "--query-port=8080/tcp")
NMCLI = (
    "nmcli", "-t", "-f",
    "connection.id,connection.autoconnect,ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns",
    "connection", "show", "id", "exam-static",
)  # fmt: skip
HOSTNAME_STATIC = ("hostnamectl", "hostname", "--static")
HOSTNAME_RUNTIME = ("hostname",)
HOSTNAME = "servera.lab.example.com"
MIB = 1024 * 1024
SWAP_UUID = "995e11a3-0000-45fe-a368-d4b5f25a5ee1"
LSBLK_SDB2 = (
    "lsblk", "-J", "-l", "-b", "-o", "PATH,KNAME,SIZE,TYPE,FSTYPE,UUID,PARTTYPENAME",
    "--", "/dev/sdb2",
)  # fmt: skip
SWAPON = ("swapon", "--show=NAME,SIZE", "--bytes", "--noheadings", "--raw")
FSTAB_SWAP = (
    "findmnt", "-J", "--fstab", "-t", "swap", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS",
)  # fmt: skip
LSBLK_SDB2_OUT = (
    '{"blockdevices": [{"path": "/dev/sdb2", "kname": "sdb2", "size": 536870912, '
    f'"type": "part", "fstype": "swap", "uuid": "{SWAP_UUID}", '
    '"parttypename": "Linux swap"}]}'
)
SWAPON_OUT = "/dev/sdb2 536866816\n"
FSTAB_SWAP_OUT = (
    f'{{"filesystems": [{{"target": "none", "source": "UUID={SWAP_UUID}", '
    '"fstype": "swap", "options": "defaults"}]}'
)
SESTATUS = ("sestatus",)
SE_STAT = ("stat", "-c", "%C", "--", "/srv/web")
SE_RULE = ("matchpathcon", "-n", "--", "/srv/web")
GETSEBOOL = ("getsebool", "httpd_can_network_connect")
SEMANAGE_BOOL = ("semanage", "boolean", "-l")
SEMANAGE_PORT = ("semanage", "port", "-l")
SE_CONTEXT = "system_u:object_r:httpd_sys_content_t:s0\n"
SEMANAGE_BOOL_OUT = (
    "SELinux boolean                State  Default Description\n\n"
    "httpd_can_network_connect      (on   ,   on)  Allow httpd to can network connect\n"
)
SEMANAGE_PORT_OUT = (
    "SELinux Port Type              Proto    Port Number\n\n"
    "http_port_t                    tcp      80, 81, 82, 443, 488, 8008, 8009, 8443, 9000\n"
)
SEMANAGE_ROOT_ERR = "ValueError: SELinux policy is not managed or store cannot be accessed.\n"
SSHD = ("sshd", "-T")
VISUDO = ("visudo", "-c")
SUDO_L = ("sudo", "-n", "-l", "-U", "alice")
SSHD_OUT = "port 22\npermitrootlogin no\npasswordauthentication yes\n"
VISUDO_OUT = "/etc/sudoers: parsed OK\n/etc/sudoers.d/alice: parsed OK\n"
SUDO_L_OUT = (
    "Matching Defaults entries for alice on localhost:\n    !visiblepw\n\n"
    "User alice may run the following commands on localhost:\n    (ALL) NOPASSWD: ALL\n"
)
ACL_OUT = "user::rwx\nuser:alice:rwx\ngroup::r-x\nmask::rwx\nother::---\n"


def fs_out(stdout: str, rc: int) -> str:
    return stdout if rc == 0 else ""


def make_runner(
    group_rc: int = 0,
    lvm_rc: int = 0,
    fs_rc: int = 0,
    mount_device: str = DEVICE,
    svc_rc: int = 0,
    default_target: str = "multi-user.target",
    fw_rc: int = 0,
    selinux_mode: str = "enforcing",
    semanage_rc: int = 0,
    blockdev_rc: int = 0,
    net_method: str = "manual",
    running_hostname: str = HOSTNAME,
    root_rc: int = 0,
    permit_root_login: str = "no",
) -> FakeCommandRunner:
    group_out = "devs:x:5000:alice\n" if group_rc == 0 else ""
    # sin root, LVM avisa por stderr y sale con codigo distinto de cero
    lvm_err = "" if lvm_rc == 0 else "WARNING: Running as a non-root user.\n"
    mount_out = MOUNT_OUT.replace(DEVICE, mount_device)
    show_out = SHOW_OUT if svc_rc == 0 else ""
    fw_out = "yes\n" if fw_rc == 0 else ""
    sestatus_out = (
        "SELinux status:                 enabled\n"
        f"Current mode:                   {selinux_mode}\n"
        f"Mode from config file:          {selinux_mode}\n"
    )
    # sin root, semanage falla con rc 1 y un ValueError sobre el store de politica
    semanage_err = SEMANAGE_ROOT_ERR if semanage_rc == 1 else ""
    # rc 32 = lsblk no encuentra el dispositivo
    lsblk_out = LSBLK_SDB2_OUT if blockdev_rc == 0 else ""
    nmcli_out = (
        "connection.id:exam-static\nconnection.autoconnect:yes\n"
        f"ipv4.method:{net_method}\nipv4.addresses:192.168.122.50/24\n"
        "ipv4.gateway:192.168.122.1\nipv4.dns:192.168.122.1\n"
    )
    # sin root, sshd/visudo dicen "Permission denied" y sudo -n pide contrasena
    sshd_err = "/etc/ssh/sshd_config: Permission denied\n" if root_rc else ""
    visudo_err = "visudo: unable to open /etc/sudoers: Permission denied\n" if root_rc else ""
    sudo_err = "sudo: a password is required\n" if root_rc else ""
    sshd_out = SSHD_OUT.replace("permitrootlogin no", f"permitrootlogin {permit_root_login}")
    blkid = ("blkid", "-o", "value", "-s", "UUID", "--", mount_device)
    return FakeCommandRunner(
        {
            GROUP: make_result(GROUP, returncode=group_rc, stdout=group_out),
            PASSWD: make_result(PASSWD, stdout="alice:x:1234:1234:A:/home/alice:/bin/bash\n"),
            IDG: make_result(IDG, stdout="alice devs\n"),
            STAT: make_result(STAT, stdout="2770 root devs\n"),
            VGS: make_result(VGS, returncode=lvm_rc, stdout=VGS_OUT, stderr=lvm_err),
            PVS: make_result(PVS, returncode=lvm_rc, stdout=PVS_OUT, stderr=lvm_err),
            LVS: make_result(LVS, returncode=lvm_rc, stdout=LVS_OUT, stderr=lvm_err),
            MOUNT: make_result(MOUNT, returncode=fs_rc, stdout=fs_out(mount_out, fs_rc)),
            FSTAB: make_result(FSTAB, returncode=fs_rc, stdout=fs_out(FSTAB_OUT, fs_rc)),
            LSBLK_SDB2: make_result(LSBLK_SDB2, returncode=blockdev_rc, stdout=lsblk_out),
            SWAPON: make_result(SWAPON, stdout=SWAPON_OUT),
            FSTAB_SWAP: make_result(FSTAB_SWAP, stdout=FSTAB_SWAP_OUT),
            blkid: make_result(blkid, stdout=f"{UUID}\n"),
            GETFACL: make_result(GETFACL, returncode=fs_rc, stdout=fs_out(ACL_OUT, fs_rc)),
            SHOW: make_result(SHOW, returncode=svc_rc, stdout=show_out),
            GET_DEFAULT: make_result(
                GET_DEFAULT, returncode=svc_rc, stdout=f"{default_target}\n" if svc_rc == 0 else ""
            ),
            FW_SVC_PERM: make_result(FW_SVC_PERM, returncode=fw_rc, stdout=fw_out),
            FW_SVC_RUN: make_result(FW_SVC_RUN, returncode=fw_rc, stdout=fw_out),
            FW_PORT_PERM: make_result(FW_PORT_PERM, returncode=fw_rc, stdout=fw_out),
            FW_PORT_RUN: make_result(FW_PORT_RUN, returncode=fw_rc, stdout=fw_out),
            NMCLI: make_result(NMCLI, stdout=nmcli_out),
            HOSTNAME_STATIC: make_result(HOSTNAME_STATIC, stdout=f"{HOSTNAME}\n"),
            HOSTNAME_RUNTIME: make_result(HOSTNAME_RUNTIME, stdout=f"{running_hostname}\n"),
            SSHD: make_result(
                SSHD, returncode=255 if root_rc else 0, stderr=sshd_err,
                stdout="" if root_rc else sshd_out,
            ),
            VISUDO: make_result(
                VISUDO, returncode=root_rc, stderr=visudo_err,
                stdout="" if root_rc else VISUDO_OUT,
            ),
            SUDO_L: make_result(
                SUDO_L, returncode=root_rc, stderr=sudo_err,
                stdout="" if root_rc else SUDO_L_OUT,
            ),
            SESTATUS: make_result(SESTATUS, stdout=sestatus_out),
            SE_RULE: make_result(SE_RULE, stdout=SE_CONTEXT),
            SE_STAT: make_result(SE_STAT, stdout=SE_CONTEXT),
            GETSEBOOL: make_result(GETSEBOOL, stdout="httpd_can_network_connect --> on\n"),
            SEMANAGE_BOOL: make_result(
                SEMANAGE_BOOL, returncode=semanage_rc, stderr=semanage_err,
                stdout=SEMANAGE_BOOL_OUT if semanage_rc == 0 else "",
            ),
            SEMANAGE_PORT: make_result(
                SEMANAGE_PORT, returncode=semanage_rc, stderr=semanage_err,
                stdout=SEMANAGE_PORT_OUT if semanage_rc == 0 else "",
            ),
        }
    )


def run_cli(argv: Sequence[str], runner: FakeCommandRunner) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, runner=runner, stdout=out, stderr=err, env={})
    return code, out.getvalue(), err.getvalue()


def test_list() -> None:
    code, out, _ = run_cli(["list"], make_runner())
    assert code == 0
    assert "users-01" in out and "files-01" in out


def test_show_and_unknown() -> None:
    code, out, _ = run_cli(["show", "users-01"], make_runner())
    assert code == 0 and "devs" in out
    code, _, err = run_cli(["show", "nope"], make_runner())
    assert code == 2 and "unknown task" in err


def test_check_single_ok_and_ko() -> None:
    code, out, _ = run_cli(["check", "users-01"], make_runner())
    assert code == 0 and "[OK] users-01" in out
    code, out, _ = run_cli(["check", "users-01"], make_runner(group_rc=2))
    assert code == 1 and "[KO] users-01" in out


def test_check_all_pass() -> None:
    code, out, _ = run_cli(["check", "--all"], make_runner())
    assert code == 0
    assert "210/210" in out and "PASS" in out


def test_check_all_with_failure() -> None:
    runner = make_runner(
        group_rc=2, lvm_rc=5, fs_rc=1, svc_rc=1, fw_rc=253, semanage_rc=1, blockdev_rc=32,
        net_method="auto", running_hostname="localhost", root_rc=1,
    )
    code, out, _ = run_cli(["check", "--all"], runner)
    assert code == 1
    assert "40/210" in out and "FAIL" in out


def test_check_storage_failure_shows_root_hint() -> None:
    code, out, _ = run_cli(["check", "storage-01"], make_runner(lvm_rc=5))
    assert code == 1 and "[KO] storage-01" in out
    assert "exit 5" in out and "sudo" in out


def test_check_filesystem_tasks_ok_and_ko() -> None:
    code, out, _ = run_cli(["check", "fs-01"], make_runner())
    assert code == 0 and "[OK] fs-01" in out
    code, out, _ = run_cli(["check", "fs-02"], make_runner())
    assert code == 0 and "[OK] fs-02" in out
    code, out, _ = run_cli(["check", "fs-01"], make_runner(fs_rc=1))
    assert code == 1 and "[KO] fs-01" in out and "not mounted" in out
    code, out, _ = run_cli(["check", "fs-02"], make_runner(fs_rc=127))
    assert code == 1 and "[KO] fs-02" in out and "install package acl" in out


def test_check_partition_and_swap_tasks_ok_and_ko() -> None:
    for task_id in ("part-01", "swap-01"):
        code, out, _ = run_cli(["check", task_id], make_runner())
        assert code == 0 and f"[OK] {task_id}" in out
    code, out, _ = run_cli(["check", "part-01"], make_runner(blockdev_rc=32))
    assert code == 1 and "[KO] part-01" in out and "/dev/sdb2" in out
    assert "does not exist" in out


def test_check_fs_01_fails_when_mounted_from_another_device() -> None:
    runner = make_runner(mount_device="/dev/sdb2")
    code, out, _ = run_cli(["check", "fs-01"], runner)
    assert code == 1 and "[KO] fs-01" in out
    assert "/dev/sdb2" in out and DEVICE in out


def test_check_service_tasks_ok_and_ko() -> None:
    code, out, _ = run_cli(["check", "svc-01"], make_runner())
    assert code == 0 and "[OK] svc-01" in out
    runner = make_runner(default_target="graphical.target")
    code, out, _ = run_cli(["check", "svc-02"], runner)
    assert code == 1 and "[KO] svc-02" in out
    assert "graphical.target" in out and "multi-user.target" in out


def test_check_firewall_tasks_ok_and_ko() -> None:
    code, out, _ = run_cli(["check", "fw-01"], make_runner())
    assert code == 0 and "[OK] fw-01" in out
    code, out, _ = run_cli(["check", "fw-02"], make_runner())
    assert code == 0 and "[OK] fw-02" in out
    code, out, _ = run_cli(["check", "fw-01"], make_runner(fw_rc=253))
    assert code == 1 and "[KO] fw-01" in out and "sudo" in out


def test_check_networking_tasks_ok_and_ko() -> None:
    for task_id in ("net-01", "net-02"):
        code, out, _ = run_cli(["check", task_id], make_runner())
        assert code == 0 and f"[OK] {task_id}" in out
    code, out, _ = run_cli(["check", "net-01"], make_runner(net_method="auto"))
    assert code == 1 and "[KO] net-01" in out
    assert "ipv4.method is auto, expected manual" in out
    code, out, _ = run_cli(["check", "net-02"], make_runner(running_hostname="localhost"))
    assert code == 1 and "[KO] net-02" in out
    assert "running hostname is localhost" in out


def test_check_selinux_tasks_ok_and_ko() -> None:
    for task_id in ("se-01", "se-02", "se-03", "se-04"):
        code, out, _ = run_cli(["check", task_id], make_runner())
        assert code == 0 and f"[OK] {task_id}" in out
    code, out, _ = run_cli(["check", "se-01"], make_runner(selinux_mode="permissive"))
    assert code == 1 and "[KO] se-01" in out
    assert "permissive" in out and "enforcing" in out
    code, out, _ = run_cli(["check", "se-03"], make_runner(semanage_rc=1))
    assert code == 1 and "[KO] se-03" in out and "sudo" in out


def test_check_security_tasks_ok_and_ko() -> None:
    for task_id in ("sec-01", "sec-02"):
        code, out, _ = run_cli(["check", task_id], make_runner())
        assert code == 0 and f"[OK] {task_id}" in out
    code, out, _ = run_cli(["check", "sec-01"], make_runner(permit_root_login="yes"))
    assert code == 1 and "[KO] sec-01" in out
    assert "permitrootlogin is yes, expected no" in out
    code, out, _ = run_cli(["check", "sec-01"], make_runner(root_rc=1))
    assert code == 1 and "[KO] sec-01" in out and "sudo" in out
    code, out, _ = run_cli(["check", "sec-02"], make_runner(root_rc=1))
    assert code == 1 and "[KO] sec-02" in out and "requires root" in out


def test_check_requires_exactly_one_selector() -> None:
    code, _, err = run_cli(["check"], make_runner())
    assert code == 2 and "exactly one" in err
    code, _, _ = run_cli(["check", "users-01", "--all"], make_runner())
    assert code == 2


def test_unknown_task_id_is_sanitized() -> None:
    _, _, err = run_cli(["check", "\x1b[31mx"], make_runner())
    assert "\x1b" not in err


def test_missing_command_returns_usage_code(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    capsys.readouterr()

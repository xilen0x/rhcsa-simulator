from __future__ import annotations

import json

import pytest

from rhcsa_sim.checks.containers import (
    ContainerHasBindMount,
    ContainerImageExists,
    ContainerPublishesPort,
    ContainerRunning,
    LingerEnabled,
    QuadletUnitDefined,
    UserServiceActive,
)
from rhcsa_sim.models import Check
from rhcsa_sim.testing import FakeCommandRunner, make_result

IMAGE = "registry.access.redhat.com/ubi10/ubi-minimal"
ID_ALICE = ("id", "-u", "--", "alice")
PREFIX = ("runuser", "-u", "alice", "--", "env", "XDG_RUNTIME_DIR=/run/user/1234", "podman")
LINGER = ("stat", "-c", "%F", "--", "/var/lib/systemd/linger/alice")
GETENT = ("getent", "passwd", "alice")
UNIT_FILE = "/home/alice/.config/containers/systemd/web.container"
CAT_UNIT = ("cat", "--", UNIT_FILE)
SHOW = (
    "systemctl", "--user", "-M", "alice@", "show", "-p", "LoadState,ActiveState", "--",
    "web.service",
)  # fmt: skip
PASSWD = "alice:x:1234:1234::/home/alice:/bin/bash\n"
QUADLET = (
    "# web\n"
    "[Unit]\n"
    "Description=Web\n"
    "\n"
    "[Container]\n"
    f"Image={IMAGE}:latest\n"
    "PublishPort=8080:80\n"
    "\n"
    "[Install]\n"
    "WantedBy=default.target\n"
)
PS_OUT = json.dumps(
    [
        {"Names": ["web"], "Image": f"{IMAGE}:latest", "State": "running"},
        {"Names": ["old"], "Image": "docker.io/library/nginx:1", "State": "exited"},
    ]
)
PORTS_OUT = json.dumps({"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]}) + "\n"
MOUNTS_OUT = (
    json.dumps(
        [{"Type": "bind", "Source": "/srv/web", "Destination": "/usr/share/web", "RW": True}]
    )
    + "\n"
)


def podman(*args: str) -> tuple[str, ...]:
    return PREFIX + args


def fake(*pairs: tuple[tuple[str, ...], dict[str, object]]) -> FakeCommandRunner:
    return FakeCommandRunner({a: make_result(a, **kw) for a, kw in pairs})  # type: ignore[arg-type]


def with_podman(
    args: tuple[str, ...], stdout: str = "", returncode: int = 0, stderr: str = ""
) -> FakeCommandRunner:
    return fake(
        (ID_ALICE, {"stdout": "1234\n"}),
        (args, {"stdout": stdout, "returncode": returncode, "stderr": stderr}),
    )


def test_checks_satisfy_protocol() -> None:
    runner = FakeCommandRunner({})
    checks: list[Check] = [
        LingerEnabled(runner, "alice"),
        ContainerImageExists(runner, "alice", IMAGE),
        ContainerRunning(runner, "alice", "web", IMAGE),
        ContainerPublishesPort(runner, "alice", "web", 8080, 80),
        ContainerHasBindMount(runner, "alice", "web", "/srv/web", "/usr/share/web"),
        QuadletUnitDefined(runner, "alice", "web", IMAGE),
        UserServiceActive(runner, "alice", "web.service"),
    ]
    assert all(c.describe() for c in checks)


def test_validation() -> None:
    r = FakeCommandRunner({})
    with pytest.raises(ValueError):
        LingerEnabled(r, "Bad User")
    with pytest.raises(ValueError):
        ContainerImageExists(r, "alice", "--all")
    with pytest.raises(ValueError):
        ContainerImageExists(r, "alice", "a b")
    with pytest.raises(ValueError):
        ContainerImageExists(r, "alice", "")
    with pytest.raises(ValueError):
        ContainerRunning(r, "alice", "-x")
    with pytest.raises(ValueError):
        ContainerRunning(r, "alice", "web", "-image")
    with pytest.raises(ValueError):
        ContainerPublishesPort(r, "alice", "web", 0, 80)
    with pytest.raises(ValueError):
        ContainerPublishesPort(r, "alice", "web", 8080, 70000)
    with pytest.raises(ValueError):
        ContainerPublishesPort(r, "alice", "web", 8080, 80, "icmp")
    with pytest.raises(ValueError):
        ContainerHasBindMount(r, "alice", "web", "rel", "/d")
    with pytest.raises(ValueError):
        ContainerHasBindMount(r, "alice", "web", "/s", "rel")
    with pytest.raises(ValueError):
        QuadletUnitDefined(r, "alice", "a/b")
    with pytest.raises(ValueError):
        QuadletUnitDefined(r, "alice", "..")
    with pytest.raises(ValueError):
        QuadletUnitDefined(r, "alice", "web", "bad image")
    with pytest.raises(ValueError):
        QuadletUnitDefined(r, "alice", "web", wanted_by="no-suffix")
    with pytest.raises(ValueError):
        UserServiceActive(r, "alice", "web")


# --- LingerEnabled ---


def test_linger_enabled() -> None:
    runner = fake((LINGER, {"stdout": "regular empty file\n"}))
    assert LingerEnabled(runner, "alice").run().passed


def test_linger_missing() -> None:
    runner = fake((LINGER, {"returncode": 1, "stderr": "No such file or directory"}))
    result = LingerEnabled(runner, "alice").run()
    assert not result.passed and "linger not enabled for alice" in result.detail


# --- ContainerImageExists ---


def test_image_exists() -> None:
    runner = with_podman(podman("image", "exists", "--", IMAGE))
    assert ContainerImageExists(runner, "alice", IMAGE).run().passed


def test_image_missing() -> None:
    runner = with_podman(podman("image", "exists", "--", IMAGE), returncode=1)
    result = ContainerImageExists(runner, "alice", IMAGE).run()
    assert not result.passed and "not present" in result.detail


def test_image_other_error_shows_stderr() -> None:
    runner = with_podman(podman("image", "exists", "--", IMAGE), returncode=125, stderr="boom\n")
    result = ContainerImageExists(runner, "alice", IMAGE).run()
    assert not result.passed and "boom" in result.detail


def test_runuser_without_root_hints_sudo() -> None:
    runner = with_podman(
        podman("image", "exists", "--", IMAGE),
        returncode=1,
        stderr="runuser: may not be used by non-root users\n",
    )
    result = ContainerImageExists(runner, "alice", IMAGE).run()
    assert not result.passed and "sudo" in result.detail


def test_unknown_user_fails() -> None:
    runner = fake((ID_ALICE, {"returncode": 1, "stderr": "id: 'alice': no such user"}))
    result = ContainerImageExists(runner, "alice", IMAGE).run()
    assert not result.passed and "alice" in result.detail


def test_bad_uid_output_fails() -> None:
    runner = fake((ID_ALICE, {"stdout": "abc\n"}))
    assert not ContainerImageExists(runner, "alice", IMAGE).run().passed


# --- ContainerRunning ---

PS = podman("ps", "-a", "--format", "json")


def test_running_ok_without_image() -> None:
    assert ContainerRunning(with_podman(PS, PS_OUT), "alice", "web").run().passed


def test_running_ok_with_image_tag_normalized() -> None:
    assert ContainerRunning(with_podman(PS, PS_OUT), "alice", "web", IMAGE).run().passed
    assert ContainerRunning(with_podman(PS, PS_OUT), "alice", "web", IMAGE + ":latest").run().passed


def test_running_wrong_image() -> None:
    result = ContainerRunning(with_podman(PS, PS_OUT), "alice", "web", "docker.io/nginx").run()
    assert not result.passed and "image" in result.detail


def test_running_not_running() -> None:
    result = ContainerRunning(with_podman(PS, PS_OUT), "alice", "old").run()
    assert not result.passed and "exited" in result.detail


def test_running_not_found_and_empty() -> None:
    assert not ContainerRunning(with_podman(PS, PS_OUT), "alice", "nope").run().passed
    result = ContainerRunning(with_podman(PS, "[]\n"), "alice", "web").run()
    assert not result.passed and "not found" in result.detail


def test_running_name_must_match_exactly() -> None:
    out = json.dumps([{"Names": ["web2"], "Image": IMAGE, "State": "running"}])
    assert not ContainerRunning(with_podman(PS, out), "alice", "web").run().passed


@pytest.mark.parametrize("out", ["not json", '{"a": 1}', '["x"]', '[{"Names": "web"}]', ""])
def test_running_unexpected_output(out: str) -> None:
    result = ContainerRunning(with_podman(PS, out), "alice", "web").run()
    assert not result.passed and "unexpected" in result.detail


def test_running_podman_failure() -> None:
    result = ContainerRunning(with_podman(PS, returncode=125, stderr="x"), "alice", "web").run()
    assert not result.passed


# --- ContainerPublishesPort ---

PORTS = podman("inspect", "--format", "{{json .HostConfig.PortBindings}}", "--", "web")


def test_port_ok() -> None:
    assert ContainerPublishesPort(with_podman(PORTS, PORTS_OUT), "alice", "web", 8080, 80).run().passed


def test_port_wrong_host_port() -> None:
    result = ContainerPublishesPort(
        with_podman(PORTS, PORTS_OUT), "alice", "web", 9090, 80
    ).run()
    assert not result.passed and "8080" in result.detail


def test_port_wrong_protocol_and_null() -> None:
    assert not ContainerPublishesPort(
        with_podman(PORTS, PORTS_OUT), "alice", "web", 8080, 80, "udp"
    ).run().passed
    result = ContainerPublishesPort(with_podman(PORTS, "null\n"), "alice", "web", 8080, 80).run()
    assert not result.passed and "no published ports" in result.detail


def test_port_container_not_found() -> None:
    runner = with_podman(PORTS, returncode=125, stderr="Error: no such object")
    result = ContainerPublishesPort(runner, "alice", "web", 8080, 80).run()
    assert not result.passed and "container not found" in result.detail


@pytest.mark.parametrize("out", ["nope", "[]", '{"80/tcp": "x"}', '{"80/tcp": [1]}'])
def test_port_unexpected_output(out: str) -> None:
    result = ContainerPublishesPort(with_podman(PORTS, out), "alice", "web", 8080, 80).run()
    assert not result.passed and "unexpected" in result.detail


# --- ContainerHasBindMount ---

MOUNTS = podman("inspect", "--format", "{{json .Mounts}}", "--", "web")


def test_mount_ok() -> None:
    check = ContainerHasBindMount(
        with_podman(MOUNTS, MOUNTS_OUT), "alice", "web", "/srv/web", "/usr/share/web"
    )
    assert check.run().passed


def test_mount_wrong_source_or_type() -> None:
    runner = with_podman(MOUNTS, MOUNTS_OUT)
    assert not ContainerHasBindMount(runner, "alice", "web", "/other", "/usr/share/web").run().passed
    volume = json.dumps([{"Type": "volume", "Source": "/srv/web", "Destination": "/usr/share/web"}])
    result = ContainerHasBindMount(
        with_podman(MOUNTS, volume), "alice", "web", "/srv/web", "/usr/share/web"
    ).run()
    assert not result.passed


def test_mount_empty_and_not_found() -> None:
    assert not ContainerHasBindMount(
        with_podman(MOUNTS, "[]\n"), "alice", "web", "/srv/web", "/d"
    ).run().passed
    result = ContainerHasBindMount(
        with_podman(MOUNTS, returncode=125), "alice", "web", "/srv/web", "/d"
    ).run()
    assert not result.passed and "container not found" in result.detail


@pytest.mark.parametrize("out", ["nope", "{}", '["x"]'])
def test_mount_unexpected_output(out: str) -> None:
    result = ContainerHasBindMount(
        with_podman(MOUNTS, out), "alice", "web", "/srv/web", "/d"
    ).run()
    assert not result.passed and "unexpected" in result.detail


# --- QuadletUnitDefined ---


def quadlet(text: str = QUADLET, passwd: str = PASSWD, cat_rc: int = 0) -> FakeCommandRunner:
    return fake(
        (GETENT, {"stdout": passwd}),
        (CAT_UNIT, {"stdout": text, "returncode": cat_rc}),
    )


def test_quadlet_ok() -> None:
    assert QuadletUnitDefined(quadlet(), "alice", "web", IMAGE).run().passed
    assert QuadletUnitDefined(quadlet(), "alice", "web").run().passed


def test_quadlet_missing_file() -> None:
    result = QuadletUnitDefined(quadlet(cat_rc=1), "alice", "web").run()
    assert not result.passed and "cannot read" in result.detail


def test_quadlet_permission_denied_hints_sudo() -> None:
    runner = fake(
        (GETENT, {"stdout": PASSWD}),
        (CAT_UNIT, {"returncode": 1, "stderr": "cat: x: Permission denied"}),
    )
    result = QuadletUnitDefined(runner, "alice", "web").run()
    assert not result.passed and "sudo" in result.detail


def test_quadlet_no_container_section() -> None:
    text = "[Unit]\nDescription=x\n[Install]\nWantedBy=default.target\n"
    result = QuadletUnitDefined(quadlet(text), "alice", "web").run()
    assert not result.passed and "[Container]" in result.detail


def test_quadlet_wrong_image() -> None:
    result = QuadletUnitDefined(quadlet(), "alice", "web", "docker.io/nginx").run()
    assert not result.passed and "Image" in result.detail


def test_quadlet_missing_install() -> None:
    text = f"[Container]\nImage={IMAGE}\n"
    result = QuadletUnitDefined(quadlet(text), "alice", "web").run()
    assert not result.passed and "WantedBy" in result.detail


def test_quadlet_wanted_by_multiple_and_other_target() -> None:
    text = f"[Container]\nImage={IMAGE}\n[Install]\nWantedBy=multi-user.target default.target\n"
    assert QuadletUnitDefined(quadlet(text), "alice", "web").run().passed
    other = f"[Container]\nImage={IMAGE}\n[Install]\nWantedBy=multi-user.target\n"
    assert not QuadletUnitDefined(quadlet(other), "alice", "web").run().passed


def test_quadlet_key_in_wrong_section_does_not_count() -> None:
    text = f"[Container]\nWantedBy=default.target\n[Install]\nImage={IMAGE}\n"
    assert not QuadletUnitDefined(quadlet(text), "alice", "web", IMAGE).run().passed


def test_quadlet_ignores_comments_and_spaces() -> None:
    text = (
        f"[Container]\n; c\n# c\n Image = {IMAGE}:latest \n[Install]\nWantedBy = default.target\n"
    )
    assert QuadletUnitDefined(quadlet(text), "alice", "web", IMAGE).run().passed


@pytest.mark.parametrize("passwd", ["", "alice:x:1:1\n", "alice:x:1:1::relative:/bin/sh\n"])
def test_quadlet_bad_passwd(passwd: str) -> None:
    runner = fake((GETENT, {"stdout": passwd}))
    assert not QuadletUnitDefined(runner, "alice", "web").run().passed


def test_quadlet_getent_failure() -> None:
    runner = fake((GETENT, {"returncode": 2}))
    result = QuadletUnitDefined(runner, "alice", "web").run()
    assert not result.passed and "alice" in result.detail


# --- UserServiceActive ---


def test_service_active() -> None:
    runner = fake((SHOW, {"stdout": "LoadState=loaded\nActiveState=active\n"}))
    assert UserServiceActive(runner, "alice", "web.service").run().passed


def test_service_inactive() -> None:
    runner = fake((SHOW, {"stdout": "LoadState=loaded\nActiveState=inactive\n"}))
    result = UserServiceActive(runner, "alice", "web.service").run()
    assert not result.passed and "inactive" in result.detail


def test_service_not_found_hints_linger() -> None:
    runner = fake((SHOW, {"stdout": "LoadState=not-found\nActiveState=inactive\n"}))
    result = UserServiceActive(runner, "alice", "web.service").run()
    assert not result.passed and "linger" in result.detail


def test_service_manager_not_running_hints_linger() -> None:
    runner = fake((SHOW, {"returncode": 1, "stderr": "Failed to connect to bus"}))
    result = UserServiceActive(runner, "alice", "web.service").run()
    assert not result.passed and "linger" in result.detail


def test_service_non_root_hints_sudo() -> None:
    runner = fake((SHOW, {"returncode": 1, "stderr": "Access denied"}))
    result = UserServiceActive(runner, "alice", "web.service").run()
    assert not result.passed and "sudo" in result.detail


@pytest.mark.parametrize("out", ["", "garbage", "LoadState=loaded\n"])
def test_service_unexpected_output(out: str) -> None:
    runner = fake((SHOW, {"stdout": out}))
    result = UserServiceActive(runner, "alice", "web.service").run()
    assert not result.passed and "unexpected" in result.detail

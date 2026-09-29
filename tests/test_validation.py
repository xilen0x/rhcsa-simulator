from __future__ import annotations

import pytest

from rhcsa_sim.checks._validation import (
    validate_acl_entry,
    validate_block_device,
    validate_fstype,
    validate_lvm_name,
    validate_unit_name,
    validate_uuid,
)


@pytest.mark.parametrize("name", ["examvg", "data_lv", "a", "vg-1.x+y", "_x", "a" * 127])
def test_valid_lvm_names(name: str) -> None:
    assert validate_lvm_name(name) == name


@pytest.mark.parametrize(
    "name", ["", "-vg", ".", "..", "a b", "vg;x", "a/b", "a\nb", "vgá", "a" * 128]
)
def test_invalid_lvm_names(name: str) -> None:
    with pytest.raises(ValueError):
        validate_lvm_name(name)


@pytest.mark.parametrize(
    "path", ["/dev/sdb1", "/dev/vda", "/dev/mapper/examvg-datalv", "/dev/disk/by-id/a:b", "/dev/_x"]
)
def test_valid_block_devices(path: str) -> None:
    assert validate_block_device(path) == path


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/dev/",
        "/dev/../etc/passwd",
        "/dev/sdb/../sda",
        "/dev/./sdb",
        "/etc/sdb1",
        "dev/sdb1",
        "/dev/-x",
        "/dev/sd b",
        "/dev/sdb\n",
        "/dev/sdb\x00",
        "/dev/sdb\t1",
        "/dev/sdb;x",
    ],
)
def test_invalid_block_devices(path: str) -> None:
    with pytest.raises(ValueError):
        validate_block_device(path)


@pytest.mark.parametrize("name", ["xfs", "ext4", "vfat", "fuse.sshfs", "iso9660", "a", "x" * 32])
def test_valid_fstypes(name: str) -> None:
    assert validate_fstype(name) == name


@pytest.mark.parametrize("name", ["", "-xfs", ".x", "XFS", "xf s", "xfs\n", "a/b", "x" * 33, "xfs;x"])
def test_invalid_fstypes(name: str) -> None:
    with pytest.raises(ValueError):
        validate_fstype(name)


@pytest.mark.parametrize(
    "value",
    ["476c00b7-0000-45fe-a368-d4b5f25a5ee1", "476C00B7-0000-45FE-A368-D4B5F25A5EE1", "1A2B-3C4D"],
)
def test_valid_uuids(value: str) -> None:
    assert validate_uuid(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "deadbeef",
        "476c00b7-0000-45fe-a368-d4b5f25a5ee",
        "476c00b7-0000-45fe-a368-d4b5f25a5ee1a",
        "476c00b70000-45fe-a368-d4b5f25a5ee1",
        "476c00g7-0000-45fe-a368-d4b5f25a5ee1",
        "1A2B-3C4",
        "1A2B3C4D",
        "1A2B-3C4D\n",
        "476c00b7-0000-45fe-a368-d4b5f25a5ee1\n",
    ],
)
def test_invalid_uuids(value: str) -> None:
    with pytest.raises(ValueError):
        validate_uuid(value)


@pytest.mark.parametrize(
    "entry",
    [
        "user:alice:rwx",
        "user::rw-",
        "group:devs:r-x",
        "group::---",
        "mask::rwx",
        "other::r--",
        "default:user:alice:rwx",
        "default:mask::r-x",
        "default:other::---",
    ],
)
def test_valid_acl_entries(entry: str) -> None:
    assert validate_acl_entry(entry) == entry


@pytest.mark.parametrize(
    "entry",
    [
        "",
        "user:alice",
        "user:alice:rwz",
        "user:alice:rw",
        "user:alice:rwxx",
        "user:alice:wrx",
        "user:Alice:rwx",
        "user:al ice:rwx",
        "user:alice:rwx\n",
        "mask:alice:rwx",
        "other:bob:r--",
        "mask::rwx:x",
        "default:default:user:a:rwx",
        "owner:alice:rwx",
        "default:user:alice:rwx:",
    ],
)
def test_invalid_acl_entries(entry: str) -> None:
    with pytest.raises(ValueError):
        validate_acl_entry(entry)


@pytest.mark.parametrize(
    "name",
    [
        "sshd.service",
        "getty@tty1.service",
        "fstrim.timer",
        "multi-user.target",
        "systemd-fsck@dev-sda1.service",
        "data.mount",
        "a.b.socket",
    ],
)
def test_valid_unit_names(name: str) -> None:
    assert validate_unit_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "",
        "sshd",
        "-x.service",
        ".x.service",
        "a b.service",
        "x;y.service",
        "../x.service",
        "a/b.service",
        "a\\b.service",
        "x.conf",
        ".service",
        "..service",
        "x.service\n",
        "x.service\x00",
        "a" * 251 + ".service",
    ],
)
def test_invalid_unit_names(name: str) -> None:
    with pytest.raises(ValueError):
        validate_unit_name(name)

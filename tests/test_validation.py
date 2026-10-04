from __future__ import annotations

import ipaddress

import pytest

from rhcsa_sim.checks._validation import (
    validate_acl_entry,
    validate_block_device,
    validate_connection_name,
    validate_fstype,
    validate_firewall_service,
    validate_hostname,
    validate_ipv4_address,
    validate_ipv4_interface,
    validate_lvm_name,
    validate_nfs_source,
    validate_port,
    validate_protocol,
    validate_selinux_boolean,
    validate_selinux_type,
    validate_unit_name,
    validate_uuid,
    validate_zone,
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


@pytest.mark.parametrize("name", ["public", "dmz", "trusted", "my_zone-1", "a", "z" * 17])
def test_valid_zones(name: str) -> None:
    assert validate_zone(name) == name


@pytest.mark.parametrize(
    "name", ["", "-public", "--zone", "a b", "z;x", "a/b", "public\n", "zoná", "z" * 18]
)
def test_invalid_zones(name: str) -> None:
    with pytest.raises(ValueError):
        validate_zone(name)


@pytest.mark.parametrize("name", ["http", "https", "ssh", "dhcpv6-client", "a", "x.y+z_1", "a" * 64])
def test_valid_firewall_services(name: str) -> None:
    assert validate_firewall_service(name) == name


@pytest.mark.parametrize(
    "name", ["", "-http", ".http", "HTTP", "ht tp", "http\n", "a/b", "x;y", "a" * 65]
)
def test_invalid_firewall_services(name: str) -> None:
    with pytest.raises(ValueError):
        validate_firewall_service(name)


@pytest.mark.parametrize("port", [1, 80, 8080, 65535])
def test_valid_ports(port: int) -> None:
    assert validate_port(port) == port


@pytest.mark.parametrize("port", [0, -1, 65536, True, False])
def test_invalid_ports(port: int) -> None:
    with pytest.raises(ValueError):
        validate_port(port)


@pytest.mark.parametrize("proto", ["tcp", "udp", "sctp", "dccp"])
def test_valid_protocols(proto: str) -> None:
    assert validate_protocol(proto) == proto


@pytest.mark.parametrize("proto", ["", "TCP", "icmp", "tcp ", "tcp\n", "tcp/udp"])
def test_invalid_protocols(proto: str) -> None:
    with pytest.raises(ValueError):
        validate_protocol(proto)


@pytest.mark.parametrize("name", ["httpd_sys_content_t", "default_t", "a_t", "a" * 126 + "_t"])
def test_valid_selinux_types(name: str) -> None:
    assert validate_selinux_type(name) == name


@pytest.mark.parametrize(
    "name", ["", "httpd", "_t", "HTTPD_t", "1a_t", "a-b_t", "a b_t", "a_t\n", "a" * 127 + "_t"]
)
def test_invalid_selinux_types(name: str) -> None:
    with pytest.raises(ValueError):
        validate_selinux_type(name)


@pytest.mark.parametrize("name", ["httpd_can_network_connect", "a", "allow_ftpd_anon_write2"])
def test_valid_selinux_booleans(name: str) -> None:
    assert validate_selinux_boolean(name) == name


@pytest.mark.parametrize("name", ["", "_x", "1a", "HTTPD", "a-b", "a b", "a;b", "a\n", "a" * 129])
def test_invalid_selinux_booleans(name: str) -> None:
    with pytest.raises(ValueError):
        validate_selinux_boolean(name)


@pytest.mark.parametrize("name", ["exam-static", "a", "Wired connection 1", "ens3", "a" * 64])
def test_valid_connection_names(name: str) -> None:
    assert validate_connection_name(name) == name


@pytest.mark.parametrize(
    "name", ["", "-x", " a", "a ", "a\nb", "a\x00b", "a\tb", "a\x1bb", "a" * 65, "a\x7fb"]
)
def test_invalid_connection_names(name: str) -> None:
    with pytest.raises(ValueError):
        validate_connection_name(name)


def test_valid_ipv4_interface_is_normalized() -> None:
    iface = validate_ipv4_interface("192.168.122.50/24")
    assert iface == ipaddress.IPv4Interface("192.168.122.50/24")
    assert validate_ipv4_interface("10.0.0.5/255.0.0.0") == ipaddress.IPv4Interface("10.0.0.5/8")


@pytest.mark.parametrize(
    "text", ["", "192.168.122.50", "192.168.122.50/33", "300.1.1.1/24", "::1/64", "a/24", " 1.1.1.1/24"]
)
def test_invalid_ipv4_interfaces(text: str) -> None:
    with pytest.raises(ValueError):
        validate_ipv4_interface(text)


def test_valid_ipv4_address() -> None:
    assert validate_ipv4_address("192.168.122.1") == ipaddress.IPv4Address("192.168.122.1")


@pytest.mark.parametrize("text", ["", "1.1.1", "1.1.1.1/24", "::1", "256.1.1.1", "1.1.1.1 ", "x"])
def test_invalid_ipv4_addresses(text: str) -> None:
    with pytest.raises(ValueError):
        validate_ipv4_address(text)


@pytest.mark.parametrize(
    "name",
    ["servera.lab.example.com", "localhost", "a", "a-b.c1", "a" * 63, ".".join(["a" * 63] * 3 + ["b" * 61])],
)
def test_valid_hostnames(name: str) -> None:
    assert validate_hostname(name) == name


@pytest.mark.parametrize(
    "name",
    ["", "A.example.com", "-a", "a-", "a..b", ".a", "a.", "a_b", "a b", "a\n", "a" * 64,
     ".".join(["a" * 63] * 4)],
)  # fmt: skip
def test_invalid_hostnames(name: str) -> None:
    with pytest.raises(ValueError):
        validate_hostname(name)


@pytest.mark.parametrize("source", ["localhost:/srv/nfsexport", "10.0.0.1:/", "[::1]:/srv/x"])
def test_valid_nfs_sources(source: str) -> None:
    assert validate_nfs_source(source) == source


@pytest.mark.parametrize("source", ["", "localhost", "host:srv", ":/x", "h :/x", "h:/x y", "h:/x\0"])
def test_invalid_nfs_sources(source: str) -> None:
    with pytest.raises(ValueError):
        validate_nfs_source(source)

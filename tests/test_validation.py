from __future__ import annotations

import pytest

from rhcsa_sim.checks._validation import validate_block_device, validate_lvm_name


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

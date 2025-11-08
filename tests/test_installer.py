from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pytest

from archinstaller.installer import ArchInstaller, InstallerConfig
from archinstaller.system import CommandRunner


class FakeRunner(CommandRunner):
    def __init__(self, responses: Dict[str, str] | None = None) -> None:
        self.responses = responses or {}
        self.commands: List[str] = []

    def run(self, command: str, check: bool = True) -> str:  # pragma: no cover - behaviour tested indirectly
        self.commands.append(command)
        return self.responses.get(command, "")


def make_config(**overrides: str) -> InstallerConfig:
    defaults = dict(
        disk="/dev/sda",
        filesystem="ext4",
        timezone="Europe/Moscow",
        username="testuser",
        password="secret",
    )
    defaults.update(overrides)
    return InstallerConfig(**defaults)


def test_partition_disk_creates_expected_commands(tmp_path: Path) -> None:
    runner = FakeRunner({"grep MemTotal /proc/meminfo | awk '{print $2}'": "1048576"})
    installer = ArchInstaller(runner, mount_point=tmp_path)
    config = make_config()

    layout = installer.partition_disk(config)

    assert layout.efi == "/dev/sda1"
    assert layout.swap == "/dev/sda2"
    assert layout.root == "/dev/sda3"

    expected = [
        "parted -s /dev/sda mklabel gpt",
        "grep MemTotal /proc/meminfo | awk '{print $2}'",
        "parted -s /dev/sda mkpart primary fat32 1MiB 513MiB",
        "parted -s /dev/sda set 1 esp on",
        "parted -s /dev/sda mkpart primary linux-swap 513MiB 1537MiB",
        "parted -s /dev/sda mkpart primary 1537MiB 100%",
        "mkfs.fat -F32 /dev/sda1",
        "mkswap /dev/sda2",
        "mkfs.ext4 -F /dev/sda3",
        f"mount /dev/sda3 {tmp_path}",
        f"mount /dev/sda1 {tmp_path / 'boot'}",
        "swapon /dev/sda2",
    ]
    assert runner.commands == expected


@pytest.mark.parametrize(
    "disk,efi",
    [("/dev/sda", "/dev/sda1"), ("/dev/nvme0n1", "/dev/nvme0n1p1")],
)
def test_partition_layout_suffixes(disk: str, efi: str, tmp_path: Path) -> None:
    runner = FakeRunner({"grep MemTotal /proc/meminfo | awk '{print $2}'": "1048576"})
    installer = ArchInstaller(runner, mount_point=tmp_path)
    config = make_config(disk=disk)

    layout = installer.partition_disk(config)

    assert layout.efi == efi


def test_configure_system_writes_configuration(tmp_path: Path) -> None:
    mount_point = tmp_path / "mnt"
    mount_point.mkdir()
    findmnt = f"findmnt -n -o SOURCE {mount_point}"
    runner = FakeRunner(
        {
            findmnt: "/dev/sda3",
            "blkid -s UUID -o value /dev/sda3": "1234-UUID",
        }
    )
    installer = ArchInstaller(runner, mount_point=mount_point)
    config = make_config()

    installer.configure_system(config)

    locale_path = mount_point / "etc/locale.gen"
    assert locale_path.exists()
    content = locale_path.read_text(encoding="utf-8")
    assert "en_US.UTF-8 UTF-8" in content
    assert "ru_RU.UTF-8 UTF-8" in content

    hosts_path = mount_point / "etc/hosts"
    hosts_text = hosts_path.read_text(encoding="utf-8")
    assert "127.0.1.1\tarchlinux.localdomain\tarchlinux" in hosts_text

    loader_conf = mount_point / "boot/loader/loader.conf"
    assert loader_conf.read_text(encoding="utf-8") == "default arch\ntimeout 3\neditor no\n"

    entry = mount_point / "boot/loader/entries/arch.conf"
    entry_text = entry.read_text(encoding="utf-8")
    assert "initrd /initramfs-linux.img" in entry_text
    assert "options root=UUID=1234-UUID rw" in entry_text

    assert findmnt in runner.commands
    assert "arch-chroot" in "\n".join(runner.commands)


def test_install_additional_packages_enables_networkmanager(tmp_path: Path) -> None:
    runner = FakeRunner()
    installer = ArchInstaller(runner, mount_point=tmp_path)

    installer.install_additional_packages(["networkmanager", "vim"])

    assert runner.commands[0] == (
        f"arch-chroot {tmp_path} pacman -S --noconfirm networkmanager vim"
    )
    assert runner.commands[1] == f"arch-chroot {tmp_path} systemctl enable NetworkManager"


def test_install_additional_packages_skips_when_empty(tmp_path: Path) -> None:
    runner = FakeRunner()
    installer = ArchInstaller(runner, mount_point=tmp_path)

    installer.install_additional_packages([])

    assert runner.commands == []

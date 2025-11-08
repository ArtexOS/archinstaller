"""Core installation routines for Arch Linux."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from shlex import quote
from typing import Iterable, Sequence, Tuple

from .system import CommandRunner


@dataclass(frozen=True)
class InstallerConfig:
    """Configuration collected from the user before installation."""

    disk: str
    filesystem: str
    timezone: str
    username: str
    password: str


@dataclass(frozen=True)
class PartitionLayout:
    """Partition names derived from a disk identifier."""

    efi: str
    swap: str
    root: str


DEFAULT_PACKAGES: Tuple[str, ...] = (
    "networkmanager",
    "sudo",
    "vim",
    "bash-completion",
    "git",
    "openssh",
    "htop",
    "man-db",
    "man-pages",
    "texinfo",
    "gdm",
    "gnome",
    "gnome-tweaks",
)


@dataclass
class ArchInstaller:
    """High level orchestration of Arch Linux installation steps."""

    runner: CommandRunner
    mount_point: Path = field(default_factory=lambda: Path("/mnt"))
    packages: Sequence[str] = field(default_factory=lambda: DEFAULT_PACKAGES)

    def __post_init__(self) -> None:
        self.mount_point = Path(self.mount_point)

    # ---------------------------- partitioning ----------------------------
    def partition_disk(self, config: InstallerConfig) -> PartitionLayout:
        """Partition the target disk and mount partitions."""

        disk = config.disk
        self.runner.run(f"parted -s {disk} mklabel gpt")
        mem_kib = int(self.runner.run("grep MemTotal /proc/meminfo | awk '{print $2}'"))
        ram_mb = max(mem_kib // 1024, 512)
        swap_end = ram_mb + 513
        self.runner.run(f"parted -s {disk} mkpart primary fat32 1MiB 513MiB")
        self.runner.run(f"parted -s {disk} set 1 esp on")
        self.runner.run(
            f"parted -s {disk} mkpart primary linux-swap 513MiB {swap_end}MiB"
        )
        self.runner.run(f"parted -s {disk} mkpart primary {swap_end}MiB 100%")
        layout = self._partition_names(disk)
        self.runner.run(f"mkfs.fat -F32 {layout.efi}")
        self.runner.run(f"mkswap {layout.swap}")
        self._format_root(layout.root, config.filesystem)
        self.mount_point.mkdir(parents=True, exist_ok=True)
        self.runner.run(f"mount {layout.root} {self.mount_point}")
        boot_dir = self.mount_point / "boot"
        boot_dir.mkdir(parents=True, exist_ok=True)
        self.runner.run(f"mount {layout.efi} {boot_dir}")
        self.runner.run(f"swapon {layout.swap}")
        return layout

    def _format_root(self, partition: str, fs_type: str) -> None:
        if fs_type == "btrfs":
            self.runner.run(f"mkfs.btrfs -f {partition}")
        elif fs_type == "xfs":
            self.runner.run(f"mkfs.xfs -f {partition}")
        elif fs_type == "ext3":
            self.runner.run(f"mkfs.ext3 -F {partition}")
        else:
            self.runner.run(f"mkfs.ext4 -F {partition}")

    @staticmethod
    def _partition_names(disk: str) -> PartitionLayout:
        suffix = "p" if any(prefix in disk for prefix in ("nvme", "mmcblk")) else ""
        return PartitionLayout(
            efi=f"{disk}{suffix}1",
            swap=f"{disk}{suffix}2",
            root=f"{disk}{suffix}3",
        )

    # --------------------------- base system ---------------------------
    def install_base_system(self) -> None:
        """Install the base Arch Linux system via ``pacstrap``."""

        self.runner.run(
            f"pacstrap {self.mount_point} base base-devel linux linux-firmware"
        )

    # ------------------------- system configuration -------------------------
    def configure_system(self, config: InstallerConfig) -> None:
        """Configure the newly installed system inside the chroot."""

        self.runner.run(
            f"genfstab -U {self.mount_point} >> {self.mount_point}/etc/fstab"
        )
        self.runner.run(
            f"arch-chroot {self.mount_point} ln -sf "
            f"/usr/share/zoneinfo/{config.timezone} /etc/localtime"
        )
        self.runner.run(f"arch-chroot {self.mount_point} hwclock --systohc")
        self._update_locale_gen()
        self.runner.run(f"arch-chroot {self.mount_point} locale-gen")
        self._write_file("etc/locale.conf", "LANG=en_US.UTF-8\n")
        self._write_file("etc/hostname", "archlinux\n")
        self._write_hosts_file()
        self.runner.run(
            f"arch-chroot {self.mount_point} sh -c \"echo {quote(f'root:{config.password}')} | chpasswd\""
        )
        self.runner.run(
            f"arch-chroot {self.mount_point} useradd -m -G wheel -s /bin/bash {config.username}"
        )
        self.runner.run(
            f"arch-chroot {self.mount_point} sh -c \"echo {quote(f'{config.username}:{config.password}')} | chpasswd\""
        )
        self.runner.run(
            f"arch-chroot {self.mount_point} sed -i "
            "'s/^# %wheel ALL=(ALL) ALL/%wheel ALL=(ALL) ALL/' /etc/sudoers"
        )
        self.runner.run(f"arch-chroot {self.mount_point} bootctl install")
        self._write_bootloader_config(config.filesystem)
        self.runner.run(
            f"arch-chroot {self.mount_point} systemctl enable "
            "systemd-networkd systemd-resolved"
        )

    def _update_locale_gen(self) -> None:
        path = self.mount_point / "etc/locale.gen"
        lines = ["en_US.UTF-8 UTF-8", "ru_RU.UTF-8 UTF-8"]
        existing = []
        if path.exists():
            existing = path.read_text(encoding="utf-8").splitlines()
        updated = [line for line in existing if line]
        for line in lines:
            if line not in updated:
                updated.append(line)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(updated) + "\n", encoding="utf-8")

    def _write_hosts_file(self) -> None:
        content = """127.0.0.1\tlocalhost
::1\t\tlocalhost
127.0.1.1\tarchlinux.localdomain\tarchlinux
"""
        self._write_file("etc/hosts", content)

    def _write_bootloader_config(self, fs_type: str) -> None:
        loader_dir = self.mount_point / "boot/loader"
        entries_dir = loader_dir / "entries"
        loader_dir.mkdir(parents=True, exist_ok=True)
        entries_dir.mkdir(parents=True, exist_ok=True)
        (loader_dir / "loader.conf").write_text(
            "default arch\n" "timeout 3\n" "editor no\n",
            encoding="utf-8",
        )
        root_source = self.runner.run(
            f"findmnt -n -o SOURCE {self.mount_point}"
        )
        root_uuid = self.runner.run(
            f"blkid -s UUID -o value {root_source}"
        )
        initrd = "initramfs-linux-btrfs.img" if fs_type == "btrfs" else "initramfs-linux.img"
        (entries_dir / "arch.conf").write_text(
            "title Arch Linux\n"
            "linux /vmlinuz-linux\n"
            f"initrd /{initrd}\n"
            f"options root=UUID={root_uuid} rw\n",
            encoding="utf-8",
        )

    def _write_file(self, relative_path: str, content: str) -> None:
        path = self.mount_point / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    # ------------------------ additional packages ------------------------
    def install_additional_packages(self, packages: Iterable[str] | None = None) -> None:
        pkg_list = list(packages) if packages is not None else list(self.packages)
        if not pkg_list:
            return
        joined = " ".join(pkg_list)
        self.runner.run(
            f"arch-chroot {self.mount_point} pacman -S --noconfirm {joined}"
        )
        if "networkmanager" in pkg_list:
            self.runner.run(
                f"arch-chroot {self.mount_point} systemctl enable NetworkManager"
            )

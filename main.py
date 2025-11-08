"""Command line interface for the Arch Linux installer helper."""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from typing import List, Sequence, Tuple

from archinstaller import ArchInstaller, CommandExecutionError, InstallerConfig, SubprocessRunner
from archinstaller.console import DEFAULT_COLORS as COLORS, clear_screen, print_color
from archinstaller.system import CommandRunner

FILESYSTEMS: Sequence[str] = ("ext4", "btrfs", "xfs", "ext3")


def get_disks(runner: CommandRunner) -> List[Tuple[str, str]]:
    """Return a list of available block devices using ``lsblk``."""

    print_color("\nОпределение доступных дисков...", COLORS.ok_blue)
    output = runner.run("lsblk -d -o NAME,SIZE,MODEL -n -l")
    disks: List[Tuple[str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        disk_name = f"/dev/{parts[0]}"
        disk_info = parts[1] if len(parts) > 1 else "Unknown"
        disks.append((disk_name, disk_info))
    if not disks:
        raise RuntimeError("Не найдено доступных дисков для установки")
    for index, (disk_name, disk_info) in enumerate(disks, start=1):
        print_color(f" {index}. {disk_name} ({disk_info})", COLORS.ok_cyan)
    return disks


def select_disk(runner: CommandRunner) -> str:
    disks = get_disks(runner)
    while True:
        choice = input("\nВведите номер диска в списке: ").strip()
        if not choice.isdigit():
            print_color("Пожалуйста, введите число.", COLORS.warning)
            continue
        idx = int(choice)
        if 1 <= idx <= len(disks):
            return disks[idx - 1][0]
        print_color("Некорректный номер диска. Попробуйте снова.", COLORS.warning)


def get_timezones(runner: CommandRunner) -> List[str]:
    print_color("\nПолучение списка часовых поясов...", COLORS.ok_blue)
    output = runner.run("timedatectl list-timezones")
    timezones = output.splitlines()
    for index, timezone in enumerate(timezones[:20], start=1):
        print_color(f" {index}. {timezone}", COLORS.ok_cyan)
    if len(timezones) > 20:
        print_color(" ... (полный список будет доступен при выборе)", COLORS.ok_cyan)
    if not timezones:
        raise RuntimeError("Не удалось получить список часовых поясов")
    return timezones


def select_timezone(timezones: Sequence[str]) -> str:
    while True:
        print("\nВы можете:")
        print_color(" 1. Просмотреть полный список часовых поясов", COLORS.ok_blue)
        print_color(" 2. Ввести свой часовой пояс (например: Europe/Moscow)", COLORS.ok_blue)
        print_color(" 3. Использовать предложенные выше варианты", COLORS.ok_blue)
        choice = input("Ваш выбор (1/2/3): ").strip()
        if choice == "1":
            for index, timezone in enumerate(timezones, start=1):
                print(f" {index}. {timezone}")
                if index % 20 == 0:
                    input("Нажмите Enter для продолжения...")
        elif choice == "2":
            timezone = input("Введите часовой пояс (например Europe/Moscow): ").strip()
            if timezone in timezones:
                return timezone
            print_color("Указанный часовой пояс не найден в списке.", COLORS.warning)
        elif choice == "3":
            return _select_timezone_from_list(timezones)
        else:
            print_color("Некорректный выбор. Попробуйте снова.", COLORS.warning)


def _select_timezone_from_list(timezones: Sequence[str]) -> str:
    while True:
        choice = input(f"Введите номер часового пояса (1-{len(timezones)}): ").strip()
        if not choice.isdigit():
            print_color("Пожалуйста, введите число.", COLORS.warning)
            continue
        idx = int(choice)
        if 1 <= idx <= len(timezones):
            return timezones[idx - 1]
        print_color("Некорректный номер. Попробуйте снова.", COLORS.warning)


def get_user_info() -> Tuple[str, str]:
    print_color("\nВведите данные пользователя", COLORS.header)
    username = _prompt_username()
    password = _prompt_password()
    return username, password


def _prompt_username() -> str:
    pattern = re.compile(r"^[a-z][a-z0-9_-]*$")
    while True:
        username = input("Имя пользователя: ").strip()
        if not username:
            print_color("Имя пользователя не может быть пустым", COLORS.warning)
            continue
        if not pattern.match(username):
            print_color(
                "Имя пользователя должно начинаться с буквы и содержать только "
                "строчные буквы, цифры, подчеркивания или дефисы",
                COLORS.warning,
            )
            continue
        return username


def _prompt_password() -> str:
    while True:
        password = input("Пароль: ").strip()
        if not password:
            print_color("Пароль не может быть пустым", COLORS.warning)
            continue
        confirmation = input("Подтвердите пароль: ").strip()
        if password == confirmation:
            return password
        print_color("Пароли не совпадают. Попробуйте снова.", COLORS.warning)


def select_filesystem(filesystems: Sequence[str] = FILESYSTEMS) -> str:
    print_color("\nДоступные файловые системы:", COLORS.ok_blue)
    for index, fs in enumerate(filesystems, start=1):
        print_color(f" {index}. {fs}", COLORS.ok_cyan)
    while True:
        choice = input("Выберите файловую систему (номер): ").strip()
        if not choice.isdigit():
            print_color("Пожалуйста, введите число.", COLORS.warning)
            continue
        idx = int(choice)
        if 1 <= idx <= len(filesystems):
            return filesystems[idx - 1]
        print_color("Некорректный номер. Попробуйте снова.", COLORS.warning)


def confirm_installation(config: InstallerConfig) -> None:
    clear_screen()
    print_color("=== Подтверждение установки ===", COLORS.header)
    print(f"Диск для установки: {config.disk}")
    print(f"Часовой пояс: {config.timezone}")
    print(f"Имя пользователя: {config.username}")
    print(f"Файловая система: {config.filesystem}")
    print_color("\nВСЕ ДАННЫЕ НА ВЫБРАННОМ ДИСКЕ БУДУТ УДАЛЕНЫ!", COLORS.fail)
    confirmation = input("\nПродолжить установку? (y/N): ").strip().lower()
    if confirmation != "y":
        print_color("Установка отменена", COLORS.warning)
        sys.exit(0)


def perform_installation(installer: ArchInstaller, config: InstallerConfig) -> None:
    start_time = datetime.now()
    layout = installer.partition_disk(config)
    installer.install_base_system()
    installer.configure_system(config)
    installer.install_additional_packages()
    installer.runner.run(f"umount -R {installer.mount_point}")
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds() / 60
    clear_screen()
    print_color("=== Установка завершена успешно! ===", COLORS.ok_green)
    print(f"\nEFI раздел: {layout.efi}")
    print(f"SWAP раздел: {layout.swap}")
    print(f"ROOT раздел: {layout.root}")
    print(f"\nОбщее время установки: {duration:.1f} минут")
    print_color("Необходима перезагрузка.", COLORS.warning)
    reboot = input("Перезагрузить? (Y/n): ").strip().lower()
    if reboot in {"", "y"}:
        installer.runner.run("reboot now", check=False)


def main() -> None:
    runner = SubprocessRunner()
    try:
        runner.run("setfont cyr-sun16", check=False)
        clear_screen()
        print_color("=== ArchLinux Installer ===", COLORS.header)
        print_color("\nЭтот скрипт установит ArchLinux на ваш компьютер.", COLORS.ok_blue)
        print_color(
            "Перед началом убедитесь, что вы запустили его из live-окружения ArchLinux.",
            COLORS.warning,
        )
        input("Для продолжения нажмите Enter...")
        if os.path.ismount("/mnt"):
            print_color("Ошибка: похоже, система уже смонтирована в /mnt", COLORS.fail)
            sys.exit(1)
        disk = select_disk(runner)
        timezones = get_timezones(runner)
        timezone = select_timezone(timezones)
        username, password = get_user_info()
        filesystem = select_filesystem()
        config = InstallerConfig(
            disk=disk,
            filesystem=filesystem,
            timezone=timezone,
            username=username,
            password=password,
        )
        confirm_installation(config)
        installer = ArchInstaller(runner)
        perform_installation(installer, config)
    except CommandExecutionError as exc:
        print_color(f"\nОшибка во время установки: {exc}", COLORS.fail)
        if exc.stderr.strip():
            print_color(exc.stderr.strip(), COLORS.fail)
        sys.exit(1)
    except RuntimeError as exc:
        print_color(f"\n{exc}", COLORS.fail)
        sys.exit(1)
    except KeyboardInterrupt:
        print_color("\nУстановка прервана пользователем", COLORS.warning)
        sys.exit(1)


if __name__ == "__main__":
    if os.geteuid() != 0:
        print_color("Этот скрипт должен быть запущен с правами root", COLORS.fail)
        sys.exit(1)
    main()

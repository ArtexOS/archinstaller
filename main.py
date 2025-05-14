import os
import subprocess
import sys
import re
from datetime import datetime

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')

def print_color(text, color):
    print(color + text + Colors.ENDC)

def run_command(cmd, check=True):
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and result.returncode != 0:
        print_color(f"Ошибка выполнения команды: {cmd}", Colors.FAIL)
        print_color(f"STDERR: {result.stderr.strip()}", Colors.FAIL)
        raise subprocess.CalledProcessError(result.returncode, cmd)
    return result.stdout.strip()

def get_disks():
    print_color("\nОпределение доступных дисков...", Colors.OKBLUE)
    disks = []
    try:
        output = run_command("lsblk -d -o NAME,SIZE,MODEL -n -l")
        for i, line in enumerate(output.split('\n'), 1):
            if line.strip():
                parts = line.split(maxsplit=1)
                disk_name = f"/dev/{parts[0]}"
                disk_info = parts[1] if len(parts) > 1 else "Unknown"
                disks.append((disk_name, disk_info))
                print_color(f" {i}. {disk_name} ({disk_info})", Colors.OKCYAN)
    except subprocess.CalledProcessError:
        print_color("Ошибка при получении списка дисков", Colors.FAIL)
        sys.exit(1)
    return disks

def select_disk():
    disks = get_disks()
    if not disks:
        print_color("Не найдено доступных дисков для установки", Colors.FAIL)
        sys.exit(1)
    while True:
        try:
            choice = int(input("\nВведите номер диска в списке: "))
            if 1 <= choice <= len(disks):
                return disks[choice - 1][0]
            print_color("Некорректный номер диска. Попробуйте снова.", Colors.WARNING)
        except ValueError:
            print_color("Пожалуйста, введите число.", Colors.WARNING)

def get_timezones():
    print_color("\nПолучение списка часовых поясов...", Colors.OKBLUE)
    timezones = []
    try:
        output = run_command("timedatectl list-timezones")
        timezones = output.split('\n')
        for i, tz in enumerate(timezones[:20], 1):
            print_color(f" {i}. {tz}", Colors.OKCYAN)
        print_color(" ... (полный список будет доступен при выборе)", Colors.OKCYAN)
    except subprocess.CalledProcessError:
        print_color("Ошибка при получении списка часовых поясов", Colors.FAIL)
        sys.exit(1)
    return timezones

def select_timezone(timezones):
    while True:
        print("\nВы можете:")
        print_color(" 1. Просмотреть полный список часовых поясов", Colors.OKBLUE)
        print_color(" 2. Ввести свой часовой пояс (например: Europe/Moscow)", Colors.OKBLUE)
        print_color(" 3. Использовать предложенные выше варианты", Colors.OKBLUE)
        choice = input("Ваш выбор (1/2/3): ").strip()
        if choice == "1":
            for i, tz in enumerate(timezones, 1):
                print(f" {i}. {tz}")
                if i % 20 == 0:
                    input("Нажмите Enter для продолжения...")
        elif choice == "2":
            tz = input("Введите часовой пояс (например Europe/Moscow): ").strip()
            if tz in timezones:
                return tz
            print_color("Указанный часовой пояс не найден в списке.", Colors.WARNING)
        elif choice == "3":
            while True:
                try:
                    num = int(input(f"Введите номер часового пояса (1-{len(timezones)}): "))
                    if 1 <= num <= len(timezones):
                        return timezones[num - 1]
                    print_color("Некорректный номер. Попробуйте снова.", Colors.WARNING)
                except ValueError:
                    print_color("Пожалуйста, введите число.", Colors.WARNING)
        else:
            print_color("Некорректный выбор. Попробуйте снова.", Colors.WARNING)

def get_user_info():
    print_color("\nВведите данные пользователя", Colors.HEADER)
    while True:
        username = input("Имя пользователя: ").strip()
        if not username:
            print_color("Имя пользователя не может быть пустым", Colors.WARNING)
            continue
        if not re.match(r'^[a-z][a-z0-9_-]*$', username):
            print_color("Имя пользователя должно начинаться с буквы и содержать только буквы, цифры, подчеркивания или дефисы", Colors.WARNING)
            continue
        break
    while True:
        password = input("Пароль: ").strip()
        if not password:
            print_color("Пароль не может быть пустым", Colors.WARNING)
            continue
        confirm = input("Подтвердите пароль: ").strip()
        if password == confirm:
            break
        print_color("Пароли не совпадают. Попробуйте снова.", Colors.WARNING)
    return username, password

def select_filesystem():
    filesystems = ["ext4", "btrfs", "xfs", "ext3"]
    print_color("\nДоступные файловые системы:", Colors.OKBLUE)
    for i, fs in enumerate(filesystems, 1):
        print_color(f" {i}. {fs}", Colors.OKCYAN)
    while True:
        try:
            choice = int(input("Выберите файловую систему (номер): "))
            if 1 <= choice <= len(filesystems):
                return filesystems[choice - 1]
            print_color("Некорректный номер. Попробуйте снова.", Colors.WARNING)
        except ValueError:
            print_color("Пожалуйста, введите число.", Colors.WARNING)

def partition_disk(disk, fs_type):
    print_color(f"\nРазметка диска {disk}...", Colors.HEADER)
    run_command(f"parted -s {disk} mklabel gpt")
    ram_size = int(run_command("grep MemTotal /proc/meminfo | awk '{print $2}'")) // 1024
    run_command(f"parted -s {disk} mkpart primary fat32 1MiB 513MiB")
    run_command(f"parted -s {disk} set 1 esp on")
    run_command(f"parted -s {disk} mkpart primary linux-swap 513MiB {ram_size + 513}MiB")
    run_command(f"parted -s {disk} mkpart primary {ram_size + 513}MiB 100%")
    if 'nvme' in disk or 'mmcblk' in disk:
        efi_part = f"{disk}p1"
        swap_part = f"{disk}p2"
        root_part = f"{disk}p3"
    else:
        efi_part = f"{disk}1"
        swap_part = f"{disk}2"
        root_part = f"{disk}3"
    run_command(f"mkfs.fat -F32 {efi_part}")
    run_command(f"mkswap {swap_part}")
    if fs_type == "btrfs":
        run_command(f"mkfs.btrfs -f {root_part}")
    elif fs_type == "xfs":
        run_command(f"mkfs.xfs -f {root_part}")
    elif fs_type == "ext3":
        run_command(f"mkfs.ext3 -F {root_part}")
    else:
        run_command(f"mkfs.ext4 -F {root_part}")
    run_command(f"mount {root_part} /mnt")
    run_command(f"mkdir -p /mnt/boot")
    run_command(f"mount {efi_part} /mnt/boot")
    run_command(f"swapon {swap_part}")
    print_color("Диск успешно размечен и смонтирован", Colors.OKGREEN)

def install_base_system():
    print_color("\nУстановка базовой системы...", Colors.HEADER)
    run_command("pacstrap /mnt base base-devel linux linux-firmware")
    print_color("Базовая система установлена", Colors.OKGREEN)

def configure_system(username, password, timezone, fs_type):
    print_color("\nКонфигурация системы...", Colors.HEADER)
    run_command("genfstab -U /mnt >> /mnt/etc/fstab")
    run_command(f"arch-chroot /mnt ln -sf /usr/share/zoneinfo/{timezone} /etc/localtime")
    run_command("arch-chroot /mnt hwclock --systohc")
    with open("/mnt/etc/locale.gen", "a") as f:
        f.write("en_US.UTF-8 UTF-8\nru_RU.UTF-8 UTF-8\n")
    run_command("arch-chroot /mnt locale-gen")
    run_command('arch-chroot /mnt echo "LANG=en_US.UTF-8" > /etc/locale.conf')
    run_command('arch-chroot /mnt echo "archlinux" > /etc/hostname')
    with open("/mnt/etc/hosts", "w") as f:
        f.write("127.0.0.1\tlocalhost\n")
        f.write("::1\t\tlocalhost\n")
        f.write("127.0.1.1\tarchlinux.localdomain\tarchlinux\n")
    run_command(f"arch-chroot /mnt sh -c \"echo 'root:{password}' | chpasswd\"")
    run_command(f"arch-chroot /mnt useradd -m -G wheel -s /bin/bash {username}")
    run_command(f"arch-chroot /mnt sh -c \"echo '{username}:{password}' | chpasswd\"")
    run_command("arch-chroot /mnt sed -i 's/^# %wheel ALL=(ALL) ALL/%wheel ALL=(ALL) ALL/' /etc/sudoers")
    run_command("arch-chroot /mnt bootctl install")
    with open("/mnt/boot/loader/loader.conf", "w") as f:
        f.write("default arch\n")
        f.write("timeout 3\n")
        f.write("editor no\n")
    root_part = run_command("findmnt -n -o SOURCE /mnt")
    with open("/mnt/boot/loader/entries/arch.conf", "w") as f:
        f.write("title Arch Linux\n")
        f.write("linux /vmlinuz-linux\n")
        if fs_type == "btrfs":
            f.write("initrd /initramfs-linux-btrfs.img\n")
        else:
            f.write("initrd /initramfs-linux.img\n")
        f.write(f"options root=UUID={run_command(f'blkid -s UUID -o value {root_part}')} rw\n")
    run_command("arch-chroot /mnt systemctl enable systemd-networkd systemd-resolved")
    print_color("Система успешно сконфигурирована", Colors.OKGREEN)

def install_additional_packages():
    print_color("\nУстановка дополнительных пакетов...", Colors.HEADER)
    packages = ["networkmanager", "sudo", "vim", "bash-completion", "git", "openssh", "htop", "man-db", "man-pages", "texinfo", "gdm", "gnome", "gnome-tweaks"]
    run_command(f"arch-chroot /mnt pacman -S --noconfirm {' '.join(packages)}")
    run_command("arch-chroot /mnt systemctl enable NetworkManager")
    print_color("Дополнительные пакеты установлены", Colors.OKGREEN)

def main():
    try:
        run_command("setfont cyr-sun16", check=False)
        clear_screen()
        print_color("=== ArchLinux Installer ===", Colors.HEADER)
        print_color("\nЭтот скрипт установит ArchLinux на ваш компьютер.", Colors.OKBLUE)
        print_color("Перед началом убедитесь, что вы запустили его из live-окружения ArchLinux.", Colors.WARNING)
        print_color("Для продолжения нажмите Enter...", Colors.OKGREEN)
        input()
        if os.path.ismount('/mnt'):
            print_color("Ошибка: похоже, система уже смонтирована в /mnt", Colors.FAIL)
            sys.exit(1)
        disk = select_disk()
        timezones = get_timezones()
        timezone = select_timezone(timezones)
        username, password = get_user_info()
        fs_type = select_filesystem()
        clear_screen()
        print_color("=== Подтверждение установки ===", Colors.HEADER)
        print(f"Диск для установки: {disk}")
        print(f"Часовой пояс: {timezone}")
        print(f"Имя пользователя: {username}")
        print(f"Файловая система: {fs_type}")
        print_color("\nВСЕ ДАННЫЕ НА ВЫБРАННОМ ДИСКЕ БУДУТ УДАЛЕНЫ!", Colors.FAIL)
        confirm = input("\nПродолжить установку? (y/N): ").strip().lower()
        if confirm != 'y':
            print_color("Установка отменена", Colors.WARNING)
            sys.exit(0)
        start_time = datetime.now()
        partition_disk(disk, fs_type)
        install_base_system()
        configure_system(username, password, timezone, fs_type)
        install_additional_packages()
        run_command("umount -R /mnt")
        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds() / 60
        clear_screen()
        print_color("=== Установка завершена успешно! ===", Colors.OKGREEN)
        print(f"\nОбщее время установки: {total_time:.1f} минут")
        print_color("Необходима перезагрузка.", Colors.WARNING)
        confirmation_for_reboot = input("Перезагрузить? (Y/n): ").strip().lower()
        if confirmation_for_reboot == "y":
            run_command("reboot now")
    except subprocess.CalledProcessError as e:
        print_color(f"\nОшибка во время установки: {e}", Colors.FAIL)
        print_color("Проверьте сообщения выше для диагностики проблемы", Colors.WARNING)
        sys.exit(1)
    except KeyboardInterrupt:
        print_color("\nУстановка прервана пользователем", Colors.WARNING)
        sys.exit(1)

if __name__ == "__main__":
    if os.geteuid() != 0:
        print_color("Этот скрипт должен быть запущен с правами root", Colors.FAIL)
        sys.exit(1)
    main()
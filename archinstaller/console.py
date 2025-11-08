"""Console helpers for the Arch installer CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ColorScheme:
    """ANSI colour codes used by the installer UI."""

    header: str = "\033[95m"
    ok_blue: str = "\033[94m"
    ok_cyan: str = "\033[96m"
    ok_green: str = "\033[92m"
    warning: str = "\033[93m"
    fail: str = "\033[91m"
    end: str = "\033[0m"
    bold: str = "\033[1m"
    underline: str = "\033[4m"


DEFAULT_COLORS = ColorScheme()


def clear_screen() -> None:
    """Clear the terminal screen when supported by the platform."""

    os.system("clear" if os.name == "posix" else "cls")


def print_color(text: str, color: str, colors: ColorScheme = DEFAULT_COLORS) -> None:
    """Print ``text`` using the provided ``color`` escape code."""

    print(f"{color}{text}{colors.end}")

"""System level helpers for executing commands during installation."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


class CommandExecutionError(RuntimeError):
    """Raised when a command executed by :class:`CommandRunner` fails."""

    def __init__(self, command: str, returncode: int, stdout: str, stderr: str) -> None:
        super().__init__(f"Command '{command}' failed with exit code {returncode}")
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class CommandRunner:
    """Protocol-like base class for running shell commands."""

    def run(self, command: str, check: bool = True) -> str:  # pragma: no cover - interface only
        raise NotImplementedError


@dataclass
class SubprocessRunner(CommandRunner):
    """Concrete ``CommandRunner`` that proxies to :func:`subprocess.run`."""

    encoding: str = "utf-8"

    def run(self, command: str, check: bool = True) -> str:
        result = subprocess.run(  # nosec - shell commands are controlled by the user
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding=self.encoding,
        )
        if check and result.returncode != 0:
            raise CommandExecutionError(command, result.returncode, result.stdout, result.stderr)
        return result.stdout.strip()

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from patchproof.errors import CommandValidationError


_SHELL_OPERATORS = {"&&", "||", "|", ">", ">>", "<", ";", "$(", "`"}
_ALLOWED_FLAGS_WITH_VALUE = {"-k", "--tb"}
_ALLOWED_STANDALONE_FLAGS = {"-q", "-v", "-x", "-s"}


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


def _looks_like_test_path(token: str) -> bool:
    return token.endswith(".py") or token.startswith("tests") or token.startswith("test")


def parse_pytest_command(command: str) -> list[str]:
    for operator in _SHELL_OPERATORS:
        if operator in command:
            raise CommandValidationError(f"Shell operator is not allowed: {operator}")

    parts = shlex.split(command)
    if not parts:
        raise CommandValidationError("Test command cannot be empty.")

    if parts[0] == "pytest":
        remaining = parts[1:]
    elif len(parts) >= 3 and parts[0] == "python" and parts[1] == "-m" and parts[2] == "pytest":
        remaining = parts[3:]
    else:
        raise CommandValidationError("Only pytest or python -m pytest commands are allowed.")

    index = 0
    while index < len(remaining):
        token = remaining[index]
        if token in _ALLOWED_STANDALONE_FLAGS:
            index += 1
            continue
        if token in _ALLOWED_FLAGS_WITH_VALUE:
            if index + 1 >= len(remaining):
                raise CommandValidationError(f"Missing value for pytest argument: {token}")
            index += 2
            continue
        if token.startswith("--tb="):
            index += 1
            continue
        if _looks_like_test_path(token):
            index += 1
            continue
        raise CommandValidationError(f"Unsupported pytest argument: {token}")

    return parts


class CommandRunner:
    def __init__(self, timeout_seconds: int) -> None:
        self.timeout_seconds = timeout_seconds

    def run(self, command: list[str], cwd: Path) -> CommandResult:
        start = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                shell=False,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            return CommandResult(
                command=command,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            return CommandResult(
                command=command,
                exit_code=None,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                duration_ms=duration_ms,
                timed_out=True,
            )

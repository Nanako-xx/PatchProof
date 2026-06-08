from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PatchApplyResult:
    applied: bool
    stdout: str = ""
    stderr: str = ""


class PatchApplier:
    def apply(self, project_path: Path, diff_text: str) -> PatchApplyResult:
        normalized_diff = diff_text.replace("\r\n", "\n").replace("\r", "\n")
        if normalized_diff and not normalized_diff.endswith("\n"):
            normalized_diff += "\n"
        diff_bytes = normalized_diff.encode("utf-8")
        check = subprocess.run(
            ["git", "apply", "--check", "-"],
            input=diff_bytes,
            cwd=project_path,
            capture_output=True,
            shell=False,
        )
        if check.returncode != 0:
            return PatchApplyResult(
                False,
                check.stdout.decode("utf-8", errors="replace"),
                check.stderr.decode("utf-8", errors="replace"),
            )

        apply = subprocess.run(
            ["git", "apply", "-"],
            input=diff_bytes,
            cwd=project_path,
            capture_output=True,
            shell=False,
        )
        return PatchApplyResult(
            applied=apply.returncode == 0,
            stdout=apply.stdout.decode("utf-8", errors="replace"),
            stderr=apply.stderr.decode("utf-8", errors="replace"),
        )

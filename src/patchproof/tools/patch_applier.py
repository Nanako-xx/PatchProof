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
        check = subprocess.run(
            ["git", "apply", "--check", "-"],
            input=diff_text,
            cwd=project_path,
            text=True,
            capture_output=True,
            shell=False,
        )
        if check.returncode != 0:
            return PatchApplyResult(False, check.stdout, check.stderr)

        apply = subprocess.run(
            ["git", "apply", "-"],
            input=diff_text,
            cwd=project_path,
            text=True,
            capture_output=True,
            shell=False,
        )
        return PatchApplyResult(
            applied=apply.returncode == 0,
            stdout=apply.stdout,
            stderr=apply.stderr,
        )

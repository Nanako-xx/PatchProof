from __future__ import annotations

from pathlib import PurePosixPath

from unidiff import PatchSet

from patchproof.core.config import Settings
from patchproof.core.state import DiffMetadata


class DiffParser:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def parse(self, diff_text: str) -> DiffMetadata:
        patch_set = PatchSet(diff_text.splitlines(keepends=True))
        changed_files: list[str] = []
        added_lines = 0
        removed_lines = 0
        violations: list[str] = []

        for patched_file in patch_set:
            path = patched_file.path
            changed_files.append(path)
            added_lines += sum(1 for hunk in patched_file for line in hunk if line.is_added)
            removed_lines += sum(1 for hunk in patched_file for line in hunk if line.is_removed)
            violations.extend(self._validate_path(path))
            if patched_file.is_binary_file:
                violations.append(f"binary patches are not allowed: {path}")
            if patched_file.is_removed_file:
                violations.append(f"file deletion is not allowed: {path}")

        if len(changed_files) > self.settings.max_patch_files:
            violations.append(f"too many changed files: {len(changed_files)}")
        if added_lines + removed_lines > self.settings.max_patch_changed_lines:
            violations.append(f"too many changed lines: {added_lines + removed_lines}")

        return DiffMetadata(
            changed_files=changed_files,
            added_lines=added_lines,
            removed_lines=removed_lines,
            rule_violations=violations,
        )

    def _validate_path(self, path: str) -> list[str]:
        violations: list[str] = []
        pure = PurePosixPath(path)
        if pure.is_absolute():
            violations.append(f"absolute paths are not allowed: {path}")
        if ".." in pure.parts:
            violations.append(f"path traversal is not allowed: {path}")
        if not path.endswith(".py"):
            violations.append(f"only .py changes are allowed in v0.1: {path}")
        if pure.name.startswith("test_") or "/test_" in path or path.startswith("tests/"):
            violations.append(f"test-file changes are not allowed in v0.1: {path}")
        return violations

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from patchproof.core.state import (
    BugEvidence,
    VerificationCommand,
    VerificationCommandSource,
    VerificationPlan,
)


class VerificationPlanner:
    def plan(
        self,
        project_path: Path,
        evidence: BugEvidence,
        changed_files: Sequence[str],
        user_test_command: Sequence[str],
        unsafe_candidates: Optional[Sequence[Sequence[str]]] = None,
    ) -> VerificationPlan:
        skipped_commands = self._skipped_commands(unsafe_candidates or [])
        commands: List[VerificationCommand] = []

        if user_test_command:
            commands.append(
                VerificationCommand(
                    command=list(user_test_command),
                    source=VerificationCommandSource.USER_PROVIDED,
                )
            )
            return VerificationPlan(commands=commands, skipped_commands=skipped_commands)

        traceback_command = self._traceback_entrypoint_command(project_path, evidence.entrypoint_files)
        if traceback_command is not None:
            commands.append(traceback_command)
            return VerificationPlan(commands=commands, skipped_commands=skipped_commands)

        matched_commands = self._matched_test_commands(project_path, evidence.suspected_files, changed_files)
        if matched_commands:
            return VerificationPlan(commands=matched_commands, skipped_commands=skipped_commands)

        default_command = self._default_pytest_command(project_path)
        if default_command is not None:
            commands.append(default_command)

        return VerificationPlan(commands=commands, skipped_commands=skipped_commands)

    def _skipped_commands(self, unsafe_candidates: Sequence[Sequence[str]]) -> List[VerificationCommand]:
        return [
            VerificationCommand(
                command=list(candidate),
                source=VerificationCommandSource.SKIPPED_UNSAFE,
                reason="Outside the v0.2 verification allowlist.",
            )
            for candidate in unsafe_candidates
        ]

    def _traceback_entrypoint_command(
        self,
        project_path: Path,
        entrypoint_files: Sequence[str],
    ) -> Optional[VerificationCommand]:
        for entrypoint in entrypoint_files:
            path = project_path / entrypoint
            if path.is_file() and self._is_test_like_file(path):
                return VerificationCommand(
                    command=["pytest", Path(entrypoint).as_posix(), "-q"],
                    source=VerificationCommandSource.TRACEBACK_ENTRYPOINT,
                )
        return None

    def _matched_test_commands(
        self,
        project_path: Path,
        suspected_files: Sequence[str],
        changed_files: Sequence[str],
    ) -> List[VerificationCommand]:
        tests_dir = project_path / "tests"
        if not tests_dir.is_dir():
            return []

        source_stems = self._source_stems([*suspected_files, *changed_files])
        matched_paths: List[Path] = []
        seen_paths = set()

        for stem in source_stems:
            for pattern in (f"test_{stem}.py", f"*{stem}*.py"):
                for path in sorted(tests_dir.rglob(pattern)):
                    if not path.is_file() or not self._is_test_like_file(path):
                        continue
                    relative_path = path.relative_to(project_path)
                    relative_key = relative_path.as_posix()
                    if relative_key in seen_paths:
                        continue
                    seen_paths.add(relative_key)
                    matched_paths.append(relative_path)

        return [
            VerificationCommand(
                command=["pytest", path.as_posix(), "-q"],
                source=VerificationCommandSource.MATCHED_TEST,
            )
            for path in sorted(matched_paths, key=lambda item: item.as_posix())
        ]

    def _default_pytest_command(self, project_path: Path) -> Optional[VerificationCommand]:
        tests_dir = project_path / "tests"
        if not tests_dir.is_dir():
            return None

        for path in tests_dir.rglob("*.py"):
            if self._is_test_like_file(path):
                return VerificationCommand(
                    command=["pytest", "-q"],
                    source=VerificationCommandSource.DEFAULT_PYTEST,
                )
        return None

    def _source_stems(self, source_files: Iterable[str]) -> List[str]:
        stems: List[str] = []
        seen_stems = set()
        for source_file in source_files:
            stem = Path(source_file).stem
            if not stem or stem in seen_stems:
                continue
            seen_stems.add(stem)
            stems.append(stem)
        return sorted(stems)

    def _is_test_like_file(self, path: Path) -> bool:
        return path.suffix == ".py" and (path.name.startswith("test_") or path.name.endswith("_test.py"))

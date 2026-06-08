from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


_IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
_IGNORED_SUFFIXES = {".pem", ".key"}
_IGNORED_FILES = {".env"}


@dataclass(frozen=True)
class CodeSearchMatch:
    file_path: str
    line_number: int
    line_text: str


class ProjectIndexer:
    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path

    def list_python_files(self) -> list[str]:
        files: list[str] = []
        for path in self.project_path.rglob("*.py"):
            if self._is_ignored(path):
                continue
            files.append(path.relative_to(self.project_path).as_posix())
        return sorted(files)

    def search_code(self, query: str, limit: int = 20) -> list[CodeSearchMatch]:
        matches: list[CodeSearchMatch] = []
        for relative in self.list_python_files():
            path = self.project_path / relative
            for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if query in line:
                    matches.append(CodeSearchMatch(relative, index, line.strip()))
                    if len(matches) >= limit:
                        return matches
        return matches

    def _is_ignored(self, path: Path) -> bool:
        relative_parts = path.relative_to(self.project_path).parts
        if any(part in _IGNORED_DIRS for part in relative_parts):
            return True
        if path.name in _IGNORED_FILES:
            return True
        return path.suffix in _IGNORED_SUFFIXES

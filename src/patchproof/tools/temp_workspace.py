from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from types import TracebackType
from typing import Optional, Type


class TempWorkspace:
    def __init__(self, source_project: Path) -> None:
        self.source_project = source_project
        self._temp_dir: Optional[tempfile.TemporaryDirectory[str]] = None
        self.path: Optional[Path] = None

    def __enter__(self) -> Path:
        self._temp_dir = tempfile.TemporaryDirectory(prefix="patchproof-")
        destination = Path(self._temp_dir.name) / self.source_project.name
        ignore = shutil.ignore_patterns(".git", ".venv", "venv", "__pycache__", ".pytest_cache")
        shutil.copytree(self.source_project, destination, ignore=ignore)
        self.path = destination
        return destination

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        if self._temp_dir is not None:
            self._temp_dir.cleanup()

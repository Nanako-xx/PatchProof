from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodeContext:
    file_path: str
    start_line: int
    end_line: int
    text: str


class CodeContextTool:
    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path

    def read_context(self, file_path: str, line_number: int, radius: int = 20) -> CodeContext:
        full_path = (self.project_path / file_path).resolve()
        project_root = self.project_path.resolve()
        try:
            full_path.relative_to(project_root)
        except ValueError as exc:
            raise ValueError(f"Path escapes project root: {file_path}") from exc

        lines = full_path.read_text(encoding="utf-8").splitlines()
        start = max(1, line_number - radius)
        end = min(len(lines), line_number + radius)
        numbered = [
            f"{line_no}: {lines[line_no - 1]}"
            for line_no in range(start, end + 1)
        ]
        return CodeContext(
            file_path=file_path,
            start_line=start,
            end_line=end,
            text="\n".join(numbered),
        )

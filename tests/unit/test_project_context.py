from pathlib import Path

import pytest

from patchproof.tools.code_context import CodeContextTool
from patchproof.tools.project_indexer import ProjectIndexer


def test_project_indexer_ignores_sensitive_and_cache_paths(tmp_path: Path):
    (tmp_path / "app.py").write_text("def add(): pass\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "cache.py").write_text("x = 1\n", encoding="utf-8")

    files = ProjectIndexer(tmp_path).list_python_files()

    assert files == ["app.py"]


def test_search_code_finds_matching_lines(tmp_path: Path):
    (tmp_path / "calculator.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    matches = ProjectIndexer(tmp_path).search_code("return a - b")

    assert matches[0].file_path == "calculator.py"
    assert matches[0].line_number == 2
    assert matches[0].line_text == "return a - b"


def test_code_context_returns_bounded_window(tmp_path: Path):
    (tmp_path / "calculator.py").write_text(
        "line1\nline2\nline3\nline4\nline5\n",
        encoding="utf-8",
    )

    context = CodeContextTool(tmp_path).read_context("calculator.py", line_number=3, radius=1)

    assert context.start_line == 2
    assert context.end_line == 4
    assert "2: line2" in context.text
    assert "4: line4" in context.text


def test_code_context_rejects_path_outside_project(tmp_path: Path):
    outside = tmp_path.parent / "outside.py"
    outside.write_text("SECRET = 1\n", encoding="utf-8")

    with pytest.raises(ValueError):
        CodeContextTool(tmp_path).read_context("../outside.py", line_number=1, radius=1)

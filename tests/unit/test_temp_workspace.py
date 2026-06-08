from pathlib import Path

from patchproof.tools.temp_workspace import TempWorkspace


def test_temp_workspace_copies_project_and_cleans_up(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text("VALUE = 1\n", encoding="utf-8")

    with TempWorkspace(source) as copied:
        assert copied.exists()
        assert (copied / "app.py").read_text(encoding="utf-8") == "VALUE = 1\n"
        (copied / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        copied_path = copied

    assert not copied_path.exists()
    assert (source / "app.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_temp_workspace_ignores_environment_and_cache_dirs(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (source / ".venv").mkdir()
    (source / ".venv" / "ignored.py").write_text("VALUE = 2\n", encoding="utf-8")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "app.pyc").write_bytes(b"cache")

    with TempWorkspace(source) as copied:
        assert (copied / "app.py").exists()
        assert not (copied / ".venv").exists()
        assert not (copied / "__pycache__").exists()

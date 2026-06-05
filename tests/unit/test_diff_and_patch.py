from pathlib import Path

from patchproof.core.config import Settings
from patchproof.tools.diff_parser import DiffParser
from patchproof.tools.patch_applier import PatchApplier


SAFE_DIFF = """diff --git a/calculator.py b/calculator.py
--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""


def test_diff_parser_accepts_small_python_source_patch():
    metadata = DiffParser(Settings()).parse(SAFE_DIFF)

    assert metadata.changed_files == ["calculator.py"]
    assert metadata.changed_line_count == 2
    assert metadata.rule_violations == []


def test_diff_parser_rejects_test_file_changes():
    diff = SAFE_DIFF.replace("calculator.py", "test_calculator.py")

    metadata = DiffParser(Settings()).parse(diff)

    assert "test-file changes are not allowed in v0.1: test_calculator.py" in metadata.rule_violations


def test_diff_parser_rejects_path_traversal():
    diff = SAFE_DIFF.replace("calculator.py", "../secret.py")

    metadata = DiffParser(Settings()).parse(diff)

    assert "path traversal is not allowed: ../secret.py" in metadata.rule_violations


def test_patch_applier_applies_safe_patch(tmp_path: Path):
    (tmp_path / "calculator.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    result = PatchApplier().apply(tmp_path, SAFE_DIFF)

    assert result.applied is True
    assert "return a + b" in (tmp_path / "calculator.py").read_text(encoding="utf-8")


def test_patch_applier_returns_failure_without_modifying_file(tmp_path: Path):
    (tmp_path / "calculator.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    result = PatchApplier().apply(tmp_path, SAFE_DIFF)

    assert result.applied is False
    assert (tmp_path / "calculator.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"

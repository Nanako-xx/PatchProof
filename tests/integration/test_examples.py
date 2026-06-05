import os
import subprocess
import sys
from pathlib import Path


def test_required_example_projects_exist():
    for name in ["buggy_calculator", "buggy_auth", "buggy_parser"]:
        path = Path("examples") / name
        assert path.exists()
        assert any(path.glob("test_*.py"))


def test_example_projects_fail_with_test_assertions():
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for name in ["buggy_calculator", "buggy_auth", "buggy_parser"]:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
            cwd=Path("examples") / name,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout + result.stderr

        assert result.returncode == 1
        assert "ERROR collecting" not in output
        assert "failed" in output

import sys

import pytest

from patchproof.errors import CommandValidationError
from patchproof.tools.command_runner import CommandRunner, parse_pytest_command, parse_verification_command


def test_parse_allows_pytest_with_safe_args():
    assert parse_pytest_command("pytest -q") == ["pytest", "-q"]
    assert parse_pytest_command("python -m pytest -q") == ["python", "-m", "pytest", "-q"]


def test_parse_rejects_shell_operators():
    with pytest.raises(CommandValidationError):
        parse_pytest_command("pytest -q && echo hacked")

    with pytest.raises(CommandValidationError):
        parse_pytest_command("pytest -q > out.txt")


def test_parse_rejects_non_pytest_command():
    with pytest.raises(CommandValidationError):
        parse_pytest_command("python cleanup.py")


def test_parse_rejects_unknown_pytest_flags():
    with pytest.raises(CommandValidationError):
        parse_pytest_command("pytest --junitxml=result.xml")

    with pytest.raises(CommandValidationError):
        parse_pytest_command("pytest --maxfail=1")


def test_parse_rejects_missing_flag_value():
    with pytest.raises(CommandValidationError):
        parse_pytest_command("pytest -k")


def test_command_runner_captures_success(tmp_path):
    result = CommandRunner(timeout_seconds=5).run(
        [sys.executable, "-c", "print('ok')"],
        cwd=tmp_path,
    )

    assert result.exit_code == 0
    assert "ok" in result.stdout
    assert result.timed_out is False


def test_command_runner_captures_timeout(tmp_path):
    result = CommandRunner(timeout_seconds=1).run(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        cwd=tmp_path,
    )

    assert result.exit_code is None
    assert result.timed_out is True


def test_parse_verification_command_allows_pytest_and_unittest():
    assert parse_verification_command("pytest tests/test_parser.py -q") == ["pytest", "tests/test_parser.py", "-q"]
    assert parse_verification_command("python -m pytest tests -q") == ["python", "-m", "pytest", "tests", "-q"]
    assert parse_verification_command("python -m unittest") == ["python", "-m", "unittest"]
    assert parse_verification_command("python -m unittest discover") == ["python", "-m", "unittest", "discover"]


def test_parse_verification_command_rejects_unsafe_commands():
    with pytest.raises(CommandValidationError):
        parse_verification_command("make deploy")

    with pytest.raises(CommandValidationError):
        parse_verification_command("npm run test")

    with pytest.raises(CommandValidationError):
        parse_verification_command("pytest -q && echo hacked")

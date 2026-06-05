from typer.testing import CliRunner

from patchproof.cli import app


def test_cli_rejects_non_pytest_command():
    runner = CliRunner()

    result = runner.invoke(app, ["run", ".", "--test", "python cleanup.py"])

    assert result.exit_code != 0
    assert "Only pytest" in result.output or "Unsupported" in result.output

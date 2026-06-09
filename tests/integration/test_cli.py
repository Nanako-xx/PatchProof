from typer.testing import CliRunner

from patchproof.cli import app


def test_cli_requires_at_least_one_bug_input():
    runner = CliRunner()

    result = runner.invoke(app, ["run", "."])

    assert result.exit_code != 0
    assert "Provide at least one" in result.output


def test_cli_rejects_non_pytest_test_command():
    runner = CliRunner()

    result = runner.invoke(app, ["run", ".", "--test", "python cleanup.py"])

    assert result.exit_code != 0
    assert "Only pytest" in result.output or "Unsupported" in result.output


def test_cli_rejects_missing_bug_log_with_friendly_error():
    runner = CliRunner()

    result = runner.invoke(app, ["run", ".", "--bug-log", "missing.log"])

    assert result.exit_code != 0
    assert "bug log" in result.output.lower()
    assert "does not exist" in result.output.lower()
    assert "Traceback" not in result.output


def test_cli_accepts_test_only_path(monkeypatch):
    calls = []

    class FakeOrchestrator:
        def __init__(self, settings, llm) -> None:
            pass

        def run(self, project_path, command):
            calls.append((project_path, command))

            class State:
                final_status = type("Status", (), {"value": "unverified"})()

            return State()

    monkeypatch.setattr("patchproof.cli.WorkflowOrchestrator", FakeOrchestrator)
    monkeypatch.setattr("patchproof.cli.create_llm_client", lambda settings: object())
    runner = CliRunner()

    result = runner.invoke(app, ["run", ".", "--test", "pytest -q"])

    assert result.exit_code == 0
    assert calls[0][1] == ["pytest", "-q"]


def test_cli_accepts_bug_text_without_test(monkeypatch):
    calls = []

    class FakeOrchestrator:
        def __init__(self, settings, llm) -> None:
            pass

        def run_evidence(self, **kwargs):
            calls.append(kwargs)

            class State:
                final_status = type("Status", (), {"value": "unverified"})()

            return State()

    monkeypatch.setattr("patchproof.cli.WorkflowOrchestrator", FakeOrchestrator)
    monkeypatch.setattr("patchproof.cli.create_llm_client", lambda settings: object())
    runner = CliRunner()

    result = runner.invoke(app, ["run", ".", "--bug-text", "ValueError: bad"])

    assert result.exit_code == 0
    assert calls[0]["bug_text"] == "ValueError: bad"
    assert calls[0]["test_command"] == []

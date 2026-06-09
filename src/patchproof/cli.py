from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console

from patchproof.core.config import Settings
from patchproof.core.orchestrator import WorkflowOrchestrator
from patchproof.errors import CommandValidationError, LLMProviderError
from patchproof.llm.factory import create_llm_client
from patchproof.tools.command_runner import parse_pytest_command


app = typer.Typer(help="PatchProof: evidence-driven patch suggestions for Python bugs.")
console = Console()


@app.callback()
def main() -> None:
    """PatchProof debugging assistant."""


@app.command()
def run(
    project_path: Path = typer.Argument(..., help="Path to a local Python project."),
    test: Optional[str] = typer.Option(None, "--test", help="Restricted pytest command, such as 'pytest -q'."),
    bug_text: Optional[str] = typer.Option(None, "--bug-text", help="Inline bug description or traceback."),
    bug_log: Optional[Path] = typer.Option(None, "--bug-log", help="Path to a bug log file."),
    bug_image: Optional[Path] = typer.Option(None, "--bug-image", help="Path to a bug screenshot or image."),
) -> None:
    """Run PatchProof against local bug evidence."""
    load_dotenv()
    try:
        has_bug_evidence = any([bug_text, bug_log, bug_image])
        if not any([test, has_bug_evidence]):
            raise CommandValidationError(
                "Provide at least one of --test, --bug-text, --bug-log, or --bug-image."
            )
        if bug_log is not None:
            _validate_bug_log_path(bug_log)
        command = parse_pytest_command(test) if test is not None else []
        settings = Settings.from_env()
        llm = create_llm_client(settings)
        orchestrator = WorkflowOrchestrator(settings, llm)
        if has_bug_evidence:
            state = orchestrator.run_evidence(
                project_path=project_path.resolve(),
                test_command=command,
                bug_text=bug_text,
                bug_log=bug_log,
                bug_image=bug_image,
            )
        else:
            state = orchestrator.run(project_path.resolve(), command)
    except (CommandValidationError, LLMProviderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]PatchProof finished with status:[/green] {state.final_status.value}")
    console.print("Reports written: report.md, report.json")


def _validate_bug_log_path(path: Path) -> None:
    if not path.exists():
        raise CommandValidationError(f"Bug log does not exist: {path}")
    if not path.is_file():
        raise CommandValidationError(f"Bug log is not a file: {path}")
    try:
        with path.open("r", encoding="utf-8"):
            pass
    except OSError as exc:
        raise CommandValidationError(f"Bug log is not readable: {path}") from exc

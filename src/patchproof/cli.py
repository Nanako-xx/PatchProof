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
        if not any([test, bug_text, bug_log, bug_image]):
            raise CommandValidationError(
                "Provide at least one of --test, --bug-text, --bug-log, or --bug-image."
            )
        command = parse_pytest_command(test) if test is not None else []
        settings = Settings.from_env()
        llm = create_llm_client(settings)
        state = WorkflowOrchestrator(settings, llm).run_evidence(
            project_path=project_path.resolve(),
            test_command=command,
            bug_text=bug_text,
            bug_log=bug_log,
            bug_image=bug_image,
        )
    except (CommandValidationError, LLMProviderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]PatchProof finished with status:[/green] {state.final_status.value}")
    console.print("Reports written: report.md, report.json")

from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

from patchproof.core.config import Settings
from patchproof.core.orchestrator import WorkflowOrchestrator
from patchproof.errors import CommandValidationError, LLMProviderError
from patchproof.llm.factory import create_llm_client
from patchproof.tools.command_runner import parse_pytest_command


app = typer.Typer(help="PatchProof: verified patch suggestions for pytest failures.")
console = Console()


@app.callback()
def main() -> None:
    """PatchProof debugging assistant."""


@app.command()
def run(
    project_path: Path = typer.Argument(..., help="Path to a local Python project."),
    test: str = typer.Option(..., "--test", help="Restricted pytest command, such as 'pytest -q'."),
) -> None:
    """Run PatchProof against a local pytest failure."""
    load_dotenv()
    try:
        command = parse_pytest_command(test)
        settings = Settings.from_env()
        llm = create_llm_client(settings)
        state = WorkflowOrchestrator(settings, llm).run(project_path.resolve(), command)
    except (CommandValidationError, LLMProviderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]PatchProof finished with status:[/green] {state.final_status.value}")
    console.print("Reports written: report.md, report.json")

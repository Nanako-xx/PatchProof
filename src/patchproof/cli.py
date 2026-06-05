from __future__ import annotations

import typer


app = typer.Typer(help="PatchProof debugging assistant.")


@app.callback()
def main() -> None:
    """PatchProof debugging assistant."""


@app.command()
def run(
    project_path: str = typer.Argument(..., help="Path to the Python project to debug."),
    test: str = typer.Option(..., "--test", help="Test command to reproduce the failure."),
) -> None:
    """Placeholder command until the workflow orchestrator is implemented."""
    typer.echo(
        "PatchProof CLI is installed, but the run workflow is not implemented yet. "
        f"Received project_path={project_path!r}, test={test!r}."
    )
    raise typer.Exit(code=2)

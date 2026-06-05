import json
from pathlib import Path

from patchproof.core.state import FinalStatus, RunState
from patchproof.reporting.json_report import write_json_report
from patchproof.reporting.markdown import render_markdown_report, write_markdown_report


def test_render_markdown_report_includes_status(tmp_path: Path):
    state = RunState(
        project_path=Path("demo"),
        test_command=["pytest", "-q"],
        final_status=FinalStatus.NOT_REPRODUCED,
        stop_reason="Baseline tests passed.",
    )

    markdown = render_markdown_report(state)

    assert "# PatchProof Report" in markdown
    assert "not_reproduced" in markdown
    assert "Baseline tests passed." in markdown


def test_write_reports(tmp_path: Path):
    state = RunState(project_path=Path("demo"), test_command=["pytest", "-q"])

    write_markdown_report(state, tmp_path / "report.md")
    write_json_report(state, tmp_path / "report.json")

    assert (tmp_path / "report.md").exists()
    payload = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert payload["test_command"] == ["pytest", "-q"]
    assert payload["final_status"] == "created"

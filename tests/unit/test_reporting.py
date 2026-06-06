import json
from pathlib import Path

from patchproof.core.state import FinalStatus, RunState
from patchproof.llm.base import LLMCallTrace
from patchproof.reporting.json_report import write_json_report, write_llm_trace
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
    assert "llm_call_trace" not in payload
    assert "llm_call_count" not in payload


def test_write_llm_trace_to_private_debug_file(tmp_path: Path):
    trace_path = tmp_path / ".patchproof" / "llm_trace.json"

    write_llm_trace(
        [
            LLMCallTrace(
                response_model="InvestigationStep",
                provider="fake",
                model="fake",
                raw_responses=['{"action":"list_project_files"}'],
                call_count=1,
            )
        ],
        trace_path,
    )

    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert payload["llm_call_count"] == 1
    assert payload["llm_call_trace"][0]["response_model"] == "InvestigationStep"

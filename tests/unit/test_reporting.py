import json
from pathlib import Path

from patchproof.core.state import (
    AttemptResult,
    BugEvidence,
    BugEvidenceSource,
    EvidenceSourceType,
    FinalStatus,
    RunState,
    TracebackFrame,
    TracebackSummary,
    VerificationCommand,
    VerificationCommandSource,
    VerificationPlan,
    VerificationStatus,
)
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


def test_markdown_report_includes_each_patch_attempt_and_failure_reason():
    state = RunState(
        project_path=Path("demo"),
        test_command=["pytest", "-q"],
        attempts=[
            AttemptResult(
                patch_diff="invalid diff",
                patch_explanation="First patch.",
                verification_status=VerificationStatus.PATCH_FAILED,
                patch_apply_error="error: corrupt patch",
            ),
            AttemptResult(
                patch_diff="valid diff",
                patch_explanation="Second patch.",
                verification_status=VerificationStatus.TESTS_FAILED,
            ),
        ],
    )

    markdown = render_markdown_report(state)

    assert "invalid diff" in markdown
    assert "error: corrupt patch" in markdown
    assert "valid diff" in markdown


def test_markdown_report_includes_bug_evidence_and_verification_plan():
    state = RunState(
        project_path=Path("demo"),
        bug_evidence=BugEvidence(
            sources=[
                BugEvidenceSource(
                    source_type=EvidenceSourceType.BUG_IMAGE,
                    label="error.png",
                    raw_text="ValueError: bad",
                )
            ],
            traceback_summary=TracebackSummary(
                frames=[TracebackFrame(file_path="src/parser.py", line_number=2, function_name="parse")]
            ),
            suspected_files=["src/parser.py"],
            summary="ValueError in src/parser.py",
        ),
        verification_plan=VerificationPlan(
            commands=[
                VerificationCommand(
                    command=["pytest", "tests/test_parser.py", "-q"],
                    source=VerificationCommandSource.MATCHED_TEST,
                    reason="Matched parser.py.",
                )
            ],
            skipped_commands=[
                VerificationCommand(
                    command=["make", "deploy"],
                    source=VerificationCommandSource.SKIPPED_UNSAFE,
                    reason="Outside allowlist.",
                )
            ],
        ),
    )

    markdown = render_markdown_report(state)

    assert "## Bug Evidence" in markdown
    assert "bug_image" in markdown
    assert "ValueError: bad" in markdown
    assert "src/parser.py:2" in markdown
    assert "## Verification Plan" in markdown
    assert "Planned candidates:" in markdown
    assert "Attempted candidates:" not in markdown
    assert "pytest tests/test_parser.py -q" in markdown
    assert "Skipped" in markdown
    assert "make deploy" in markdown


def test_markdown_report_uses_placeholder_for_empty_verification_commands():
    state = RunState(
        project_path=Path("demo"),
        verification_plan=VerificationPlan(
            commands=[
                VerificationCommand(
                    command=[],
                    source=VerificationCommandSource.MATCHED_TEST,
                    reason="Matched parser.py.",
                )
            ],
            skipped_commands=[
                VerificationCommand(
                    command=[],
                    source=VerificationCommandSource.SKIPPED_UNSAFE,
                    reason="Outside allowlist.",
                )
            ],
        ),
        attempts=[
            AttemptResult(
                patch_diff="diff --git a/src/parser.py b/src/parser.py\n",
                verification_command=VerificationCommand(
                    command=[],
                    source=VerificationCommandSource.MATCHED_TEST,
                    reason="Matched parser.py.",
                ),
            )
        ],
    )

    markdown = render_markdown_report(state)

    assert "- `not provided` (matched_test): Matched parser.py." in markdown
    assert "- Skipped `not provided` (skipped_unsafe): Outside allowlist." in markdown
    assert "- Verification command: `not provided`" in markdown
    assert "`` (matched_test)" not in markdown
    assert "Skipped ``" not in markdown
    assert "Verification command: ``" not in markdown

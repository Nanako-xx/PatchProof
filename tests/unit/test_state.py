from pathlib import Path

import pytest
from pydantic import ValidationError

from patchproof.core.state import (
    AttemptResult,
    BugEvidence,
    BugEvidenceSource,
    EvidenceSourceType,
    FinalStatus,
    Hypothesis,
    InvestigationResult,
    LogSignal,
    ReviewDecision,
    RunState,
    TestRunResult as RunResultModel,
    TestRunStatus as RunStatus,
    TracebackFrame,
    TracebackSummary,
    VerificationCommand,
    VerificationCommandSource,
    VerificationPlan,
    VerificationStatus,
)


def test_run_state_starts_with_no_attempts():
    state = RunState(project_path=Path("demo"), test_command=["pytest", "-q"])

    assert state.project_path == Path("demo")
    assert state.test_command == ["pytest", "-q"]
    assert state.attempts == []
    assert state.final_status == FinalStatus.CREATED


def test_investigation_requires_evidence_backed_hypothesis():
    result = InvestigationResult(
        suspected_files=["calculator.py"],
        hypotheses=[
            Hypothesis(
                description="add uses subtraction instead of addition",
                evidence="test_add expected 5 but got -1",
                confidence=0.91,
            )
        ],
        selected_hypothesis_index=0,
        reasoning_summary="The failed assertion points to calculator.add.",
        tool_trace=[],
    )

    assert result.selected_hypothesis.description.startswith("add uses")


def test_hypothesis_requires_non_empty_evidence():
    with pytest.raises(ValidationError):
        Hypothesis(
            description="add uses subtraction instead of addition",
            evidence="",
            confidence=0.91,
        )


def test_investigation_rejects_out_of_range_selected_hypothesis():
    with pytest.raises(ValidationError):
        InvestigationResult(
            hypotheses=[
                Hypothesis(
                    description="add uses subtraction instead of addition",
                    evidence="test_add expected 5 but got -1",
                    confidence=0.91,
                )
            ],
            selected_hypothesis_index=1,
        )


def test_attempt_result_records_review_and_verification():
    attempt = AttemptResult(
        patch_diff="diff --git a/calculator.py b/calculator.py\n",
        patch_explanation="Replace subtraction with addition.",
        review_decision=ReviewDecision.APPROVED,
        review_summary="Small patch matching evidence.",
        verification_status=VerificationStatus.VERIFIED,
    )

    assert attempt.review_decision == ReviewDecision.APPROVED
    assert attempt.verification_status == VerificationStatus.VERIFIED


def test_test_run_result_has_status_and_output():
    result = RunResultModel(
        status=RunStatus.FAILED,
        command=["pytest", "-q"],
        exit_code=1,
        stdout="failed output",
        stderr="",
        duration_ms=123,
        failed_tests=["test_calculator.py::test_add"],
        traceback_text="AssertionError",
        summary="1 failed",
    )

    assert result.status == RunStatus.FAILED
    assert result.failed_tests == ["test_calculator.py::test_add"]


def test_bug_evidence_records_sources_and_file_hints():
    evidence = BugEvidence(
        sources=[
            BugEvidenceSource(
                source_type=EvidenceSourceType.BUG_TEXT,
                label="pasted error",
                raw_text='File "app.py", line 3, in handler\nValueError: bad',
            )
        ],
        raw_text='File "app.py", line 3, in handler\nValueError: bad',
        traceback_summary=TracebackSummary(
            exception_type="ValueError",
            frames=[TracebackFrame(file_path="app.py", line_number=3, function_name="handler")],
        ),
        log_signals=[LogSignal(level="ERROR", message="ValueError: bad", file_path="app.py", line_number=3)],
        suspected_files=["app.py"],
        entrypoint_files=[],
        summary="ValueError in app.py",
    )

    assert evidence.sources[0].source_type == EvidenceSourceType.BUG_TEXT
    assert evidence.traceback_summary.exception_type == "ValueError"
    assert evidence.suspected_files == ["app.py"]


def test_run_state_allows_evidence_without_test_command():
    state = RunState(project_path=Path("demo"))

    assert state.test_command == []
    assert state.bug_evidence is None
    assert state.verification_plan is None


def test_verification_plan_records_attempted_and_skipped_commands():
    plan = VerificationPlan(
        commands=[
            VerificationCommand(
                command=["pytest", "tests/test_parser.py", "-q"],
                source=VerificationCommandSource.MATCHED_TEST,
                reason="Matched src/parser.py to tests/test_parser.py.",
            )
        ],
        skipped_commands=[
            VerificationCommand(
                command=["make", "deploy"],
                source=VerificationCommandSource.SKIPPED_UNSAFE,
                reason="Outside the v0.2 allowlist.",
            )
        ],
    )

    assert plan.commands[0].command == ["pytest", "tests/test_parser.py", "-q"]
    assert plan.skipped_commands[0].source == VerificationCommandSource.SKIPPED_UNSAFE

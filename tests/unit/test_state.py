from pathlib import Path

import pytest
from pydantic import ValidationError

from patchproof.core.state import (
    AttemptResult,
    FinalStatus,
    Hypothesis,
    InvestigationResult,
    ReviewDecision,
    RunState,
    TestRunResult as RunResultModel,
    TestRunStatus as RunStatus,
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

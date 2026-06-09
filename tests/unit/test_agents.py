import pytest

from patchproof.agents.coach import CoachExplainer
from patchproof.agents.investigator import InvestigatorAgent
from patchproof.agents.patcher import PatchAgent
from patchproof.agents.reviewer import ReviewerAgent
from patchproof.core.config import Settings
from patchproof.core.state import (
    BugEvidence,
    BugEvidenceSource,
    DiffMetadata,
    EvidenceSourceType,
    Hypothesis,
    InvestigationResult,
    ReviewDecision,
    TestRunResult as RunResultModel,
    TestRunStatus as RunStatus,
    TracebackSummary,
)
from patchproof.llm.base import FakeLLMClient


def baseline_result() -> RunResultModel:
    return RunResultModel(
        status=RunStatus.FAILED,
        command=["pytest", "-q"],
        exit_code=1,
        stdout="assert -1 == 5",
        stderr="",
        failed_tests=["test_calculator.py::test_add"],
        traceback_text="AssertionError",
        summary="1 failed",
    )


def investigation_result() -> InvestigationResult:
    return InvestigationResult(
        suspected_files=["calculator.py"],
        hypotheses=[Hypothesis(description="bad operator", evidence="assertion", confidence=0.9)],
        selected_hypothesis_index=0,
    )


@pytest.fixture
def sample_bug_evidence() -> BugEvidence:
    return BugEvidence(
        sources=[
            BugEvidenceSource(
                source_type=EvidenceSourceType.BUG_TEXT,
                label="pasted",
                raw_text="ValueError: bad",
            )
        ],
        raw_text="ValueError: bad",
        traceback_summary=TracebackSummary(exception_type="ValueError"),
        suspected_files=["parser.py"],
        summary="ValueError in parser.py",
    )


def test_investigator_returns_structured_hypothesis():
    client = FakeLLMClient(
        [
            {
                "suspected_files": ["calculator.py"],
                "hypotheses": [
                    {
                        "description": "add uses subtraction instead of addition",
                        "evidence": "test_add expected 5 but got -1",
                        "confidence": 0.9,
                    }
                ],
                "selected_hypothesis_index": 0,
                "reasoning_summary": "The failed assertion points to add.",
                "tool_trace": [],
            }
        ]
    )

    result = InvestigatorAgent(client, Settings()).run(baseline_result(), repository_context="calculator.py")

    assert result.selected_hypothesis.description.startswith("add uses")
    assert "Max hypotheses: 3" in client.calls[0].user_prompt


def test_investigator_prompt_includes_bug_evidence(sample_bug_evidence: BugEvidence):
    client = FakeLLMClient(
        [
            {
                "suspected_files": ["parser.py"],
                "hypotheses": [
                    {
                        "description": "parser rejects a valid input",
                        "evidence": "BugEvidence says ValueError in parser.py",
                        "confidence": 0.8,
                    }
                ],
                "selected_hypothesis_index": 0,
                "reasoning_summary": "Evidence points to parser.py.",
                "tool_trace": [],
            }
        ]
    )

    result = InvestigatorAgent(client, Settings()).run_with_evidence(
        sample_bug_evidence,
        repository_context="parser.py",
    )

    assert result.suspected_files == ["parser.py"]
    assert "Bug evidence:" in client.calls[0].user_prompt
    assert "ValueError in parser.py" in client.calls[0].user_prompt


def test_patch_agent_returns_diff():
    client = FakeLLMClient(
        [
            {
                "unified_diff": "diff --git a/calculator.py b/calculator.py\n",
                "explanation": "Use addition.",
            }
        ]
    )

    result = PatchAgent(client).run(investigation_result(), baseline_result(), "def add(a, b): return a - b")

    assert result.patch_diff.startswith("diff --git")
    assert result.patch_explanation == "Use addition."


def test_patch_agent_prompt_includes_bug_evidence(sample_bug_evidence: BugEvidence):
    client = FakeLLMClient(
        [
            {
                "unified_diff": "diff --git a/parser.py b/parser.py\n",
                "explanation": "Handle invalid values.",
            }
        ]
    )

    result = PatchAgent(client).run_with_evidence(
        investigation_result(),
        sample_bug_evidence,
        code_context="def parse(value): return int(value)",
    )

    assert result.patch_diff.startswith("diff --git")
    assert "Bug evidence:" in client.calls[0].user_prompt
    assert "ValueError in parser.py" in client.calls[0].user_prompt


def test_reviewer_rejects_rule_violations_without_llm():
    client = FakeLLMClient([])
    metadata = DiffMetadata(
        changed_files=["test_calculator.py"],
        rule_violations=["test-file changes are not allowed"],
    )

    result = ReviewerAgent(client).run(investigation_result(), "diff", metadata)

    assert result.decision == ReviewDecision.REJECTED
    assert client.calls == []


def test_coach_explainer_returns_learning_points():
    client = FakeLLMClient(
        [
            {
                "bug_explanation": "The function used the wrong operator.",
                "evidence_walkthrough": "The assertion showed -1 instead of 5.",
                "patch_explanation": "The patch changes subtraction to addition.",
                "verification_explanation": "The provided pytest command passed.",
                "learning_points": ["Read the failing assertion first."],
            }
        ]
    )

    result = CoachExplainer(client).run("summary")

    assert result.learning_points == ["Read the failing assertion first."]

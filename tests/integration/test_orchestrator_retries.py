import shutil
from pathlib import Path

from patchproof.core.config import Settings
from patchproof.core.orchestrator import WorkflowOrchestrator
from patchproof.core.state import FinalStatus, VerificationStatus
from patchproof.llm.base import FakeLLMClient


VALID_PATCH = (
    "diff --git a/calculator.py b/calculator.py\n"
    "--- a/calculator.py\n"
    "+++ b/calculator.py\n"
    "@@ -1,2 +1,2 @@\n"
    " def add(a, b):\n"
    "-    return a - b\n"
    "+    return a + b\n"
)

WRONG_BUT_APPLICABLE_PATCH = VALID_PATCH.replace("+    return a + b", "+    return a * b")


def investigation_responses(evidence: str = "calculator.py line 2 returns a - b"):
    return [
        {"action": "read_code_context", "file_path": "calculator.py", "line_number": 2},
        {
            "action": "final",
            "suspected_files": ["calculator.py"],
            "hypotheses": [
                {
                    "description": "add uses the wrong operator",
                    "evidence": evidence,
                    "confidence": 0.95,
                }
            ],
            "selected_hypothesis_index": 0,
            "reasoning_summary": "The implementation does not match the failing test.",
        },
    ]


def approved_review():
    return {
        "decision": "approved",
        "semantic_risks": [],
        "review_summary": "The patch is small and relevant.",
    }


def coach_response():
    return {
        "bug_explanation": "The function used the wrong operator.",
        "evidence_walkthrough": "The test output and source identify the mismatch.",
        "patch_explanation": "The final patch uses addition.",
        "verification_explanation": "The provided pytest command passed.",
        "learning_points": ["Use verification feedback to refine a patch."],
    }


def copy_calculator(tmp_path: Path) -> Path:
    source = Path(__file__).parents[2] / "examples" / "buggy_calculator"
    project = tmp_path / "buggy_calculator"
    shutil.copytree(source, project)
    return project


def test_orchestrator_returns_patch_apply_error_to_patch_agent(tmp_path: Path, monkeypatch):
    project = copy_calculator(tmp_path)
    monkeypatch.chdir(tmp_path)
    fake_llm = FakeLLMClient(
        investigation_responses()
        + [
            {"unified_diff": "not a valid diff", "explanation": "First patch."},
            approved_review(),
            {"unified_diff": VALID_PATCH, "explanation": "Corrected patch."},
            approved_review(),
            coach_response(),
        ]
    )

    state = WorkflowOrchestrator(Settings(max_patch_attempts=3), fake_llm).run(project, ["pytest", "-q"])

    assert state.final_status == FinalStatus.VERIFIED
    assert len(state.attempts) == 2
    assert state.attempts[0].verification_status == VerificationStatus.PATCH_FAILED
    assert "error" in state.attempts[0].patch_apply_error
    patch_prompts = [call.user_prompt for call in fake_llm.calls if "Code context:" in call.user_prompt]
    assert state.attempts[0].patch_apply_error in patch_prompts[1]
    assert state.attempts[0].patch_diff in patch_prompts[1]


def test_orchestrator_returns_failed_verification_to_investigator(tmp_path: Path, monkeypatch):
    project = copy_calculator(tmp_path)
    monkeypatch.chdir(tmp_path)
    fake_llm = FakeLLMClient(
        investigation_responses()
        + [
            {"unified_diff": WRONG_BUT_APPLICABLE_PATCH, "explanation": "First patch."},
            approved_review(),
        ]
        + investigation_responses("The verification test still fails after multiplication.")
        + [
            {"unified_diff": VALID_PATCH, "explanation": "Corrected patch."},
            approved_review(),
            coach_response(),
        ]
    )

    state = WorkflowOrchestrator(Settings(max_patch_attempts=3), fake_llm).run(project, ["pytest", "-q"])

    assert state.final_status == FinalStatus.VERIFIED
    assert len(state.attempts) == 2
    assert state.attempts[0].verification_status == VerificationStatus.TESTS_FAILED
    assert state.attempts[0].verification_result is not None
    investigation_prompts = [call.user_prompt for call in fake_llm.calls if call.user_prompt.startswith("Bug evidence:")]
    assert state.attempts[0].verification_result.summary in investigation_prompts[2]


def test_orchestrator_stops_after_max_patch_attempts(tmp_path: Path, monkeypatch):
    project = copy_calculator(tmp_path)
    monkeypatch.chdir(tmp_path)
    fake_llm = FakeLLMClient(
        investigation_responses()
        + [
            {"unified_diff": "invalid patch one", "explanation": "First patch."},
            approved_review(),
            {"unified_diff": "invalid patch two", "explanation": "Second patch."},
            approved_review(),
            coach_response(),
        ]
    )

    state = WorkflowOrchestrator(Settings(max_patch_attempts=2), fake_llm).run(project, ["pytest", "-q"])

    assert state.final_status == FinalStatus.UNVERIFIED
    assert len(state.attempts) == 2
    assert "maximum patch attempts" in state.stop_reason.lower()

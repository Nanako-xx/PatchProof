import shutil
from pathlib import Path

from patchproof.core.config import Settings
from patchproof.core.orchestrator import WorkflowOrchestrator
from patchproof.core.state import FinalStatus
from patchproof.llm.base import FakeLLMClient


def test_orchestrator_verifies_buggy_calculator(tmp_path: Path, monkeypatch):
    source = Path(__file__).parents[2] / "examples" / "buggy_calculator"
    project = tmp_path / "buggy_calculator"
    shutil.copytree(source, project)
    monkeypatch.chdir(tmp_path)

    fake_llm = FakeLLMClient(
        [
            {
                "suspected_files": ["calculator.py"],
                "hypotheses": [
                    {
                        "description": "add uses subtraction instead of addition",
                        "evidence": "test_add expects 5 but receives -1",
                        "confidence": 0.95,
                    }
                ],
                "selected_hypothesis_index": 0,
                "reasoning_summary": "The failing assertion points to the add function.",
                "tool_trace": [],
            },
            {
                "unified_diff": (
                    "diff --git a/calculator.py b/calculator.py\n"
                    "--- a/calculator.py\n"
                    "+++ b/calculator.py\n"
                    "@@ -1,2 +1,2 @@\n"
                    " def add(a, b):\n"
                    "-    return a - b\n"
                    "+    return a + b\n"
                ),
                "explanation": "Replace subtraction with addition.",
            },
            {
                "decision": "approved",
                "semantic_risks": [],
                "review_summary": "The patch is minimal and matches the failing assertion.",
            },
            {
                "bug_explanation": "The function used subtraction when the test expected addition.",
                "evidence_walkthrough": "The baseline test showed add(2, 3) returned -1.",
                "patch_explanation": "The patch changes the operator to plus.",
                "verification_explanation": "The same pytest command passed in the temporary copy.",
                "learning_points": ["Use the failing assertion to locate expected behavior."],
            },
        ]
    )

    state = WorkflowOrchestrator(Settings(), fake_llm).run(project, ["pytest", "-q"])

    assert state.final_status == FinalStatus.VERIFIED
    assert state.attempts[0].verification_status.value == "verified"
    assert "return a - b" in (project / "calculator.py").read_text(encoding="utf-8")
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "report.json").exists()

import json
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
            {"action": "search_code", "query": "return a - b", "file_path": None, "line_number": None},
            {"action": "read_code_context", "query": None, "file_path": "calculator.py", "line_number": 2},
            {
                "action": "final",
                "suspected_files": ["calculator.py"],
                "hypotheses": [
                    {
                        "description": "add uses subtraction instead of addition",
                        "evidence": "calculator.py line 2 returns a - b",
                        "confidence": 0.95,
                    }
                ],
                "selected_hypothesis_index": 0,
                "reasoning_summary": "The code context confirms the wrong operator.",
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
    assert state.investigation is not None
    assert len(state.investigation.tool_trace) == 2
    assert state.attempts[0].verification_status.value == "verified"
    assert "return a - b" in (project / "calculator.py").read_text(encoding="utf-8")
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "report.json").exists()
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert "llm_call_count" not in report
    assert "llm_call_trace" not in report
    trace = json.loads((tmp_path / ".patchproof" / "llm_trace.json").read_text(encoding="utf-8"))
    assert trace["llm_call_count"] == 6
    assert trace["llm_call_trace"][0]["response_model"] == "InvestigationStep"
    assert trace["llm_call_trace"][0]["raw_responses"]
    assert trace["llm_call_trace"][0]["call_count"] == 1

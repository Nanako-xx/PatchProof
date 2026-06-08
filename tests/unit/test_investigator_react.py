from pathlib import Path

import pytest
from pydantic import ValidationError

from patchproof.agents.investigator import InvestigationStep, InvestigatorAgent
from patchproof.core.config import Settings
from patchproof.core.state import TestRunResult as RunResultModel
from patchproof.core.state import TestRunStatus as RunStatus
from patchproof.llm.base import FakeLLMClient
from patchproof.tools.code_context import CodeContextTool
from patchproof.tools.project_indexer import ProjectIndexer


def test_investigator_react_uses_read_only_tools(tmp_path: Path):
    (tmp_path / "calculator.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    baseline = RunResultModel(
        status=RunStatus.FAILED,
        command=["pytest", "-q"],
        exit_code=1,
        stdout="assert -1 == 5",
        failed_tests=["test_calculator.py::test_add"],
        traceback_text="AssertionError",
    )
    client = FakeLLMClient(
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
                        "confidence": 0.9,
                    }
                ],
                "selected_hypothesis_index": 0,
                "reasoning_summary": "The code context confirms the wrong operator.",
            },
        ]
    )

    result = InvestigatorAgent(client, Settings()).run_with_tools(
        baseline=baseline,
        indexer=ProjectIndexer(tmp_path),
        context_tool=CodeContextTool(tmp_path),
    )

    assert result.selected_hypothesis.evidence == "calculator.py line 2 returns a - b"
    assert len(result.tool_trace) == 2
    assert "Every response must include an action" in client.calls[0].user_prompt


def test_investigation_step_requires_fields_for_selected_action():
    with pytest.raises(ValidationError):
        InvestigationStep(action="search_code")

    with pytest.raises(ValidationError):
        InvestigationStep(action="read_code_context", file_path="calculator.py")

    with pytest.raises(ValidationError):
        InvestigationStep(action="final")

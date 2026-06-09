import json
from pathlib import Path

from patchproof.core.config import Settings
from patchproof.core.orchestrator import WorkflowOrchestrator
from patchproof.core.state import FinalStatus, VerificationCommandSource, VerificationStatus
from patchproof.llm.base import FakeLLMClient


VALID_PATCH = (
    "diff --git a/src/parser.py b/src/parser.py\n"
    "--- a/src/parser.py\n"
    "+++ b/src/parser.py\n"
    "@@ -1,2 +1,2 @@\n"
    " def parse_count(value):\n"
    "-    return value\n"
    "+    return int(value)\n"
)


def investigation_responses():
    return [
        {"action": "read_code_context", "file_path": "src/parser.py", "line_number": 2},
        {
            "action": "final",
            "suspected_files": ["src/parser.py"],
            "hypotheses": [
                {
                    "description": "parse_count returns a string instead of an int",
                    "evidence": "The bug evidence points at src/parser.py.",
                    "confidence": 0.95,
                }
            ],
            "selected_hypothesis_index": 0,
            "reasoning_summary": "The implementation returns the raw value.",
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
        "bug_explanation": "parse_count returned the raw string.",
        "evidence_walkthrough": "The evidence pointed at src/parser.py.",
        "patch_explanation": "The patch casts the value to int.",
        "verification_explanation": "The selected pytest command passed in the temporary copy.",
        "learning_points": ["Verify the narrowest relevant test first."],
    }


def fake_llm_with_patch(image_responses=None):
    return FakeLLMClient(
        investigation_responses()
        + [
            {"unified_diff": VALID_PATCH, "explanation": "Cast the parsed value."},
            approved_review(),
            coach_response(),
        ],
        image_responses=image_responses,
    )


def write_parser_project(project: Path) -> None:
    (project / "src").mkdir(parents=True)
    (project / "tests").mkdir()
    (project / "src" / "__init__.py").write_text("", encoding="utf-8")
    (project / "src" / "parser.py").write_text(
        "def parse_count(value):\n"
        "    return value\n",
        encoding="utf-8",
    )
    (project / "tests" / "test_parser.py").write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parents[1]))\n\n"
        "from src.parser import parse_count\n\n"
        "def test_parse_count_returns_int():\n"
        "    assert parse_count('3') == 3\n",
        encoding="utf-8",
    )


def test_bug_text_without_user_test_uses_matched_test(tmp_path: Path, monkeypatch):
    project = tmp_path / "parser_project"
    write_parser_project(project)
    monkeypatch.chdir(tmp_path)

    state = WorkflowOrchestrator(Settings(), fake_llm_with_patch()).run_evidence(
        project_path=project,
        test_command=[],
        bug_text=(
            "Traceback (most recent call last):\n"
            "  File \"src/parser.py\", line 2, in parse_count\n"
            "    return value\n"
            "TypeError: parse_count returns the wrong value type\n"
        ),
        bug_log=None,
        bug_image=None,
    )

    assert state.final_status == FinalStatus.VERIFIED
    assert state.attempts[0].verification_status == VerificationStatus.VERIFIED
    assert state.attempts[0].verification_command is not None
    assert state.attempts[0].verification_command.command == ["pytest", "tests/test_parser.py", "-q"]
    assert state.attempts[0].verification_command.source == VerificationCommandSource.MATCHED_TEST
    assert "return value" in (project / "src" / "parser.py").read_text(encoding="utf-8")
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["verification_plan"]["commands"][0]["command"] == ["pytest", "tests/test_parser.py", "-q"]


def test_bug_log_with_user_test_uses_user_test(tmp_path: Path, monkeypatch):
    project = tmp_path / "parser_project"
    write_parser_project(project)
    bug_log = tmp_path / "bug.log"
    bug_log.write_text("ERROR src/parser.py:2 parse_count returns text\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    state = WorkflowOrchestrator(Settings(), fake_llm_with_patch()).run_evidence(
        project_path=project,
        test_command=["pytest", "-q"],
        bug_text=None,
        bug_log=bug_log,
        bug_image=None,
    )

    assert state.final_status == FinalStatus.VERIFIED
    assert state.verification_plan is not None
    assert state.verification_plan.commands[0].command == ["pytest", "-q"]
    assert state.verification_plan.commands[0].source == VerificationCommandSource.USER_PROVIDED


def test_bug_image_flows_through_fake_vision(tmp_path: Path, monkeypatch):
    project = tmp_path / "parser_project"
    write_parser_project(project)
    image_path = tmp_path / "bug.png"
    image_path.write_bytes(b"not a real image; fake llm reads the path only")
    monkeypatch.chdir(tmp_path)

    state = WorkflowOrchestrator(
        Settings(),
        fake_llm_with_patch(
            image_responses=[
                {"extracted_text": "ERROR src/parser.py:2 visible failure mentions parse_count."},
            ]
        ),
    ).run_evidence(
        project_path=project,
        test_command=[],
        bug_text=None,
        bug_log=None,
        bug_image=image_path,
    )

    assert state.final_status == FinalStatus.VERIFIED
    assert state.bug_evidence is not None
    assert state.bug_evidence.sources[0].source_type.value == "bug_image"
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["bug_evidence"]["sources"][0]["source_type"] == "bug_image"

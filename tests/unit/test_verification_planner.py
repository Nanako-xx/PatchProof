from pathlib import Path

from patchproof.core.state import (
    BugEvidence,
    TracebackFrame,
    TracebackSummary,
    VerificationCommandSource,
)
from patchproof.tools.verification_planner import VerificationPlanner


def evidence_with_frames(frames):
    return BugEvidence(
        raw_text="traceback",
        traceback_summary=TracebackSummary(exception_type="ValueError", frames=frames),
        suspected_files=[frame.file_path for frame in frames if frame.file_path.startswith("src/")],
        entrypoint_files=[frame.file_path for frame in frames if frame.file_path.startswith("tests/")],
        summary="ValueError",
    )


def test_planner_uses_user_provided_test_first(tmp_path: Path):
    plan = VerificationPlanner().plan(
        project_path=tmp_path,
        evidence=BugEvidence(),
        changed_files=["src/parser.py"],
        user_test_command=["pytest", "-q"],
    )

    assert plan.commands[0].source == VerificationCommandSource.USER_PROVIDED
    assert plan.commands[0].command == ["pytest", "-q"]


def test_planner_uses_traceback_test_entrypoint(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_parser.py").write_text("def test_parse(): pass\n", encoding="utf-8")
    evidence = evidence_with_frames(
        [
            TracebackFrame(file_path="tests/test_parser.py", line_number=4, function_name="test_parse"),
            TracebackFrame(file_path="src/parser.py", line_number=3, function_name="parse_count"),
        ]
    )

    plan = VerificationPlanner().plan(tmp_path, evidence, changed_files=["src/parser.py"], user_test_command=[])

    assert plan.commands[0].command == ["pytest", "tests/test_parser.py", "-q"]
    assert plan.commands[0].source == VerificationCommandSource.TRACEBACK_ENTRYPOINT


def test_planner_normalizes_absolute_traceback_entrypoint(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    test_path = tmp_path / "tests" / "test_parser.py"
    test_path.write_text("def test_parse(): pass\n", encoding="utf-8")
    evidence = BugEvidence(entrypoint_files=[str(test_path)])

    plan = VerificationPlanner().plan(tmp_path, evidence, changed_files=[], user_test_command=[])

    assert plan.commands[0].command == ["pytest", "tests/test_parser.py", "-q"]
    assert plan.commands[0].source == VerificationCommandSource.TRACEBACK_ENTRYPOINT


def test_planner_uses_all_traceback_test_entrypoints_in_deterministic_order(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    first_test = tmp_path / "tests" / "test_alpha.py"
    second_test = tmp_path / "tests" / "test_beta.py"
    first_test.write_text("def test_alpha(): pass\n", encoding="utf-8")
    second_test.write_text("def test_beta(): pass\n", encoding="utf-8")
    evidence = BugEvidence(
        entrypoint_files=[
            "tests/test_beta.py",
            "tests/test_alpha.py",
            str(first_test),
        ]
    )

    plan = VerificationPlanner().plan(tmp_path, evidence, changed_files=[], user_test_command=[])

    assert [command.command for command in plan.commands] == [
        ["pytest", "tests/test_alpha.py", "-q"],
        ["pytest", "tests/test_beta.py", "-q"],
    ]
    assert all(command.source == VerificationCommandSource.TRACEBACK_ENTRYPOINT for command in plan.commands)


def test_planner_matches_source_file_to_test_file(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "src" / "traceback_parser.py").write_text("def parse(): pass\n", encoding="utf-8")
    (tmp_path / "tests" / "unit" / "test_traceback_parser.py").write_text("def test_parse(): pass\n", encoding="utf-8")
    evidence = BugEvidence(suspected_files=["src/traceback_parser.py"], summary="bug")

    plan = VerificationPlanner().plan(tmp_path, evidence, changed_files=["src/traceback_parser.py"], user_test_command=[])

    assert plan.commands[0].command == ["pytest", "tests/unit/test_traceback_parser.py", "-q"]
    assert plan.commands[0].source == VerificationCommandSource.MATCHED_TEST


def test_planner_falls_back_to_default_pytest_when_tests_dir_exists(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_smoke.py").write_text("def test_smoke(): pass\n", encoding="utf-8")

    plan = VerificationPlanner().plan(tmp_path, BugEvidence(), changed_files=["src/app.py"], user_test_command=[])

    assert plan.commands[0].command == ["pytest", "-q"]
    assert plan.commands[0].source == VerificationCommandSource.DEFAULT_PYTEST


def test_planner_records_skipped_unsafe_candidates(tmp_path: Path):
    plan = VerificationPlanner().plan(
        project_path=tmp_path,
        evidence=BugEvidence(),
        changed_files=[],
        user_test_command=[],
        unsafe_candidates=[["make", "deploy"], ["npm", "run", "test"]],
    )

    assert [command.command for command in plan.skipped_commands] == [["make", "deploy"], ["npm", "run", "test"]]
    assert all(command.source == VerificationCommandSource.SKIPPED_UNSAFE for command in plan.skipped_commands)

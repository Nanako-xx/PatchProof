from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional, Union

from pydantic import BaseModel, Field, computed_field, model_validator


class FinalStatus(str, Enum):
    CREATED = "created"
    NOT_REPRODUCED = "not_reproduced"
    STOPPED = "stopped"
    VERIFIED = "verified_against_provided_test_command"
    UNVERIFIED = "unverified"


class TestRunStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    COMMAND_ERROR = "command_error"
    TIMEOUT = "timeout"


class ReviewDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class VerificationStatus(str, Enum):
    NOT_RUN = "not_run"
    VERIFIED = "verified"
    PATCH_FAILED = "patch_failed"
    TESTS_FAILED = "tests_failed"
    TIMEOUT = "timeout"


class TestRunResult(BaseModel):
    status: TestRunStatus
    command: list[str]
    exit_code: Optional[int]
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    failed_tests: list[str] = Field(default_factory=list)
    traceback_text: str = ""
    summary: str = ""


class TracebackFrame(BaseModel):
    file_path: str
    line_number: int
    function_name: Optional[str] = None


class TracebackSummary(BaseModel):
    exception_type: Optional[str] = None
    frames: list[TracebackFrame] = Field(default_factory=list)


class ToolTraceEntry(BaseModel):
    tool_name: str
    tool_input: dict[str, Union[str, int, list[str]]]
    observation: str


class Hypothesis(BaseModel):
    description: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class InvestigationResult(BaseModel):
    suspected_files: list[str] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    selected_hypothesis_index: int = Field(default=0, ge=0)
    reasoning_summary: str = ""
    tool_trace: list[ToolTraceEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _selected_hypothesis_index_must_exist(self):
        if not self.hypotheses:
            raise ValueError("InvestigationResult requires at least one hypothesis.")
        if self.selected_hypothesis_index >= len(self.hypotheses):
            raise ValueError("selected_hypothesis_index must refer to an existing hypothesis.")
        return self

    @computed_field
    @property
    def selected_hypothesis(self) -> Hypothesis:
        return self.hypotheses[self.selected_hypothesis_index]


class DiffMetadata(BaseModel):
    changed_files: list[str] = Field(default_factory=list)
    added_lines: int = 0
    removed_lines: int = 0
    rule_violations: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def changed_line_count(self) -> int:
        return self.added_lines + self.removed_lines


class AttemptResult(BaseModel):
    patch_diff: str
    patch_explanation: str = ""
    diff_metadata: Optional[DiffMetadata] = None
    review_decision: Optional[ReviewDecision] = None
    review_summary: str = ""
    semantic_risks: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.NOT_RUN
    verification_result: Optional[TestRunResult] = None
    patch_apply_error: str = ""


class CoachExplanation(BaseModel):
    bug_explanation: str = ""
    evidence_walkthrough: str = ""
    patch_explanation: str = ""
    verification_explanation: str = ""
    learning_points: list[str] = Field(default_factory=list)


class RunState(BaseModel):
    project_path: Path
    test_command: list[str]
    baseline_test_result: Optional[TestRunResult] = None
    traceback_summary: Optional[TracebackSummary] = None
    investigation: Optional[InvestigationResult] = None
    attempts: list[AttemptResult] = Field(default_factory=list)
    final_status: FinalStatus = FinalStatus.CREATED
    stop_reason: str = ""
    coach_explanation: Optional[CoachExplanation] = None

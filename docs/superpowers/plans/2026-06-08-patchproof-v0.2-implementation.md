# PatchProof v0.2 Evidence-Driven Debugging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement PatchProof v0.2 so users can provide bug text, log files, screenshots, or a test command, and PatchProof can repair from structured bug evidence with restricted automatic Python verification.

**Architecture:** Keep `WorkflowOrchestrator` as the deterministic state machine, but introduce a `BugEvidence` pipeline before investigation. Keep LLM calls limited to investigation, patching, review, coaching, and vision text extraction; keep traceback parsing, log parsing, command validation, verification planning, patch application, and reporting deterministic. Preserve the existing v0.1 `run(project_path, test_command)` compatibility path by making it call the new evidence-driven workflow with only test evidence.

**Tech Stack:** Python 3.11+, Typer, Pydantic v2, pytest, Rich, python-dotenv, httpx, existing OpenAI-compatible LLM adapter, existing deterministic tools, and standard library modules (`pathlib`, `base64`, `mimetypes`, `re`, `shlex`).

---

## File Structure

### Create

- `src/patchproof/tools/log_parser.py`: Parse log-like text into deterministic `LogSignal` records.
- `src/patchproof/tools/evidence.py`: Read `--bug-text`, `--bug-log`, `--bug-image`, test output, and build `BugEvidence`.
- `src/patchproof/tools/verification_planner.py`: Produce allowlisted verification commands from user tests, traceback entrypoints, source-to-test matching, and project defaults.
- `tests/unit/test_evidence.py`: Unit tests for evidence readers and `BugEvidenceBuilder`.
- `tests/unit/test_log_parser.py`: Unit tests for log parsing.
- `tests/unit/test_vision_evidence.py`: Unit tests for image text extraction, including unsupported model behavior.
- `tests/unit/test_verification_planner.py`: Unit tests for restricted automatic verification planning.
- `tests/integration/test_orchestrator_evidence.py`: End-to-end fake-LLM tests for text/log/image evidence and automatic verification.

### Modify

- `src/patchproof/core/state.py`: Add evidence, log, verification plan models; make `RunState.test_command` default to `[]`; add evidence fields to `RunState` and attempts.
- `src/patchproof/llm/base.py`: Add image-capable request/response hook to fake and protocol shapes without breaking existing text-only clients.
- `src/patchproof/llm/providers/openai_compatible.py`: Add image structured generation using OpenAI-compatible chat content arrays and data URLs.
- `src/patchproof/tools/traceback_parser.py`: Keep current parser, but ensure it is reused by the evidence builder for all text sources.
- `src/patchproof/tools/command_runner.py`: Add restricted `parse_verification_command` support for pytest and unittest commands used by the planner.
- `src/patchproof/agents/investigator.py`: Add evidence-first prompt path while preserving baseline-only wrapper behavior.
- `src/patchproof/agents/patcher.py`: Add evidence-first patch prompt while preserving old `run(...)` call shape where practical.
- `src/patchproof/core/orchestrator.py`: Add evidence-driven workflow and route old `run(...)` through it.
- `src/patchproof/cli.py`: Make `--test` optional and add `--bug-text`, `--bug-log`, `--bug-image`.
- `src/patchproof/reporting/markdown.py`: Render evidence sources, extracted image text, parsed frames, attempted verification commands, and skipped commands.
- `src/patchproof/reporting/json_report.py`: No structural code needed beyond `RunState.model_dump`, but tests should verify new fields are present.
- `tests/unit/test_state.py`: Cover new models and `RunState` defaults.
- `tests/unit/test_command_runner.py`: Cover verification command allowlist.
- `tests/unit/test_agents.py`: Cover evidence prompt content.
- `tests/integration/test_cli.py`: Cover new CLI validation.
- `tests/integration/test_orchestrator_happy_path.py`: Update expected final status value if `FinalStatus.VERIFIED` becomes `verified`.
- `tests/integration/test_orchestrator_retries.py`: Update prompt assertions to evidence-first wording.
- `README.md`: Document v0.2 inputs and verification boundaries after implementation passes.

---

### Task 1: Add Evidence And Verification State Models

**Files:**
- Modify: `src/patchproof/core/state.py`
- Test: `tests/unit/test_state.py`

- [ ] **Step 1: Write failing state tests**

Append these tests to `tests/unit/test_state.py`:

```python
from patchproof.core.state import (
    BugEvidence,
    BugEvidenceSource,
    EvidenceSourceType,
    LogSignal,
    TracebackFrame,
    TracebackSummary,
    VerificationCommand,
    VerificationCommandSource,
    VerificationPlan,
)


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
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
pytest tests/unit/test_state.py -q
```

Expected: FAIL because the new evidence and verification models do not exist.

- [ ] **Step 3: Implement state models**

Modify `src/patchproof/core/state.py`.

Add imports:

```python
from typing import Optional, Union
```

Add these enums and models after `VerificationStatus`:

```python
class EvidenceSourceType(str, Enum):
    TEST_OUTPUT = "test_output"
    BUG_TEXT = "bug_text"
    BUG_LOG = "bug_log"
    BUG_IMAGE = "bug_image"


class VerificationCommandSource(str, Enum):
    USER_PROVIDED = "user_provided"
    TRACEBACK_ENTRYPOINT = "traceback_entrypoint"
    MATCHED_TEST = "matched_test"
    DEFAULT_PYTEST = "default_pytest"
    DEFAULT_UNITTEST = "default_unittest"
    SKIPPED_UNSAFE = "skipped_unsafe"


class BugEvidenceSource(BaseModel):
    source_type: EvidenceSourceType
    label: str
    path: Optional[Path] = None
    raw_text: str = ""
    extracted_text: str = ""


class LogSignal(BaseModel):
    level: Optional[str] = None
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None


class BugEvidence(BaseModel):
    sources: list[BugEvidenceSource] = Field(default_factory=list)
    raw_text: str = ""
    traceback_summary: TracebackSummary = Field(default_factory=TracebackSummary)
    log_signals: list[LogSignal] = Field(default_factory=list)
    suspected_files: list[str] = Field(default_factory=list)
    entrypoint_files: list[str] = Field(default_factory=list)
    summary: str = ""


class VerificationCommand(BaseModel):
    command: list[str]
    source: VerificationCommandSource
    reason: str


class VerificationPlan(BaseModel):
    commands: list[VerificationCommand] = Field(default_factory=list)
    skipped_commands: list[VerificationCommand] = Field(default_factory=list)
```

Change `FinalStatus.VERIFIED` to the general v0.2 status value:

```python
class FinalStatus(str, Enum):
    CREATED = "created"
    NOT_REPRODUCED = "not_reproduced"
    STOPPED = "stopped"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
```

Add verification command tracking to `AttemptResult`:

```python
class AttemptResult(BaseModel):
    patch_diff: str
    patch_explanation: str = ""
    diff_metadata: Optional[DiffMetadata] = None
    review_decision: Optional[ReviewDecision] = None
    review_summary: str = ""
    semantic_risks: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.NOT_RUN
    verification_command: Optional[VerificationCommand] = None
    verification_result: Optional[TestRunResult] = None
    patch_apply_error: str = ""
```

Change `RunState` to allow evidence-only runs:

```python
class RunState(BaseModel):
    project_path: Path
    test_command: list[str] = Field(default_factory=list)
    baseline_test_result: Optional[TestRunResult] = None
    traceback_summary: Optional[TracebackSummary] = None
    bug_evidence: Optional[BugEvidence] = None
    verification_plan: Optional[VerificationPlan] = None
    investigation: Optional[InvestigationResult] = None
    attempts: list[AttemptResult] = Field(default_factory=list)
    final_status: FinalStatus = FinalStatus.CREATED
    stop_reason: str = ""
    coach_explanation: Optional[CoachExplanation] = None
```

- [ ] **Step 4: Run the state tests**

Run:

```powershell
pytest tests/unit/test_state.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add -- src/patchproof/core/state.py tests/unit/test_state.py
git commit -m "feat: add bug evidence state models"
```

---

### Task 2: Add Log Parsing And Evidence Building

**Files:**
- Create: `src/patchproof/tools/log_parser.py`
- Create: `src/patchproof/tools/evidence.py`
- Test: `tests/unit/test_log_parser.py`
- Test: `tests/unit/test_evidence.py`

- [ ] **Step 1: Write failing log parser tests**

Create `tests/unit/test_log_parser.py`:

```python
from patchproof.tools.log_parser import LogParser


def test_log_parser_extracts_level_file_line_and_message():
    text = "2026-06-08 ERROR src/app.py:42 ValueError: invalid user id"

    signals = LogParser().parse(text)

    assert len(signals) == 1
    assert signals[0].level == "ERROR"
    assert signals[0].file_path == "src/app.py"
    assert signals[0].line_number == 42
    assert "invalid user id" in signals[0].message


def test_log_parser_extracts_exception_line_without_file_hint():
    text = "ValueError: invalid user id"

    signals = LogParser().parse(text)

    assert len(signals) == 1
    assert signals[0].level is None
    assert signals[0].file_path is None
    assert signals[0].message == "ValueError: invalid user id"
```

- [ ] **Step 2: Write failing evidence builder tests**

Create `tests/unit/test_evidence.py`:

```python
from pathlib import Path

from patchproof.core.state import EvidenceSourceType, TestRunResult, TestRunStatus
from patchproof.tools.evidence import BugEvidenceBuilder, EvidenceInput, LogFileEvidenceReader, TextEvidenceReader


TRACEBACK_TEXT = '''
Traceback (most recent call last):
  File "tests/test_parser.py", line 6, in test_parse
    parse_count("x")
  File "src/parser.py", line 3, in parse_count
    return int(value)
ValueError: invalid literal for int() with base 10: 'x'
'''


def test_text_evidence_reader_returns_source():
    source = TextEvidenceReader().read("pasted traceback", TRACEBACK_TEXT)

    assert source.source_type == EvidenceSourceType.BUG_TEXT
    assert source.label == "pasted traceback"
    assert "ValueError" in source.raw_text


def test_log_file_evidence_reader_reads_utf8_file(tmp_path: Path):
    log_path = tmp_path / "error.log"
    log_path.write_text(TRACEBACK_TEXT, encoding="utf-8")

    source = LogFileEvidenceReader().read(log_path)

    assert source.source_type == EvidenceSourceType.BUG_LOG
    assert source.path == log_path
    assert "tests/test_parser.py" in source.raw_text


def test_bug_evidence_builder_merges_sources_and_classifies_files():
    source = TextEvidenceReader().read("pasted traceback", TRACEBACK_TEXT)

    evidence = BugEvidenceBuilder().build([source])

    assert evidence.traceback_summary.exception_type == "ValueError"
    assert evidence.entrypoint_files == ["tests/test_parser.py"]
    assert evidence.suspected_files == ["src/parser.py"]
    assert evidence.summary == "ValueError in src/parser.py"


def test_bug_evidence_builder_adds_test_output_source():
    result = TestRunResult(
        status=TestRunStatus.FAILED,
        command=["pytest", "-q"],
        exit_code=1,
        stdout=TRACEBACK_TEXT,
        stderr="",
        traceback_text=TRACEBACK_TEXT,
        summary="1 failed",
    )

    evidence = BugEvidenceBuilder().build([EvidenceInput.from_test_result(result)])

    assert evidence.sources[0].source_type == EvidenceSourceType.TEST_OUTPUT
    assert evidence.raw_text.count("ValueError") == 1
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```powershell
pytest tests/unit/test_log_parser.py tests/unit/test_evidence.py -q
```

Expected: FAIL because `log_parser.py` and `evidence.py` do not exist.

- [ ] **Step 4: Implement `LogParser`**

Create `src/patchproof/tools/log_parser.py`:

```python
from __future__ import annotations

import re

from patchproof.core.state import LogSignal


_LEVEL_RE = re.compile(r"\b(ERROR|WARNING|WARN|CRITICAL|FATAL)\b")
_FILE_LINE_RE = re.compile(r"([A-Za-z0-9_./\\-]+\.py):(\d+)")
_EXCEPTION_LINE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)):\s*(.+)")


class LogParser:
    def parse(self, text: str) -> list[LogSignal]:
        signals: list[LogSignal] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            level_match = _LEVEL_RE.search(stripped)
            exception_match = _EXCEPTION_LINE_RE.search(stripped)
            if not level_match and not exception_match:
                continue

            file_match = _FILE_LINE_RE.search(stripped)
            signals.append(
                LogSignal(
                    level=level_match.group(1) if level_match else None,
                    message=stripped,
                    file_path=file_match.group(1) if file_match else None,
                    line_number=int(file_match.group(2)) if file_match else None,
                )
            )
        return signals
```

- [ ] **Step 5: Implement evidence readers and builder**

Create `src/patchproof/tools/evidence.py`:

```python
from __future__ import annotations

from pathlib import Path

from patchproof.core.state import (
    BugEvidence,
    BugEvidenceSource,
    EvidenceSourceType,
    TestRunResult,
    TracebackFrame,
    TracebackSummary,
)
from patchproof.tools.log_parser import LogParser
from patchproof.tools.traceback_parser import TracebackParser


class EvidenceInput:
    @staticmethod
    def from_test_result(result: TestRunResult) -> BugEvidenceSource:
        text = result.traceback_text or result.stdout + "\n" + result.stderr
        return BugEvidenceSource(
            source_type=EvidenceSourceType.TEST_OUTPUT,
            label="test output",
            raw_text=text,
        )


class TextEvidenceReader:
    def read(self, label: str, text: str) -> BugEvidenceSource:
        return BugEvidenceSource(
            source_type=EvidenceSourceType.BUG_TEXT,
            label=label,
            raw_text=text,
        )


class LogFileEvidenceReader:
    def read(self, path: Path) -> BugEvidenceSource:
        return BugEvidenceSource(
            source_type=EvidenceSourceType.BUG_LOG,
            label=str(path),
            path=path,
            raw_text=path.read_text(encoding="utf-8"),
        )


class BugEvidenceBuilder:
    def __init__(self) -> None:
        self.traceback_parser = TracebackParser()
        self.log_parser = LogParser()

    def build(self, sources: list[BugEvidenceSource]) -> BugEvidence:
        raw_text = "\n\n".join(source.raw_text for source in sources if source.raw_text)
        traceback_summary = self.traceback_parser.parse(raw_text)
        log_signals = self.log_parser.parse(raw_text)
        entrypoint_files = self._entrypoint_files(traceback_summary.frames)
        suspected_files = self._suspected_files(traceback_summary.frames, entrypoint_files)
        if not suspected_files:
            suspected_files = self._files_from_log_signals(log_signals)

        return BugEvidence(
            sources=sources,
            raw_text=raw_text,
            traceback_summary=traceback_summary,
            log_signals=log_signals,
            entrypoint_files=entrypoint_files,
            suspected_files=suspected_files,
            summary=self._summary(traceback_summary, suspected_files),
        )

    def _entrypoint_files(self, frames: list[TracebackFrame]) -> list[str]:
        result: list[str] = []
        for frame in frames:
            normalized = frame.file_path.replace("\\", "/")
            name = Path(normalized).name
            if normalized.startswith("tests/") or name.startswith("test_") or name.endswith("_test.py"):
                if frame.file_path not in result:
                    result.append(frame.file_path)
        return result

    def _suspected_files(self, frames: list[TracebackFrame], entrypoint_files: list[str]) -> list[str]:
        result: list[str] = []
        for frame in frames:
            if frame.file_path in entrypoint_files:
                continue
            if frame.file_path.endswith(".py") and frame.file_path not in result:
                result.append(frame.file_path)
        return result

    def _files_from_log_signals(self, signals) -> list[str]:
        result: list[str] = []
        for signal in signals:
            if signal.file_path and signal.file_path not in result:
                result.append(signal.file_path)
        return result

    def _summary(self, traceback_summary: TracebackSummary, suspected_files: list[str]) -> str:
        if traceback_summary.exception_type and suspected_files:
            return f"{traceback_summary.exception_type} in {suspected_files[-1]}"
        if traceback_summary.exception_type:
            return traceback_summary.exception_type
        if suspected_files:
            return f"Bug evidence points to {suspected_files[-1]}"
        return "Bug evidence collected without a parsed traceback."
```

- [ ] **Step 6: Run tests**

Run:

```powershell
pytest tests/unit/test_log_parser.py tests/unit/test_evidence.py tests/unit/test_traceback_parser.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add -- src/patchproof/tools/log_parser.py src/patchproof/tools/evidence.py tests/unit/test_log_parser.py tests/unit/test_evidence.py
git commit -m "feat: build structured bug evidence"
```

---

### Task 3: Add Vision Text Extraction For Bug Screenshots

**Files:**
- Modify: `src/patchproof/llm/base.py`
- Modify: `src/patchproof/llm/providers/openai_compatible.py`
- Modify: `src/patchproof/tools/evidence.py`
- Test: `tests/unit/test_vision_evidence.py`
- Test: `tests/unit/test_llm.py`

- [ ] **Step 1: Write failing vision evidence tests**

Create `tests/unit/test_vision_evidence.py`:

```python
from pathlib import Path

import pytest

from patchproof.core.state import EvidenceSourceType
from patchproof.errors import LLMProviderError
from patchproof.llm.base import FakeLLMClient
from patchproof.tools.evidence import VisionTextExtractor


def test_vision_text_extractor_fails_when_model_lacks_image_support(tmp_path: Path):
    image_path = tmp_path / "error.png"
    image_path.write_bytes(b"not really an image")
    client = FakeLLMClient([])

    with pytest.raises(LLMProviderError, match="does not support image input"):
        VisionTextExtractor(client).extract(image_path)


def test_vision_text_extractor_returns_bug_image_source(tmp_path: Path):
    image_path = tmp_path / "error.png"
    image_path.write_bytes(b"fake image")
    client = FakeLLMClient(
        responses=[],
        image_responses=[{"extracted_text": "ValueError: bad value"}],
    )

    source = VisionTextExtractor(client).extract(image_path)

    assert source.source_type == EvidenceSourceType.BUG_IMAGE
    assert source.path == image_path
    assert source.raw_text == "ValueError: bad value"
    assert source.extracted_text == "ValueError: bad value"
```

- [ ] **Step 2: Write failing OpenAI-compatible image payload test**

Append this test to `tests/unit/test_llm.py`:

```python
def test_openai_compatible_client_sends_local_image_as_data_url(tmp_path, monkeypatch):
    payloads = []
    image_path = tmp_path / "error.png"
    image_path.write_bytes(b"image-bytes")

    def fake_post(*args, **kwargs):
        payloads.append(kwargs["json"])
        return _response('{"extracted_text": "ValueError: bad"}')

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenAICompatibleClient("https://api.example.com/v1", "secret", "model")

    class ExtractedText(BaseModel):
        extracted_text: str

    response = client.generate_structured_with_image(
        LLMRequest(system_prompt="system", user_prompt="extract text"),
        image_path,
        ExtractedText,
    )

    user_content = payloads[0]["messages"][1]["content"]
    assert response.data.extracted_text == "ValueError: bad"
    assert user_content[0]["type"] == "text"
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"].startswith("data:image/png;base64,")
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
pytest tests/unit/test_vision_evidence.py tests/unit/test_llm.py -q
```

Expected: FAIL because image-capable LLM methods and `VisionTextExtractor` do not exist.

- [ ] **Step 4: Extend fake and protocol-side LLM support**

Modify `src/patchproof/llm/base.py`.

Add imports:

```python
from pathlib import Path
```

Add `image_responses`, `supports_images`, and `generate_structured_with_image` to `FakeLLMClient`:

```python
class FakeLLMClient:
    def __init__(self, responses: list[dict[str, Any]], image_responses: list[dict[str, Any]] | None = None) -> None:
        self.responses = responses
        self.image_responses = image_responses or []
        self.supports_images = bool(image_responses)
        self.calls: list[LLMRequest] = []
        self.image_calls: list[tuple[LLMRequest, Path]] = []
        self.call_trace: list[LLMCallTrace] = []

    def generate_structured(self, request: LLMRequest, response_model: type[T]) -> LLMResponse:
        self.calls.append(request)
        payload = self.responses.pop(0)
        raw_text = json.dumps(payload, ensure_ascii=False)
        self.call_trace.append(
            LLMCallTrace(
                response_model=response_model.__name__,
                provider="fake",
                model="fake",
                raw_responses=[raw_text],
                call_count=1,
            )
        )
        return LLMResponse(
            data=response_model.model_validate(payload),
            raw_text=raw_text,
            provider="fake",
            model="fake",
            call_count=1,
        )

    def generate_structured_with_image(
        self,
        request: LLMRequest,
        image_path: Path,
        response_model: type[T],
    ) -> LLMResponse:
        self.image_calls.append((request, image_path))
        payload = self.image_responses.pop(0)
        raw_text = json.dumps(payload, ensure_ascii=False)
        self.call_trace.append(
            LLMCallTrace(
                response_model=response_model.__name__,
                provider="fake",
                model="fake",
                raw_responses=[raw_text],
                call_count=1,
            )
        )
        return LLMResponse(
            data=response_model.model_validate(payload),
            raw_text=raw_text,
            provider="fake",
            model="fake",
            call_count=1,
        )
```

Keep the `LLMClient` protocol text-only so existing clients remain valid, but the vision extractor will check `supports_images` and method presence dynamically.

- [ ] **Step 5: Add OpenAI-compatible image generation**

Modify `src/patchproof/llm/providers/openai_compatible.py`.

Add imports:

```python
import base64
import mimetypes
from pathlib import Path
```

Add this method to `OpenAICompatibleClient`:

```python
    @property
    def supports_images(self) -> bool:
        return True

    def generate_structured_with_image(
        self,
        request: LLMRequest,
        image_path: Path,
        response_model: type[T],
    ) -> LLMResponse:
        schema = response_model.model_json_schema()
        schema_text = json.dumps(schema, indent=2, ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    f"{request.system_prompt}\n\n"
                    "Return exactly one JSON object with no Markdown fences or extra text. "
                    "The object must validate against this JSON Schema:\n"
                    f"{schema_text}"
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": request.user_prompt},
                    {"type": "image_url", "image_url": {"url": self._image_data_url(image_path)}},
                ],
            },
        ]
        content, call_count = self._request_content(
            messages=messages,
            temperature=request.temperature,
            response_model=response_model,
            schema=schema,
        )
        data = response_model.model_validate(json.loads(content))
        self.call_trace.append(
            LLMCallTrace(
                response_model=response_model.__name__,
                provider="openai_compatible",
                model=self.model,
                raw_responses=[content],
                call_count=call_count,
            )
        )
        return LLMResponse(
            data=data,
            raw_text=content,
            provider="openai_compatible",
            model=self.model,
            call_count=call_count,
        )

    def _image_data_url(self, image_path: Path) -> str:
        mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"
```

Change `_request_content` type annotation to accept both string and content-array messages:

```python
    def _request_content(
        self,
        messages: list[dict],
        temperature: float,
        response_model: type[T],
        schema: dict,
    ) -> tuple[str, int]:
```

- [ ] **Step 6: Implement `VisionTextExtractor`**

Modify `src/patchproof/tools/evidence.py`.

Add imports:

```python
from pydantic import BaseModel

from patchproof.errors import LLMProviderError
from patchproof.llm.base import LLMClient, LLMRequest
```

Add:

```python
class ExtractedImageText(BaseModel):
    extracted_text: str


class VisionTextExtractor:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def extract(self, image_path: Path) -> BugEvidenceSource:
        supports_images = bool(getattr(self.llm, "supports_images", False))
        generate_with_image = getattr(self.llm, "generate_structured_with_image", None)
        if not supports_images or generate_with_image is None:
            raise LLMProviderError(
                "The selected model/provider does not support image input. "
                "Use --bug-text or --bug-log instead."
            )

        response = generate_with_image(
            LLMRequest(
                system_prompt=(
                    "You are VisionTextExtractor for PatchProof. Extract only visible error text, "
                    "tracebacks, file paths, line numbers, and log messages from the image."
                ),
                user_prompt="Extract the raw visible bug/error text from this screenshot.",
            ),
            image_path,
            ExtractedImageText,
        )
        extracted_text = response.data.extracted_text
        return BugEvidenceSource(
            source_type=EvidenceSourceType.BUG_IMAGE,
            label=str(image_path),
            path=image_path,
            raw_text=extracted_text,
            extracted_text=extracted_text,
        )
```

- [ ] **Step 7: Run tests**

Run:

```powershell
pytest tests/unit/test_vision_evidence.py tests/unit/test_llm.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```powershell
git add -- src/patchproof/llm/base.py src/patchproof/llm/providers/openai_compatible.py src/patchproof/tools/evidence.py tests/unit/test_vision_evidence.py tests/unit/test_llm.py
git commit -m "feat: extract bug evidence from images"
```

---

### Task 4: Add Restricted Verification Command Parsing And Planning

**Files:**
- Modify: `src/patchproof/tools/command_runner.py`
- Create: `src/patchproof/tools/verification_planner.py`
- Test: `tests/unit/test_command_runner.py`
- Test: `tests/unit/test_verification_planner.py`

- [ ] **Step 1: Write failing command parser tests**

Append to `tests/unit/test_command_runner.py`:

```python
from patchproof.tools.command_runner import parse_verification_command


def test_parse_verification_command_allows_pytest_and_unittest():
    assert parse_verification_command("pytest tests/test_parser.py -q") == ["pytest", "tests/test_parser.py", "-q"]
    assert parse_verification_command("python -m pytest tests -q") == ["python", "-m", "pytest", "tests", "-q"]
    assert parse_verification_command("python -m unittest") == ["python", "-m", "unittest"]
    assert parse_verification_command("python -m unittest discover") == ["python", "-m", "unittest", "discover"]


def test_parse_verification_command_rejects_unsafe_commands():
    with pytest.raises(CommandValidationError):
        parse_verification_command("make deploy")

    with pytest.raises(CommandValidationError):
        parse_verification_command("npm run test")

    with pytest.raises(CommandValidationError):
        parse_verification_command("pytest -q && echo hacked")
```

- [ ] **Step 2: Write failing verification planner tests**

Create `tests/unit/test_verification_planner.py`:

```python
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
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
pytest tests/unit/test_command_runner.py tests/unit/test_verification_planner.py -q
```

Expected: FAIL because `parse_verification_command` and `VerificationPlanner` do not exist.

- [ ] **Step 4: Implement restricted verification parser**

Modify `src/patchproof/tools/command_runner.py`.

Add:

```python
def parse_verification_command(command: str) -> list[str]:
    for operator in _SHELL_OPERATORS:
        if operator in command:
            raise CommandValidationError(f"Shell operator is not allowed: {operator}")

    parts = shlex.split(command)
    if not parts:
        raise CommandValidationError("Verification command cannot be empty.")

    if parts[0] == "pytest":
        parse_pytest_command(command)
        return parts

    if len(parts) >= 3 and parts[0] == "python" and parts[1] == "-m" and parts[2] == "pytest":
        parse_pytest_command(command)
        return parts

    if parts == ["python", "-m", "unittest"] or parts == ["python", "-m", "unittest", "discover"]:
        return parts

    raise CommandValidationError("Only pytest, python -m pytest, and python -m unittest commands are allowed.")
```

- [ ] **Step 5: Implement verification planner**

Create `src/patchproof/tools/verification_planner.py`:

```python
from __future__ import annotations

from pathlib import Path

from patchproof.core.state import (
    BugEvidence,
    VerificationCommand,
    VerificationCommandSource,
    VerificationPlan,
)


class VerificationPlanner:
    def plan(
        self,
        project_path: Path,
        evidence: BugEvidence,
        changed_files: list[str],
        user_test_command: list[str],
        unsafe_candidates: list[list[str]] | None = None,
    ) -> VerificationPlan:
        skipped = [
            VerificationCommand(
                command=command,
                source=VerificationCommandSource.SKIPPED_UNSAFE,
                reason="Outside the v0.2 verification allowlist.",
            )
            for command in (unsafe_candidates or [])
        ]

        if user_test_command:
            return VerificationPlan(
                commands=[
                    VerificationCommand(
                        command=user_test_command,
                        source=VerificationCommandSource.USER_PROVIDED,
                        reason="User provided --test.",
                    )
                ],
                skipped_commands=skipped,
            )

        commands: list[VerificationCommand] = []
        commands.extend(self._traceback_entrypoint_commands(project_path, evidence))
        if not commands:
            commands.extend(self._matched_test_commands(project_path, evidence.suspected_files + changed_files))
        if not commands and self._has_pytest_suite(project_path):
            commands.append(
                VerificationCommand(
                    command=["pytest", "-q"],
                    source=VerificationCommandSource.DEFAULT_PYTEST,
                    reason="Project has a tests directory; using default pytest verification.",
                )
            )

        return VerificationPlan(commands=commands, skipped_commands=skipped)

    def _traceback_entrypoint_commands(self, project_path: Path, evidence: BugEvidence) -> list[VerificationCommand]:
        commands: list[VerificationCommand] = []
        for file_path in evidence.entrypoint_files:
            candidate = project_path / file_path
            if candidate.exists() and self._looks_like_test_file(candidate):
                commands.append(
                    VerificationCommand(
                        command=["pytest", file_path.replace("\\", "/"), "-q"],
                        source=VerificationCommandSource.TRACEBACK_ENTRYPOINT,
                        reason=f"Traceback includes test entrypoint {file_path}.",
                    )
                )
        return commands

    def _matched_test_commands(self, project_path: Path, source_files: list[str]) -> list[VerificationCommand]:
        tests_dir = project_path / "tests"
        if not tests_dir.exists():
            return []

        commands: list[VerificationCommand] = []
        seen: set[str] = set()
        for source_file in source_files:
            stem = Path(source_file).stem
            if not stem:
                continue
            patterns = [f"test_{stem}.py", f"*{stem}*.py"]
            for pattern in patterns:
                for test_file in sorted(tests_dir.rglob(pattern)):
                    relative = test_file.relative_to(project_path).as_posix()
                    if relative in seen or not self._looks_like_test_file(test_file):
                        continue
                    seen.add(relative)
                    commands.append(
                        VerificationCommand(
                            command=["pytest", relative, "-q"],
                            source=VerificationCommandSource.MATCHED_TEST,
                            reason=f"Matched source file {source_file} to test file {relative}.",
                        )
                    )
        return commands

    def _has_pytest_suite(self, project_path: Path) -> bool:
        tests_dir = project_path / "tests"
        return tests_dir.exists() and any(self._looks_like_test_file(path) for path in tests_dir.rglob("*.py"))

    def _looks_like_test_file(self, path: Path) -> bool:
        name = path.name
        return name.startswith("test_") or name.endswith("_test.py")
```

- [ ] **Step 6: Run tests**

Run:

```powershell
pytest tests/unit/test_command_runner.py tests/unit/test_verification_planner.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add -- src/patchproof/tools/command_runner.py src/patchproof/tools/verification_planner.py tests/unit/test_command_runner.py tests/unit/test_verification_planner.py
git commit -m "feat: plan restricted verification commands"
```

---

### Task 5: Update CLI For Evidence Inputs

**Files:**
- Modify: `src/patchproof/cli.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Replace `tests/integration/test_cli.py` with:

```python
from typer.testing import CliRunner

from patchproof.cli import app


def test_cli_requires_at_least_one_bug_input():
    runner = CliRunner()

    result = runner.invoke(app, ["run", "."])

    assert result.exit_code != 0
    assert "Provide at least one" in result.output


def test_cli_rejects_non_pytest_test_command():
    runner = CliRunner()

    result = runner.invoke(app, ["run", ".", "--test", "python cleanup.py"])

    assert result.exit_code != 0
    assert "Only pytest" in result.output or "Unsupported" in result.output


def test_cli_accepts_bug_text_without_test(monkeypatch):
    calls = []

    class FakeOrchestrator:
        def __init__(self, settings, llm) -> None:
            pass

        def run_evidence(self, **kwargs):
            calls.append(kwargs)

            class State:
                final_status = type("Status", (), {"value": "unverified"})()

            return State()

    monkeypatch.setattr("patchproof.cli.WorkflowOrchestrator", FakeOrchestrator)
    monkeypatch.setattr("patchproof.cli.create_llm_client", lambda settings: object())
    runner = CliRunner()

    result = runner.invoke(app, ["run", ".", "--bug-text", "ValueError: bad"])

    assert result.exit_code == 0
    assert calls[0]["bug_text"] == "ValueError: bad"
    assert calls[0]["test_command"] == []
```

- [ ] **Step 2: Run CLI tests and verify failure**

Run:

```powershell
pytest tests/integration/test_cli.py -q
```

Expected: FAIL because `--test` is still required and `run_evidence` is not called.

- [ ] **Step 3: Implement CLI options**

Modify `src/patchproof/cli.py`.

Change the Typer help text:

```python
app = typer.Typer(help="PatchProof: evidence-driven patch suggestions for Python bugs.")
```

Replace the `run` command with:

```python
@app.command()
def run(
    project_path: Path = typer.Argument(..., help="Path to a local Python project."),
    test: str | None = typer.Option(None, "--test", help="Restricted pytest command, such as 'pytest -q'."),
    bug_text: str | None = typer.Option(None, "--bug-text", help="Pasted traceback, error text, or log snippet."),
    bug_log: Path | None = typer.Option(None, "--bug-log", help="Path to a bug log file."),
    bug_image: Path | None = typer.Option(None, "--bug-image", help="Path to an error screenshot."),
) -> None:
    """Run PatchProof against bug evidence."""
    load_dotenv()
    try:
        if not any([test, bug_text, bug_log, bug_image]):
            raise CommandValidationError("Provide at least one of --test, --bug-text, --bug-log, or --bug-image.")
        command = parse_pytest_command(test) if test else []
        settings = Settings.from_env()
        llm = create_llm_client(settings)
        state = WorkflowOrchestrator(settings, llm).run_evidence(
            project_path=project_path.resolve(),
            test_command=command,
            bug_text=bug_text,
            bug_log=bug_log,
            bug_image=bug_image,
        )
    except (CommandValidationError, LLMProviderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]PatchProof finished with status:[/green] {state.final_status.value}")
    console.print("Reports written: report.md, report.json")
```

- [ ] **Step 4: Run CLI tests**

Run:

```powershell
pytest tests/integration/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add -- src/patchproof/cli.py tests/integration/test_cli.py
git commit -m "feat: accept bug evidence in CLI"
```

---

### Task 6: Make Investigator And Patcher Evidence-Aware

**Files:**
- Modify: `src/patchproof/agents/investigator.py`
- Modify: `src/patchproof/agents/patcher.py`
- Test: `tests/unit/test_agents.py`
- Test: `tests/unit/test_investigator_react.py`

- [ ] **Step 1: Write failing agent tests**

Append to `tests/unit/test_agents.py`:

```python
from patchproof.core.state import BugEvidence, BugEvidenceSource, EvidenceSourceType, TracebackSummary


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


def test_investigator_prompt_includes_bug_evidence():
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

    result = InvestigatorAgent(client, Settings()).run_with_evidence(sample_bug_evidence(), repository_context="parser.py")

    assert result.suspected_files == ["parser.py"]
    assert "Bug evidence:" in client.calls[0].user_prompt
    assert "ValueError in parser.py" in client.calls[0].user_prompt


def test_patch_agent_prompt_includes_bug_evidence():
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
        sample_bug_evidence(),
        code_context="def parse(value): return int(value)",
    )

    assert result.patch_diff.startswith("diff --git")
    assert "Bug evidence:" in client.calls[0].user_prompt
    assert "ValueError in parser.py" in client.calls[0].user_prompt
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
pytest tests/unit/test_agents.py -q
```

Expected: FAIL because `run_with_evidence` methods do not exist.

- [ ] **Step 3: Implement `InvestigatorAgent.run_with_evidence`**

Modify `src/patchproof/agents/investigator.py`.

Add import:

```python
from patchproof.core.state import BugEvidence
```

Add method before `run_with_tools`:

```python
    def run_with_evidence(self, evidence: BugEvidence, repository_context: str) -> InvestigationResult:
        user_prompt = f"""Bug evidence:
{evidence.model_dump()}
Repository context:
{repository_context}
Max hypotheses: {self.settings.max_hypotheses}
"""
        response = self.llm.generate_structured(
            LLMRequest(system_prompt=_SYSTEM_PROMPT, user_prompt=user_prompt),
            InvestigationResult,
        )
        return response.data
```

Change `run(...)` to build a minimal `BugEvidence` wrapper around the old baseline:

```python
    def run(self, baseline: TestRunResult, repository_context: str) -> InvestigationResult:
        evidence = BugEvidence(
            raw_text=baseline.traceback_text,
            summary=baseline.summary,
        )
        return self.run_with_evidence(evidence, repository_context)
```

Add `run_with_evidence_and_tools`:

```python
    def run_with_evidence_and_tools(
        self,
        evidence: BugEvidence,
        indexer: ProjectIndexer,
        context_tool: CodeContextTool,
    ) -> InvestigationResult:
        observations: list[str] = []
        trace: list[ToolTraceEntry] = []
        for _ in range(self.settings.max_investigation_tool_calls + 1):
            prompt = f"""Bug evidence:
{evidence.model_dump()}
Observations:
{chr(10).join(observations)}

{_STEP_INSTRUCTIONS}"""
            step_response = self.llm.generate_structured(
                LLMRequest(system_prompt=_SYSTEM_PROMPT, user_prompt=prompt),
                InvestigationStep,
            )
            step = step_response.data
            if step.action == "final":
                hypotheses = step.hypotheses[: self.settings.max_hypotheses]
                selected_index = min(step.selected_hypothesis_index, max(len(hypotheses) - 1, 0))
                return InvestigationResult(
                    suspected_files=step.suspected_files,
                    hypotheses=hypotheses,
                    selected_hypothesis_index=selected_index,
                    reasoning_summary=step.reasoning_summary,
                    tool_trace=trace,
                )

            observation = self._execute_read_only_action(step, indexer, context_tool)
            observations.append(observation)
            trace.append(
                ToolTraceEntry(
                    tool_name=step.action,
                    tool_input={
                        "query": step.query or "",
                        "file_path": step.file_path or "",
                        "line_number": step.line_number or 0,
                    },
                    observation=observation[:1000],
                )
            )

        return self.run_with_evidence(evidence, "\n".join(observations))
```

Change old `run_with_tools(...)` to delegate:

```python
    def run_with_tools(
        self,
        baseline: TestRunResult,
        indexer: ProjectIndexer,
        context_tool: CodeContextTool,
    ) -> InvestigationResult:
        evidence = BugEvidence(raw_text=baseline.traceback_text, summary=baseline.summary)
        return self.run_with_evidence_and_tools(evidence, indexer, context_tool)
```

- [ ] **Step 4: Implement `PatchAgent.run_with_evidence`**

Modify `src/patchproof/agents/patcher.py`.

Add import:

```python
from patchproof.core.state import BugEvidence
```

Add method:

```python
    def run_with_evidence(
        self,
        investigation: InvestigationResult,
        evidence: BugEvidence,
        code_context: str,
        previous_patch: str = "",
        feedback: str = "",
    ) -> AttemptResult:
        user_prompt = f"""Investigation: {investigation.model_dump()}
Bug evidence: {evidence.model_dump()}
Code context:
{code_context}
Previous patch:
{previous_patch or "None"}
Feedback from the previous attempt:
{feedback or "None"}

Generate a complete replacement patch against the original code context.
"""
        response = self.llm.generate_structured(
            LLMRequest(system_prompt=_SYSTEM_PROMPT, user_prompt=user_prompt),
            PatchGeneration,
        )
        patch = response.data
        return AttemptResult(
            patch_diff=patch.unified_diff,
            patch_explanation=patch.explanation,
        )
```

Change old `run(...)` to build a baseline evidence wrapper:

```python
    def run(
        self,
        investigation: InvestigationResult,
        baseline: TestRunResult,
        code_context: str,
        previous_patch: str = "",
        feedback: str = "",
    ) -> AttemptResult:
        evidence = BugEvidence(raw_text=baseline.traceback_text, summary=baseline.summary)
        return self.run_with_evidence(
            investigation,
            evidence,
            code_context,
            previous_patch=previous_patch,
            feedback=feedback,
        )
```

- [ ] **Step 5: Run agent tests**

Run:

```powershell
pytest tests/unit/test_agents.py tests/unit/test_investigator_react.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add -- src/patchproof/agents/investigator.py src/patchproof/agents/patcher.py tests/unit/test_agents.py tests/unit/test_investigator_react.py
git commit -m "feat: make agents use bug evidence"
```

---

### Task 7: Add Evidence-Driven Orchestrator Flow

**Files:**
- Modify: `src/patchproof/core/orchestrator.py`
- Test: `tests/integration/test_orchestrator_happy_path.py`
- Test: `tests/integration/test_orchestrator_retries.py`
- Test: `tests/integration/test_orchestrator_evidence.py`

- [ ] **Step 1: Write failing evidence orchestrator tests**

Create `tests/integration/test_orchestrator_evidence.py`:

```python
import json
from pathlib import Path

from patchproof.core.config import Settings
from patchproof.core.orchestrator import WorkflowOrchestrator
from patchproof.core.state import FinalStatus, VerificationStatus
from patchproof.llm.base import FakeLLMClient


VALID_PATCH = (
    "diff --git a/parser.py b/parser.py\n"
    "--- a/parser.py\n"
    "+++ b/parser.py\n"
    "@@ -1,2 +1,2 @@\n"
    " def parse_count(value):\n"
    "-    return value\n"
    "+    return int(value)\n"
)


def create_parser_project(tmp_path: Path) -> Path:
    project = tmp_path / "parser_project"
    (project / "src").mkdir(parents=True)
    (project / "tests").mkdir()
    (project / "src" / "parser.py").write_text("def parse_count(value):\n    return value\n", encoding="utf-8")
    (project / "tests" / "test_parser.py").write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))\n"
        "from parser import parse_count\n\n"
        "def test_parse_count():\n"
        "    assert parse_count('3') == 3\n",
        encoding="utf-8",
    )
    return project


def fake_success_llm():
    return FakeLLMClient(
        [
            {"action": "read_code_context", "file_path": "src/parser.py", "line_number": 2},
            {
                "action": "final",
                "suspected_files": ["src/parser.py"],
                "hypotheses": [
                    {
                        "description": "parse_count returns a string instead of an int",
                        "evidence": "Bug evidence and code point to src/parser.py",
                        "confidence": 0.95,
                    }
                ],
                "selected_hypothesis_index": 0,
                "reasoning_summary": "The parser does not convert the value.",
            },
            {"unified_diff": VALID_PATCH, "explanation": "Convert the input to int."},
            {"decision": "approved", "semantic_risks": [], "review_summary": "Minimal source fix."},
            {
                "bug_explanation": "The parser returned the raw string.",
                "evidence_walkthrough": "The evidence pointed to parse_count.",
                "patch_explanation": "The patch converts to int.",
                "verification_explanation": "The selected verification command passed.",
                "learning_points": ["Verify behavior through a test entrypoint."],
            },
        ]
    )


def test_bug_text_without_user_test_uses_matched_test(tmp_path: Path, monkeypatch):
    project = create_parser_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    bug_text = '''
Traceback (most recent call last):
  File "src/parser.py", line 2, in parse_count
AssertionError: expected int
'''

    state = WorkflowOrchestrator(Settings(), fake_success_llm()).run_evidence(
        project_path=project,
        test_command=[],
        bug_text=bug_text,
        bug_log=None,
        bug_image=None,
    )

    assert state.final_status == FinalStatus.VERIFIED
    assert state.bug_evidence is not None
    assert state.verification_plan is not None
    assert state.verification_plan.commands[0].command == ["pytest", "tests/test_parser.py", "-q"]
    assert state.attempts[0].verification_status == VerificationStatus.VERIFIED
    assert "return value" in (project / "src" / "parser.py").read_text(encoding="utf-8")


def test_bug_log_with_user_test_uses_user_test(tmp_path: Path, monkeypatch):
    project = create_parser_project(tmp_path)
    log_path = tmp_path / "error.log"
    log_path.write_text("ERROR src/parser.py:2 AssertionError: expected int", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    state = WorkflowOrchestrator(Settings(), fake_success_llm()).run_evidence(
        project_path=project,
        test_command=["pytest", "-q"],
        bug_text=None,
        bug_log=log_path,
        bug_image=None,
    )

    assert state.final_status == FinalStatus.VERIFIED
    assert state.verification_plan is not None
    assert state.verification_plan.commands[0].command == ["pytest", "-q"]


def test_bug_image_flows_through_fake_vision(tmp_path: Path, monkeypatch):
    project = create_parser_project(tmp_path)
    image_path = tmp_path / "error.png"
    image_path.write_bytes(b"fake image")
    monkeypatch.chdir(tmp_path)
    llm = FakeLLMClient(
        responses=fake_success_llm().responses,
        image_responses=[{"extracted_text": "ERROR src/parser.py:2 AssertionError: expected int"}],
    )

    state = WorkflowOrchestrator(Settings(), llm).run_evidence(
        project_path=project,
        test_command=[],
        bug_text=None,
        bug_log=None,
        bug_image=image_path,
    )

    assert state.final_status == FinalStatus.VERIFIED
    assert state.bug_evidence is not None
    assert state.bug_evidence.sources[0].extracted_text.startswith("ERROR src/parser.py")
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["bug_evidence"]["sources"][0]["source_type"] == "bug_image"
```

- [ ] **Step 2: Run integration tests and verify failure**

Run:

```powershell
pytest tests/integration/test_orchestrator_evidence.py -q
```

Expected: FAIL because `WorkflowOrchestrator.run_evidence` does not exist.

- [ ] **Step 3: Add evidence collection helpers to orchestrator**

Modify `src/patchproof/core/orchestrator.py`.

Add imports:

```python
from patchproof.core.state import BugEvidence, VerificationCommand, VerificationPlan
from patchproof.tools.evidence import (
    BugEvidenceBuilder,
    EvidenceInput,
    LogFileEvidenceReader,
    TextEvidenceReader,
    VisionTextExtractor,
)
from patchproof.tools.verification_planner import VerificationPlanner
```

Add method:

```python
    def _collect_evidence_sources(
        self,
        baseline: TestRunResult | None,
        bug_text: str | None,
        bug_log: Path | None,
        bug_image: Path | None,
    ):
        sources = []
        if baseline is not None and baseline.status != TestRunStatus.PASSED:
            sources.append(EvidenceInput.from_test_result(baseline))
        if bug_text:
            sources.append(TextEvidenceReader().read("pasted bug text", bug_text))
        if bug_log:
            sources.append(LogFileEvidenceReader().read(bug_log))
        if bug_image:
            sources.append(VisionTextExtractor(self.llm).extract(bug_image))
        return sources
```

- [ ] **Step 4: Implement `run_evidence`**

Add this method to `WorkflowOrchestrator` and keep existing helper methods:

```python
    def run_evidence(
        self,
        project_path: Path,
        test_command: list[str],
        bug_text: str | None,
        bug_log: Path | None,
        bug_image: Path | None,
    ) -> RunState:
        state = RunState(project_path=project_path, test_command=test_command)
        baseline: TestRunResult | None = None
        if test_command:
            baseline = self._run_tests(project_path, test_command)
            state.baseline_test_result = baseline
            state.traceback_summary = TracebackParser().parse(baseline.stdout + "\n" + baseline.stderr)

        sources = self._collect_evidence_sources(baseline, bug_text, bug_log, bug_image)
        if not sources and baseline is not None and baseline.status == TestRunStatus.PASSED:
            state.final_status = FinalStatus.NOT_REPRODUCED
            state.stop_reason = "Baseline tests passed; failure was not reproduced."
            return self._write_reports(state)
        if not sources:
            state.final_status = FinalStatus.STOPPED
            state.stop_reason = "No bug evidence was available for investigation."
            return self._write_reports(state)

        evidence = BugEvidenceBuilder().build(sources)
        state.bug_evidence = evidence
        state.traceback_summary = evidence.traceback_summary

        if baseline is not None and baseline.status in {TestRunStatus.COMMAND_ERROR, TestRunStatus.TIMEOUT} and not evidence.raw_text:
            state.final_status = FinalStatus.STOPPED
            state.stop_reason = "Baseline test command failed before usable bug evidence was available."
            return self._write_reports(state)

        indexer = ProjectIndexer(project_path)
        context_tool = CodeContextTool(project_path)
        investigation = InvestigatorAgent(self.llm, self.settings).run_with_evidence_and_tools(
            evidence=evidence,
            indexer=indexer,
            context_tool=context_tool,
        )
        state.investigation = investigation

        repository_context = self._build_repository_context(project_path)
        previous_patch = ""
        feedback = ""

        for attempt_number in range(1, self.settings.max_patch_attempts + 1):
            attempt = PatchAgent(self.llm).run_with_evidence(
                investigation,
                evidence,
                repository_context,
                previous_patch=previous_patch,
                feedback=feedback,
            )
            attempt.diff_metadata = DiffParser(self.settings).parse(attempt.patch_diff)

            review = ReviewerAgent(self.llm).run(investigation, attempt.patch_diff, attempt.diff_metadata)
            attempt.review_decision = review.decision
            attempt.review_summary = review.review_summary
            attempt.semantic_risks = review.semantic_risks

            if review.decision == ReviewDecision.REJECTED:
                state.attempts.append(attempt)
                previous_patch = attempt.patch_diff
                feedback = self._review_feedback(attempt)
                continue

            with TempWorkspace(project_path) as copied_project:
                apply_result = PatchApplier().apply(copied_project, attempt.patch_diff)
                if not apply_result.applied:
                    attempt.verification_status = VerificationStatus.PATCH_FAILED
                    attempt.patch_apply_error = apply_result.stderr
                    state.attempts.append(attempt)
                    previous_patch = attempt.patch_diff
                    feedback = self._patch_apply_feedback(attempt)
                    continue

                changed_files = attempt.diff_metadata.changed_files if attempt.diff_metadata else []
                plan = VerificationPlanner().plan(
                    copied_project,
                    evidence,
                    changed_files=changed_files,
                    user_test_command=test_command,
                )
                state.verification_plan = plan

                if not plan.commands:
                    attempt.verification_status = VerificationStatus.NOT_RUN
                    state.attempts.append(attempt)
                    state.final_status = FinalStatus.UNVERIFIED
                    state.stop_reason = "Patch applied, but no allowed behavioral verification command was available."
                    break

                command = plan.commands[0]
                attempt.verification_command = command
                verification = self._run_tests(copied_project, command.command)
                attempt.verification_result = verification

            state.attempts.append(attempt)
            if verification.status == TestRunStatus.PASSED:
                attempt.verification_status = VerificationStatus.VERIFIED
                state.final_status = FinalStatus.VERIFIED
                state.stop_reason = f"Patch verified with: {' '.join(command.command)}"
                break
            if verification.status == TestRunStatus.TIMEOUT:
                attempt.verification_status = VerificationStatus.TIMEOUT
                state.final_status = FinalStatus.UNVERIFIED
                state.stop_reason = "Verification timed out in the temporary workspace."
                break

            attempt.verification_status = VerificationStatus.TESTS_FAILED
            previous_patch = attempt.patch_diff
            feedback = self._verification_feedback(attempt)
            evidence = BugEvidenceBuilder().build(sources + [EvidenceInput.from_test_result(verification)])
            state.bug_evidence = evidence
            if attempt_number < self.settings.max_patch_attempts:
                investigation = InvestigatorAgent(self.llm, self.settings).run_with_evidence_and_tools(
                    evidence=evidence,
                    indexer=indexer,
                    context_tool=context_tool,
                )
                state.investigation = investigation

        if state.final_status == FinalStatus.CREATED:
            state.final_status = FinalStatus.UNVERIFIED
            state.stop_reason = (
                f"Stopped after reaching the maximum patch attempts: {self.settings.max_patch_attempts}."
            )

        return self._explain_and_write(state)
```

- [ ] **Step 5: Route old `run(...)` through the new method**

Replace the old `run(...)` body with:

```python
    def run(self, project_path: Path, test_command: list[str]) -> RunState:
        return self.run_evidence(
            project_path=project_path,
            test_command=test_command,
            bug_text=None,
            bug_log=None,
            bug_image=None,
        )
```

- [ ] **Step 6: Update retry test prompt assertions**

In `tests/integration/test_orchestrator_retries.py`, change:

```python
investigation_prompts = [call.user_prompt for call in fake_llm.calls if call.user_prompt.startswith("Baseline:")]
```

to:

```python
investigation_prompts = [call.user_prompt for call in fake_llm.calls if call.user_prompt.startswith("Bug evidence:")]
```

Change patch prompt filtering:

```python
patch_prompts = [call.user_prompt for call in fake_llm.calls if "Code context:" in call.user_prompt]
```

to keep working, because evidence-first patch prompts still contain `Code context:`.

- [ ] **Step 7: Run orchestrator tests**

Run:

```powershell
pytest tests/integration/test_orchestrator_evidence.py tests/integration/test_orchestrator_happy_path.py tests/integration/test_orchestrator_retries.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```powershell
git add -- src/patchproof/core/orchestrator.py tests/integration/test_orchestrator_evidence.py tests/integration/test_orchestrator_happy_path.py tests/integration/test_orchestrator_retries.py
git commit -m "feat: orchestrate evidence-driven repairs"
```

---

### Task 8: Update Reports For Evidence And Verification Plans

**Files:**
- Modify: `src/patchproof/reporting/markdown.py`
- Test: `tests/unit/test_reporting.py`

- [ ] **Step 1: Write failing report tests**

Append to `tests/unit/test_reporting.py`:

```python
from patchproof.core.state import (
    BugEvidence,
    BugEvidenceSource,
    EvidenceSourceType,
    TracebackFrame,
    TracebackSummary,
    VerificationCommand,
    VerificationCommandSource,
    VerificationPlan,
)


def test_markdown_report_includes_bug_evidence_and_verification_plan():
    state = RunState(
        project_path=Path("demo"),
        bug_evidence=BugEvidence(
            sources=[
                BugEvidenceSource(
                    source_type=EvidenceSourceType.BUG_IMAGE,
                    label="error.png",
                    raw_text="ValueError: bad",
                    extracted_text="ValueError: bad",
                )
            ],
            raw_text="ValueError: bad",
            traceback_summary=TracebackSummary(
                exception_type="ValueError",
                frames=[TracebackFrame(file_path="src/parser.py", line_number=2, function_name="parse")],
            ),
            suspected_files=["src/parser.py"],
            summary="ValueError in src/parser.py",
        ),
        verification_plan=VerificationPlan(
            commands=[
                VerificationCommand(
                    command=["pytest", "tests/test_parser.py", "-q"],
                    source=VerificationCommandSource.MATCHED_TEST,
                    reason="Matched parser.py.",
                )
            ],
            skipped_commands=[
                VerificationCommand(
                    command=["make", "deploy"],
                    source=VerificationCommandSource.SKIPPED_UNSAFE,
                    reason="Outside allowlist.",
                )
            ],
        ),
    )

    markdown = render_markdown_report(state)

    assert "## Bug Evidence" in markdown
    assert "bug_image" in markdown
    assert "ValueError: bad" in markdown
    assert "src/parser.py:2" in markdown
    assert "## Verification Plan" in markdown
    assert "pytest tests/test_parser.py -q" in markdown
    assert "Skipped" in markdown
    assert "make deploy" in markdown
```

- [ ] **Step 2: Run report tests and verify failure**

Run:

```powershell
pytest tests/unit/test_reporting.py -q
```

Expected: FAIL because reports do not render evidence or verification plans.

- [ ] **Step 3: Implement markdown sections**

Modify `src/patchproof/reporting/markdown.py`.

Change the test command line to avoid rendering an empty command as blank:

```python
        f"- Test command: `{' '.join(state.test_command) if state.test_command else 'not provided'}`",
```

Add this block after the baseline section and before investigation:

```python
    if state.bug_evidence is not None:
        lines.extend(["", "## Bug Evidence", ""])
        lines.append(f"- Summary: {state.bug_evidence.summary}")
        lines.append(f"- Suspected files: {', '.join(state.bug_evidence.suspected_files) or 'none'}")
        lines.append(f"- Entrypoint files: {', '.join(state.bug_evidence.entrypoint_files) or 'none'}")
        for source in state.bug_evidence.sources:
            lines.append(f"- Source `{source.source_type.value}`: {source.label}")
            if source.extracted_text:
                lines.extend(["", "Extracted text:", "", "```text", source.extracted_text.strip(), "```"])
        if state.bug_evidence.traceback_summary.frames:
            lines.extend(["", "Parsed frames:"])
            for frame in state.bug_evidence.traceback_summary.frames:
                function_name = f" in {frame.function_name}" if frame.function_name else ""
                lines.append(f"- `{frame.file_path}:{frame.line_number}{function_name}`")
```

Add this block before attempts:

```python
    if state.verification_plan is not None:
        lines.extend(["", "## Verification Plan", ""])
        if state.verification_plan.commands:
            lines.append("Attempted candidates:")
            for command in state.verification_plan.commands:
                lines.append(f"- `{' '.join(command.command)}` ({command.source.value}): {command.reason}")
        if state.verification_plan.skipped_commands:
            lines.append("Skipped candidates:")
            for command in state.verification_plan.skipped_commands:
                lines.append(f"- `{' '.join(command.command)}` ({command.source.value}): {command.reason}")
```

Inside the attempts loop, after verification status, add:

```python
            if attempt.verification_command is not None:
                lines.append(f"- Verification command: `{' '.join(attempt.verification_command.command)}`")
```

- [ ] **Step 4: Run report tests**

Run:

```powershell
pytest tests/unit/test_reporting.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add -- src/patchproof/reporting/markdown.py tests/unit/test_reporting.py
git commit -m "feat: report bug evidence and verification plans"
```

---

### Task 9: Update Documentation For v0.2 Behavior

**Files:**
- Modify: `README.md`
- Test: `README.md` manual review

- [ ] **Step 1: Update README usage section**

Modify `README.md` to include:

````markdown
## v0.2 Evidence Inputs

PatchProof can now start from several forms of bug evidence:

```powershell
patchproof run ./project --test "pytest -q"
patchproof run ./project --bug-text "Traceback ..."
patchproof run ./project --bug-log .\error.log
patchproof run ./project --bug-image .\error.png
patchproof run ./project --bug-log .\error.log --test "pytest -q"
```

All text-like inputs go through deterministic traceback/log parsing before agent reasoning. Screenshot input is handled as:

```text
image -> vision text extraction -> traceback/log parsing -> BugEvidence
```

## Verification Boundaries

When `--test` is provided, PatchProof uses it as the most trusted verification command.

When `--test` is not provided, PatchProof only runs restricted Python verification commands:

```text
pytest <test-file-or-dir> -q
python -m pytest <test-file-or-dir> -q
python -m unittest
python -m unittest discover
```

PatchProof v0.2 does not automatically execute `make`, `npm run`, deployment commands, install commands, migrations, network commands, or arbitrary shell commands. Those may be recorded as skipped candidates in the report, but they are not run.

Reports distinguish `verified`, `not_reproduced`, `unverified`, and `stopped`.
````

- [ ] **Step 2: Run README grep check**

Run:

```powershell
rg "v0.2 Evidence Inputs|Verification Boundaries|bug-image" README.md
```

Expected: all three phrases are found.

- [ ] **Step 3: Commit**

Run:

```powershell
git add -- README.md
git commit -m "docs: document v0.2 evidence workflow"
```

---

### Task 10: Full Regression Verification And Cleanup

**Files:**
- Modify only if tests expose small integration mismatches.

- [ ] **Step 1: Run unit tests**

Run:

```powershell
pytest tests/unit -q
```

Expected: PASS.

- [ ] **Step 2: Run integration tests**

Run:

```powershell
pytest tests/integration -q
```

Expected: PASS.

- [ ] **Step 3: Run full suite**

Run:

```powershell
pytest -q
```

Expected: PASS. Existing v0.1 tests should still pass, with expected status value changes updated to v0.2's `verified`.

- [ ] **Step 4: Try local CLI validation**

Run:

```powershell
patchproof run . --bug-text "ValueError: sample"
```

Expected: The command reaches LLM provider setup or produces an actionable provider configuration error. It must not fail because `--test` is missing.

- [ ] **Step 5: Check worktree**

Run:

```powershell
git status --short
```

Expected: no uncommitted implementation files from v0.2 tasks. If unrelated files are dirty before execution begins, leave them alone and mention them in the handoff.

---

## Self-Review

### Spec Coverage

- Multiple evidence inputs are covered by Tasks 2, 3, 5, and 7.
- Deterministic traceback/log parsing before agent reasoning is covered by Tasks 2 and 7.
- Screenshot input uses vision text extraction before parsing in Tasks 3 and 7.
- `BugEvidence` state and prompt flow are covered by Tasks 1, 2, 6, and 7.
- User-provided `--test` remains highest priority in Tasks 4 and 7.
- Restricted automatic Python verification is covered by Task 4 and exercised in Task 7.
- Unsafe command skipping is covered by Task 4 and reporting in Task 8.
- Reports distinguish verified and unverified outcomes in Tasks 1, 7, and 8.
- v0.1 compatibility path is preserved by Task 7 and regression checked in Task 10.

### Placeholder Scan

This plan contains no unresolved `TBD`, `TODO`, or "implement later" instructions. Each implementation task includes exact file paths, test commands, expected outcomes, and concrete code snippets for the new interfaces.

### Type Consistency

The plan consistently uses:

- `BugEvidence`
- `BugEvidenceSource`
- `EvidenceSourceType`
- `LogSignal`
- `VerificationCommand`
- `VerificationCommandSource`
- `VerificationPlan`
- `VisionTextExtractor`
- `BugEvidenceBuilder`
- `VerificationPlanner`
- `WorkflowOrchestrator.run_evidence(...)`
- `InvestigatorAgent.run_with_evidence(...)`
- `InvestigatorAgent.run_with_evidence_and_tools(...)`
- `PatchAgent.run_with_evidence(...)`

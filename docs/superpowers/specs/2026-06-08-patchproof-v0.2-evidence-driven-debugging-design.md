# PatchProof v0.2 Evidence-Driven Debugging Design

Date: 2026-06-08
Branch: patchproof-v0.2

## Goal

PatchProof v0.2 upgrades the v0.1 pytest-driven workflow into an evidence-driven bug fixing workflow.

v0.1 assumes the user provides a pytest command and the failing test output is the primary bug evidence. v0.2 should accept bug evidence in the forms real users are likely to provide: pasted error text, log files, screenshots, and optional test commands.

The product goal is not yet to run arbitrary project commands. The v0.2 goal is:

1. Accept multiple bug evidence inputs.
2. Normalize all evidence into structured `BugEvidence`.
3. Use deterministic traceback/log parsing before agent reasoning.
4. Let the investigator and patcher work from `BugEvidence`, not only pytest output.
5. Verify patches with user-provided commands or a restricted allowlist of automatically discovered Python test commands.
6. Clearly report when a patch is verified, not reproduced, or only suggested without behavioral verification.

## Non-Goals

v0.2 will not execute arbitrary shell commands such as `make deploy`, `npm run ...`, project-defined scripts, or unknown commands discovered in CI or package files.

Those commands are deferred to a later version. Before implementing that capability, PatchProof should study how tools like Codex and Claude Code handle command approval, dangerous command detection, working-directory boundaries, network access, secrets, destructive filesystem operations, long-running processes, and user-visible permission prompts.

v0.2 also does not aim to support every programming language. The existing project is Python-first, so v0.2 should keep verification and traceback parsing focused on Python projects.

## CLI Shape

The existing command remains valid:

```powershell
patchproof run ./project --test "pytest -q"
```

v0.2 adds evidence inputs:

```powershell
patchproof run ./project --bug-text "Traceback ..."
patchproof run ./project --bug-log .\error.log
patchproof run ./project --bug-image .\error.png
patchproof run ./project --bug-log .\error.log --test "pytest -q"
patchproof run ./project --bug-image .\error.png --test "pytest -q"
```

Input validation:

1. At least one of `--test`, `--bug-text`, `--bug-log`, or `--bug-image` is required.
2. Multiple evidence sources may be provided in one run.
3. `--test` remains the most trusted verification command when provided.
4. If `--bug-image` is provided but the selected model does not support image input, PatchProof fails early with an actionable message telling the user to use `--bug-text` or `--bug-log`.

## Evidence Pipeline

All bug inputs flow through the same evidence pipeline:

```text
bug-text
-> TextEvidenceReader
-> TracebackParser / LogParser
-> BugEvidenceBuilder
-> BugEvidence

bug-log
-> LogFileEvidenceReader
-> TracebackParser / LogParser
-> BugEvidenceBuilder
-> BugEvidence

bug-image
-> VisionTextExtractor
-> TracebackParser / LogParser
-> BugEvidenceBuilder
-> BugEvidence

test output
-> TracebackParser / LogParser
-> BugEvidenceBuilder
-> BugEvidence
```

`VisionTextExtractor` should only extract raw visible error text from the screenshot. It should not directly produce final `BugEvidence`. The extracted text must still go through `TracebackParser` and `LogParser`.

This keeps the pipeline auditable: deterministic parsers identify files, line numbers, exception types, stack frames, and log signals before the LLM reasons about the code.

## Data Model

Add bug evidence models near the existing state models.

Suggested shape:

```python
class EvidenceSourceType(str, Enum):
    TEST_OUTPUT = "test_output"
    BUG_TEXT = "bug_text"
    BUG_LOG = "bug_log"
    BUG_IMAGE = "bug_image"


class BugEvidenceSource(BaseModel):
    source_type: EvidenceSourceType
    label: str
    path: Path | None = None
    raw_text: str


class LogSignal(BaseModel):
    level: str | None = None
    message: str
    file_path: str | None = None
    line_number: int | None = None


class BugEvidence(BaseModel):
    sources: list[BugEvidenceSource]
    raw_text: str
    traceback_summary: TracebackSummary
    log_signals: list[LogSignal] = []
    suspected_files: list[str] = []
    entrypoint_files: list[str] = []
    summary: str
```

`TracebackSummary` can remain the shared traceback representation. It should be reused for pytest output, pasted text, logs, and text extracted from screenshots.

`entrypoint_files` represent files near the top of the stack that may be runnable reproduction entrypoints, such as tests, examples, or scripts. `suspected_files` represent source files likely to contain the root cause.

## Orchestrator Flow

The orchestrator should support both the v0.1 path and the new evidence-driven path.

High-level flow:

```text
1. Collect input evidence.
2. If --test is present, run baseline test command.
3. Parse all text outputs into BugEvidence.
4. If no bug evidence exists and baseline test passes, stop as not_reproduced.
5. Run InvestigatorAgent with BugEvidence.
6. Run PatchAgent with BugEvidence, investigation, and code context.
7. Run ReviewerAgent.
8. Apply patch in a temporary workspace.
9. Plan verification.
10. Run allowed verification commands.
11. Write report.
```

If `--test` is present and fails, its output becomes one evidence source. If `--test` is present and passes but the user also supplied bug evidence, PatchProof may still investigate from the supplied evidence, but the final report cannot claim the user-provided test reproduced the issue.

If no `--test` is present, PatchProof can still investigate and produce a patch. The final status depends on whether the restricted verification planner finds and passes a relevant command.

## Agent Prompt Changes

`InvestigatorAgent` should receive `BugEvidence` instead of relying only on `TestRunResult`.

The investigator prompt should include:

1. Evidence sources and labels.
2. Parsed exception type and message.
3. Stack frames.
4. Entrypoint files.
5. Suspected source files.
6. Log signals.
7. Any baseline test result if available.

`PatchAgent` should also receive `BugEvidence`. It should explain how the patch addresses the parsed failure and avoid making changes that only silence tests without fixing the root cause.

The retry loop remains similar to v0.1:

1. Patch apply failure goes back to `PatchAgent` with apply feedback.
2. Verification failure goes back to `InvestigatorAgent` with the failed verification output.

## Verification Planner

The v0.2 verification planner is restricted by design.

Priority order:

1. Use the user-provided `--test` command when present.
2. If traceback includes a test file entrypoint, run that specific test file with pytest.
3. If modified or suspected source files have obvious matching tests, run those tests with pytest.
4. If the project has a Python test suite, run a default Python test command.
5. If no behavioral verification command is available, only check patch application and optionally Python syntax for changed files.

Allowed commands in v0.2:

```text
pytest <test-file-or-dir> -q
python -m pytest <test-file-or-dir> -q
python -m unittest
python -m unittest discover
```

Commands outside the allowlist are not executed automatically in v0.2. They may be recorded as skipped candidates in the report.

The planner should treat source files and tests differently:

1. Source files are likely places to patch.
2. Test files, examples, and scripts may be reproduction entrypoints.
3. The agent should test behavior through a relevant entrypoint, not simply run the modified source file.

## Matching Source Files To Tests

The first version of test matching should be simple and deterministic.

Examples:

```text
src/patchproof/tools/traceback_parser.py
-> tests/**/test_traceback_parser.py
-> tests/**/test_tools.py
-> tests/**/*traceback*.py

src/patchproof/core/orchestrator.py
-> tests/**/test_orchestrator.py
-> tests/**/*orchestrator*.py
```

If multiple tests match, run the most specific candidates first. If they fail after the patch, the failure output becomes new evidence for the retry loop.

## Statuses And Reporting

The report should clearly distinguish:

1. `verified`: patch applied and an allowed verification command passed.
2. `not_reproduced`: the provided test command passed before any patch and no other bug evidence justified a repair.
3. `unverified`: patch was generated and applied in a temporary workspace, but no behavioral verification command passed or was available.
4. `stopped`: the workflow stopped because evidence was insufficient, the patch was rejected, the command was unsafe, or retry limits were reached.

The report should include:

1. Evidence sources.
2. Extracted text for image evidence.
3. Parsed traceback frames and exception.
4. Suspected files and entrypoint files.
5. Verification commands attempted.
6. Verification commands skipped because they were outside the v0.2 allowlist.
7. Final status and reason.

Reports must not imply a patch is fixed when only patch application or syntax checks passed.

## Safety Rules

v0.2 automatic verification must be conservative.

1. Do not execute unknown commands from `Makefile`, `package.json`, CI config, README, comments, or model output.
2. Do not run deploy, publish, install, migration, delete, network, or arbitrary shell commands.
3. Run verification only inside the temporary patched workspace.
4. Keep timeouts bounded.
5. Preserve the v0.1 behavior of never modifying the user's original project directly during patch attempts.

## Tests

Add unit tests for:

1. CLI validation requiring at least one evidence input.
2. `--bug-text` evidence collection.
3. `--bug-log` evidence collection.
4. `--bug-image` unsupported-model failure.
5. Vision text extraction using a fake model client.
6. Traceback parsing from pasted text, logs, and image-extracted text.
7. `BugEvidenceBuilder` merging multiple evidence sources.
8. Verification planner choosing a user-provided `--test`.
9. Verification planner choosing a traceback test entrypoint.
10. Verification planner matching source files to tests.
11. Verification planner skipping unsafe commands.

Add integration tests for:

1. `--test` only preserves v0.1 behavior.
2. `--bug-text` without `--test` can generate an unverified patch.
3. `--bug-log --test` can verify a patch.
4. `--bug-image` can flow through fake vision extraction into traceback parsing.
5. Verification failure is routed back to the investigator as retry evidence.

## Acceptance Criteria

v0.2 is complete when:

1. Existing v0.1 tests still pass.
2. The CLI accepts text, log, image, and test evidence inputs.
3. All evidence types produce structured `BugEvidence`.
4. Image input is parsed as text first, then traceback/log parsed.
5. Investigator and patcher use `BugEvidence`.
6. Verification uses `--test` first, then restricted automatic Python verification.
7. Unsafe discovered commands are skipped and reported.
8. Final reports distinguish verified patches from unverified suggestions.

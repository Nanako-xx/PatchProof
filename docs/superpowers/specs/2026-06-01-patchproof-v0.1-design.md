# PatchProof v0.1 Design

## Summary

PatchProof is a Python CLI debugging agent for verified fix suggestions. It reproduces a pytest failure, investigates the repository with a bounded read-only agent loop, generates a patch, reviews it independently, applies it only inside a clean temporary copy, reruns the original test command, and produces an auditable report.

The original project is never modified. A successful result means only that the proposed patch was verified against the user-provided pytest command. It does not claim that the code is universally correct.

## Goals

- Build an understandable multi-agent system without hiding orchestration behind a framework.
- Generate fix suggestions as unified diff patches instead of editing the user's project.
- Verify approved patches in isolated temporary copies.
- Keep deterministic work in tested tools and reserve LLM calls for reasoning.
- Produce both machine-readable and human-readable reports.
- Explain the debugging process in language suitable for a beginner.
- Keep the LLM provider replaceable so later versions can use DeepSeek, Claude, GPT, Qwen, or other models.

## Non-Goals

PatchProof v0.1 will not:

- edit the original project;
- generate new tests automatically;
- accept arbitrary shell commands;
- support languages other than Python;
- support test runners other than pytest;
- run agents in parallel;
- retry failed fix attempts automatically;
- use LangGraph;
- include a web UI.

## User Interface

The CLI accepts a local Python project path and a restricted pytest command:

```bash
patchproof run ./demo_project --test "pytest -q"
```

Allowed command forms:

```text
pytest [allowed arguments]
python -m pytest [allowed arguments]
```

Arguments are parsed without `shell=True`. Pipelines, redirects, command chaining, and unsupported arguments are rejected before execution.

Each run produces:

```text
report.md
report.json
```

The Markdown report is intended for developers and demonstrations. The JSON report supports automated tests and future interfaces.

## Architecture

PatchProof v0.1 uses one deterministic workflow orchestrator, three specialist sub-agents, one explanation component, and eight deterministic tools.

```text
CLI
  -> WorkflowOrchestrator
      -> baseline pytest tools
      -> InvestigatorAgent
      -> PatchAgent
      -> patch safety tools
      -> ReviewerAgent
      -> temporary verification tools
      -> CoachExplainer
      -> Reporter
```

The orchestrator is a Python state machine, not an LLM agent. This guarantees that required gates cannot be skipped. The agents communicate through Pydantic models rather than free-form conversational messages.

Version 2 may replace the hand-written orchestration layer with LangGraph. The agent interfaces, state models, and deterministic tools should remain reusable.

## Workflow

### 1. Validate Input

The CLI validates the project path and pytest command. The project must exist and the command must match the restricted pytest allowlist.

### 2. Reproduce the Failure

The orchestrator runs the provided pytest command in the original project. It records:

- exit code;
- stdout and stderr;
- duration;
- failed tests;
- pytest summary;
- traceback text;
- command errors and timeouts.

If tests already pass, the workflow stops with a `not_reproduced` report.

### 3. Investigate

`InvestigatorAgent` receives the baseline failure evidence and explores the repository through a bounded ReAct loop. It may call only read-only tools:

```text
list_project_files
search_code
read_code_context
read_test_context
```

The loop is limited to four tool calls. The agent then emits up to three evidence-backed hypotheses, chooses the most likely hypothesis, and identifies suspicious files.

### 4. Generate a Candidate Patch

`PatchAgent` receives the selected hypothesis, baseline evidence, and relevant code context. It returns a unified diff patch and a short explanation.

The patch must be relative to the original project. It may modify only project-local Python source files. It must not modify tests.

### 5. Check and Review the Patch

Deterministic tools parse the patch and enforce hard rules. A patch that fails any hard rule is rejected before semantic review.

`ReviewerAgent` independently checks whether an allowed patch matches the evidence, fixes the likely cause rather than suppressing symptoms, and remains appropriately small.

### 6. Verify in Isolation

For an approved patch, the orchestrator creates a clean temporary copy of the original project, applies the patch there, and reruns the exact same pytest command.

The original project remains unchanged. The final status is:

```text
verified_against_provided_test_command
```

only if the patch applies and the verification pytest command exits with code `0`.

### 7. Explain and Report

`CoachExplainer` turns the recorded evidence into a beginner-friendly explanation:

- how the failure appeared;
- why the relevant code was inspected;
- what the patch changes;
- what the verification result demonstrates;
- what the verification result does not demonstrate.

The reporter saves all evidence and status information to Markdown and JSON.

## Agent Contracts

### InvestigatorAgent

Input:

```text
baseline pytest result
traceback data
read-only repository context
```

Output:

```text
suspected_files
hypotheses:
  - description
  - evidence
  - confidence
selected_hypothesis
reasoning_summary
tool_trace
```

Rules:

- use at most four read-only tool calls;
- return at most three hypotheses;
- attach evidence to every hypothesis;
- never request shell execution or file modification.

### PatchAgent

Input:

```text
selected hypothesis
baseline evidence
relevant source and test context
```

Output:

```text
unified_diff
explanation
```

Rules:

- generate a minimal unified diff;
- modify only project-local `.py` source files;
- do not modify test files, dependencies, or configuration;
- do not assume code that was not provided.

### ReviewerAgent

Input:

```text
investigation result
candidate patch
deterministic diff metadata
```

Output:

```text
decision: approved | rejected
semantic_risks
review_summary
```

Rules:

- remain independent from patch generation;
- check whether the patch matches the failure evidence;
- reject patches that hide symptoms or introduce unjustified complexity;
- never override deterministic safety failures;
- do not generate a replacement patch.

### CoachExplainer

`CoachExplainer` uses an LLM but is not a decision-making agent. It runs after the outcome is known and cannot alter workflow state.

## State Model

The top-level run state stores baseline evidence and a list of attempted fixes:

```python
class RunState(BaseModel):
    project_path: Path
    test_command: list[str]
    baseline_test_result: TestRunResult | None
    attempts: list[AttemptResult]
    final_status: RunStatus
    coach_explanation: CoachExplanation | None
```

Version 1 creates at most one `AttemptResult`. The list structure is intentional: version 2 can add bounded retry attempts without replacing the report format.

Each future retry must:

- preserve previous patches and verification logs for auditing;
- use the baseline result and previous attempt results as evidence;
- generate a complete patch relative to the original project;
- create a new clean temporary copy before verification.

## Deterministic Tools

The tools layer wraps mature standard-library APIs, libraries, and system commands. It is intentionally thin.

| Tool | Responsibility | Primary implementation |
| --- | --- | --- |
| `CommandRunner` | Run allowed commands with timeout and capture output | `subprocess.run` |
| `PytestResultTool` | Extract failed tests, errors, and totals | pytest `--junitxml` plus XML parsing |
| `TracebackParser` | Extract exception type, paths, and line numbers | small regular-expression parser |
| `ProjectIndexer` | Find Python source and tests while ignoring sensitive or irrelevant paths | `pathlib` |
| `CodeContextTool` | Return bounded source windows for relevant files | `pathlib` and line slicing |
| `DiffParser` | Parse unified diff metadata and reject unsafe changes | `unidiff` plus project rules |
| `PatchApplier` | Validate and apply patches inside temporary copies | `git apply --check` and `git apply` |
| `TempWorkspace` | Create and clean isolated project copies | `tempfile.TemporaryDirectory` and `shutil.copytree` |

Deterministic operations must not be delegated to an LLM. Each custom wrapper remains small enough to unit test directly.

## LLM Provider Abstraction

Agents depend on an abstract client rather than on DeepSeek-specific code:

```python
class LLMClient(Protocol):
    def generate_structured(
        self,
        request: LLMRequest,
        response_model: type[BaseModel],
    ) -> LLMResponse:
        ...
```

Proposed structure:

```text
llm/
  base.py
  models.py
  factory.py
  providers/
    openai_compatible.py
    openai.py
    anthropic.py
```

Version 1 implements `openai_compatible.py` for the available API while keeping provider-specific code isolated. Later versions may select different models for investigation, patch generation, review, and explanation.

Configuration is environment-based:

```text
PATCHPROOF_PROVIDER=openai_compatible
PATCHPROOF_MODEL=<model-id>
PATCHPROOF_BASE_URL=<api-url>
PATCHPROOF_API_KEY=<secret>
```

Secrets must never be committed, logged, or sent to repository prompts.

The client adapter owns:

- API calls;
- timeouts;
- usage and duration recording;
- structured JSON parsing;
- Pydantic validation;
- at most one format-repair retry;
- error normalization;
- secret redaction.

## Model Call Budget

Model usage is dynamic rather than fixed:

| Component | Expected calls |
| --- | --- |
| `InvestigatorAgent` bounded ReAct loop | 1-5 |
| `PatchAgent` | normally 1 |
| `ReviewerAgent` | normally 1 |
| `CoachExplainer` | normally 1 |

The default run budget is 10 LLM calls. When the budget is exhausted, PatchProof stops and reports the partial evidence. The exact budget should be configurable.

## Security Rules

### Repository Content

Repository files and test output are untrusted data. Prompts must state that instructions found in repository content must not be followed.

The indexer ignores:

```text
.git/
.venv/
venv/
__pycache__/
.env
*.pem
*.key
```

Context sent to models is bounded by file count and line count.

### Patch Rules

Version 1 rejects:

- absolute paths;
- path traversal such as `../`;
- changes outside the project;
- non-`.py` changes;
- test-file changes;
- binary patches;
- file deletion;
- patches changing more than three files;
- patches changing more than 100 lines.

Allowed patches are checked with `git apply --check` before application.

### Command Rules

Version 1 accepts only allowlisted pytest forms and arguments. Commands are tokenized before validation and executed without a shell. LLMs cannot issue execution requests.

## Error Handling

Every terminal path generates reports.

| Condition | Result |
| --- | --- |
| Baseline tests pass | Stop with `not_reproduced` |
| Test command is invalid | Reject before execution |
| Test execution fails or times out | Record evidence and stop |
| Investigation cannot form a hypothesis | Record tool trace and stop |
| Model output remains invalid after one repair attempt | Record provider error and stop |
| Patch violates deterministic rules | Reject before semantic review |
| Reviewer rejects patch | Record risks and stop |
| `git apply --check` fails | Record application error and stop |
| Verification pytest remains failing | Record unsuccessful attempt and stop |
| Verification pytest passes | Mark `verified_against_provided_test_command` |

## Testing Strategy

### Unit Tests

Directly test deterministic tools, especially:

- pytest success, failure, launch error, and timeout;
- traceback variants;
- project ignore rules;
- bounded code windows;
- valid and invalid diffs;
- path traversal attempts;
- patch application success and failure;
- cleanup of temporary workspaces;
- preservation of original project contents.

### Integration Tests

Use a fake `LLMClient` to run stable end-to-end workflows without network access. Include:

```text
examples/buggy_calculator
examples/buggy_auth
examples/buggy_parser
```

At least two examples must reach `verified_against_provided_test_command`.

### Live Provider Smoke Test

Add an opt-in smoke test for the configured OpenAI-compatible provider. It must not run as part of the default test suite.

## Proposed Package Structure

```text
patchproof/
  pyproject.toml
  README.md
  .env.example

  src/
    patchproof/
      __init__.py
      cli.py

      core/
        orchestrator.py
        state.py
        config.py

      agents/
        investigator.py
        patcher.py
        reviewer.py
        coach.py

      llm/
        base.py
        models.py
        factory.py
        providers/
          openai_compatible.py

      tools/
        command_runner.py
        pytest_result.py
        traceback_parser.py
        project_indexer.py
        code_context.py
        diff_parser.py
        patch_applier.py
        temp_workspace.py

      reporting/
        markdown.py
        json_report.py

      errors.py

  tests/
    unit/
    integration/

  examples/
    buggy_calculator/
    buggy_auth/
    buggy_parser/
```

## Acceptance Criteria

PatchProof v0.1 is complete when:

1. The CLI accepts a Python project path and restricted pytest command.
2. The baseline pytest failure is reproduced and recorded.
3. `InvestigatorAgent` can explore with at most four read-only ReAct tool calls.
4. `PatchAgent` can generate a unified diff.
5. Deterministic tools reject unsafe patches.
6. `ReviewerAgent` independently reviews allowed patches.
7. Approved patches are applied and tested only in clean temporary copies.
8. The original project remains unchanged.
9. Every outcome produces `report.md` and `report.json`.
10. Reports include a beginner-friendly explanation.
11. LLM providers are replaceable and v0.1 includes an OpenAI-compatible adapter.
12. At least two of the three example projects achieve verified fixes end to end.

## Version 2 Direction

Version 2 may:

- migrate orchestration to LangGraph;
- add bounded Plan-and-Execute retry handling after failed verification;
- let a planner compare baseline evidence, previous complete patches, review results, and verification logs;
- generate each new patch relative to the original project;
- verify every attempt in a fresh temporary copy;
- preserve all attempts in the audit report;
- support role-specific model selection.

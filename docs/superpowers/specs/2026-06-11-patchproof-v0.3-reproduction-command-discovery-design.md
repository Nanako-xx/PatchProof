# PatchProof v0.3 Reproduction Command Discovery Design

## Goal

PatchProof v0.3 discovers and safely validates project-specific reproduction commands before patching.

v0.1 focused on a user-provided pytest command. v0.2 added bug evidence inputs and narrow pytest-based verification discovery. v0.3 expands the pre-patch phase so PatchProof can infer how a real project reproduces a bug from repository files, scripts, package metadata, and bug evidence.

The main product shift is:

```text
from: find a pytest verification command
to: discover, rank, risk-classify, and safely validate reproduction commands
```

## Non-Goals

v0.3 must not become arbitrary shell execution.

PatchProof v0.3 will not automatically run:

- deployment commands
- install or upgrade commands
- database migrations
- destructive file commands
- network-heavy commands
- secret-reading commands
- long training jobs without explicit user approval
- arbitrary shell pipelines or shell operators

Commands outside the safe policy can be recorded and explained, but they are not silently executed.

## Current v0.2 Boundary

PatchProof v0.2 can start from:

- `--test`
- `--bug-text`
- `--bug-log`
- `--bug-image`

If no `--test` is provided, it can select restricted pytest commands such as:

```text
pytest <matched-or-evidence-referenced-test-file> -q
pytest -q
```

This is useful, but still too narrow for real projects. Many user bug reports are reproduced by project-specific commands such as:

```text
python train.py --config configs/demo.yaml --epochs 1
python main.py --input examples/bad.json
python scripts/reproduce_issue.py
npm test
npm run test
make test
```

v0.3 addresses this gap.

## User Experience

The CLI remains evidence-first:

```powershell
patchproof run ./project --bug-text "Traceback ..."
patchproof run ./project --bug-log .\error.log
patchproof run ./project --bug-image .\error.png
patchproof run ./project --bug-log .\error.log --test "pytest -q"
```

When `--test` is omitted, PatchProof should attempt to discover reproduction commands. The report should show:

1. Which command candidates were discovered.
2. Where each candidate came from.
3. How each candidate was risk-classified.
4. Which command was executed.
5. Whether it reproduced the bug before patching.
6. Whether it verified the patch after patching.
7. Which commands were skipped and why.

If a candidate is useful but not safe to run automatically, PatchProof should stop with an actionable message or require user approval instead of guessing.

## Command Discovery Sources

PatchProof should gather candidate commands from deterministic repository inspection before asking the LLM to reason about commands.

### Repository Metadata

Scan common project files:

- `pyproject.toml`
- `pytest.ini`
- `tox.ini`
- `noxfile.py`
- `setup.cfg`
- `package.json`
- `Makefile`
- `README.md`
- `docs/**/*.md`
- `.vscode/tasks.json`
- `.vscode/launch.json`

### Project Entrypoints

Inspect likely executable files:

- `train.py`
- `main.py`
- `app.py`
- `run.py`
- `manage.py`
- `scripts/*.py`
- `examples/*.py`
- test files referenced by traceback frames

### Bug Evidence

Extract command hints from:

- pasted text
- log files
- image-extracted text
- traceback file paths
- config paths in logs
- arguments visible in error output

Examples:

```text
python train.py --config configs/a.yaml --epochs 1
node scripts/repro.js
npm run test
make test
```

### LLM-Assisted Ranking

After deterministic scanning, an LLM may rank or explain candidates. It must not invent commands that are not grounded in repository files or bug evidence unless the command is marked `unknown` and requires user approval.

## Data Model

Add command-discovery state alongside v0.2 verification state.

```python
class CommandRisk(str, Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    UNKNOWN = "unknown"


class CommandPurpose(str, Enum):
    REPRODUCE = "reproduce"
    VERIFY = "verify"
    SETUP = "setup"
    UNKNOWN = "unknown"


class ReproductionCommandCandidate(BaseModel):
    command: list[str]
    cwd: str = "."
    source: str
    purpose: CommandPurpose = CommandPurpose.UNKNOWN
    risk: CommandRisk = CommandRisk.UNKNOWN
    reason: str = ""
    requires_approval: bool = False
    expected_runtime_seconds: Optional[int] = None


class ReproductionPlan(BaseModel):
    candidates: list[ReproductionCommandCandidate] = []
    selected: Optional[ReproductionCommandCandidate] = None
    skipped: list[ReproductionCommandCandidate] = []
```

Use Python 3.9-compatible type syntax in implementation.

## Risk Policy

Risk classification should be conservative.

### Safe

May run automatically in a temporary workspace with timeout and output limits:

- `pytest ...`
- `python -m pytest ...`
- `npm test`
- `npm run test`
- `make test`
- `python scripts/repro*.py` when the script exists and arguments are local files
- `python main.py --input <local-example-file>` when bounded by local input and timeout

### Caution

Requires explicit user approval or an allow flag:

- `python train.py ...`
- commands with `--epochs`, `--steps`, `--limit`, or config files
- commands that may write checkpoints or outputs
- commands that may take a long time
- commands that start servers

PatchProof should prefer lightweight variants when available:

```text
--dry-run
--epochs 1
--max-steps 1
--limit 1
--sample
```

### Dangerous

Never run automatically:

- `make deploy`
- `npm publish`
- `pip install`
- `npm install`
- `rm`, `del`, `Remove-Item`
- migration commands
- commands with shell operators
- commands that write outside the temp workspace
- commands that access secrets or cloud resources

### Unknown

Do not run automatically. Ask for approval or mark unverified.

## Execution Safety

All discovered commands must run only under a controlled runner:

1. Execute in a temporary copy of the project.
2. Use `shell=False`.
3. Reject shell operators and command separators.
4. Enforce timeout.
5. Limit output size.
6. Record stdout, stderr, exit code, duration, cwd, and command source.
7. Do not inherit dangerous environment variables by default.
8. Prefer read-only or small-output modes when available.
9. Do not run network, deploy, install, or migration commands without explicit user approval.

## Workflow

```text
1. Collect bug evidence.
2. Parse traceback/log/image text into BugEvidence.
3. Discover reproduction command candidates from project files and evidence.
4. Risk-classify every candidate.
5. Select safe candidate commands.
6. Run the selected command before patching in a temp workspace.
7. If it reproduces the bug, continue with investigation and patching.
8. If no safe command reproduces the bug, either ask for approval or mark the result unverified.
9. After patching, run the same reproducing command, or an equivalent selected verification command.
10. Report discovered, selected, skipped, and executed commands.
```

## Reproduction Semantics

A command reproduces the bug when:

- it exits non-zero with output matching the bug evidence, or
- it emits the parsed exception type, traceback path, failed assertion, or log signature, or
- it reaches a domain-specific failure signal from the evidence.

A command that passed before patching cannot by itself verify a patch for unrelated bug evidence.

If the command does not reproduce the bug before patching, PatchProof may still suggest a patch from evidence, but the final status must remain `unverified` unless another command validates the behavior.

## Agent Roles

### ReproductionCommandDiscoverer

Deterministic scanner that extracts candidates from project files and evidence.

### CommandRiskClassifier

Deterministic policy plus optional LLM explanation. The policy result is authoritative; the LLM cannot downgrade dangerous commands to safe.

### ReproductionRunner

Runs only approved candidates in temporary workspaces with timeout and output limits.

### Orchestrator

Coordinates discovery, pre-patch reproduction, patching, and post-patch verification.

InvestigatorAgent and PatchAgent continue to receive `BugEvidence`, now enriched with reproduction command results.

## Reporting

Reports should include:

- discovered candidates
- candidate sources
- risk classification
- selected command
- skipped commands and reasons
- pre-patch reproduction result
- post-patch verification result
- whether final status is `verified`, `unverified`, `not_reproduced`, or `stopped`

Example:

```text
## Reproduction Commands

Planned candidates:
- `python train.py --config configs/demo.yaml --epochs 1` (caution): may write checkpoints
- `pytest tests/test_parser.py -q` (safe): matched traceback source file

Executed:
- `pytest tests/test_parser.py -q`

Skipped:
- `make deploy` (dangerous): deployment command
```

## Testing Strategy

Unit tests:

1. Candidate extraction from `package.json`.
2. Candidate extraction from `Makefile`.
3. Candidate extraction from README command blocks.
4. Candidate extraction from traceback/log evidence.
5. Risk classification for safe pytest/npm/make-test commands.
6. Risk classification for dangerous deploy/install/delete/migration commands.
7. Shell operator rejection.
8. Output limit and timeout handling.

Integration tests:

1. Bug evidence with no `--test` discovers a Python script reproduction command.
2. A passing unrelated command does not verify unrelated evidence.
3. Dangerous commands are skipped and reported.
4. Caution commands require approval or remain unverified.
5. A pre-patch reproducing command becomes a post-patch passing command.
6. Original project remains unmodified.

## Acceptance Criteria

v0.3 is complete when:

1. PatchProof can discover at least pytest, npm test, make test, and local Python script reproduction candidates.
2. Every candidate has source, purpose, risk, and reason.
3. Safe candidates can run automatically in a temp workspace.
4. Dangerous candidates never run automatically.
5. Caution and unknown candidates do not run without approval.
6. Reports distinguish discovered, skipped, selected, and executed commands.
7. A passing unrelated command cannot produce a verified final status.
8. Existing v0.2 flows still pass.

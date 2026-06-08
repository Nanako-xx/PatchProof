from __future__ import annotations

from pathlib import Path

from patchproof.agents.coach import CoachExplainer
from patchproof.agents.investigator import InvestigatorAgent
from patchproof.agents.patcher import PatchAgent
from patchproof.agents.reviewer import ReviewerAgent
from patchproof.core.config import Settings
from patchproof.core.state import (
    AttemptResult,
    FinalStatus,
    ReviewDecision,
    RunState,
    TestRunResult,
    TestRunStatus,
    VerificationStatus,
)
from patchproof.llm.base import LLMClient
from patchproof.reporting.json_report import write_json_report, write_llm_trace
from patchproof.reporting.markdown import write_markdown_report
from patchproof.tools.code_context import CodeContextTool
from patchproof.tools.command_runner import CommandRunner
from patchproof.tools.diff_parser import DiffParser
from patchproof.tools.patch_applier import PatchApplier
from patchproof.tools.project_indexer import ProjectIndexer
from patchproof.tools.temp_workspace import TempWorkspace
from patchproof.tools.traceback_parser import TracebackParser


class WorkflowOrchestrator:
    def __init__(self, settings: Settings, llm: LLMClient) -> None:
        self.settings = settings
        self.llm = llm

    def run(self, project_path: Path, test_command: list[str]) -> RunState:
        state = RunState(project_path=project_path, test_command=test_command)
        baseline = self._run_tests(project_path, test_command)
        state.baseline_test_result = baseline
        state.traceback_summary = TracebackParser().parse(baseline.stdout + "\n" + baseline.stderr)

        if baseline.status == TestRunStatus.PASSED:
            state.final_status = FinalStatus.NOT_REPRODUCED
            state.stop_reason = "Baseline tests passed; failure was not reproduced."
            return self._write_reports(state)
        if baseline.status in {TestRunStatus.COMMAND_ERROR, TestRunStatus.TIMEOUT}:
            state.final_status = FinalStatus.STOPPED
            state.stop_reason = "Baseline test command failed before a reproducible pytest failure was available."
            return self._write_reports(state)

        indexer = ProjectIndexer(project_path)
        context_tool = CodeContextTool(project_path)
        investigation = InvestigatorAgent(self.llm, self.settings).run_with_tools(
            baseline=baseline,
            indexer=indexer,
            context_tool=context_tool,
        )
        state.investigation = investigation

        repository_context = self._build_repository_context(project_path)
        evidence = baseline
        previous_patch = ""
        feedback = ""

        for attempt_number in range(1, self.settings.max_patch_attempts + 1):
            attempt = PatchAgent(self.llm).run(
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

                verification = self._run_tests(copied_project, test_command)
                attempt.verification_result = verification

            state.attempts.append(attempt)
            if verification.status == TestRunStatus.PASSED:
                attempt.verification_status = VerificationStatus.VERIFIED
                state.final_status = FinalStatus.VERIFIED
                state.stop_reason = "Patch verified against the provided test command in a temporary copy."
                break
            if verification.status == TestRunStatus.TIMEOUT:
                attempt.verification_status = VerificationStatus.TIMEOUT
                state.final_status = FinalStatus.UNVERIFIED
                state.stop_reason = "Verification timed out in the temporary workspace."
                break

            attempt.verification_status = VerificationStatus.TESTS_FAILED
            previous_patch = attempt.patch_diff
            feedback = self._verification_feedback(attempt)
            evidence = verification
            if attempt_number < self.settings.max_patch_attempts:
                investigation = InvestigatorAgent(self.llm, self.settings).run_with_tools(
                    baseline=verification,
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

    def _patch_apply_feedback(self, attempt: AttemptResult) -> str:
        return f"""The previous patch could not be applied.
Patch application error:
{attempt.patch_apply_error}
Return a corrected complete replacement patch against the original code."""

    def _review_feedback(self, attempt: AttemptResult) -> str:
        risks = "\n".join(attempt.semantic_risks)
        return f"""The previous patch was rejected.
Review summary: {attempt.review_summary}
Risks and rule violations:
{risks}
Return a corrected complete replacement patch against the original code."""

    def _verification_feedback(self, attempt: AttemptResult) -> str:
        verification = attempt.verification_result
        if verification is None:
            return "The previous patch did not produce a verification result."
        return f"""The previous patch applied, but the provided pytest command still failed.
Verification summary: {verification.summary}
Stdout:
{verification.stdout}
Stderr:
{verification.stderr}
Return a corrected complete replacement patch against the original code."""

    def _run_tests(self, project_path: Path, test_command: list[str]) -> TestRunResult:
        result = CommandRunner(timeout_seconds=self.settings.command_timeout_seconds).run(
            test_command,
            cwd=project_path,
        )
        combined_output = result.stdout + "\n" + result.stderr
        if result.timed_out:
            status = TestRunStatus.TIMEOUT
        elif result.exit_code == 0:
            status = TestRunStatus.PASSED
        else:
            status = TestRunStatus.FAILED

        return TestRunResult(
            status=status,
            command=test_command,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=result.duration_ms,
            failed_tests=self._extract_failed_tests(combined_output),
            traceback_text=combined_output,
            summary=self._extract_summary(combined_output),
        )

    def _extract_failed_tests(self, output: str) -> list[str]:
        failed_tests: list[str] = []
        for line in output.splitlines():
            if line.startswith("FAILED "):
                parts = line.split()
                if len(parts) >= 2:
                    failed_tests.append(parts[1])
        return failed_tests

    def _extract_summary(self, output: str) -> str:
        for line in reversed(output.splitlines()):
            stripped = line.strip()
            if stripped and ("failed" in stripped or "passed" in stripped or "error" in stripped):
                return stripped
        return ""

    def _build_repository_context(self, project_path: Path) -> str:
        indexer = ProjectIndexer(project_path)
        files = indexer.list_python_files()
        context_tool = CodeContextTool(project_path)
        contexts: list[str] = []
        for file_path in files[:5]:
            context = context_tool.read_context(file_path, line_number=1, radius=40)
            contexts.append(f"File: {file_path}\n{context.text}")
        return "\n\n".join(contexts)

    def _explain_and_write(self, state: RunState) -> RunState:
        state.coach_explanation = CoachExplainer(self.llm).run(state.model_dump_json())
        return self._write_reports(state)

    def _write_reports(self, state: RunState) -> RunState:
        write_llm_trace(self.llm.call_trace, Path(".patchproof") / "llm_trace.json")
        write_markdown_report(state, Path("report.md"))
        write_json_report(state, Path("report.json"))
        return state

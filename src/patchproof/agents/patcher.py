from __future__ import annotations

from pydantic import BaseModel

from patchproof.agents.investigator import _bug_evidence_from_test_result
from patchproof.core.state import AttemptResult, BugEvidence, InvestigationResult, TestRunResult
from patchproof.llm.base import LLMClient, LLMRequest


class PatchGeneration(BaseModel):
    unified_diff: str
    explanation: str = ""


_SYSTEM_PROMPT = """You are PatchAgent for PatchProof.
Generate one minimal unified diff for source files only.
Do not modify tests.
Do not include Markdown fences.
Return only JSON matching the schema."""


class PatchAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def run(
        self,
        investigation: InvestigationResult,
        baseline: TestRunResult,
        code_context: str,
        previous_patch: str = "",
        feedback: str = "",
    ) -> AttemptResult:
        evidence = _bug_evidence_from_test_result(baseline)
        return self.run_with_evidence(investigation, evidence, code_context, previous_patch, feedback)

    def run_with_evidence(
        self,
        investigation: InvestigationResult,
        evidence: BugEvidence,
        code_context: str,
        previous_patch: str = "",
        feedback: str = "",
    ) -> AttemptResult:
        user_prompt = f"""Investigation: {investigation.model_dump()}
Bug evidence:
{evidence.model_dump()}
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

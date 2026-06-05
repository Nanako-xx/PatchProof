from __future__ import annotations

from pydantic import BaseModel

from patchproof.core.state import AttemptResult, InvestigationResult, TestRunResult
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
    ) -> AttemptResult:
        user_prompt = f"""Investigation: {investigation.model_dump()}
Baseline summary: {baseline.summary}
Failed tests: {baseline.failed_tests}
Code context:
{code_context}
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

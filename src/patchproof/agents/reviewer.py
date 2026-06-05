from __future__ import annotations

from pydantic import BaseModel, Field

from patchproof.core.state import DiffMetadata, InvestigationResult, ReviewDecision
from patchproof.llm.base import LLMClient, LLMRequest


class ReviewResult(BaseModel):
    decision: ReviewDecision
    semantic_risks: list[str] = Field(default_factory=list)
    review_summary: str = ""


_SYSTEM_PROMPT = """You are ReviewerAgent for PatchProof.
Be skeptical.
Check whether the patch matches the failure evidence.
Reject patches that hide symptoms, modify unrelated code, or introduce unjustified complexity.
Do not generate a replacement patch."""


class ReviewerAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def run(
        self,
        investigation: InvestigationResult,
        patch_diff: str,
        diff_metadata: DiffMetadata,
    ) -> ReviewResult:
        if diff_metadata.rule_violations:
            return ReviewResult(
                decision=ReviewDecision.REJECTED,
                semantic_risks=diff_metadata.rule_violations,
                review_summary="Patch rejected by deterministic safety rules.",
            )
        prompt = f"""Investigation: {investigation.model_dump()}
Diff metadata: {diff_metadata.model_dump()}
Patch:
{patch_diff}
"""
        response = self.llm.generate_structured(
            LLMRequest(system_prompt=_SYSTEM_PROMPT, user_prompt=prompt),
            ReviewResult,
        )
        return response.data

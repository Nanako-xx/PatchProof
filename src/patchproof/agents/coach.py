from __future__ import annotations

from patchproof.core.state import CoachExplanation
from patchproof.llm.base import LLMClient, LLMRequest


_SYSTEM_PROMPT = """You are CoachExplainer for PatchProof.
Explain the debugging process to a beginner.
Do not change decisions or claim more than the verification result proves."""


class CoachExplainer:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def run(self, run_summary: str) -> CoachExplanation:
        response = self.llm.generate_structured(
            LLMRequest(system_prompt=_SYSTEM_PROMPT, user_prompt=run_summary),
            CoachExplanation,
        )
        return response.data

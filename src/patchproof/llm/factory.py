from __future__ import annotations

from patchproof.core.config import Settings
from patchproof.errors import LLMProviderError
from patchproof.llm.base import LLMClient
from patchproof.llm.providers.openai_compatible import OpenAICompatibleClient


def create_llm_client(settings: Settings) -> LLMClient:
    if settings.provider == "openai_compatible":
        if not settings.base_url or not settings.api_key or not settings.model:
            raise LLMProviderError("OpenAI-compatible provider requires base_url, api_key, and model.")
        return OpenAICompatibleClient(
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model,
        )
    raise LLMProviderError(f"Unsupported LLM provider: {settings.provider}")

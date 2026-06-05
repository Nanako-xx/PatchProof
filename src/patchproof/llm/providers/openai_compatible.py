from __future__ import annotations

import json

import httpx

from patchproof.errors import LLMProviderError
from patchproof.llm.base import LLMRequest, LLMResponse, T


class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout_seconds: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate_structured(self, request: LLMRequest, response_model: type[T]) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
            "response_format": {"type": "json_object"},
        }
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            data = response_model.model_validate(json.loads(content))
            return LLMResponse(
                data=data,
                raw_text=content,
                provider="openai_compatible",
                model=self.model,
            )
        except Exception as exc:
            raise LLMProviderError(f"LLM provider call failed: {exc}") from exc

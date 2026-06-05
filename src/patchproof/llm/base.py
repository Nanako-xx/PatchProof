from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)


class LLMRequest(BaseModel):
    system_prompt: str
    user_prompt: str
    temperature: float = 0.0


class LLMResponse(BaseModel):
    data: BaseModel
    raw_text: str = ""
    provider: str = "fake"
    model: str = "fake"
    call_count: int = 1


class LLMClient(Protocol):
    def generate_structured(self, request: LLMRequest, response_model: type[T]) -> LLMResponse:
        ...


class FakeLLMClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[LLMRequest] = []

    def generate_structured(self, request: LLMRequest, response_model: type[T]) -> LLMResponse:
        self.calls.append(request)
        payload = self.responses.pop(0)
        return LLMResponse(
            data=response_model.model_validate(payload),
            raw_text=str(payload),
            provider="fake",
            model="fake",
            call_count=len(self.calls),
        )

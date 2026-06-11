from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Protocol, Tuple, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T", bound=BaseModel)


class LLMRequest(BaseModel):
    system_prompt: str
    user_prompt: str
    temperature: float = 0.0


class LLMRepairRecord(BaseModel):
    invalid_response: str
    validation_error: str
    corrected_response: str


class LLMCallTrace(BaseModel):
    response_model: str
    provider: str
    model: str
    raw_responses: list[str] = Field(default_factory=list)
    repair_records: list[LLMRepairRecord] = Field(default_factory=list)
    call_count: int = 0


class LLMResponse(BaseModel):
    data: BaseModel
    raw_text: str = ""
    provider: str = "fake"
    model: str = "fake"
    call_count: int = 1


class LLMClient(Protocol):
    call_trace: list[LLMCallTrace]

    def generate_structured(self, request: LLMRequest, response_model: type[T]) -> LLMResponse:
        ...


class FakeLLMClient:
    def __init__(
        self,
        responses: list[dict[str, Any]],
        image_responses: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self.responses = responses
        self.image_responses = image_responses or []
        self.supports_images = image_responses is not None
        self.calls: list[LLMRequest] = []
        self.image_calls: list[Tuple[LLMRequest, Path]] = []
        self.call_trace: list[LLMCallTrace] = []

    def generate_structured(self, request: LLMRequest, response_model: type[T]) -> LLMResponse:
        self.calls.append(request)
        payload = self.responses.pop(0)
        raw_text = json.dumps(payload, ensure_ascii=False)
        self.call_trace.append(
            LLMCallTrace(
                response_model=response_model.__name__,
                provider="fake",
                model="fake",
                raw_responses=[raw_text],
                call_count=1,
            )
        )
        return LLMResponse(
            data=response_model.model_validate(payload),
            raw_text=raw_text,
            provider="fake",
            model="fake",
            call_count=1,
        )

    def generate_structured_with_image(
        self,
        request: LLMRequest,
        image_path: Path,
        response_model: type[T],
    ) -> LLMResponse:
        self.image_calls.append((request, image_path))
        payload = self.image_responses.pop(0)
        raw_text = json.dumps(payload, ensure_ascii=False)
        self.call_trace.append(
            LLMCallTrace(
                response_model=response_model.__name__,
                provider="fake",
                model="fake",
                raw_responses=[raw_text],
                call_count=1,
            )
        )
        return LLMResponse(
            data=response_model.model_validate(payload),
            raw_text=raw_text,
            provider="fake",
            model="fake",
            call_count=1,
        )

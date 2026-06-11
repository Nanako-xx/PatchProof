from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Optional

import httpx
from pydantic import ValidationError

from patchproof.errors import LLMProviderError
from patchproof.llm.base import LLMCallTrace, LLMRepairRecord, LLMRequest, LLMResponse, T


class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout_seconds: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._json_schema_supported: Optional[bool] = None
        self.call_trace: list[LLMCallTrace] = []

    @property
    def supports_images(self) -> bool:
        return True

    def generate_structured(self, request: LLMRequest, response_model: type[T]) -> LLMResponse:
        schema = response_model.model_json_schema()
        schema_text = json.dumps(schema, indent=2, ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    f"{request.system_prompt}\n\n"
                    "Return exactly one JSON object with no Markdown fences or extra text. "
                    "The object must validate against this JSON Schema:\n"
                    f"{schema_text}"
                ),
            },
            {"role": "user", "content": request.user_prompt},
        ]
        return self._generate_structured_from_messages(
            messages=messages,
            request=request,
            response_model=response_model,
            schema=schema,
            error_prefix="LLM provider call failed",
        )

    def _generate_structured_from_messages(
        self,
        messages: list[dict],
        request: LLMRequest,
        response_model: type[T],
        schema: dict,
        error_prefix: str,
    ) -> LLMResponse:
        call_count = 0
        raw_responses: list[str] = []
        repair_records: list[LLMRepairRecord] = []
        try:
            content, initial_calls = self._request_content(
                messages=messages,
                temperature=request.temperature,
                response_model=response_model,
                schema=schema,
            )
            call_count += initial_calls
            raw_responses.append(content)
            try:
                data = response_model.model_validate(json.loads(content))
            except (json.JSONDecodeError, ValidationError) as validation_error:
                invalid_response = content
                repair_messages = messages + [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            "Your previous response did not validate against the required JSON Schema.\n"
                            f"Validation errors:\n{validation_error}\n"
                            "Return one corrected JSON object only."
                        ),
                    },
                ]
                content, repair_calls = self._request_content(
                    messages=repair_messages,
                    temperature=request.temperature,
                    response_model=response_model,
                    schema=schema,
                )
                call_count += repair_calls
                raw_responses.append(content)
                repair_records.append(
                    LLMRepairRecord(
                        invalid_response=invalid_response,
                        validation_error=str(validation_error),
                        corrected_response=content,
                    )
                )
                data = response_model.model_validate(json.loads(content))

            self.call_trace.append(
                LLMCallTrace(
                    response_model=response_model.__name__,
                    provider="openai_compatible",
                    model=self.model,
                    raw_responses=raw_responses,
                    repair_records=repair_records,
                    call_count=call_count,
                )
            )
            return LLMResponse(
                data=data,
                raw_text=content,
                provider="openai_compatible",
                model=self.model,
                call_count=call_count,
            )
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(f"{error_prefix}: {exc}") from exc

    def generate_structured_with_image(
        self,
        request: LLMRequest,
        image_path: Path,
        response_model: type[T],
    ) -> LLMResponse:
        schema = response_model.model_json_schema()
        schema_text = json.dumps(schema, indent=2, ensure_ascii=False)
        data_url = self._image_data_url(image_path)
        messages = [
            {
                "role": "system",
                "content": (
                    f"{request.system_prompt}\n\n"
                    "Return exactly one JSON object with no Markdown fences or extra text. "
                    "The object must validate against this JSON Schema:\n"
                    f"{schema_text}"
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": request.user_prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]
        return self._generate_structured_from_messages(
            messages=messages,
            request=request,
            response_model=response_model,
            schema=schema,
            error_prefix="LLM provider image call failed",
        )

    def _request_content(
        self,
        messages: list[dict],
        temperature: float,
        response_model: type[T],
        schema: dict,
    ) -> tuple[str, int]:
        response_formats: list[dict] = []
        if self._json_schema_supported is not False:
            response_formats.append(
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_model.__name__,
                        "strict": True,
                        "schema": schema,
                    },
                }
            )
        response_formats.append({"type": "json_object"})

        call_count = 0
        for response_format in response_formats:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "response_format": response_format,
            }
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=self.timeout_seconds,
            )
            call_count += 1
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if (
                    response_format["type"] == "json_schema"
                    and exc.response.status_code in {400, 404, 422}
                ):
                    self._json_schema_supported = False
                    continue
                raise

            if response_format["type"] == "json_schema":
                self._json_schema_supported = True
            body = response.json()
            return body["choices"][0]["message"]["content"], call_count

        raise LLMProviderError("LLM provider rejected all supported structured output formats.")

    def _image_data_url(self, image_path: Path) -> str:
        mime_type = mimetypes.guess_type(str(image_path))[0]
        if mime_type == "image/jpg":
            mime_type = "image/jpeg"
        if mime_type not in {"image/png", "image/jpeg"}:
            raise LLMProviderError(
                "Unsupported image type for bug screenshot. "
                "Use a PNG or JPEG image, or provide text with --bug-text or --bug-log."
            )
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

import json

import httpx
import pytest
from pydantic import BaseModel

from patchproof.core.config import Settings
from patchproof.errors import LLMProviderError
from patchproof.llm.base import FakeLLMClient, LLMRequest
from patchproof.llm.factory import create_llm_client
from patchproof.llm.providers.openai_compatible import OpenAICompatibleClient


class SimpleResponse(BaseModel):
    message: str


def test_fake_llm_returns_structured_response():
    client = FakeLLMClient([{"message": "hello"}])

    response = client.generate_structured(
        LLMRequest(system_prompt="system", user_prompt="user"),
        SimpleResponse,
    )

    assert response.data.message == "hello"
    assert response.call_count == 1
    assert client.calls[0].user_prompt == "user"


def test_factory_creates_openai_compatible_client():
    settings = Settings(
        provider="openai_compatible",
        model="model",
        base_url="https://api.example.com/v1",
        api_key="secret",
    )

    client = create_llm_client(settings)

    assert client.__class__.__name__ == "OpenAICompatibleClient"


def test_factory_rejects_missing_openai_compatible_config():
    with pytest.raises(LLMProviderError):
        create_llm_client(Settings(provider="openai_compatible"))


def test_factory_rejects_unknown_provider():
    with pytest.raises(LLMProviderError):
        create_llm_client(Settings(provider="unknown"))


def _response(content: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={"choices": [{"message": {"content": content}}]},
        request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
    )


def test_openai_compatible_client_sends_pydantic_json_schema(monkeypatch):
    payloads = []

    def fake_post(*args, **kwargs):
        payloads.append(kwargs["json"])
        return _response('{"message": "hello"}')

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenAICompatibleClient("https://api.example.com/v1", "secret", "model")

    response = client.generate_structured(
        LLMRequest(system_prompt="system", user_prompt="user"),
        SimpleResponse,
    )

    response_format = payloads[0]["response_format"]
    assert response.data.message == "hello"
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["schema"] == SimpleResponse.model_json_schema()
    assert "JSON Schema" in payloads[0]["messages"][0]["content"]


def test_openai_compatible_client_repairs_invalid_structured_output(monkeypatch):
    payloads = []
    responses = iter(
        [
            _response('{"wrong_field": "hello"}'),
            _response('{"message": "hello"}'),
        ]
    )

    def fake_post(*args, **kwargs):
        payloads.append(kwargs["json"])
        return next(responses)

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenAICompatibleClient("https://api.example.com/v1", "secret", "model")

    response = client.generate_structured(
        LLMRequest(system_prompt="system", user_prompt="user"),
        SimpleResponse,
    )

    assert response.data.message == "hello"
    assert response.call_count == 2
    assert client.call_trace[0].response_model == "SimpleResponse"
    assert client.call_trace[0].raw_responses == [
        '{"wrong_field": "hello"}',
        '{"message": "hello"}',
    ]
    assert client.call_trace[0].repair_records[0].invalid_response == '{"wrong_field": "hello"}'
    assert "message" in client.call_trace[0].repair_records[0].validation_error
    assert client.call_trace[0].repair_records[0].corrected_response == '{"message": "hello"}'
    assert client.call_trace[0].call_count == 2
    repair_prompt = payloads[1]["messages"][-1]["content"]
    assert "previous response did not validate" in repair_prompt
    assert "message" in repair_prompt


def test_openai_compatible_client_falls_back_when_json_schema_is_unsupported(monkeypatch):
    payloads = []
    responses = iter(
        [
            _response(json.dumps({"error": "unsupported response format"}), status_code=400),
            _response('{"message": "hello"}'),
        ]
    )

    def fake_post(*args, **kwargs):
        payloads.append(kwargs["json"])
        return next(responses)

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenAICompatibleClient("https://api.example.com/v1", "secret", "model")

    response = client.generate_structured(
        LLMRequest(system_prompt="system", user_prompt="user"),
        SimpleResponse,
    )

    assert response.data.message == "hello"
    assert response.call_count == 2
    assert payloads[0]["response_format"]["type"] == "json_schema"
    assert payloads[1]["response_format"]["type"] == "json_object"


def test_openai_compatible_client_sends_local_image_as_data_url(tmp_path, monkeypatch):
    payloads = []
    image_path = tmp_path / "error.png"
    image_path.write_bytes(b"image-bytes")

    def fake_post(*args, **kwargs):
        payloads.append(kwargs["json"])
        return _response('{"extracted_text": "ValueError: bad"}')

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenAICompatibleClient("https://api.example.com/v1", "secret", "model")

    class ExtractedText(BaseModel):
        extracted_text: str

    response = client.generate_structured_with_image(
        LLMRequest(system_prompt="system", user_prompt="extract text"),
        image_path,
        ExtractedText,
    )

    user_content = payloads[0]["messages"][1]["content"]
    assert response.data.extracted_text == "ValueError: bad"
    assert user_content[0]["type"] == "text"
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"].startswith("data:image/png;base64,")

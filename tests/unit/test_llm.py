import pytest
from pydantic import BaseModel

from patchproof.core.config import Settings
from patchproof.errors import LLMProviderError
from patchproof.llm.base import FakeLLMClient, LLMRequest
from patchproof.llm.factory import create_llm_client


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

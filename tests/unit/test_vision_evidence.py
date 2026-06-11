from pathlib import Path

import pytest

from patchproof.core.state import EvidenceSourceType
from patchproof.errors import LLMProviderError
from patchproof.llm.base import FakeLLMClient
from patchproof.tools.evidence import VisionTextExtractor


def test_vision_text_extractor_fails_when_model_lacks_image_support(tmp_path: Path):
    image_path = tmp_path / "error.png"
    image_path.write_bytes(b"not really an image")
    client = FakeLLMClient([])

    with pytest.raises(LLMProviderError, match="does not support image input"):
        VisionTextExtractor(client).extract(image_path)


def test_vision_text_extractor_returns_bug_image_source(tmp_path: Path):
    image_path = tmp_path / "error.png"
    image_path.write_bytes(b"fake image")
    client = FakeLLMClient(
        responses=[],
        image_responses=[{"extracted_text": "ValueError: bad value"}],
    )

    source = VisionTextExtractor(client).extract(image_path)

    assert source.source_type == EvidenceSourceType.BUG_IMAGE
    assert source.path == image_path
    assert source.raw_text == "ValueError: bad value"
    assert source.extracted_text == "ValueError: bad value"

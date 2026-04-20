from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from live_vlm_webui.vlm_service import VLMService


@pytest.mark.asyncio
async def test_analyze_image_handles_none_message_content():
    service = VLMService(model="test-model")
    service.client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            id="chatcmpl-test",
            model="test-model",
            choices=[
                SimpleNamespace(
                    index=0,
                    message=SimpleNamespace(role="assistant", content=None),
                    finish_reason="stop",
                )
            ],
            usage=None,
        )
    )

    image = Image.new("RGB", (2, 2), color="white")

    result = await service.analyze_image(image)

    assert result == VLMService.EMPTY_RESPONSE_TEXT
    assert service.total_inferences == 1


@pytest.mark.asyncio
async def test_analyze_image_handles_structured_message_content():
    service = VLMService(model="test-model")
    service.client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            id="chatcmpl-test",
            model="test-model",
            choices=[
                SimpleNamespace(
                    index=0,
                    message=SimpleNamespace(
                        role="assistant",
                        content=[
                            {"type": "text", "text": "A white image"},
                            {"type": "text", "text": "."},
                        ],
                    ),
                    finish_reason="stop",
                )
            ],
            usage=None,
        )
    )

    image = Image.new("RGB", (2, 2), color="white")

    result = await service.analyze_image(image)

    assert result == "A white image."

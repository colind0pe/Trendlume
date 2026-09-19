import json

import pytest

import src.providers.image.comfyui_image as comfyui_image_module
from src.core.exceptions import ProviderException
from src.providers.image.comfyui_image import (
    DEFAULT_COMFYUI_IMAGE_WORKFLOW,
    ComfyUIImageProvider,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict, content: bytes = b""):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeAsyncClient:
    instances = []
    always_fail_validation = False

    def __init__(self, **kwargs):
        self.posts = []
        type(self).instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json):
        self.posts.append(json)
        if self.always_fail_validation or len(self.posts) == 1:
            return FakeResponse(
                400,
                {
                    "error": {
                        "type": "prompt_outputs_failed_validation",
                        "message": "Prompt outputs failed validation",
                    },
                    "node_errors": {
                        "48": {
                            "errors": [
                                {
                                    "details": "unet_name: 'flux1-dev.safetensors' not in ['z_image_turbo_int8_convrot.safetensors']"
                                }
                            ]
                        }
                    },
                },
            )
        return FakeResponse(200, {"prompt_id": "prompt-1"})

    async def get(self, url, params=None):
        if "/history/" in url:
            return FakeResponse(
                200,
                {
                    "prompt-1": {
                        "status": {"completed": True},
                        "outputs": {"9": {"images": [{"filename": "test.png"}]}},
                    }
                },
            )
        return FakeResponse(200, {}, b"generated-image")


@pytest.mark.asyncio
async def test_implicit_default_workflow_retries_with_compatible_image_workflow(monkeypatch):
    FakeAsyncClient.instances.clear()
    FakeAsyncClient.always_fail_validation = False

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(comfyui_image_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(comfyui_image_module.asyncio, "sleep", no_sleep)

    provider = ComfyUIImageProvider(default_workflow="image/image_flux.json")
    result = await provider.generate_image("一只小狗", aspect_ratio="16:9")

    client = FakeAsyncClient.instances[-1]
    assert len(client.posts) == 2
    assert client.posts[0]["prompt"]["48"]["inputs"]["unet_name"] == "flux1-dev.safetensors"
    assert client.posts[1]["prompt"]["59"]["inputs"]["unet_name"] == "z_image_turbo_int8_convrot.safetensors"
    assert client.posts[1]["prompt"]["41"]["inputs"]["width"] == 1280
    assert client.posts[1]["prompt"]["41"]["inputs"]["height"] == 720
    assert result.image_bytes == b"generated-image"
    assert DEFAULT_COMFYUI_IMAGE_WORKFLOW == "image/image_flux.json"


@pytest.mark.asyncio
async def test_explicit_or_custom_workflow_does_not_use_compatibility_fallback(monkeypatch):
    FakeAsyncClient.always_fail_validation = True
    monkeypatch.setattr(comfyui_image_module.httpx, "AsyncClient", FakeAsyncClient)

    for provider, workflow in (
        (ComfyUIImageProvider(), "image/image_flux.json"),
        (ComfyUIImageProvider(default_workflow="image/image_qwen.json"), None),
    ):
        FakeAsyncClient.instances.clear()
        with pytest.raises(ProviderException, match="unet_name: 'flux1-dev.safetensors'"):
            await provider.generate_image(
                "一只小狗",
                aspect_ratio="16:9",
                workflow=workflow,
            )
        assert len(FakeAsyncClient.instances[-1].posts) == 1


def test_text_to_image_workflow_rejects_an_explicit_reference_image():
    provider = ComfyUIImageProvider(default_workflow="image/image_flux.json")

    with pytest.raises(ProviderException, match="LoadImage"):
        provider._load_workflow_graph(
            None,
            "一只小狗",
            720,
            1280,
            reference_image_name="reference.png",
        )

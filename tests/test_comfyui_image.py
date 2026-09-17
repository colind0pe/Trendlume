import json

import pytest

import src.providers.image.comfyui_image as comfyui_image_module
from src.core.exceptions import ProviderException
from src.providers.image.comfyui_image import (
    DEFAULT_COMFYUI_IMAGE_WORKFLOW,
    DEFAULT_COMFYUI_REFERENCE_IMAGE_WORKFLOW,
    ComfyUIImageProvider,
)
from src.providers.image.reference_frame import PreparedReferenceImage


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
    fail_first_prompt = True
    available_unet_names = None

    def __init__(self, **kwargs):
        self.posts = []
        self.uploads = []
        type(self).instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None, files=None, data=None):
        if url.endswith("/upload/image"):
            self.uploads.append({"files": files, "data": data})
            return FakeResponse(
                200,
                {"name": "uploaded-reference.png", "subfolder": "", "type": "input"},
            )
        self.posts.append(json)
        if self.always_fail_validation or (self.fail_first_prompt and len(self.posts) == 1):
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
        if "/object_info/UNETLoader" in url and type(self).available_unet_names is not None:
            return FakeResponse(
                200,
                {
                    "UNETLoader": {
                        "input": {
                            "required": {
                                "unet_name": [type(self).available_unet_names],
                            }
                        }
                    }
                },
            )
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
async def test_old_default_workflow_retries_with_compatible_image_workflow(monkeypatch):
    FakeAsyncClient.instances.clear()
    FakeAsyncClient.always_fail_validation = False
    FakeAsyncClient.fail_first_prompt = True

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
async def test_default_workflow_preflights_available_unet_model(monkeypatch):
    FakeAsyncClient.instances.clear()
    FakeAsyncClient.always_fail_validation = False
    FakeAsyncClient.fail_first_prompt = False
    monkeypatch.setattr(
        FakeAsyncClient,
        "available_unet_names",
        ["z_image_turbo_int8_convrot.safetensors"],
    )

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(comfyui_image_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(comfyui_image_module.asyncio, "sleep", no_sleep)

    provider = ComfyUIImageProvider(default_workflow=DEFAULT_COMFYUI_IMAGE_WORKFLOW)
    await provider.generate_image("一只小狗", aspect_ratio="16:9")

    client = FakeAsyncClient.instances[-1]
    assert len(client.posts) == 1
    assert client.posts[0]["prompt"]["59"]["inputs"]["unet_name"] == (
        "z_image_turbo_int8_convrot.safetensors"
    )


@pytest.mark.asyncio
async def test_explicit_or_custom_workflow_does_not_use_compatibility_fallback(monkeypatch):
    FakeAsyncClient.always_fail_validation = True
    FakeAsyncClient.fail_first_prompt = True
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


@pytest.mark.asyncio
async def test_reference_image_uploads_and_uses_builtin_img2img_workflow(monkeypatch, tmp_path):
    FakeAsyncClient.instances.clear()
    FakeAsyncClient.always_fail_validation = False
    FakeAsyncClient.fail_first_prompt = False

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(comfyui_image_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(comfyui_image_module.asyncio, "sleep", no_sleep)

    reference_path = tmp_path / "character.png"
    reference_path.write_bytes(b"reference-image")
    provider = ComfyUIImageProvider()
    result = await provider.generate_image(
        "角色抬手",
        aspect_ratio="16:9",
        reference_image_path=str(reference_path),
    )

    client = FakeAsyncClient.instances[-1]
    assert len(client.uploads) == 1
    assert client.uploads[0]["data"] == {"type": "input", "overwrite": "false"}
    assert len(client.posts) == 1
    graph = client.posts[0]["prompt"]
    assert DEFAULT_COMFYUI_REFERENCE_IMAGE_WORKFLOW == "image/image_flux2_img2img.json"
    assert graph["76"]["inputs"]["image"] == "uploaded-reference.png"
    assert graph["75:122"]["inputs"]["pixels"] == ["75:80", 0]
    assert graph["75:123"]["inputs"]["latent"] == ["75:122", 0]
    assert graph["75:66"]["inputs"]["width"] == ["75:99", 0]
    assert graph["75:66"]["inputs"]["height"] == ["75:99", 1]
    assert "角色抬手" in graph["75:74"]["inputs"]["text"]
    assert graph["75:82"]["class_type"] == "ConditioningZeroOut"
    assert graph["75:121"]["inputs"]["conditioning"] == ["75:82", 0]
    assert graph["75:62"]["inputs"]["steps"] == 4
    assert graph["75:63"]["inputs"]["cfg"] == 1
    assert result.image_bytes == b"generated-image"


@pytest.mark.asyncio
async def test_reference_upload_is_reused_for_same_file(monkeypatch, tmp_path):
    FakeAsyncClient.instances.clear()
    FakeAsyncClient.always_fail_validation = False
    FakeAsyncClient.fail_first_prompt = False
    monkeypatch.setattr(comfyui_image_module.httpx, "AsyncClient", FakeAsyncClient)

    reference_path = tmp_path / "character.png"
    reference_path.write_bytes(b"reference-image")
    provider = ComfyUIImageProvider()
    await provider.generate_image("第一个姿态", reference_image_path=str(reference_path))
    await provider.generate_image("第二个姿态", reference_image_path=str(reference_path))

    assert sum(len(client.uploads) for client in FakeAsyncClient.instances) == 1


@pytest.mark.asyncio
async def test_reference_frame_options_are_prepared_once_and_reused(monkeypatch, tmp_path):
    FakeAsyncClient.instances.clear()
    FakeAsyncClient.always_fail_validation = False
    FakeAsyncClient.fail_first_prompt = False
    monkeypatch.setattr(comfyui_image_module.httpx, "AsyncClient", FakeAsyncClient)

    prepared_options = []

    async def fake_prepare(path, options):
        prepared_options.append(options)
        return PreparedReferenceImage(path)

    monkeypatch.setattr(comfyui_image_module, "prepare_reference_image", fake_prepare)
    reference_path = tmp_path / "character.png"
    reference_path.write_bytes(b"reference-image")
    options = {
        "enabled": True,
        "width": 720,
        "height": 1280,
        "fit": "contain",
        "face_alignment": {
            "enabled": True,
            "source_box": {"x": 0.4, "y": 0.1, "width": 0.2, "height": 0.12},
        },
    }
    provider = ComfyUIImageProvider()
    await provider.generate_image(
        "第一个姿态",
        reference_image_path=str(reference_path),
        reference_image_options=options,
    )
    await provider.generate_image(
        "第二个姿态",
        reference_image_path=str(reference_path),
        reference_image_options=options,
    )

    assert len(prepared_options) == 1
    assert prepared_options[0]["width"] == 720
    assert prepared_options[0]["face_alignment"]["source_box"]["x"] == pytest.approx(0.4)
    assert sum(len(client.uploads) for client in FakeAsyncClient.instances) == 1


@pytest.mark.asyncio
async def test_reference_image_rejects_plain_text_to_image_workflow(monkeypatch, tmp_path):
    FakeAsyncClient.instances.clear()
    FakeAsyncClient.always_fail_validation = False
    FakeAsyncClient.fail_first_prompt = False
    monkeypatch.setattr(comfyui_image_module.httpx, "AsyncClient", FakeAsyncClient)

    reference_path = tmp_path / "character.png"
    reference_path.write_bytes(b"reference-image")
    provider = ComfyUIImageProvider()

    with pytest.raises(ProviderException, match="LoadImage"):
        await provider.generate_image(
            "角色抬手",
            workflow=DEFAULT_COMFYUI_IMAGE_WORKFLOW,
            reference_image_path=str(reference_path),
        )

    client = FakeAsyncClient.instances[-1]
    assert not client.uploads
    assert not client.posts

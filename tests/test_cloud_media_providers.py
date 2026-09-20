from __future__ import annotations

import base64
import json

import httpx
import pytest

from src.providers.image.aliyun_image import AliyunImageProvider
from src.providers.image.google_image import GoogleImageProvider
from src.providers.image.runninghub_image import RunningHubImageProvider
from src.providers.video.aliyun_video import AliyunVideoProvider
from src.providers.video.google_video import GoogleVideoProvider

REAL_ASYNC_CLIENT = httpx.AsyncClient


def _mock_http(monkeypatch, handler):
    transport = httpx.MockTransport(handler)

    def factory(*args, **kwargs):
        return REAL_ASYNC_CLIENT(*args, transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_aliyun_image_passes_all_references_and_downloads_result(monkeypatch, tmp_path):
    requests: list[httpx.Request] = []
    first = tmp_path / "character.png"
    second = tmp_path / "location.jpg"
    first.write_bytes(b"character")
    second.write_bytes(b"location")

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "output": {
                        "choices": [
                            {"message": {"content": [{"image": "https://cdn.example/qwen.png"}]}}
                        ]
                    },
                    "usage": {"output_width": 720, "output_height": 1280},
                },
                request=request,
            )
        return httpx.Response(
            200, content=b"qwen-image", headers={"content-type": "image/png"}, request=request
        )

    _mock_http(monkeypatch, handler)
    result = await AliyunImageProvider(api_key="key").generate_image(
        "镜头",
        reference_image_paths=[str(first), str(second)],
        width=720,
        height=1280,
    )

    payload = json.loads(requests[0].content)
    content = payload["input"]["messages"][0]["content"]
    assert [set(item) for item in content] == [{"image"}, {"image"}, {"text"}]
    assert content[0]["image"].startswith("data:image/png;base64,")
    assert result.image_bytes == b"qwen-image"
    assert (result.width, result.height) == (720, 1280)


@pytest.mark.asyncio
async def test_google_image_uses_inline_references_and_decodes_output(monkeypatch, tmp_path):
    reference = tmp_path / "actor.png"
    reference.write_bytes(b"actor")
    encoded = base64.b64encode(b"gemini-image").decode()
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"inlineData": {"mimeType": "image/png", "data": encoded}}]
                        }
                    }
                ]
            },
            request=request,
        )

    _mock_http(monkeypatch, handler)
    result = await GoogleImageProvider(api_key="key").generate_image(
        "镜头",
        aspect_ratio="16:9",
        reference_image_paths=[str(reference)],
    )

    payload = json.loads(requests[0].content)
    assert (
        payload["contents"][0]["parts"][0]["inlineData"]["data"]
        == base64.b64encode(b"actor").decode()
    )
    assert payload["generationConfig"]["responseFormat"]["image"]["aspectRatio"] == "16:9"
    assert result.image_bytes == b"gemini-image"


@pytest.mark.asyncio
async def test_aliyun_video_uses_first_and_last_frames(monkeypatch, tmp_path):
    first = tmp_path / "first.png"
    last = tmp_path / "last.png"
    first.write_bytes(b"first")
    last.write_bytes(b"last")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"output": {"task_id": "wan-task"}}, request=request)
        if request.url.path.endswith("/tasks/wan-task"):
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_status": "SUCCEEDED",
                        "video_url": "https://cdn.example/wan.mp4",
                    }
                },
                request=request,
            )
        return httpx.Response(200, content=b"wan-video", request=request)

    _mock_http(monkeypatch, handler)
    result = await AliyunVideoProvider(api_key="key").generate_video(
        "运镜",
        image_url=str(first),
        last_frame_url=str(last),
        duration_seconds=5,
    )

    payload = json.loads(requests[0].content)
    assert [item["type"] for item in payload["input"]["media"]] == ["first_frame", "last_frame"]
    assert "ratio" not in payload["parameters"]
    assert requests[0].headers["x-dashscope-async"] == "enable"
    assert result.video_bytes == b"wan-video"


@pytest.mark.asyncio
async def test_aliyun_video_uses_text_model_and_ratio_without_a_first_frame(monkeypatch):
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"output": {"task_id": "wan-task"}}, request=request)
        if request.url.path.endswith("/tasks/wan-task"):
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_status": "SUCCEEDED",
                        "video_url": "https://cdn.example/wan.mp4",
                    }
                },
                request=request,
            )
        return httpx.Response(200, content=b"wan-video", request=request)

    _mock_http(monkeypatch, handler)
    await AliyunVideoProvider(api_key="key", text_model="wan-text-test").generate_video(
        "运镜",
        aspect_ratio="9:16",
    )

    payload = json.loads(requests[0].content)
    assert payload["model"] == "wan-text-test"
    assert payload["parameters"]["ratio"] == "9:16"
    assert "media" not in payload["input"]


@pytest.mark.asyncio
async def test_google_video_passes_reference_images_and_downloads_operation(monkeypatch, tmp_path):
    reference = tmp_path / "actor.png"
    reference.write_bytes(b"actor")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"name": "operations/veo-task"}, request=request)
        if request.url.path.endswith("/operations/veo-task"):
            return httpx.Response(
                200,
                json={
                    "done": True,
                    "response": {
                        "generateVideoResponse": {
                            "generatedSamples": [{"video": {"uri": "https://cdn.example/veo.mp4"}}]
                        }
                    },
                },
                request=request,
            )
        return httpx.Response(200, content=b"veo-video", request=request)

    _mock_http(monkeypatch, handler)
    result = await GoogleVideoProvider(api_key="key").generate_video(
        "运镜",
        reference_image_urls=[str(reference)],
        duration_seconds=5,
    )

    payload = json.loads(requests[0].content)
    assert payload["instances"][0]["referenceImages"][0]["referenceType"] == "asset"
    assert payload["parameters"]["durationSeconds"] == "4"
    assert result.video_bytes == b"veo-video"


@pytest.mark.asyncio
async def test_runninghub_uploads_reference_nodes_and_downloads_image(monkeypatch, tmp_path):
    reference = tmp_path / "actor.png"
    reference.write_bytes(b"actor")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/upload"):
            return httpx.Response(
                200, json={"code": 0, "data": {"fileName": "api/actor.png"}}, request=request
            )
        if request.url.path.endswith("/create"):
            return httpx.Response(
                200, json={"code": 0, "data": {"taskId": "rh-task"}}, request=request
            )
        if request.url.path.endswith("/outputs"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": [{"fileType": "png", "fileUrl": "https://cdn.example/rh.png"}],
                },
                request=request,
            )
        return httpx.Response(
            200, content=b"rh-image", headers={"content-type": "image/png"}, request=request
        )

    _mock_http(monkeypatch, handler)
    provider = RunningHubImageProvider(
        api_key="key",
        workflow_id="workflow-1",
        prompt_node_id="6",
        reference_node_ids="10",
    )
    result = await provider.generate_image("镜头", reference_image_paths=[str(reference)])

    create_request = next(request for request in requests if request.url.path.endswith("/create"))
    nodes = json.loads(create_request.content)["nodeInfoList"]
    assert {item["nodeId"]: item["fieldValue"] for item in nodes} == {
        "6": "镜头",
        "10": "api/actor.png",
    }
    assert result.image_bytes == b"rh-image"

from __future__ import annotations

import base64
import json

import httpx
import pytest

from src.core.exceptions import ProviderException
from src.providers.image.style_presets import IMAGE_STYLE_PRESETS
from src.providers.image.volcengine_image import VolcengineImageProvider
from src.providers.tts.volcengine_tts import VolcengineTTSProvider
from src.providers.video.volcengine_video import VolcengineVideoProvider

REAL_ASYNC_CLIENT = httpx.AsyncClient


def test_doubao_tts_speed_ratio_maps_to_v3_speech_rate():
    provider = VolcengineTTSProvider(api_key="api-key", default_speed_ratio=1.4)

    assert provider.default_speed_ratio == 1.4
    assert provider._payload("测试", provider.default_voice, None)["req_params"]["audio_params"]["speech_rate"] == 40
    assert provider._payload("测试", provider.default_voice, 0.5)["req_params"]["audio_params"]["speech_rate"] == -50
    assert provider._payload("测试", provider.default_voice, 2.5)["req_params"]["audio_params"]["speech_rate"] == 100


def _mock_async_client(monkeypatch, module, handler):
    transport = httpx.MockTransport(handler)

    def factory(*args, **kwargs):
        return REAL_ASYNC_CLIENT(*args, transport=transport, **kwargs)

    monkeypatch.setattr(module.httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_seedream_uses_ark_auth_normalized_size_and_downloads_url(monkeypatch):
    import src.providers.image.volcengine_image as module

    requests: list[httpx.Request] = []
    image_bytes = b"valid-image-fixture"

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/images/generations"):
            return httpx.Response(
                200,
                json={"data": [{"url": "https://cdn.example/image.png", "size": "1440*2560"}]},
                request=request,
            )
        return httpx.Response(
            200,
            content=image_bytes,
            headers={"content-type": "image/png"},
            request=request,
        )

    _mock_async_client(monkeypatch, module, handler)
    provider = VolcengineImageProvider(api_key="ark-key")

    result = await provider.generate_image(
        "A test storyboard",
        style_preset="chinese_ink",
        width=720,
        height=1280,
    )

    assert result.image_bytes == image_bytes
    assert result.width == 1440
    assert result.height == 2560
    assert requests[0].headers["authorization"] == "Bearer ark-key"
    payload = json.loads(requests[0].content)
    assert payload["model"] == "doubao-seedream-5-0-260128"
    assert payload["size"] == "1440x2560"
    assert payload["prompt"] == f"{IMAGE_STYLE_PRESETS['chinese_ink']['description']}，A test storyboard"
    assert payload["stream"] is False
    assert requests[1].url == "https://cdn.example/image.png"


@pytest.mark.asyncio
async def test_seedream_accepts_base64_and_rejects_empty_media(monkeypatch):
    import src.providers.image.volcengine_image as module

    encoded = base64.b64encode(b"base64-image").decode("ascii")

    async def base64_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"b64_json": encoded}]}, request=request)

    _mock_async_client(monkeypatch, module, base64_handler)
    result = await VolcengineImageProvider(api_key="ark-key").generate_image("test")
    assert result.image_bytes == b"base64-image"

    async def empty_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=b"", request=request)
        return httpx.Response(200, json={"data": [{"url": "https://cdn.example/empty"}]}, request=request)

    _mock_async_client(monkeypatch, module, empty_handler)
    with pytest.raises(ProviderException, match="空图像"):
        await VolcengineImageProvider(api_key="ark-key").generate_image("test")


@pytest.mark.asyncio
async def test_seedance_creates_polls_downloads_and_disables_audio_by_default(monkeypatch):
    import src.providers.video.volcengine_video as module

    requests: list[httpx.Request] = []
    poll_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal poll_count
        requests.append(request)
        if request.url.path.endswith("/contents/generations/tasks"):
            return httpx.Response(200, json={"id": "task-123"}, request=request)
        if request.url.path.endswith("/contents/generations/tasks/task-123"):
            poll_count += 1
            if poll_count == 1:
                return httpx.Response(200, json={"status": "running"}, request=request)
            return httpx.Response(
                200,
                json={"status": "succeeded", "content": {"video_url": "https://cdn.example/video.mp4"}},
                request=request,
            )
        return httpx.Response(200, content=b"video-fixture", request=request)

    _mock_async_client(monkeypatch, module, handler)
    provider = VolcengineVideoProvider(api_key="ark-key", poll_interval=0.5)

    result = await provider.generate_video(
        "A person turns toward the camera",
        image_url="data:image/png;base64,ZmFrZQ==",
        duration_seconds=4.4,
    )

    assert result.video_bytes == b"video-fixture"
    assert result.duration_seconds == 4.0
    assert len(requests) == 4
    create_payload = json.loads(requests[0].content)
    assert create_payload["model"] == "doubao-seedance-2-0-260128"
    assert create_payload["duration"] == 4
    assert create_payload["generate_audio"] is False
    assert create_payload["content"][1]["role"] == "first_frame"
    assert requests[0].headers["authorization"] == "Bearer ark-key"
    assert "authorization" not in requests[-1].headers


@pytest.mark.asyncio
async def test_seedance_reports_task_failure_and_generation_timeout(monkeypatch):
    import src.providers.video.volcengine_video as module

    async def failed_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"id": "failed-task"}, request=request)
        return httpx.Response(
            200,
            json={"status": "failed", "error": {"message": "quota exceeded"}},
            request=request,
        )

    _mock_async_client(monkeypatch, module, failed_handler)
    with pytest.raises(ProviderException, match="quota exceeded"):
        await VolcengineVideoProvider(api_key="key", poll_interval=0.5).generate_video("test")

    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"id": "slow-task"}, request=request)
        return httpx.Response(200, json={"status": "running"}, request=request)

    _mock_async_client(monkeypatch, module, timeout_handler)
    with pytest.raises(ProviderException, match="等待超时"):
        await VolcengineVideoProvider(
            api_key="key", generation_timeout=0.0, poll_interval=0.5
        ).generate_video("test")

    async def request_timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream timeout", request=request)

    _mock_async_client(monkeypatch, module, request_timeout_handler)
    with pytest.raises(ProviderException, match="单次请求"):
        await VolcengineVideoProvider(api_key="key").generate_video("test")


@pytest.mark.asyncio
async def test_doubao_tts_http_chunked_aggregates_frames_and_duration(monkeypatch):
    import src.providers.tts.volcengine_tts as module

    first = base64.b64encode(b"mp3-").decode("ascii")
    second = base64.b64encode(b"fixture").decode("ascii")

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.headers["x-api-key"] == "api-key"
        assert request.headers["x-api-resource-id"] == "resource-id"
        assert "x-api-app-key" not in request.headers
        assert "x-api-access-key" not in request.headers
        assert "authorization" not in request.headers
        assert "x-api-sequence" not in request.headers
        assert payload["req_params"]["speaker"] == "zh_female_vv_uranus_bigtts"
        assert payload["req_params"]["audio_params"]["sample_rate"] == 24000
        assert payload["req_params"]["audio_params"]["speech_rate"] == 0
        # HTTP Chunked responses may concatenate JSON frames without a newline.
        body = "".join(
            [
                json.dumps({"code": 0, "data": first}),
                json.dumps(
                    {
                        "code": 20000000,
                        "data": second,
                        "addition": json.dumps({"duration": "1234"}),
                    }
                ),
            ]
        )
        return httpx.Response(
            200,
            content=body.encode("utf-8"),
            headers={"content-type": "application/json"},
            request=request,
        )

    _mock_async_client(monkeypatch, module, handler)
    result = await VolcengineTTSProvider(
        api_key="api-key", resource_id="resource-id"
    ).synthesize("你好")

    assert result.audio_bytes == b"mp3-fixture"
    assert result.duration_seconds == 1.234
    assert result.format == "mp3"


@pytest.mark.asyncio
async def test_doubao_tts_honors_explicit_voice_override(monkeypatch):
    import src.providers.tts.volcengine_tts as module

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["req_params"]["speaker"] == "voice-override"
        return httpx.Response(
            200,
            content=json.dumps(
                {"code": 20000000, "data": base64.b64encode(b"audio").decode()}
            ).encode(),
            headers={"content-type": "application/json"},
            request=request,
        )

    _mock_async_client(monkeypatch, module, handler)
    result = await VolcengineTTSProvider(
        api_key="api-key", default_voice="default-voice"
    ).synthesize("你好", voice_id="voice-override")

    assert result.audio_bytes == b"audio"


@pytest.mark.asyncio
async def test_doubao_tts_raises_on_business_error_and_empty_audio(monkeypatch):
    import src.providers.tts.volcengine_tts as module

    async def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=json.dumps({"code": 4501, "message": "invalid resource"}).encode(),
            headers={"content-type": "application/json"},
            request=request,
        )

    _mock_async_client(monkeypatch, module, error_handler)
    provider = VolcengineTTSProvider(api_key="api-key")
    with pytest.raises(ProviderException, match="invalid resource"):
        await provider.synthesize("test")

    async def empty_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=json.dumps({"code": 3000, "sequence": -1}).encode(),
            headers={"content-type": "application/json"},
            request=request,
        )

    _mock_async_client(monkeypatch, module, empty_handler)
    with pytest.raises(ProviderException, match="空音频"):
        await provider.synthesize("test")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "body", "expected_message"),
    [
        (401, {"message": "invalid access token"}, "invalid access token"),
        (
            403,
            {
                "header": {
                    "code": 45000030,
                    "message": "[resource_id=seed-tts-2.0] requested resource not granted",
                }
            },
            "Resource ID 未授权",
        ),
    ],
)
async def test_doubao_tts_reports_http_errors(
    monkeypatch, status_code, body, expected_message
):
    import src.providers.tts.volcengine_tts as module

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            content=json.dumps(body).encode(),
            headers={"content-type": "application/json"},
            request=request,
        )

    _mock_async_client(monkeypatch, module, handler)
    with pytest.raises(ProviderException, match=expected_message):
        await VolcengineTTSProvider(api_key="api-key").synthesize("test")

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from src.core.exceptions import ProviderException
from src.domain.enums import AssetType
from src.models import AssetModel, ProjectModel, SceneModel, TaskModel
from src.models.workflow import WorkflowStepRunModel
from src.providers.image.protocol import ImageResult
from src.providers.materials import (
    MaterialCandidate,
    MaterialDownload,
    PexelsVideoProvider,
)
from src.providers.video.protocol import VideoResult
from src.schemas.generation import StructuredSceneScript, StructuredScript
from src.services.asset_service import AssetService
from src.services.generation_service import GenerationService
from src.services.material_service import (
    MaterialImportRequest,
    MaterialSearchRequest,
    MaterialService,
    _material_search_keywords,
)
from src.services.provider_manager import ProviderManager
from src.services.rendering_service import RenderingService
from src.services.template_renderer import TemplateRenderer
from src.storage.local_storage import LocalStorageService
from src.tasks.executor import VideoWorkflowExecutor
from src.tasks.job import Job

VALID_VIDEO_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mock.mp4"


def _patch_httpx_download_client(monkeypatch, handler):
    real_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def client_factory(**kwargs):
        return real_async_client(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)


def _stub_pipeline_rendering(monkeypatch, storage, fixture: Path):
    async def render_template(*_args, output_path, **_kwargs):
        output_path.write_bytes(b"template frame")

    monkeypatch.setattr(TemplateRenderer, "render", render_template)

    async def fake_ffmpeg(_command, output_path):
        output_path.write_bytes(fixture.read_bytes())
        return True

    return lambda session: RenderingService(
        session, storage=storage, ffmpeg_runner=fake_ffmpeg
    )


def test_rendition_selection_prefers_target_aspect_before_pixel_distance():
    renditions = [
        {"link": "https://videos.pexels.com/4x3.mp4", "width": 1200, "height": 900},
        {"link": "https://videos.pexels.com/16x9.mp4", "width": 1280, "height": 720},
    ]

    selected = PexelsVideoProvider.pick_rendition(
        renditions,
        "16:9",
        min_short_edge=720,
        target_width=512,
        target_height=288,
    )

    assert selected is not None
    assert (selected["width"], selected["height"]) == (1280, 720)

    selected = PexelsVideoProvider.pick_rendition(
        [
            {"link": "https://videos.pexels.com/720.mp4", "width": 720, "height": 1280},
            {"link": "https://videos.pexels.com/1080.mp4", "width": 1080, "height": 1920},
        ],
        "9:16",
        min_short_edge=480,
        target_width=720,
        target_height=1280,
    )
    assert selected is not None
    assert (selected["width"], selected["height"]) == (720, 1280)


@pytest.mark.asyncio
async def test_pexels_search_filters_orientation_and_selects_rendition(monkeypatch, tmp_path):
    provider = PexelsVideoProvider(api_key="secret")
    requests: list[dict] = []
    downloaded: list[str] = []

    async def fake_json(url, *, params=None, headers=None):
        requests.append({"url": url, "params": params, "headers": headers})
        return {
            "videos": [
                {
                    "id": 11,
                    "duration": 6,
                    "url": "https://www.pexels.com/video/11/",
                    "user": {"name": "Author", "url": "https://www.pexels.com/@author"},
                    "video_files": [
                        {"link": "https://videos.pexels.com/640.mp4", "width": 640, "height": 1138},
                        {"link": "https://videos.pexels.com/720.mp4", "width": 720, "height": 1280},
                        {"link": "https://videos.pexels.com/1080.mp4", "width": 1080, "height": 1920},
                    ],
                },
                {
                    "id": 12,
                    "duration": 8,
                    "video_files": [{"link": "https://videos.pexels.com/landscape.mp4", "width": 1920, "height": 1080}],
                },
                {
                    "id": 13,
                    "duration": 2,
                    "video_files": [{"link": "https://videos.pexels.com/short.mp4", "width": 1080, "height": 1920}],
                },
            ]
        }

    async def fake_download(url, destination, file_name):
        downloaded.append(url)
        destination.write_bytes(b"video")
        return MaterialDownload(file_path=destination, file_name=file_name, size_bytes=5)

    monkeypatch.setattr(provider, "get_json", fake_json)
    monkeypatch.setattr(provider, "download_url", fake_download)

    candidates = await provider.search("city lights", "9:16", min_duration_seconds=4, limit=20)

    assert [item.external_id for item in candidates] == ["11"]
    assert candidates[0].width == 1080
    assert candidates[0].height == 1920
    assert requests[0]["params"] == {
        "query": "city lights",
        "orientation": "portrait",
        "size": "medium",
        "locale": "en-US",
        "per_page": 20,
    }
    assert requests[0]["headers"] == {"Authorization": "secret"}

    destination = tmp_path / "fixture-download.mp4"
    await provider.download("11", "9:16", destination)
    assert downloaded == ["https://videos.pexels.com/1080.mp4"]
    destination.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_pexels_download_fetches_video_detail_when_rendition_cache_is_empty(monkeypatch, tmp_path):
    provider = PexelsVideoProvider(api_key="secret")
    detail_urls: list[str] = []

    async def fake_json(url, *, params=None, headers=None):
        detail_urls.append(url)
        assert params is None
        assert headers == {"Authorization": "secret"}
        return {
            "video_files": [
                {"link": "https://videos.pexels.com/detail-720.mp4", "width": 720, "height": 1280}
            ]
        }

    async def fake_download(url, destination, file_name):
        assert url == "https://videos.pexels.com/detail-720.mp4"
        destination.write_bytes(b"video")
        return MaterialDownload(file_path=destination, file_name=file_name, size_bytes=5)

    monkeypatch.setattr(provider, "get_json", fake_json)
    monkeypatch.setattr(provider, "download_url", fake_download)
    assert provider._renditions == {}

    destination = tmp_path / "detail-download.mp4"
    await provider.download("42", "9:16", destination)

    assert detail_urls == ["https://api.pexels.com/v1/videos/videos/42"]
    assert provider._renditions["42"]
    destination.unlink(missing_ok=True)


def test_pexels_download_url_requires_https_and_provider_host():
    provider = PexelsVideoProvider(api_key="secret")

    with pytest.raises(Exception, match="HTTPS"):
        provider._allow_download_url("http://videos.pexels.com/video.mp4")
    with pytest.raises(Exception, match="允许的域名"):
        provider._allow_download_url("https://downloads.example.invalid/video.mp4")
    with pytest.raises(Exception, match="443"):
        provider._allow_download_url("https://videos.pexels.com:8443/video.mp4")
    with pytest.raises(Exception, match="允许的域名"):
        provider._allow_download_url("https://127.0.0.1/video.mp4")


@pytest.mark.asyncio
async def test_pexels_download_host_dns_rejects_private_addresses(monkeypatch):
    provider = PexelsVideoProvider(api_key="secret")

    def fake_getaddrinfo(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443))]

    import socket

    monkeypatch.setattr("src.providers.materials._http.socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(Exception, match="非公网"):
        await provider._validate_public_host("https://videos.pexels.com/video.mp4")


@pytest.mark.asyncio
async def test_download_accepts_real_httpx_response_200(monkeypatch, tmp_path):
    provider = PexelsVideoProvider(api_key="secret")
    fixture = VALID_VIDEO_FIXTURE
    destination = tmp_path / "response-200.mp4"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "video/mp4"},
            content=fixture.read_bytes(),
            request=request,
        )

    async def skip_dns(_url):
        return None

    monkeypatch.setattr(provider, "_validate_public_host", skip_dns)
    _patch_httpx_download_client(monkeypatch, handler)

    result = await provider.download_url(
        "https://videos.pexels.com/fixture.mp4",
        destination,
        "fixture.mp4",
    )

    assert result.file_path == destination
    assert result.mime_type == "video/mp4"
    assert result.size_bytes == fixture.stat().st_size
    assert destination.read_bytes() == fixture.read_bytes()


@pytest.mark.asyncio
async def test_download_rejects_illegal_redirect_target_and_cleans_file(monkeypatch, tmp_path):
    provider = PexelsVideoProvider(api_key="secret")
    destination = tmp_path / "illegal-target.mp4"
    destination.write_bytes(b"partial")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            308,
            headers={"location": "https://downloads.example.invalid/video.mp4"},
            request=request,
        )

    async def skip_dns(_url):
        return None

    monkeypatch.setattr(provider, "_validate_public_host", skip_dns)
    _patch_httpx_download_client(monkeypatch, handler)

    with pytest.raises(ProviderException, match="允许的域名"):
        await provider.download_url(
            "https://videos.pexels.com/start.mp4",
            destination,
            "fixture.mp4",
        )

    assert not destination.exists()


def test_pexels_rendition_rejects_non_mp4_file_types():
    assert PexelsVideoProvider.pick_rendition(
        [{"link": "https://videos.pexels.com/video.webm", "file_type": "video/webm", "width": 720, "height": 1280}],
        "9:16",
        min_short_edge=480,
    ) is None


class _FakeMaterialProvider:
    name = "pexels"

    def __init__(self, fixture: Path):
        self.fixture = fixture
        self.search_calls = 0

    async def search_videos(self, request):
        self.search_calls += 1
        return [
            MaterialCandidate(
                provider="pexels",
                external_id="fixture-1",
                title="Fixture video",
                source_page_url="https://www.pexels.com/video/fixture-1/",
                author="Fixture Author",
                author_url="https://www.pexels.com/@fixture",
                duration_seconds=0.5,
                width=64,
                height=64,
            )
        ]

    async def download(self, external_id: str, aspect_ratio: str = "9:16", destination: Path | None = None):
        assert destination is not None
        destination.write_bytes(self.fixture.read_bytes())
        return MaterialDownload(destination, "fixture.mp4", size_bytes=destination.stat().st_size)


@pytest.mark.asyncio
async def test_acquire_for_scene_retries_with_a_changed_keyword(test_session, tmp_path):
    project_id = f"project_{uuid4().hex[:8]}"
    task_id = f"task_{uuid4().hex[:8]}"
    scene_id = f"scene_{uuid4().hex[:8]}"
    project = ProjectModel(id=project_id, name="Online material fallback")
    task = TaskModel(
        id=task_id,
        project_id=project_id,
        title="Online material fallback task",
        input_payload={"content_mode": "online_asset"},
    )
    scene = SceneModel(id=scene_id, task_id=task_id, sequence_index=0, duration_seconds=0.1)
    test_session.add_all([project, task, scene])
    await test_session.commit()

    fixture = VALID_VIDEO_FIXTURE
    search_keywords: list[str] = []

    class FallbackMaterialProvider:
        name = "material-test"

        async def search_videos(self, request):
            search_keywords.append(request.keyword)
            if len(search_keywords) == 1:
                return []
            return [
                MaterialCandidate(
                    provider=self.name,
                    external_id="fallback-1",
                    title="Fallback fixture",
                    duration_seconds=1.0,
                    width=1280,
                    height=720,
                )
            ]

        async def download(self, external_id, aspect_ratio="16:9", destination=None):
            assert external_id == "fallback-1"
            assert destination is not None
            destination.write_bytes(fixture.read_bytes())
            return MaterialDownload(destination, "fallback.mp4", size_bytes=destination.stat().st_size)

    service = MaterialService(
        test_session,
        storage=LocalStorageService(tmp_path / "fallback-storage"),
        providers={"material-test": FallbackMaterialProvider()},
    )
    asset, source, reused = await service.acquire_for_scene(
        project_id,
        task_id,
        scene_id,
        "an extremely rare subject prompt",
        "16:9",
        "material-test",
        min_duration_seconds=0.1,
    )

    assert reused is False
    assert asset.metadata_json["search_keyword"] == source.search_keyword
    assert len(search_keywords) == 2
    assert search_keywords[0] != search_keywords[1]
    assert search_keywords == _material_search_keywords("an extremely rare subject prompt", "16:9")[:2]


@pytest.mark.asyncio
async def test_material_search_cache_and_import_preserve_provenance(test_session, tmp_path):
    project_id = f"project_{uuid4().hex[:8]}"
    task_id = f"task_{uuid4().hex[:8]}"
    scene_id = f"scene_{uuid4().hex[:8]}"
    project = ProjectModel(id=project_id, name="Online materials")
    task = TaskModel(
        id=task_id,
        project_id=project_id,
        title="Online material task",
        input_payload={"content_mode": "online_asset"},
    )
    scene = SceneModel(id=scene_id, task_id=task_id, sequence_index=0, duration_seconds=0.4)
    test_session.add_all([project, task, scene])
    await test_session.commit()

    storage = LocalStorageService(tmp_path / "storage")
    provider = _FakeMaterialProvider(VALID_VIDEO_FIXTURE)
    service = MaterialService(test_session, storage=storage, providers={"material-test": provider})
    request = MaterialSearchRequest(provider_id="material-test", keyword="fixture", min_duration_seconds=0.1)

    _, cached, candidates = await service.search(project_id, request)
    assert cached is False
    _, cached_again, candidates_again = await service.search(project_id, request)
    assert cached_again is True
    assert candidates_again == candidates
    assert provider.search_calls == 1

    asset, source, reused = await service.import_candidate(
        project_id,
        MaterialImportRequest(
            candidate_id=candidates[0].candidate_id,
            provider_id="material-test",
            task_id=task_id,
            scene_id=scene_id,
            keyword="fixture",
            aspect_ratio="9:16",
        ),
    )

    assert reused is False
    assert asset.asset_type == "video"
    assert asset.metadata_json["source_kind"] == "online_asset"
    assert asset.metadata_json["provider"] == "pexels"
    assert asset.metadata_json["external_id"] == "fixture-1"
    assert asset.metadata_json["duration_source"] == "ffprobe"
    assert asset.metadata_json["content_sha256"] == source.content_sha256
    assert "api_key" not in asset.metadata_json
    assert "download" not in str(asset.metadata_json).lower()
    await test_session.refresh(scene)
    assert scene.media_asset_id == asset.id
    assert scene.layout_params["media_type"] == "video"
    assert scene.layout_params["media_source"] == "online"


@pytest.mark.asyncio
@pytest.mark.parametrize("media_kind", ["image", "video"])
async def test_ai_scene_override_persists_generated_media_source(test_session, tmp_path, monkeypatch, media_kind):
    project_id = f"project_{uuid4().hex[:8]}"
    task_id = f"task_{uuid4().hex[:8]}"
    scene_id = f"scene_{uuid4().hex[:8]}"
    project = ProjectModel(id=project_id, name="Generated override")
    task = TaskModel(
        id=task_id,
        project_id=project_id,
        title="Generated override task",
        input_payload={"content_mode": "online_asset", "template_id": "video_full_overlay"},
    )
    scene = SceneModel(
        id=scene_id,
        task_id=task_id,
        visual_prompt="city lights",
        duration_seconds=0.5,
        layout_params={"media_type": "video", "media_source": "online"},
    )
    test_session.add_all([project, task, scene])
    await test_session.commit()

    service = GenerationService(test_session, storage=LocalStorageService(tmp_path / "storage"))
    fixture = VALID_VIDEO_FIXTURE
    if media_kind == "image":
        class ImageProvider:
            name = "fixture-image"

            async def generate_image(self, *_args, **_kwargs):
                return ImageResult(image_bytes=b"fixture-image", width=720, height=1280)

        monkeypatch.setattr(service, "_get_image_provider", lambda: _return(ImageProvider()))
        updated = await service.generate_scene_image(scene_id)
        expected_type, expected_mode = "image", "generated_image"
    else:
        class VideoProvider:
            name = "fixture-video"

            async def generate_video(self, **_kwargs):
                return VideoResult(
                    video_bytes=fixture.read_bytes(),
                    duration_seconds=0.5,
                    width=64,
                    height=64,
                )

        monkeypatch.setattr(service, "_get_video_provider", lambda: _return(VideoProvider()))
        updated = await service.generate_scene_video(scene_id)
        expected_type, expected_mode = "video", "generated_video"

    await test_session.commit()
    await test_session.refresh(updated)
    assert updated.layout_params["media_type"] == expected_type
    assert updated.layout_params["media_source"] == "generated"
    assert updated.layout_params["generated_content_mode"] == expected_mode


@pytest.mark.asyncio
async def test_online_pipeline_preserves_generated_scene_override(test_session, tmp_path, monkeypatch):
    project_id = f"project_{uuid4().hex[:8]}"
    task_id = f"task_{uuid4().hex[:8]}"
    scene_id = f"scene_{uuid4().hex[:8]}"
    project = ProjectModel(id=project_id, name="Generated online override")
    task = TaskModel(
        id=task_id,
        project_id=project_id,
        title="Generated online override task",
        input_payload={
            "topic": "generated override",
            "content_mode": "online_asset",
            "visual_mode": "video",
            "material_provider_id": "prov_material_pexels",
            "template_id": "video_full_overlay",
            "enable_research": False,
            "manual_storyboard_version": "manual-override-1",
        },
    )
    scene = SceneModel(
        id=scene_id,
        task_id=task_id,
        sequence_index=0,
        visual_prompt="city lights",
        duration_seconds=0.5,
        layout_params={
            "media_type": "video",
            "media_source": "generated",
            "generated_content_mode": "generated_video",
        },
    )
    test_session.add_all([project, task, scene])
    await test_session.commit()

    fixture = VALID_VIDEO_FIXTURE
    storage = LocalStorageService(tmp_path / "pipeline-storage")
    asset_service = AssetService(test_session, storage=storage)
    generated_asset = await asset_service.save_asset(
        fixture.read_bytes(),
        "generated.mp4",
        "video/mp4",
        AssetType.VIDEO,
        project_id=project_id,
        duration_seconds=0.5,
        width=64,
        height=64,
        metadata={"provider": "fixture-video"},
    )
    audio_asset = await asset_service.save_asset(
        fixture.read_bytes(),
        "voice.mp4",
        "video/mp4",
        AssetType.AUDIO,
        project_id=project_id,
        duration_seconds=0.5,
        metadata={"provider": "fixture-voice"},
    )
    scene.media_asset_id = generated_asset.id
    scene.audio_asset_id = audio_asset.id
    await test_session.commit()

    async def fail_online_acquire(*_args, **_kwargs):
        raise AssertionError("generated scene must not reacquire online material")

    monkeypatch.setattr(MaterialService, "acquire_for_scene", fail_online_acquire)

    rendering_factory = _stub_pipeline_rendering(monkeypatch, storage, fixture)

    result = await VideoWorkflowExecutor(
        session_factory=lambda: _session_context(test_session),
        rendering_service_factory=rendering_factory,
    ).execute(Job(task_id=task_id))

    assert result["video_status"] == "ready"
    await test_session.refresh(scene)
    assert scene.media_asset_id == generated_asset.id
    assert scene.layout_params["media_source"] == "generated"


@pytest.mark.asyncio
async def test_online_single_scene_refresh_replaces_generated_override(test_session, tmp_path, monkeypatch):
    project_id = f"project_{uuid4().hex[:8]}"
    task_id = f"task_{uuid4().hex[:8]}"
    scene_id = f"scene_{uuid4().hex[:8]}"
    project = ProjectModel(id=project_id, name="Online refresh")
    task = TaskModel(
        id=task_id,
        project_id=project_id,
        title="Online refresh task",
        input_payload={
            "content_mode": "online_asset",
            "visual_mode": "video",
            "material_provider_id": "prov_material_pexels",
            "template_id": "video_full_overlay",
            "enable_research": False,
        },
    )
    scene = SceneModel(
        id=scene_id,
        task_id=task_id,
        sequence_index=0,
        visual_prompt="city lights",
        duration_seconds=0.4,
        layout_params={
            "media_type": "video",
            "media_source": "generated",
            "generated_content_mode": "generated_video",
        },
    )
    test_session.add_all([project, task, scene])
    await test_session.commit()

    fixture = VALID_VIDEO_FIXTURE
    storage = LocalStorageService(tmp_path / "refresh-storage")
    old_asset = await AssetService(test_session, storage=storage).save_asset(
        fixture.read_bytes(),
        "generated.mp4",
        "video/mp4",
        AssetType.VIDEO,
        project_id=project_id,
        duration_seconds=0.5,
        width=64,
        height=64,
        metadata={"provider": "fixture-video"},
    )
    scene.media_asset_id = old_asset.id
    await test_session.commit()

    provider = _FakeMaterialProvider(fixture)
    monkeypatch.setattr(ProviderManager, "get_material", lambda self, provider_id=None: _return(provider))

    result = await VideoWorkflowExecutor(
        session_factory=lambda: _session_context(test_session),
        rendering_service_factory=lambda session: RenderingService(session, storage=storage),
    ).execute(
        Job(
            task_id=task_id,
            params={
                "single_step": "assets",
                "single_unit": scene_id,
                "content_mode_override": "online_asset",
            },
        )
    )

    assert result["asset_id"] != old_asset.id
    await test_session.refresh(scene)
    refreshed_asset = await test_session.get(AssetModel, scene.media_asset_id)
    assert refreshed_asset is not None
    assert refreshed_asset.metadata_json["source_kind"] == "online_asset"
    assert scene.layout_params["media_source"] == "online"


@pytest.mark.asyncio
async def test_online_material_pipeline_binds_distinct_video_assets(test_session, tmp_path, monkeypatch):
    project_id = f"project_{uuid4().hex[:8]}"
    task_id = f"task_{uuid4().hex[:8]}"
    project = ProjectModel(id=project_id, name="Online pipeline")
    task = TaskModel(
        id=task_id,
        project_id=project_id,
        title="Online pipeline task",
        input_payload={
            "topic": "online footage",
            "content_mode": "online_asset",
            "visual_mode": "video",
            "material_provider_id": "prov_material_pexels",
            "template_id": "video_full_overlay",
            "enable_research": False,
            "target_scene_count": 2,
        },
    )
    scenes = [
        SceneModel(
            id=f"scene_{uuid4().hex[:8]}",
            task_id=task_id,
            sequence_index=index,
            narration_text=f"Narration keywords for scene {index}",
            visual_prompt="city lights",
            duration_seconds=0.4,
        )
        for index in range(2)
    ]
    test_session.add_all([project, task, *scenes])
    await test_session.commit()

    fixture = VALID_VIDEO_FIXTURE
    second_fixture = tmp_path / "second.mp4"
    second_fixture.write_bytes(fixture.read_bytes() + b"\0")

    class PipelineProvider(_FakeMaterialProvider):
        def __init__(self, fixture):
            super().__init__(fixture)
            self.search_keywords = []

        async def search_videos(self, request):
            self.search_calls += 1
            self.search_keywords.append(request.keyword)
            return [
                MaterialCandidate(
                    provider="pexels",
                    external_id="pipeline-1",
                    title="First",
                    source_page_url="https://www.pexels.com/video/pipeline-1/",
                    duration_seconds=0.5,
                    width=64,
                    height=64,
                ),
                MaterialCandidate(
                    provider="pexels",
                    external_id="pipeline-2",
                    title="Second",
                    source_page_url="https://www.pexels.com/video/pipeline-2/",
                    duration_seconds=0.5,
                    width=64,
                    height=64,
                ),
            ]

    provider = PipelineProvider(fixture)
    # Candidate identity is asserted through external_id; reusing the valid
    # fixture variant keeps this workflow test independent of a second FFmpeg process.
    original_download = provider.download

    async def download_variant(
        external_id: str,
        aspect_ratio: str = "9:16",
        destination: Path | None = None,
    ):
        assert destination is not None
        if external_id == "pipeline-2":
            destination.write_bytes(second_fixture.read_bytes())
            return MaterialDownload(destination, "second.mp4", size_bytes=destination.stat().st_size)
        return await original_download(external_id, aspect_ratio, destination)

    provider.download = download_variant
    monkeypatch.setattr(ProviderManager, "get_material", lambda self, provider_id=None: _return(provider))

    storage = LocalStorageService(tmp_path / "pipeline-storage")

    rendering_factory = _stub_pipeline_rendering(monkeypatch, storage, fixture)

    result = await VideoWorkflowExecutor(
        session_factory=lambda: _session_context(test_session),
        rendering_service_factory=rendering_factory,
    ).execute(Job(task_id=task_id))

    assert result["video_status"] == "ready"
    await test_session.refresh(scenes[0])
    await test_session.refresh(scenes[1])
    bound = [await test_session.get(type(scenes[0]), scene.id) for scene in scenes]
    external_ids = {
        (await test_session.get(AssetModel, scene.media_asset_id)).metadata_json["external_id"]
        for scene in bound
    }
    assert external_ids == {"pipeline-1", "pipeline-2"}
    assert provider.search_keywords == [
        "Narration keywords for scene 0",
        "Narration keywords for scene 1",
    ]
    composition_runs = (
        await test_session.scalars(
            select(WorkflowStepRunModel).where(
                WorkflowStepRunModel.task_id == task_id,
                WorkflowStepRunModel.step_key == "composition",
            )
        )
    ).all()
    scene_composition_runs = [run for run in composition_runs if run.unit_key]
    assert scene_composition_runs
    assert {
        run.input_payload["scene_render_format_version"] for run in scene_composition_runs
    } == {RenderingService.ONLINE_SCENE_RENDER_FORMAT_VERSION}


@pytest.mark.asyncio
async def test_online_pipeline_initializes_mode_before_new_script_stage(
    test_session, tmp_path, monkeypatch
):
    project_id = f"project_{uuid4().hex[:8]}"
    task_id = f"task_{uuid4().hex[:8]}"
    project = ProjectModel(id=project_id, name="New online pipeline")
    task = TaskModel(
        id=task_id,
        project_id=project_id,
        title="New online pipeline task",
        input_payload={
            "topic": "city footage",
            "content_mode": "online_asset",
            "visual_mode": "video",
            "material_provider_id": "prov_material_pexels",
            "template_id": "video_full_overlay",
            "enable_research": False,
        },
    )
    test_session.add_all([project, task])
    await test_session.commit()

    fixture = VALID_VIDEO_FIXTURE
    provider = _FakeMaterialProvider(fixture)
    monkeypatch.setattr(ProviderManager, "get_material", lambda self, provider_id=None: _return(provider))

    async def fake_generate_script(_self, _request):
        return StructuredScript(
            title="City footage",
            hook="先看一个关键事实",
            narration="城市夜间的灯光正在改变出行方式。",
            scenes=[
                StructuredSceneScript(
                    sequence_index=0,
                    narration_text="城市夜间的灯光照亮了街道。",
                    visual_prompt="city lights",
                )
            ],
        )

    monkeypatch.setattr(GenerationService, "generate_script", fake_generate_script)

    storage = LocalStorageService(tmp_path / "new-pipeline-storage")
    rendering_factory = _stub_pipeline_rendering(monkeypatch, storage, fixture)

    result = await VideoWorkflowExecutor(
        session_factory=lambda: _session_context(test_session),
        rendering_service_factory=rendering_factory,
    ).execute(Job(task_id=task_id))

    assert result["video_status"] == "ready"
    scene = (await test_session.scalars(select(SceneModel).where(SceneModel.task_id == task_id))).first()
    assert scene is not None
    asset = await test_session.get(AssetModel, scene.media_asset_id)
    assert asset is not None
    assert asset.metadata_json["source_kind"] == "online_asset"


async def _return(value):
    return value


class _session_context:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False

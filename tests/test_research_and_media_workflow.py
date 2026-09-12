import asyncio
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.exceptions import ValidationException
from src.domain.enums import JobType
from src.models.asset import AssetModel
from src.models.task import TaskModel
from src.providers.image.protocol import ImageResult
from src.providers.search.protocol import SearchResult
from src.providers.tts.protocol import TTSResult
from src.providers.video.protocol import VideoResult
from src.schemas.generation import (
    ResearchQueryPlan,
    ResearchResponse,
    ScriptGenerateRequest,
    StructuredSceneScript,
    StructuredScript,
)
from src.schemas.project import ProjectCreate
from src.schemas.task import TaskCreate
from src.services.generation_service import GenerationService, create_solid_color_png
from src.services.project_service import ProjectService
from src.services.system_asset_service import (
    DEFAULT_BGM_ASSET_ID,
    ensure_default_bgm,
)
from src.services.task_service import TaskService
from src.services.workflow_service import workflow_service
from src.storage.local_storage import LocalStorageService


async def _create_project_task(
    session: AsyncSession,
    *,
    title: str = "第四阶段测试任务",
    topic: str = "测试主题",
    storage: LocalStorageService | None = None,
    bgm_enabled: bool = False,
    image_workflow_id: str | None = None,
    template_id: str | None = None,
    content_mode: str | None = None,
) -> tuple[object, TaskModel, GenerationService]:
    project = await ProjectService(session).create_project(ProjectCreate(name=f"项目-{title}"))
    input_payload = {"topic": topic, "mode": "generate"}
    if template_id:
        input_payload["template_id"] = template_id
    if content_mode:
        input_payload["content_mode"] = content_mode
    task = await TaskService(session).create_task(
        project.id,
        TaskCreate(
            title=title,
            job_type=JobType.VIDEO_COMPOSITION,
            input_payload=input_payload,
            bgm_enabled=bgm_enabled,
            image_workflow_id=image_workflow_id,
        ),
    )
    return project, task, GenerationService(session, storage=storage or LocalStorageService())


@pytest.mark.asyncio
async def test_default_bgm_initialization_is_idempotent(test_session: AsyncSession, tmp_path):
    storage = LocalStorageService(base_storage_dir=tmp_path)

    first = await ensure_default_bgm(test_session, storage=storage)
    second = await ensure_default_bgm(test_session, storage=storage)

    assert first is not None
    assert second is not None
    assert first.id == DEFAULT_BGM_ASSET_ID
    assert second.id == DEFAULT_BGM_ASSET_ID
    assert first.file_path == "audio/bgm/asset_bgm_demo_default.mp3"
    assert storage.get_path(first.file_path).is_file()
    assert first.metadata_json["scope"] == "system"
    assert first.metadata_json["source"] == "TrendlumeDemo"
    assert first.duration_seconds and first.duration_seconds > 0

    result = await test_session.execute(
        select(AssetModel).where(AssetModel.id == DEFAULT_BGM_ASSET_ID)
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_research_is_persisted_cached_and_explicitly_rerunnable(
    test_session: AsyncSession, monkeypatch
):
    _, task, _ = await _create_project_task(test_session, topic="量子电池")
    service = GenerationService(test_session)

    class RecordingSearchProvider:
        name = "recording-search"

        def __init__(self):
            self.calls: list[tuple[str, int]] = []

        async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
            self.calls.append((query, max_results))
            if query == "q1":
                return [
                    SearchResult(
                        title="资料一",
                        url="HTTPS://EXAMPLE.COM:443/story/?z=2&a=1#fragment",
                        snippet="第一条资料",
                    )
                ]
            if query == "q2":
                return [
                    SearchResult(
                        title="重复资料",
                        url="https://example.com/story?a=1&z=2",
                        snippet="重复来源",
                    )
                ]
            return [
                SearchResult(
                    title="资料二",
                    url="https://other.example.com/story/",
                    snippet="第二条资料",
                )
            ]

    provider = RecordingSearchProvider()

    async def get_provider(_provider_id=None):
        return provider

    async def plan_queries(_topic: str, _max_queries: int):
        return ResearchQueryPlan(queries=["q1", "q2", "q3"], query_source="llm")

    monkeypatch.setattr(service, "_get_search_provider", get_provider)
    monkeypatch.setattr(service, "_generate_research_queries", plan_queries)

    first = await service.research_task(task.id)
    assert first.status == "completed"
    assert first.from_cache is False
    assert len(first.sources) == 2
    assert len(provider.calls) == 3
    # The task's configured maximum is the default five, and every query is
    # bounded independently. URL normalization still removes the duplicate.
    assert all(max_results == 5 for _, max_results in provider.calls)
    assert first.sources[0].url == "https://example.com/story?a=1&z=2"

    cached = await service.research_task(task.id)
    assert cached.status == "completed"
    assert cached.from_cache is True
    assert len(provider.calls) == 3

    rerun = await service.research_task(task.id, force=True)
    assert rerun.status == "completed"
    assert rerun.from_cache is False
    assert len(provider.calls) == 6

    stored = await service.get_task_research(task.id)
    assert stored.status == "completed"
    assert len(stored.sources) == 2
    refreshed_task = await service.task_repo.get_by_id(task.id)
    assert refreshed_task is not None
    assert refreshed_task.input_payload["research"]["provider"] == "recording-search"
    assert refreshed_task.input_payload["research"]["topic"] == "量子电池"
    assert refreshed_task.input_payload["research"]["duration_seconds"] is not None


@pytest.mark.asyncio
async def test_pending_research_has_topic_and_legacy_payload_is_repaired(
    test_session: AsyncSession, monkeypatch
):
    _, task, service = await _create_project_task(test_session, topic="时空晶体")
    pending_snapshot: dict = {}

    async def fake_research_topic(topic: str, **kwargs):
        pending_snapshot.update((task.input_payload or {}).get("research") or {})
        return ResearchResponse(topic=topic, status="completed", summary="已完成检索")

    monkeypatch.setattr(service, "research_topic", fake_research_topic)
    result = await service.research_task(task.id)

    assert result.status == "completed"
    assert pending_snapshot["topic"] == "时空晶体"

    legacy_payload = dict(task.input_payload or {})
    legacy_research = dict(legacy_payload["research"])
    legacy_research.pop("topic", None)
    legacy_payload["research"] = legacy_research
    task.input_payload = legacy_payload
    await test_session.commit()

    repaired = await service.get_task_research(task.id)
    assert repaired.topic == "时空晶体"
    assert repaired.status == "completed"


@pytest.mark.asyncio
async def test_search_failure_is_returned_without_mock_fallback(test_session: AsyncSession, monkeypatch):
    service = GenerationService(test_session)

    class FailingSearchProvider:
        name = "configured-search"

        async def search(self, query: str, max_results: int = 5):
            raise RuntimeError("configured provider unavailable")

    async def get_provider(_provider_id=None):
        return FailingSearchProvider()

    async def plan_queries(_topic: str, _max_queries: int):
        return ResearchQueryPlan(queries=["故障查询"], query_source="heuristic")

    monkeypatch.setattr(service, "_get_search_provider", get_provider)
    monkeypatch.setattr(service, "_generate_research_queries", plan_queries)

    result = await service.research_topic("故障主题", max_queries=1)
    assert result.status == "failed"
    assert result.sources == []
    assert "configured provider unavailable" in (result.error_message or "")
    assert result.query_records[0].status == "failed"


@pytest.mark.asyncio
async def test_llm_plans_queries_and_content_llm_receives_sources(
    test_session: AsyncSession, monkeypatch
):
    service = GenerationService(test_session)
    events: list[str] = []
    content_prompts: list[str] = []
    query_kwargs: dict[str, object] = {}

    class OrderedSearchProvider:
        name = "ordered-search"

        async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
            events.append(f"search-start:{query}")
            await asyncio.sleep(0)
            events.append(f"search-end:{query}")
            return [
                SearchResult(
                    title=f"参考源 {query}",
                    url=f"https://sources.example/{len(events)}",
                    snippet=f"关于 {query} 的可核验事实。",
                )
            ]

    class OrderedLLMProvider:
        name = "ordered-llm"

        async def generate_text(self, prompt: str, **kwargs) -> str:
            events.append("llm-query")
            query_kwargs.update(kwargs)
            return '{"queries":["主题核心事实","主题最新数据"]}'

        async def generate_structured(self, prompt: str, **kwargs):
            events.append("llm-content")
            content_prompts.append(prompt)
            return kwargs["schema_class"].model_validate(
                {
                    "title": "研究增强短视频",
                    "hook": "先看一个关键事实",
                    "narration": "这是一段研究增强的旁白。",
                    "metadata": {
                        "title": "模型返回的旧标题",
                        "description": "先看关键事实，再理解它为什么重要，欢迎评论区交流。",
                        "tags": ["#研究主题", "研究主题", "#科技"],
                        "declaration": "内容取材网络",
                    },
                        "scenes": [
                            {
                                "sequence_index": index,
                                "narration_text": f"这是第 {index + 1} 段旁白。",
                                "visual_prompt": "A fully framed research subject, no text, no watermark",
                                "duration_seconds": 4,
                                "badge_text": "事实",
                            }
                            for index in range(8)
                        ],
                }
            )

    async def get_search(_provider_id=None):
        return OrderedSearchProvider()

    async def get_llm():
        return OrderedLLMProvider()

    monkeypatch.setattr(service, "_get_search_provider", get_search)
    monkeypatch.setattr(service, "_get_llm_provider", get_llm)

    research = await service.research_topic("研究主题", max_queries=2, max_results=1)
    context = research.format_for_prompt()
    script = await service.generate_script(
        ScriptGenerateRequest(
            topic="研究主题",
            target_scene_count=8,
            research_context=context,
        )
    )

    assert research.query_source == "llm"
    assert research.queries == ["主题核心事实", "主题最新数据"]
    assert research.status == "completed"
    assert len(research.sources) == 2
    assert events[0] == "llm-query"
    assert query_kwargs["temperature"] == 0.0
    assert query_kwargs["max_tokens"] == 1200
    assert "只输出合法 JSON" in query_kwargs["system_prompt"]
    search_end_indexes = [i for i, event in enumerate(events) if event.startswith("search-end:")]
    assert len(search_end_indexes) == 2
    assert max(search_end_indexes) < events.index("llm-content")
    assert "https://sources.example/" in content_prompts[0]
    assert "参考源" in content_prompts[0]
    assert len(script.scenes) == 8
    assert script.metadata.title == script.title
    assert script.metadata.tags == ["研究主题", "科技"]
    assert script.metadata.declaration == "内容取材网络"


@pytest.mark.asyncio
async def test_research_query_planner_rejects_topic_echo_and_uses_safe_fallback(
    test_session: AsyncSession, monkeypatch
):
    service = GenerationService(test_session)

    class EchoingLLMProvider:
        async def generate_text(self, prompt: str, **kwargs) -> str:
            return '{"queries":["量子电池", "量子电池 最新进展", "量子 电池 核心机制"]}'

    async def get_llm():
        return EchoingLLMProvider()

    monkeypatch.setattr(service, "_get_llm_provider", get_llm)

    plan = await service._generate_research_queries("量子电池", max_queries=3)

    assert plan.query_source == "heuristic"
    assert plan.queries
    assert all("量子电池" not in query for query in plan.queries)
    assert all(query != "量子电池 最新进展" for query in plan.queries)

    assert GenerationService._is_topic_echo("量子 电池 核心机制", "量子电池")


def test_research_query_parser_accepts_supported_response_shapes():
    cases = (
        (
            '模型说明\n```json\n{"queries":["量子 机制",],}\n```',
            ["量子 机制"],
        ),
        ('{"data":["量子 机制","量子 数据"]}', ["量子 机制", "量子 数据"]),
        ('["量子 机制","量子 数据"]', ["量子 机制", "量子 数据"]),
        (
            (
                '<think>```json\n{"queries":["思考阶段的错误查询"]}\n```</think>\n'
                '模型说明 {"draft":"仍不是查询"}，最终结果：'
                '{"response":{"queries":["巴格达电池 考古证据","古代电池 电化学研究"]}}'
            ),
            ["巴格达电池 考古证据", "古代电池 电化学研究"],
        ),
    )
    for raw_response, expected in cases:
        assert GenerationService._parse_research_query_response(
            raw_response, max_queries=3
        ) == expected


@pytest.mark.asyncio
async def test_research_query_planner_falls_back_for_empty_query_values(
    test_session: AsyncSession, monkeypatch
):
    service = GenerationService(test_session)

    class InvalidQueryLLM:
        async def generate_text(self, prompt: str, **kwargs) -> str:
            return '{"data":[null,42]}'

    async def get_llm():
        return InvalidQueryLLM()

    monkeypatch.setattr(service, "_get_llm_provider", get_llm)

    plan = await service._generate_research_queries("量子电池", max_queries=3)

    assert plan.query_source == "heuristic"
    assert plan.queries
    assert "未找到有效查询列表" in plan.warnings[0]
    assert all("量子电池" not in query for query in plan.queries)


@pytest.mark.asyncio
async def test_fixed_script_preserves_scene_narration_when_research_is_used(
    test_session: AsyncSession, monkeypatch
):
    service = GenerationService(test_session)
    prompts: list[str] = []

    class RecordingLLM:
        name = "recording-llm"

        async def generate_text(self, prompt: str, **kwargs):
            prompts.append(prompt)
            return "结合研究资料的中文画面提示词，主体清晰，构图简洁，细节可信"

    async def get_llm():
        return RecordingLLM()

    monkeypatch.setattr(service, "_get_llm_provider", get_llm)
    raw_script = "第一段旁白，保持原文。\n\n第二段旁白，也保持原文。"
    script = await service.generate_script(
        ScriptGenerateRequest(
            mode="fixed",
            raw_script=raw_script,
            research_context="研究资料：可用于增强事实感。",
            style_preset="stick_figure",
        )
    )

    assert [scene.narration_text for scene in script.scenes] == [
        "第一段旁白，保持原文。",
        "第二段旁白，也保持原文。",
    ]
    assert all("研究资料" in prompt for prompt in prompts)
    assert all("第一段旁白，保持原文。" in prompt or "第二段旁白，也保持原文。" in prompt for prompt in prompts[1:])
    assert script.narration == raw_script


@pytest.mark.asyncio
async def test_invalid_tts_bytes_fail_without_fake_duration(test_session: AsyncSession, tmp_path):
    storage = LocalStorageService(base_storage_dir=tmp_path)
    _, task, service = await _create_project_task(
        test_session, storage=storage, title="无效 TTS 测试"
    )
    script = StructuredScript(
        title="测试",
        hook="测试",
        narration="一段测试旁白",
        scenes=[
            StructuredSceneScript(
                sequence_index=0,
                narration_text="一段测试旁白",
                visual_prompt="A test frame",
            )
        ],
    )
    task = await service.apply_script_to_task(task.id, script)

    class InvalidTTS:
        name = "invalid-tts"

        async def synthesize(self, text: str, voice_id: str, speed: float = 1.0):
            return TTSResult(audio_bytes=b"not-audio", duration_seconds=99.0)

    service._get_tts_provider = lambda: _resolved(InvalidTTS())

    with pytest.raises(ValidationException, match="未使用伪造时长"):
        await service.generate_scene_audio(task.scenes[0].id)

    refreshed_scene = await service.scene_repo.get_by_id(task.scenes[0].id)
    assert refreshed_scene is not None
    assert refreshed_scene.audio_asset_id is None
    assert refreshed_scene.layout_params["tts_status"] == "failed"
    assert refreshed_scene.duration_seconds == 4.0


@pytest.mark.asyncio
async def test_workflow_is_snapshotted_and_passed_to_image_provider(
    test_session: AsyncSession, tmp_path
):
    snapshot = workflow_service.get_workflow_snapshot("image/image_flux.json", expected_type="image")
    assert snapshot is not None
    assert snapshot["id"] == "image/image_flux.json"
    with pytest.raises(ValueError):
        workflow_service.get_workflow_snapshot("../outside.json", expected_type="image")

    storage = LocalStorageService(base_storage_dir=tmp_path)
    _, task, service = await _create_project_task(
        test_session,
        storage=storage,
        title="工作流选择测试",
        image_workflow_id="image/image_flux.json",
    )
    script = StructuredScript(
        title="测试",
        hook="测试",
        narration="工作流测试旁白",
        scenes=[
            StructuredSceneScript(
                sequence_index=0,
                narration_text="工作流测试旁白",
                visual_prompt="A test frame",
            )
        ],
    )
    task = await service.apply_script_to_task(task.id, script)

    class RecordingImage:
        name = "recording-image"

        def __init__(self):
            self.workflows: list[str | None] = []

        async def generate_image(self, prompt: str, aspect_ratio: str, workflow: str | None = None):
            self.workflows.append(workflow)
            return ImageResult(
                image_bytes=create_solid_color_png(10, 10),
                width=10,
                height=10,
            )

    provider = RecordingImage()
    service._get_image_provider = lambda: _resolved(provider)
    await service.generate_scene_image(task.scenes[0].id)

    assert provider.workflows == ["image/image_flux.json"]
    refreshed_task = await service.task_repo.get_by_id(task.id)
    assert refreshed_task is not None
    assert refreshed_task.input_payload["image_workflow_snapshot"]["type"] == "image"


@pytest.mark.asyncio
async def test_video_provider_uses_tts_duration_without_overwriting_scene_duration(
    test_session: AsyncSession, tmp_path
):
    fixture = Path(__file__).resolve().parent / "fixtures" / "mock.mp4"
    storage = LocalStorageService(base_storage_dir=tmp_path)
    _, task, service = await _create_project_task(
        test_session,
        storage=storage,
        title="视频时长测试",
        template_id="video_full_overlay",
        content_mode="generated_video",
    )
    script = StructuredScript(
        title="测试",
        hook="测试",
        narration="视频时长测试旁白",
        scenes=[
            StructuredSceneScript(
                sequence_index=0,
                narration_text="视频时长测试旁白",
                visual_prompt="A test video",
            )
        ],
    )
    task = await service.apply_script_to_task(task.id, script)
    scene = task.scenes[0]
    scene.duration_seconds = 2.0
    await test_session.flush()

    class RecordingVideo:
        name = "recording-video"

        def __init__(self):
            self.durations: list[float] = []
            self.layouts: list[tuple[str, int | None, int | None]] = []

        async def generate_video(
            self,
            prompt: str,
            aspect_ratio: str,
            duration_seconds: float,
            workflow: str | None = None,
            width: int | None = None,
            height: int | None = None,
        ):
            self.durations.append(duration_seconds)
            self.layouts.append((aspect_ratio, width, height))
            return VideoResult(
                video_bytes=fixture.read_bytes(),
                duration_seconds=9.0,
                width=64,
                height=64,
            )

    provider = RecordingVideo()
    service._get_video_provider = lambda: _resolved(provider)
    result_scene = await service.generate_scene_video(scene.id)

    assert provider.durations == [2.0]
    assert provider.layouts == [("9:16", 1080, 1920)]
    assert result_scene.duration_seconds == 2.0
    assert result_scene.layout_params["video_actual_duration_seconds"] == pytest.approx(0.5)
    assert result_scene.layout_params["video_declared_duration_seconds"] == 9.0


@pytest.mark.asyncio
async def test_phase4_api_research_bgm_and_content_helpers(
    client: AsyncClient, test_session: AsyncSession
):
    project_response = await client.post("/api/v1/projects", json={"name": "第四阶段 API 项目"})
    assert project_response.status_code == 201
    project_data = project_response.json()["data"]
    project_id = project_data["id"]
    assert project_data["bgm_asset_id"] == DEFAULT_BGM_ASSET_ID

    bgm_response = await client.get(f"/api/v1/projects/{project_id}/bgm")
    assert bgm_response.status_code == 200
    assert any(item["id"] == DEFAULT_BGM_ASSET_ID for item in bgm_response.json()["data"])

    task_response = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={
            "title": "API 研究任务",
            "bgm_enabled": False,
            "input_payload": {"topic": "API 研究主题"},
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["data"]["id"]
    pending = await client.get(f"/api/v1/tasks/{task_id}/research")
    assert pending.status_code == 200
    assert pending.json()["data"]["status"] == "pending"
    task = await test_session.get(TaskModel, task_id)
    assert task is not None
    task.input_payload = {
        **(task.input_payload or {}),
        "research": {
            "status": "pending",
            "provider": None,
            "queries": [],
            "sources": [],
            "summary": "正在准备实时资料检索。",
            "error_message": None,
            "started_at": "2026-09-02T00:00:00Z",
            "completed_at": None,
        },
    }
    await test_session.commit()
    active_pending = await client.get(f"/api/v1/tasks/{task_id}/research")
    assert active_pending.status_code == 200
    assert active_pending.json()["data"]["topic"] == "API 研究主题"
    assert active_pending.json()["data"]["status"] == "pending"

    research = await client.post(f"/api/v1/generation/tasks/{task_id}/research")
    assert research.status_code == 200
    assert research.json()["data"]["status"] == "completed"
    assert research.json()["data"]["queries"]

    title = await client.post("/api/v1/generation/title", json={"topic": "API 主题"})
    narration = await client.post(
        "/api/v1/generation/narration", json={"raw_script": "第一段\n\n第二段"}
    )
    image_prompt = await client.post(
        "/api/v1/generation/image-prompt", json={"topic": "API 主题"}
    )
    video_prompt = await client.post(
        "/api/v1/generation/video-prompt", json={"topic": "API 主题"}
    )
    assert title.status_code == narration.status_code == image_prompt.status_code == video_prompt.status_code == 200
    assert title.json()["data"]["title"]
    assert len(narration.json()["data"]["narrations"]) == 2
    assert image_prompt.json()["data"]["prompt"]
    assert video_prompt.json()["data"]["prompt"]


async def _resolved(value):
    return value

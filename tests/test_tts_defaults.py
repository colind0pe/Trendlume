from unittest.mock import AsyncMock

import pytest
from tests.mocks import MockTTSProvider

from src.models.scene import SceneModel
from src.providers.tts.edge_tts import CURATED_VOICES, EdgeTTSProvider
from src.providers.tts.volcengine_tts import VolcengineTTSProvider
from src.schemas.project import ProjectCreate
from src.schemas.task import TaskCreate
from src.services.generation_service import GenerationService
from src.services.project_service import ProjectService
from src.services.provider_manager import ProviderManager
from src.services.task_service import TaskService
from src.storage.local_storage import LocalStorageService


@pytest.mark.asyncio
async def test_task_snapshots_system_voice_and_synthesis_uses_it(test_session, tmp_path, monkeypatch):
    manager = ProviderManager(test_session)
    model = await manager.repo.get_by_id("prov_tts_edge")
    model.config = {**model.config, "default_voice": "zh-HK-HiuMaanNeural"}
    await test_session.flush()
    project = await ProjectService(test_session).create_project(ProjectCreate(name="Voice defaults"))
    service = TaskService(test_session)
    task = await service.create_task(project.id, TaskCreate(title="Inherited", voice_id=""))
    assert task.input_payload["voice_id"] == "zh-HK-HiuMaanNeural"

    model.config = {**model.config, "default_voice": "zh-CN-XiaoxiaoNeural"}
    await test_session.flush()
    next_task = await service.create_task(project.id, TaskCreate(title="New default"))
    assert next_task.input_payload["voice_id"] == "zh-CN-XiaoxiaoNeural"
    assert task.input_payload["voice_id"] == "zh-HK-HiuMaanNeural"
    explicit = await service.create_task(project.id, TaskCreate(title="Override", voice_id="en-US-GuyNeural"))
    assert explicit.input_payload["voice_id"] == "en-US-GuyNeural"

    scene = SceneModel(id="voice-scene", task_id=task.id, narration_text="测试系统音色")
    test_session.add(scene)
    await test_session.commit()
    provider = MockTTSProvider()
    provider.synthesize = AsyncMock(wraps=provider.synthesize)
    generation = GenerationService(test_session, storage=LocalStorageService(base_storage_dir=tmp_path))
    monkeypatch.setattr(generation, "_get_tts_provider", AsyncMock(return_value=provider))
    await generation.generate_scene_audio(scene.id)
    assert provider.synthesize.call_args.kwargs["voice_id"] == "zh-HK-HiuMaanNeural"


@pytest.mark.asyncio
async def test_edge_provider_reads_saved_default_and_allows_override(test_session, monkeypatch):
    manager = ProviderManager(test_session)
    model = await manager.repo.get_by_id("prov_tts_edge")
    model.config = {**model.config, "default_voice": "zh-TW-HsiaoYuNeural"}
    await test_session.flush()
    provider = await manager.get_tts()
    stream = AsyncMock(return_value=(b"audio", 2.0))
    monkeypatch.setattr(provider, "_stream_edge_tts", stream)
    await provider.synthesize("测试")
    assert stream.call_args.args[1] == "zh-TW-HsiaoYuNeural"
    await provider.synthesize("测试", voice_id="zh-CN-YunxiNeural")
    assert stream.call_args.args[1] == "zh-CN-YunxiNeural"


@pytest.mark.asyncio
async def test_task_voice_catalog_contains_all_settings_voices(client):
    settings = (await client.get("/api/v1/providers/voices")).json()["data"]
    active = (await client.get("/api/v1/providers/voices", params={"active": "true"})).json()["data"]
    assert {v["id"] for v in active} == {v["id"] for v in settings}
    assert {v["id"] for v in settings} == {v.id for v in CURATED_VOICES}


def test_provider_fallback_defaults():
    assert EdgeTTSProvider().default_voice == "zh-CN-YunxiNeural"
    provider = VolcengineTTSProvider(api_key="api-key")
    assert provider.resource_id == "seed-tts-2.0"
    assert provider.default_voice == "zh_female_vv_uranus_bigtts"
    assert provider.default_speed_ratio == 1.0

import pytest
from pydantic import ValidationError
from src.core.exceptions import ValidationException
from src.domain.enums import JobType
from src.schemas.generation import ContentGenerateRequest, ScriptGenerateRequest
from src.schemas.project import ProjectCreate
from src.schemas.task import TaskCreate
from src.services.durable_pipeline import (
    _LegacyScriptGenerateRequest,
    _script_request_model_for_persisted_count,
)
from src.services.generation_service import GenerationService, get_genre_instruction
from src.services.project_service import ProjectService
from src.services.task_service import TaskService

_PUBLIC_REQUEST_FACTORIES = (
    lambda count: ContentGenerateRequest(topic="主题", target_scene_count=count),
    lambda count: ScriptGenerateRequest(topic="主题", target_scene_count=count),
    lambda count: TaskCreate(
        title="边界测试任务", job_type=JobType.VIDEO_COMPOSITION, target_scene_count=count
    ),
)


@pytest.mark.parametrize(
    ("count", "is_valid"),
    [(7, False), (8, True), (20, True), (21, False)],
)
def test_public_scene_count_boundaries_are_consistent_across_request_models(count, is_valid):
    for request_factory in _PUBLIC_REQUEST_FACTORIES:
        if is_valid:
            assert request_factory(count).target_scene_count == count
        else:
            with pytest.raises(ValidationError):
                request_factory(count)


@pytest.mark.asyncio
async def test_task_service_persists_twenty_scenes_and_rejects_payload_legacy_count(test_session):
    project = await ProjectService(test_session).create_project(ProjectCreate(name="分镜范围测试"))
    service = TaskService(test_session)

    task = await service.create_task(
        project.id,
        TaskCreate(
            title="20 镜任务",
            job_type=JobType.VIDEO_COMPOSITION,
            target_scene_count=20,
        ),
    )
    assert task.input_payload["target_scene_count"] == 20

    with pytest.raises(ValidationException, match="8 到 20"):
        await service.create_task(
            project.id,
            TaskCreate(
                title="旧范围不可用于新建",
                job_type=JobType.VIDEO_COMPOSITION,
                input_payload={"target_scene_count": 7},
            ),
        )


class _CapturingLLM:
    name = "genre-capture"

    def __init__(self):
        self.text_calls = []
        self.structured_calls = []

    async def generate_text(self, prompt="", **kwargs):
        self.text_calls.append({"prompt": prompt, **kwargs})
        if "发布元数据输入" in prompt:
            return '{"description":"基于已有内容整理","tags":["主题","测试"],"declaration":"内容由AI生成"}'
        if "请创作" in (kwargs.get("system_prompt") or ""):
            return "\n".join(f"第 {index + 1} 段旁白" for index in range(8))
        return "测试标题"

    async def generate_structured(self, **kwargs):
        self.structured_calls.append(kwargs)
        return kwargs["schema_class"].model_validate(
            {
                "title": "自动匹配脚本",
                "hook": "先看一个关键事实",
                "narration": "这是完整旁白。",
                "scenes": [
                    {
                        "sequence_index": index,
                        "narration_text": f"第 {index + 1} 段旁白",
                        "visual_prompt": "A clear documentary image",
                    }
                    for index in range(8)
                ],
                "metadata": {
                    "title": "自动匹配脚本",
                    "description": "基于已有内容整理",
                    "tags": ["主题", "测试"],
                    "declaration": "内容由AI生成",
                },
            }
        )


def _assert_auto_genre_guidance(prompt: str):
    assert "自动匹配" in prompt
    for direction in (
        "科普解说与前沿科技",
        "商业财经与财富思维",
        "个人成长与情感心理",
        "人文历史与传统文化",
        "幽默段子与趣味吐槽",
        "产品测评与种草体验",
        "通用随笔",
    ):
        assert direction in prompt


@pytest.mark.asyncio
async def test_auto_genre_guidance_and_explicit_genre_instruction(test_session, monkeypatch):
    llm = _CapturingLLM()
    service = GenerationService(test_session)

    async def get_provider():
        return llm

    monkeypatch.setattr(service, "_get_llm_provider", get_provider)

    await service.generate_narration(
        ContentGenerateRequest(
            topic="城市夜间交通",
            genre="auto",
            target_scene_count=8,
            enable_research=False,
        )
    )
    _assert_auto_genre_guidance(llm.text_calls[0]["system_prompt"])
    assert len(llm.text_calls) == 1

    await service.generate_script(
        ScriptGenerateRequest(topic="城市夜间交通", genre="auto", target_scene_count=8)
    )
    _assert_auto_genre_guidance(llm.structured_calls[0]["system_prompt"])
    assert len(llm.structured_calls) == 1

    await service.generate_script(
        ScriptGenerateRequest(
            mode="fixed",
            raw_script="第一段原文",
            genre="auto",
            content_mode="online_asset",
        )
    )
    metadata_call = next(call for call in llm.text_calls if "发布元数据输入" in call["prompt"])
    _assert_auto_genre_guidance(metadata_call["system_prompt"] + metadata_call["prompt"])
    assert len(llm.text_calls) == 3  # narration, fixed title, fixed metadata
    explicit_instruction = get_genre_instruction("science_tech")
    assert explicit_instruction.startswith("科普解说与前沿科技：")
    assert "自动匹配" not in explicit_instruction


def test_legacy_scene_count_model_is_internal_only_and_preserves_persisted_value():
    assert _script_request_model_for_persisted_count({"target_scene_count": 6}) is _LegacyScriptGenerateRequest
    assert _script_request_model_for_persisted_count({}, fallback_scene_count=6) is _LegacyScriptGenerateRequest
    assert _LegacyScriptGenerateRequest(target_scene_count=6).target_scene_count == 6
    request = _LegacyScriptGenerateRequest(topic="旧任务", target_scene_count=6)
    assert request.target_scene_count == 6
    assert _script_request_model_for_persisted_count({"target_scene_count": 8}) is ScriptGenerateRequest

    with pytest.raises(ValidationError):
        ScriptGenerateRequest(topic="公开请求", target_scene_count=6)

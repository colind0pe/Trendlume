import json
from unittest.mock import AsyncMock

import pytest
from src.schemas.generation import (
    PlatformMetadata,
    ScriptGenerateRequest,
    StructuredScript,
)
from src.services.generation_service import GenerationService

TITLE = "宋朝人喝的奶茶 其实比现代还高级"
NARRATION = "宋朝点茶要将茶末调膏，注水击拂，形成细密的汤花。这是古代茶饮文化的一部分。"
CONTENT_TAGS = ["宋朝", "点茶", "茶文化", "古代饮食", "历史文化"]


def make_script(tags):
    return StructuredScript(
        title=TITLE, hook="看看宋朝怎么喝茶", narration=NARRATION,
        scenes=[{"sequence_index": 0, "narration_text": NARRATION, "visual_prompt": "tea"}],
        metadata=PlatformMetadata(description="原有发布文案", tags=tags, declaration="内容取材网络"),
    )


def test_filter_rejects_title_and_title_clauses_but_keeps_topics():
    tags = [TITLE, "#宋朝人喝的奶茶", "其实比现代还高级", *CONTENT_TAGS, "#点茶"]
    assert GenerationService._filter_platform_tags(tags, TITLE) == CONTENT_TAGS


def test_missing_metadata_fallback_never_turns_topic_into_tag():
    script = GenerationService._finalize_script_metadata(
        make_script([TITLE]), topic=TITLE, genre="culture_history",
    )
    assert script.metadata.tags == ["历史", "传统文化"]
    assert "AI创作" not in script.metadata.tags


@pytest.mark.asyncio
async def test_generated_title_tags_are_replaced_using_narration(test_session, monkeypatch):
    provider = type("LLM", (), {})()
    provider.generate_structured = AsyncMock(return_value=make_script([TITLE, "点茶"]))
    provider.generate_text = AsyncMock(return_value=json.dumps({"tags": CONTENT_TAGS}))
    service = GenerationService(test_session)
    monkeypatch.setattr(service, "_get_llm_provider", AsyncMock(return_value=provider))
    script = await service.generate_script(
        ScriptGenerateRequest(topic=TITLE, genre="culture_history")
    )
    assert script.metadata.tags == CONTENT_TAGS
    assert script.metadata.description == "原有发布文案"
    assert script.metadata.declaration == "内容取材网络"
    provider.generate_text.assert_awaited_once()
    assert NARRATION in provider.generate_text.call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_good_tags_do_not_trigger_extra_llm_call(test_session, monkeypatch):
    provider = type("LLM", (), {})()
    provider.generate_structured = AsyncMock(return_value=make_script(CONTENT_TAGS))
    provider.generate_text = AsyncMock()
    service = GenerationService(test_session)
    monkeypatch.setattr(service, "_get_llm_provider", AsyncMock(return_value=provider))
    result = await service.generate_script(ScriptGenerateRequest(topic=TITLE))
    assert result.metadata.tags == CONTENT_TAGS
    provider.generate_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [RuntimeError("unavailable"), json.dumps({"tags": TITLE.split()})])
async def test_failed_repair_keeps_valid_tags_without_title_echo(test_session, monkeypatch, response):
    provider = type("LLM", (), {})()
    provider.generate_structured = AsyncMock(return_value=make_script([TITLE, "点茶"]))
    provider.generate_text = AsyncMock(
        side_effect=response if isinstance(response, Exception) else None,
        return_value=response,
    )
    service = GenerationService(test_session)
    monkeypatch.setattr(service, "_get_llm_provider", AsyncMock(return_value=provider))
    result = await service.generate_script(ScriptGenerateRequest(topic=TITLE, genre="culture_history"))
    assert result.metadata.tags == ["点茶"]
    provider.generate_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_fixed_script_uses_content_tags(test_session, monkeypatch):
    provider = type("LLM", (), {})()
    async def generate_text(prompt, **kwargs):
        if "发布元数据" in prompt:
            return json.dumps({"tags": CONTENT_TAGS})
        return "宋朝茶文化"

    provider.generate_text = AsyncMock(side_effect=generate_text)
    service = GenerationService(test_session)
    monkeypatch.setattr(service, "_get_llm_provider", AsyncMock(return_value=provider))
    result = await service.generate_script(ScriptGenerateRequest(
        mode="fixed", topic=TITLE, raw_script=NARRATION, genre="culture_history",
    ))
    assert result.metadata.tags == CONTENT_TAGS
    assert result.narration == NARRATION

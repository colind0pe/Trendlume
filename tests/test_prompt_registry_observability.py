import json
from pathlib import Path
from typing import ClassVar

import pytest

from src.providers.llm.protocol import StructuredOutputException
from src.schemas.generation import (
    ScriptGenerateRequest,
    VisualPromptBatch,
)
from src.services.durable_pipeline import build_script_generation_inputs
from src.services.generation_service import GenerationService
from src.services.prompt_registry import (
    PromptRegistry,
    PromptSpec,
    PromptVersionError,
    prompt_registry,
)
from src.services.workflow_runtime import fingerprint

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def test_prompt_inventory_and_registry_have_explicit_hashes():
    inventory = json.loads(
        (BACKEND / "evals" / "prompt_inventory.json").read_text(encoding="utf-8")
    )
    registry_snapshot = prompt_registry.snapshot()
    entries = {entry["prompt_id"]: entry for entry in inventory["prompt_ids"]}

    ids = [entry["prompt_id"] for entry in inventory["prompt_ids"]]
    assert len(ids) == len(set(ids))
    assert {
        "research_query", "structured_script", "fixed_script_title",
        "fixed_script_visual_batch", "platform_metadata", "structured_repair",
    }.issubset({entry["kind"] for entry in inventory["prompt_ids"]})
    for entry in inventory["prompt_ids"]:
        assert (BACKEND.parent / entry["source"]).is_file()

    assert set(entries) == set(registry_snapshot)
    for prompt_id, snapshot in registry_snapshot.items():
        assert snapshot["prompt_version"] == entries[prompt_id]["prompt_version"]
        assert snapshot["template_hash"] == entries[prompt_id]["template_hash"]
        assert len(snapshot["template_hash"]) == 64


def test_template_hash_is_derived_from_template_and_candidate_rollback_is_reproducible():
    original = PromptSpec("demo", "v1", "actual rules")
    changed = PromptSpec("demo", "v1", "actual rules changed")
    assert original.template_hash != changed.template_hash

    registry = PromptRegistry()
    assert registry.resolve("script.structured").version == "v1"
    candidate = registry.set_active_version("script.structured", "v2-candidate")
    assert candidate.status == "candidate"
    assert registry.resolve("script.structured").version == "v2-candidate"
    assert registry.rollback("script.structured").version == "v1"
    assert registry.resolve("script.structured").version == "v1"

    with pytest.raises(PromptVersionError):
        registry.resolve("script.structured", {"script.structured": "does-not-exist"})
    with pytest.raises(PromptVersionError):
        registry.resolve("unknown.prompt")


def test_prompt_selection_and_content_change_durable_fingerprint():
    base = {
        "mode": "generate",
        "topic": "可持续城市交通",
        "knowledge_brief": {"thesis": "解释核心机制"},
        "provider": {"model": "mock-model", "temperature": 0.7},
    }
    stable = build_script_generation_inputs(base, topic=base["topic"])
    candidate = build_script_generation_inputs(
        {**base, "prompt_versions": {"script.structured": "v2-candidate"}},
        topic=base["topic"],
    )
    changed_brief = build_script_generation_inputs(
        {**base, "knowledge_brief": {"thesis": "解释争议与边界"}}, topic=base["topic"]
    )

    assert stable["prompt_selection"]["script.structured"]["prompt_version"] == "v1"
    assert candidate["prompt_selection"]["script.structured"]["prompt_version"] == "v2-candidate"
    assert candidate["prompt_selection"]["script.structured"]["template_hash"] != stable["prompt_selection"]["script.structured"]["template_hash"]
    assert fingerprint(candidate) != fingerprint(stable)
    assert fingerprint(changed_brief) != fingerprint(stable)

    default_inputs = build_script_generation_inputs({"mode": "generate"}, topic="新任务")
    assert default_inputs["prompt_selection"]["script.structured"]["prompt_version"] == "v1"


class _StructuredRepairProvider:
    name = "stage5-structured"
    model = "offline-model"
    supports_native_json_schema = True
    last_usage: ClassVar = {"prompt_tokens": 11, "completion_tokens": 3}
    last_structured_repair_count = 1
    last_structured_native_json_schema = True

    async def generate_structured(self, **kwargs):
        raise StructuredOutputException("offline malformed JSON")


@pytest.mark.asyncio
async def test_structured_observation_contains_native_and_repair_metadata(test_session, monkeypatch):
    service = GenerationService(test_session)
    provider = _StructuredRepairProvider()

    with pytest.raises(StructuredOutputException):
        await service._llm_structured(
            provider,
            "script.structured",
            "offline structured input",
            VisualPromptBatch,
            temperature=0.7,
            max_tokens=6000,
        )

    record = service.prompt_observations.records[-1]
    assert record["mode"] == "structured"
    assert record["native_json_schema"] is True
    assert record["repair_count"] == 1
    assert record["token_usage"] == {"prompt_tokens": 11, "completion_tokens": 3}


@pytest.mark.asyncio
async def test_batch_business_downgrade_is_observed_without_provider_retry(test_session, monkeypatch):
    class BlankBatchProvider:
        name = "stage5-batch"

        async def generate_text(self, prompt: str, **kwargs):
            if "发布元数据输入" in prompt:
                return '{"description":"说明","tags":["测试"],"declaration":"内容由AI生成"}'
            return "固定标题"

        async def generate_structured(self, **kwargs):
            return kwargs["schema_class"].model_validate(
                {"items": [{"sequence_index": 0, "visual_prompt": ""}, {"sequence_index": 1, "visual_prompt": "valid"}]}
            )

    service = GenerationService(test_session)
    provider = BlankBatchProvider()

    async def get_provider():
        return provider

    monkeypatch.setattr(service, "_get_llm_provider", get_provider)
    await service.generate_script(
        ScriptGenerateRequest(mode="fixed", raw_script="第一段\n第二段", split_mode="line")
    )
    batch_record = next(
        item for item in service.prompt_observations.records if item["prompt_id"] == "visual.fixed_batch"
    )
    assert batch_record["status"] == "success"
    assert batch_record["fallback_count"] == 1


def test_offline_replay_reports_improvement_regression_and_unchanged():
    from evals.prompt_replay import compare_files

    report = compare_files()
    assert report["offline"] is True
    assert report["counts"]["improved"] >= 1
    assert report["counts"]["regressed"] >= 1
    assert report["counts"]["unchanged"] >= 1
    assert report["manual_quality_is_not_scored"] is True
    assert "secret" not in json.dumps(report, ensure_ascii=False).casefold()

from __future__ import annotations

import pytest

from src.domain.enums import VisualRole
from src.schemas.generation import (
    KnowledgeBrief,
    ResearchSource,
    ScriptGenerateRequest,
    StructuredSceneScript,
    StructuredScript,
)
from src.schemas.project import ProjectCreate
from src.schemas.scene import SceneCreate
from src.schemas.task import TaskCreate
from src.services.generation_service import normalize_knowledge_script
from src.services.project_service import ProjectService
from src.services.scene_service import SceneService
from src.services.task_service import TaskService


def test_knowledge_brief_normalizes_claims_and_sources():
    brief = KnowledgeBrief.from_payload(
        {
            "audience": "普通观众",
            "thesis": "先定义，再说明机制",
            "viewer_takeaway": "解释一个现象",
            "key_claims": [{"statement": "机制需要证据", "source_refs": ["source-old"]}],
            "source_refs": ["source-old"],
        }
    )

    assert brief.audience == "普通观众"
    assert brief.thesis == "先定义，再说明机制"
    assert brief.viewer_takeaway == "解释一个现象"
    assert brief.key_claims[0].statement == "机制需要证据"
    assert brief.key_claims[0].source_refs == ["source-old"]


def test_research_source_ids_and_scene_provenance_survive_script_normalization():
    source = ResearchSource(title="权威资料", url="https://example.com/fact")
    payload = ScriptGenerateRequest(
        topic="一个有来源的知识主题",
        research_sources=[source],
        knowledge_brief={
            "audience": "普通观众",
            "thesis": "证据要跟着主张走",
            "viewer_takeaway": "知道去哪里复核",
            "key_claims": [
                {"id": "claim-1", "statement": "来源关系应被保留", "source_refs": [source.url]}
            ],
        },
    )
    script = StructuredScript(
        title="来源关系",
        hook="先看证据",
        narration="来源关系应被保留。",
        scenes=[
            StructuredSceneScript(
                sequence_index=0,
                narration_text="来源关系应被保留。",
                visual_prompt="一张清晰的来源卡片",
                visual_role=VisualRole.QUOTE,
                claim_refs=["claim-1"],
                source_refs=[source.url],
            )
        ],
    )

    normalized = normalize_knowledge_script(script, payload=payload)
    ref_id = source.ref_id

    assert ref_id
    assert normalized.knowledge_brief.source_refs == [ref_id]
    assert normalized.knowledge_brief.key_claims[0].source_refs == [ref_id]
    assert normalized.scenes[0].source_refs == [ref_id]
    assert normalized.scenes[0].claim_refs == ["claim-1"]
    assert normalized.scenes[0].production_metadata == {}


def test_scene_create_exposes_knowledge_metadata_separately_from_layout():
    scene = SceneCreate(
        sequence_index=0,
        narration_text="按步骤解释机制。",
        visual_prompt="步骤卡片",
        duration_seconds=4,
        visual_role=VisualRole.PROCESS,
        claim_refs=["claim-1"],
        source_refs=["source-1"],
        production_metadata={"knowledge": {"reading_order": "left_to_right"}},
    )

    assert scene.visual_role is VisualRole.PROCESS
    assert scene.claim_refs == ["claim-1"]
    assert scene.source_refs == ["source-1"]
    assert scene.production_metadata["knowledge"]["reading_order"] == "left_to_right"


@pytest.mark.asyncio
async def test_scene_knowledge_metadata_persists_without_entering_layout_params(test_session):
    project = await ProjectService(test_session).create_project(ProjectCreate(name="Knowledge scenes"))
    task = await TaskService(test_session).create_task(project.id, TaskCreate(title="Scene metadata"))
    created = await SceneService(test_session).replace_task_scenes(
        task.id,
        [
            SceneCreate(
                sequence_index=0,
                narration_text="先定义，再解释。",
                visual_prompt="概念卡片",
                duration_seconds=4,
                layout_params={"badge_text": "定义"},
                visual_role=VisualRole.CONCEPT,
                claim_refs=["claim-1"],
                source_refs=["source-1"],
                production_metadata={"knowledge": {"reading_order": "top_to_bottom"}},
            )
        ],
    )

    assert created[0].visual_role == "concept"
    assert created[0].claim_refs == ["claim-1"]
    assert created[0].source_refs == ["source-1"]
    assert created[0].production_metadata["knowledge"]["reading_order"] == "top_to_bottom"
    assert "claim_refs" not in created[0].layout_params
    assert "source_refs" not in created[0].layout_params

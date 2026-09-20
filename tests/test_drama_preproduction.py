from __future__ import annotations

import pytest

from src.core.exceptions import ValidationException
from src.domain.drama import ApprovalStatus, DramaSourceType, DramaStage, character_prompt_anchor
from src.domain.enums import ProductionMode
from src.schemas.drama import DramaBibleCreate, DramaPlanRequest, DramaShotUpdate
from src.schemas.project import ProjectCreate
from src.services.drama_production_service import DramaProductionService
from src.services.drama_render_adapter import adapt_approved_shots_to_render_scenes
from src.services.project_service import ProjectService

SCRIPT = """# 标题：夜班之后
# 题材：都市

## 角色
- 林夏 | 夜班程序员，敏感但有行动力 | 短发、清晰眉骨、左耳银色耳钉 | 深蓝风衣，银色耳钉 | voice-lin
- 陈默 | 画室老师，克制而温和 | 戴圆框眼镜、深色眼睛 | 灰色针织衫 | voice-chen

## 分镜
### 镜头一
场景：办公室
角色：林夏
景别：中景
运镜：缓慢推进
动作：林夏合上电脑，望向窗外。
画面：深夜办公室只剩一盏台灯，林夏合上电脑望向窗外。
台词：林夏：又是凌晨两点。
时长：5 秒

### 镜头二
场景：街角画室
角色：林夏、陈默
景别：双人中景
运镜：固定
动作：陈默打开画室的门，林夏停在门口。
画面：雨后的街角画室亮起暖光，两人在门口对视。
台词：陈默：你终于来了。
时长：6 秒
"""


@pytest.mark.asyncio
async def test_script_entry_builds_explicit_episode_scene_shot_hierarchy(test_session):
    project = await ProjectService(test_session).create_project(
        ProjectCreate(name="Drama project", primary_production_mode=ProductionMode.DRAMA)
    )
    service = DramaProductionService(test_session)
    bible = await service.create_bible(
        project.id,
        DramaBibleCreate(source_type=DramaSourceType.SCRIPT, title="输入稿", source_text=SCRIPT),
    )

    detail = await service.plan(bible.id, DramaPlanRequest())

    assert detail.source_type == DramaSourceType.SCRIPT.value
    assert detail.current_stage == DramaStage.APPROVAL.value
    assert len(detail.characters) == 2
    assert [character.voice_id for character in detail.characters] == ["voice-lin", "voice-chen"]
    assert len(detail.locations) == 2
    assert len(detail.episodes) == 1
    assert [scene.sequence_index for scene in detail.episodes[0].scenes] == [1, 2]
    assert [len(scene.shots) for scene in detail.episodes[0].scenes] == [1, 1]
    assert detail.episodes[0].scenes[0].shots[0].dialogue_lines[0].speaker_name == "林夏"
    assert detail.episodes[0].scenes[0].shots[0].prompt_anchor.startswith("shot:storyboard:")
    assert detail.stage_state[DramaStage.STORYBOARD.value]["status"] == "awaiting_approval"
    assert detail.checkpoint["resume_stage"] == DramaStage.ASSETS.value
    assert character_prompt_anchor("林夏", "短发", "深蓝风衣") == character_prompt_anchor("林夏", "短发", "深蓝风衣")
    assert character_prompt_anchor("林夏", "短发", "深蓝风衣") != character_prompt_anchor("林夏", "长发", "深蓝风衣")


@pytest.mark.asyncio
async def test_approval_gate_blocks_render_adapter_until_every_shot_is_approved(test_session):
    project = await ProjectService(test_session).create_project(
        ProjectCreate(name="Approval project", primary_production_mode=ProductionMode.DRAMA)
    )
    service = DramaProductionService(test_session)
    bible = await service.create_bible(
        project.id,
        DramaBibleCreate(
            source_type=DramaSourceType.IDEA,
            title="一盏灯",
            source_text="一个夜班程序员在关灯前决定重新拿起画笔。",
        ),
    )
    detail = await service.plan(bible.id, DramaPlanRequest())

    with pytest.raises(ValidationException, match="尚未批准"):
        adapt_approved_shots_to_render_scenes(detail)

    for character in detail.characters:
        detail = await service.approve_character(detail.id, character.id)
    for location in detail.locations:
        detail = await service.approve_location(detail.id, location.id)
    shot = detail.episodes[0].scenes[0].shots[0]
    with pytest.raises(ValidationException, match="单集剧本"):
        await service.approve_shot(detail.id, shot.id)
    for episode in detail.episodes:
        detail = await service.approve_episode(detail.id, episode.id)
        for scene in episode.scenes:
            detail = await service.approve_scene(detail.id, scene.id)
            for shot in scene.shots:
                detail = await service.approve_shot(detail.id, shot.id)

    preflight = await service.storyboard_preflight(detail.id)
    assert preflight["ready"] is True
    approved, final_preflight = await service.approve_storyboard(detail.id)
    assert approved.approval_status == ApprovalStatus.APPROVED.value
    assert final_preflight["ready"] is True
    assert approved.episodes[0].approval_status == ApprovalStatus.APPROVED.value
    assert approved.episodes[0].scenes[0].approval_status == ApprovalStatus.APPROVED.value

    drafts = adapt_approved_shots_to_render_scenes(approved)
    assert len(drafts) == 5
    assert drafts[0].production_metadata["source"] == "drama_shot"
    assert drafts[0].visual_prompt.endswith(f"{approved.episodes[0].scenes[0].shots[0].prompt_anchor}.")


@pytest.mark.asyncio
async def test_shot_editor_rebuilds_dialogue_lines_with_voice_and_timing_metadata(test_session):
    project = await ProjectService(test_session).create_project(
        ProjectCreate(name="Dialogue editor", primary_production_mode=ProductionMode.DRAMA)
    )
    service = DramaProductionService(test_session)
    bible = await service.create_bible(
        project.id,
        DramaBibleCreate(
            source_type=DramaSourceType.SCRIPT,
            title="对白编辑",
            source_text=SCRIPT,
        ),
    )
    detail = await service.plan(bible.id, DramaPlanRequest())
    shot = detail.episodes[0].scenes[0].shots[0]

    detail = await service.update_shot(
        detail.id,
        shot.id,
        DramaShotUpdate(dialogue="林夏（低声） @0-2s：别关灯。\n旁白：她停了一秒。"),
    )

    updated_lines = detail.episodes[0].scenes[0].shots[0].dialogue_lines
    assert [(line.speaker_name, line.text) for line in updated_lines] == [
        ("林夏", "别关灯。"),
        ("旁白", "她停了一秒。"),
    ]
    assert updated_lines[0].delivery == "低声"
    assert updated_lines[0].timing_hint == "0-2s"
    assert updated_lines[0].character_id == next(
        character.id for character in detail.characters if character.name == "林夏"
    )


@pytest.mark.asyncio
async def test_script_entry_preserves_episode_headings(test_session):
    project = await ProjectService(test_session).create_project(
        ProjectCreate(name="Multi episode", primary_production_mode=ProductionMode.DRAMA)
    )
    service = DramaProductionService(test_session)
    source = """# 标题：两集短剧
## 角色
- 林夏 | 夜班程序员 | 短发 | 深蓝风衣 | voice-lin
## 第1集：灯还亮着
### 镜头一
场景：办公室
角色：林夏
动作：林夏盯着屏幕。
画面：办公室只剩一盏灯。
台词：林夏：我还不能停。
时长：3 秒
## EP2：门外的人
### 镜头一
场景：办公室门口
角色：林夏
动作：门外传来敲门声。
画面：林夏回头看向门口。
台词：旁白：有人来了。
时长：3 秒
"""
    bible = await service.create_bible(
        project.id,
        DramaBibleCreate(source_type=DramaSourceType.SCRIPT, title="输入稿", source_text=source),
    )

    detail = await service.plan(bible.id, DramaPlanRequest())

    assert [(episode.episode_number, episode.title) for episode in detail.episodes] == [
        (1, "灯还亮着 · 两集短剧"),
        (2, "门外的人 · 两集短剧"),
    ]
    assert [len(episode.scenes[0].shots) for episode in detail.episodes] == [1, 1]

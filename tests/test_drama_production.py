from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select

from src.domain.drama import DramaSourceType
from src.models.asset import AssetModel
from src.models.scene import SceneModel
from src.models.workflow import WorkflowArtifactModel, WorkflowStepRunModel
from src.providers.registry import provider_registry
from src.schemas.drama import (
    DramaBibleCreate,
    DramaCharacterUpdate,
    DramaPlanRequest,
    DramaProductionStartRequest,
)
from src.schemas.project import ProjectCreate
from src.services.drama_production_service import DramaProductionService
from src.services.generation_service import create_solid_color_png
from src.services.project_service import ProjectService
from src.services.rendering_service import RenderingService
from src.services.template_renderer import TemplateRenderer
from src.storage.local_storage import LocalStorageService
from src.tasks.executor import VideoWorkflowExecutor
from src.tasks.job import Job

SCRIPT = """# 标题：夜班之后
## 角色
- 林夏 | 夜班程序员 | 短发、左耳银色耳钉 | 深蓝风衣 | voice-lin
- 陈默 | 画室老师 | 圆框眼镜 | 灰色针织衫 | voice-chen
## 分镜
### 镜头一
场景：办公室
角色：林夏
动作：林夏合上电脑，望向窗外。
画面：深夜办公室只剩一盏台灯，林夏合上电脑望向窗外。
台词：林夏：又是凌晨两点。\n旁白：她决定今晚不再逃避。
时长：2 秒
### 镜头二
场景：街角画室
角色：林夏、陈默
动作：陈默打开画室的门，林夏停在门口。
画面：雨后的街角画室亮起暖光，两人在门口对视。
台词：陈默：你终于来了。
时长：2 秒
"""


async def _approved_drama(session):
    project = await ProjectService(session).create_project(ProjectCreate(name="Drama production"))
    service = DramaProductionService(session)
    bible = await service.create_bible(
        project.id,
        DramaBibleCreate(source_type=DramaSourceType.SCRIPT, title="夜班之后", source_text=SCRIPT),
    )
    detail = await service.plan(bible.id, DramaPlanRequest())
    for character in detail.characters:
        voice = "voice-lin" if character.name == "林夏" else "voice-chen"
        detail = await service.update_character(
            detail.id,
            character.id,
            DramaCharacterUpdate(voice_id=voice),
        )
        detail = await service.approve_character(detail.id, character.id)
    for location in detail.locations:
        detail = await service.approve_location(detail.id, location.id)
    for episode in detail.episodes:
        detail = await service.approve_episode(detail.id, episode.id)
        for scene in episode.scenes:
            detail = await service.approve_scene(detail.id, scene.id)
            for shot in scene.shots:
                detail = await service.approve_shot(detail.id, shot.id)
    detail, _ = await service.approve_storyboard(detail.id)
    return project, service, detail


def _rendering_factory(storage: LocalStorageService, fixture: Path):
    async def render_frame(*args, output_path, **kwargs):
        output_path.write_bytes(create_solid_color_png(720, 1280))

    async def fake_ffmpeg(command: list[str], output_path: Path) -> bool:
        if output_path.suffix.lower() == ".wav":
            await asyncio.to_thread(
                subprocess.run,
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        else:
            output_path.write_bytes(fixture.read_bytes())
        return True

    return render_frame, lambda session: RenderingService(
        session,
        storage=storage,
        ffmpeg_runner=fake_ffmpeg,
    )


@pytest.mark.asyncio
async def test_drama_production_mixes_dialogue_and_creates_timed_subtitles(
    test_session, tmp_path, monkeypatch
):
    project, service, detail = await _approved_drama(test_session)
    task = await service.create_production_task(
        detail.id,
        DramaProductionStartRequest(episode_id=detail.episodes[0].id),
    )
    fixture = Path(__file__).parent / "fixtures" / "mock.mp4"
    storage = LocalStorageService(tmp_path / "drama-storage")
    render_frame, rendering_factory = _rendering_factory(storage, fixture)
    monkeypatch.setattr(TemplateRenderer, "render", render_frame)
    result = await VideoWorkflowExecutor(
        session_factory=lambda: _session_context(test_session),
        rendering_service_factory=rendering_factory,
    ).execute(Job(task_id=task.id))

    assert result["video_status"] == "ready"
    assert result["drama_id"] == detail.id
    assert len(result["subtitle_artifact_ids"]) == 2
    status = await service.get_production_status(detail.id, detail.episodes[0].id)
    assert status.status == "completed"
    assert status.final_video_url
    assert all(shot.status == "completed" for shot in status.shots)
    assert sum(len(shot.dialogue_timeline) for shot in status.shots) == 3
    # The stock mock does not record calls; the persisted line assets still
    # prove that each DialogueLine was synthesized before the shot mix.
    line_assets = (
        await test_session.scalars(
            select(AssetModel).where(AssetModel.project_id == project.id)
        )
    ).all()
    assert sum(1 for asset in line_assets if (asset.metadata_json or {}).get("dialogue_line_id")) == 3
    mixed = [asset for asset in line_assets if (asset.metadata_json or {}).get("dialogue_line_ids")]
    assert len(mixed) == 2

    srt_artifact = await test_session.scalar(
        select(WorkflowArtifactModel).where(
            WorkflowArtifactModel.id.in_(result["subtitle_artifact_ids"]),
            WorkflowArtifactModel.kind == "srt",
        )
    )
    srt = storage.get_path(srt_artifact.relative_path).read_text(encoding="utf-8")
    assert "又是凌晨两点。" in srt
    assert "她决定今晚不再逃避。" in srt
    assert srt.count(" --> ") == 3
    assert not any("Deterministic continuity anchor" in line for line in srt.splitlines())


@pytest.mark.asyncio
async def test_drama_production_retries_one_failed_shot_only(test_session, tmp_path, monkeypatch):
    _, service, detail = await _approved_drama(test_session)
    task = await service.create_production_task(
        detail.id,
        DramaProductionStartRequest(episode_id=detail.episodes[0].id),
    )
    fixture = Path(__file__).parent / "fixtures" / "mock.mp4"
    storage = LocalStorageService(tmp_path / "drama-storage")
    render_frame, rendering_factory = _rendering_factory(storage, fixture)
    monkeypatch.setattr(TemplateRenderer, "render", render_frame)
    original = provider_registry.image
    failed = {"prompt": None, "allow_success": False}
    calls: list[str] = []

    class FailOnceImage:
        name = "mock"

        async def generate_image(self, prompt, **kwargs):
            calls.append(prompt)
            if failed["prompt"] is None and "Character anchor" in prompt:
                failed["prompt"] = prompt
            if failed["prompt"] == prompt and not failed["allow_success"]:
                raise RuntimeError("one shot failed")
            return await original.generate_image(prompt, **kwargs)

    monkeypatch.setattr(provider_registry, "_image_provider", FailOnceImage())
    executor = VideoWorkflowExecutor(
        session_factory=lambda: _session_context(test_session),
        rendering_service_factory=rendering_factory,
    )
    with pytest.raises(Exception, match="QA|Episode"):
        await executor.execute(Job(task_id=task.id))
    render_scenes = list((await test_session.scalars(select(SceneModel).where(SceneModel.task_id == task.id))).all())
    runs = list((await test_session.scalars(select(WorkflowStepRunModel).where(WorkflowStepRunModel.task_id == task.id))).all())
    media_runs = [run for run in runs if run.step_key == "media"]
    failed_scene = next(scene for scene in render_scenes if scene.media_asset_id is None)
    successful_scene = next(scene for scene in render_scenes if scene.media_asset_id)
    assert any(run.unit_key == failed_scene.id and run.status == "failed" for run in media_runs)
    assert any(run.unit_key == successful_scene.id and run.status in {"completed", "reused"} for run in media_runs)
    failed_prompt = failed["prompt"]
    successful_prompt = next(prompt for prompt in calls if prompt != failed_prompt)
    successful_calls_before_retry = calls.count(successful_prompt)
    failed_calls_before_retry = calls.count(failed_prompt)

    failed["allow_success"] = True
    await executor.execute(
        Job(
            task_id=task.id,
            params={"force_step": "media", "force_unit": failed_scene.id},
        )
    )
    # A forced unit retry must not re-run the already completed Shot. The
    # provider compatibility path may make more than one call for the
    # retried Shot, so assert the unit-level boundary instead of a global
    # call count.
    assert calls.count(successful_prompt) == successful_calls_before_retry
    assert calls.count(failed_prompt) > failed_calls_before_retry
    render_scenes = list((await test_session.scalars(select(SceneModel).where(SceneModel.task_id == task.id))).all())
    assert all(scene.media_asset_id for scene in render_scenes)


class _session_context:
    """Tiny async-context adapter for the shared test session."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


def _session_factory(session):
    return lambda: _session_context(session)

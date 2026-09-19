import subprocess
from pathlib import Path

import pytest

from src.domain.enums import AssetType, JobType, TaskStatus
from src.models.asset import AssetModel
from src.models.project import ProjectModel
from src.models.scene import SceneModel
from src.models.task import TaskModel
from src.services.asset_service import AssetService
from src.services.media_probe import media_probe_service
from src.services.rendering_service import RenderingService
from src.services.template_renderer import TemplateRenderer
from src.storage.local_storage import LocalStorageService


@pytest.mark.asyncio
async def test_rendering_service_persists_scene_and_composition(test_session, tmp_path, monkeypatch):
    rendered_frame_bytes = b"template-frame"
    rendered_media_bytes = b"rendered-media"
    render_calls: list[str] = []
    ffmpeg_calls: list[list[str]] = []

    async def fake_template_render(*_args, output_path, **_kwargs):
        render_calls.append(str(output_path))
        output_path.write_bytes(rendered_frame_bytes)

    async def fake_ffmpeg_runner(cmd: list[str], output_path: Path) -> bool:
        ffmpeg_calls.append(cmd)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(rendered_media_bytes)
        return True

    monkeypatch.setattr(TemplateRenderer, "render", fake_template_render)

    storage = LocalStorageService(base_storage_dir=tmp_path / "rendering-storage")
    asset_service = AssetService(test_session, storage=storage)
    rendering_service = RenderingService(
        test_session,
        storage=storage,
        ffmpeg_runner=fake_ffmpeg_runner,
    )

    img_asset = await asset_service.save_asset(
        content=b"source-image",
        file_name="test-source.png",
        mime_type="image/png",
        asset_type=AssetType.IMAGE,
    )

    proj = ProjectModel(id="proj_rendering_service", name="Rendering service", aspect_ratio="9:16")
    task = TaskModel(
        id="task_rendering_service",
        project_id=proj.id,
        title="Rendering service video",
        job_type=JobType.VIDEO_COMPOSITION.value,
        status=TaskStatus.RUNNING.value,
    )
    scene = SceneModel(
        id="scene_rendering_service_1",
        task_id=task.id,
        sequence_index=0,
        narration_text="Real test",
        visual_prompt="Solid color",
        duration_seconds=2.0,
        media_asset_id=img_asset.id,
        layout_params={
            "dialogue_timeline": [
                {"text": "对白会进入成片", "start": 0.2, "end": 1.4},
            ]
        },
    )
    test_session.add_all([proj, task, scene])
    await test_session.commit()

    # Keep the service's image rendering and persistence path under test.
    clip_rel = await rendering_service.render_scene_clip(scene.id)
    assert clip_rel is not None
    clip_path = storage.get_path(clip_rel)
    assert clip_path.exists()
    assert clip_path.read_bytes() == rendered_media_bytes
    assert len(render_calls) == 1
    assert len(ffmpeg_calls) == 1
    assert ffmpeg_calls[0][0] == "ffmpeg"
    assert "-loop" in ffmpeg_calls[0]
    assert "-map" in ffmpeg_calls[0]
    assert "ass=filename=" in ffmpeg_calls[0][ffmpeg_calls[0].index("-filter_complex") + 1]
    await test_session.refresh(scene)
    clip_asset = await test_session.get(AssetModel, scene.rendered_segment_asset_id)
    assert clip_asset is not None
    assert clip_asset.metadata_json["subtitle_burned"] is True
    assert clip_asset.metadata_json["subtitle_line_count"] == 1

    # Composition should reuse the rendered clip and persist the final result.
    final_asset = await rendering_service.compose_task_video(task.id)
    assert final_asset is not None
    final_path = storage.get_path(final_asset.file_path)
    assert final_path.exists()
    assert final_path.read_bytes() == rendered_media_bytes
    assert len(ffmpeg_calls) == 2
    assert ffmpeg_calls[1][0] == "ffmpeg"
    assert "-filter_complex" in ffmpeg_calls[1]
    await test_session.refresh(task)
    updated_task = task
    assert updated_task.result_payload is not None
    assert updated_task.result_payload["final_video_asset_id"] == final_asset.id
    assert "final_video_url" in updated_task.result_payload


def _create_online_layout_source(path: Path, size: str, duration: float = 0.8) -> None:
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=12",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
            "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k", str(path),
        ],
        timeout=30,
        check=True,
        capture_output=True,
    )


@pytest.mark.asyncio
async def test_online_asset_layout_covers_mismatched_source_aspect(test_session, tmp_path):
    source_size = "480x360"
    storage = LocalStorageService(base_storage_dir=tmp_path / "online-layout-storage")
    asset_service = AssetService(test_session, storage=storage)
    source_path = tmp_path / f"source-{source_size}.mp4"
    _create_online_layout_source(source_path, source_size)
    source_probe = await media_probe_service.probe(source_path)

    project = ProjectModel(id=f"project_online_layout_{source_size.replace('x', '_')}", name="Online layout")
    task = TaskModel(
        id=f"task_online_layout_{source_size.replace('x', '_')}",
        project_id=project.id,
        title="在线素材安全构图",
        job_type=JobType.VIDEO_COMPOSITION.value,
        status=TaskStatus.RUNNING.value,
        input_payload={"template_id": "video_cinema_scope", "content_mode": "online_asset"},
    )
    asset = await asset_service.save_asset_from_file(
        source_path,
        file_name=f"source-{source_size}.mp4",
        mime_type="video/mp4",
        asset_type=AssetType.VIDEO,
        project_id=project.id,
        duration_seconds=source_probe.duration_seconds,
        width=source_probe.width,
        height=source_probe.height,
        metadata={"source_kind": "online_asset", "external_id": source_size},
    )
    scene = SceneModel(
        id=f"scene_online_layout_{source_size.replace('x', '_')}",
        task_id=task.id,
        sequence_index=0,
        narration_text="不同素材比例都使用统一的安全字幕区域",
        duration_seconds=0.8,
        media_asset_id=asset.id,
    )
    test_session.add_all([project, task, scene])
    await test_session.commit()

    rendering_service = RenderingService(test_session, storage=storage)
    clip_path = storage.get_path(await rendering_service.render_scene_clip(scene.id))
    clip_probe = await media_probe_service.probe(clip_path)

    assert clip_probe.width == 1080
    assert clip_probe.height == 1920
    assert clip_probe.has_video is True
    assert clip_probe.has_audio is True
    assert clip_probe.duration_seconds == pytest.approx(0.8, abs=RenderingService.DURATION_TOLERANCE_SECONDS)
    filter_graph = rendering_service.commands[0][
        rendering_service.commands[0].index("-filter_complex") + 1
    ]
    assert "split=2" in filter_graph
    assert "boxblur" in filter_graph
    assert "crop=1080:1920" in filter_graph
    assert "crop=1080:1120" in filter_graph
    assert "overlay=0:260" in filter_graph

    await test_session.refresh(scene)
    clip_asset = await test_session.get(AssetModel, scene.rendered_segment_asset_id)
    assert clip_asset is not None
    assert clip_asset.metadata_json["layout_strategy"] == "online_cover_blurred_background"
    assert clip_asset.metadata_json["scene_render_format_version"] == RenderingService.ONLINE_SCENE_RENDER_FORMAT_VERSION


@pytest.mark.asyncio
async def test_online_scene_render_version_invalidates_old_clip_and_reuses_current_clip(
    test_session, tmp_path, monkeypatch
):
    storage = LocalStorageService(base_storage_dir=tmp_path / "online-version-storage")
    asset_service = AssetService(test_session, storage=storage)
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "mock.mp4"
    source_path = tmp_path / "old-scene-clip.mp4"
    fixture_bytes = fixture_path.read_bytes()
    source_path.write_bytes(fixture_bytes)

    project = ProjectModel(id="project_online_version", name="Online version")
    task = TaskModel(
        id="task_online_version",
        project_id=project.id,
        title="在线素材版本失效",
        job_type=JobType.VIDEO_COMPOSITION.value,
        status=TaskStatus.RUNNING.value,
        input_payload={"template_id": "video_full_overlay", "content_mode": "online_asset"},
    )
    old_clip = await asset_service.save_asset_from_file(
        source_path,
        file_name="old-scene-clip.mp4",
        mime_type="video/mp4",
        asset_type=AssetType.VIDEO,
        project_id=project.id,
        duration_seconds=0.5,
        width=64,
        height=64,
        metadata={"type": "scene_clip"},
    )
    scene = SceneModel(
        id="scene_online_version",
        task_id=task.id,
        sequence_index=0,
        narration_text="版本变化后需要重新检查在线素材构图",
        duration_seconds=0.5,
        rendered_segment_asset_id=old_clip.id,
    )
    test_session.add_all([project, task, scene])
    await test_session.commit()

    ffmpeg_calls: list[list[str]] = []

    async def fake_ffmpeg_runner(cmd: list[str], output_path: Path) -> bool:
        ffmpeg_calls.append(cmd)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(fixture_bytes)
        return True

    rendering_service = RenderingService(
        test_session,
        storage=storage,
        ffmpeg_runner=fake_ffmpeg_runner,
    )
    render_calls: list[str] = []

    async def refresh_old_clip(scene_id: str) -> str:
        render_calls.append(scene_id)
        clip = await test_session.get(AssetModel, old_clip.id)
        assert clip is not None
        clip.metadata_json = {
            **(clip.metadata_json or {}),
            "scene_render_format_version": RenderingService.ONLINE_SCENE_RENDER_FORMAT_VERSION,
        }
        await test_session.commit()
        return clip.file_path

    monkeypatch.setattr(rendering_service, "render_scene_clip", refresh_old_clip)
    await rendering_service.compose_task_video(task.id)
    assert render_calls == [scene.id]
    assert len(ffmpeg_calls) == 1

    async def unexpected_rerender(scene_id: str) -> str:
        raise AssertionError(f"current online clip should be reused: {scene_id}")

    monkeypatch.setattr(rendering_service, "render_scene_clip", unexpected_rerender)
    await rendering_service.compose_task_video(task.id, bgm_asset_id="")
    assert len(ffmpeg_calls) == 2

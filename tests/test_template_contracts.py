import asyncio
import subprocess

import pytest
from httpx import AsyncClient

from src.core.exceptions import ValidationException
from src.domain.enums import AssetType, JobType, TaskStatus
from src.models.project import ProjectModel
from src.models.scene import SceneModel
from src.models.task import TaskModel
from src.services.asset_service import AssetService
from src.services.rendering_service import RenderingService
from src.services.template_catalog import (
    parse_media_size,
    parse_parameters,
    render_template_html,
    template_catalog,
)
from src.services.template_renderer import TemplateRenderer
from src.storage.local_storage import LocalStorageService


def test_template_catalog_supports_multi_resolution_catalog_and_aliases_are_stable():
    template_catalog.invalidate()
    all_templates = template_catalog.scan()
    assert len(all_templates) == 19

    # 9:16 (Vertical): 7 active templates
    vertical = template_catalog.scan("9:16")
    assert len(vertical) == 7
    assert {item["width"] for item in vertical} == {1080}
    assert {item["height"] for item in vertical} == {1920}
    assert {item["aspect_ratio"] for item in vertical} == {"9:16"}

    # 16:9 (Landscape): 6 active templates
    landscape = template_catalog.scan("16:9")
    assert len(landscape) == 6
    assert {item["width"] for item in landscape} == {1920}
    assert {item["height"] for item in landscape} == {1080}
    assert {item["aspect_ratio"] for item in landscape} == {"16:9"}
    assert {item["id"] for item in landscape} == {
        "image_wide_minimal",
        "image_wide_cinema",
        "image_wide_editorial",
        "static_wide_bulletin",
        "video_wide_full",
        "video_wide_cinema_scope",
    }

    # 1:1 (Square): 6 active templates
    square = template_catalog.scan("1:1")
    assert len(square) == 6
    assert {item["width"] for item in square} == {1080}
    assert {item["height"] for item in square} == {1080}
    assert {item["aspect_ratio"] for item in square} == {"1:1"}
    assert {item["id"] for item in square} == {
        "image_square_matted",
        "image_square_frosted",
        "image_square_editorial",
        "static_square_quote",
        "video_square_full",
        "video_square_card",
    }

    # Video frames
    assert template_catalog.get_video_frame("video_cinema_scope") == (0, 260, 1080, 1120)
    assert template_catalog.get_video_frame("video_wide_full") == (0, 0, 1920, 1080)
    assert template_catalog.get_video_frame("video_wide_cinema_scope") == (0, 138, 1920, 804)
    assert template_catalog.get_video_frame("video_square_full") == (0, 0, 1080, 1080)
    assert template_catalog.get_video_frame("video_square_card") == (0, 236, 1080, 608)

    # Aspect default resolution
    assert template_catalog.get_default_for_aspect("9:16") == "image_gallery_matted"
    assert template_catalog.get_default_for_aspect("16:9") == "image_wide_minimal"
    assert template_catalog.get_default_for_aspect("1:1") == "image_square_matted"
    assert template_catalog.get_default_for_aspect("9:16", "generated_video") == "video_full_overlay"
    assert template_catalog.get_default_for_aspect("16:9", "generated_video") == "video_wide_full"
    assert template_catalog.get_default_for_aspect("1:1", "generated_video") == "video_square_full"

    # Aliases
    assert template_catalog.get("image_gallery_matted")["html_path"].endswith("image_gallery_matted.html")
    assert template_catalog.get("image_wide_minimal")["html_path"].endswith("image_wide_minimal.html")
    assert template_catalog.get("image_square_matted")["html_path"].endswith("image_square_matted.html")
    assert template_catalog.get("video_full_overlay")["html_path"].endswith("video_full_overlay.html")
    assert template_catalog.get("video_wide_full")["html_path"].endswith("video_wide_full.html")
    assert template_catalog.get("video_square_full")["html_path"].endswith("video_square_full.html")
    assert template_catalog.get("static_editorial_quote")["html_path"].endswith("static_editorial_quote.html")

    # Demo media contract used by generation
    assert template_catalog.get("image_gallery_matted")["media_width"] == 1024
    assert template_catalog.get("image_gallery_matted")["media_height"] == 1024
    assert template_catalog.get("video_full_overlay")["media_width"] == 1080
    assert template_catalog.get("video_full_overlay")["media_height"] == 1920
    assert template_catalog.get_media_aspect_ratio("image_gallery_matted") == "1:1"
    assert template_catalog.get_media_aspect_ratio("video_full_overlay") == "9:16"
    assert parse_media_size(
        '<meta content="512" name="template:media-width">'
        '<meta name="template:media-height" content="288">'
    ) == (512, 288)
    assert parse_media_size("<html><head></head></html>") == (1024, 1024)


def test_template_parameter_dsl_escapes_text_and_validates_typed_values():
    source = "{{ title }} {{accent_color:color=#764ba2}} {{title_font_size:number=72}}"
    assert [item["name"] for item in parse_parameters(source)] == [
        "accent_color",
        "title_font_size",
    ]
    rendered = render_template_html(
        source,
        {"title": "<script>alert(1)</script>", "accent_color": "#123456", "title_font_size": 80},
    )
    assert "&lt;script&gt;" in rendered
    assert "#123456" in rendered
    assert "80" in rendered


@pytest.mark.asyncio
async def test_template_renderer_does_not_duplicate_narration_with_template_metadata(
    tmp_path, monkeypatch
):
    narration = "唯一的旁白文本-duplicate-regression"
    captured: dict[str, str] = {}

    async def fake_ensure_browser():
        return object()

    async def fake_capture_page(browser, *, html_path, destination, **kwargs):
        captured["html"] = html_path.read_text(encoding="utf-8")
        destination.write_bytes(b"rendered frame")

    monkeypatch.setattr(TemplateRenderer, "_requires_proactor_worker", staticmethod(lambda: False))
    monkeypatch.setattr(TemplateRenderer, "_ensure_browser", staticmethod(fake_ensure_browser))
    monkeypatch.setattr(TemplateRenderer, "_capture_page", staticmethod(fake_capture_page))

    output = tmp_path / "image-gallery.png"
    await TemplateRenderer.render(
        "image_gallery_matted",
        title="标题",
        text=narration,
        custom_params={"author": "@Trendlume"},
        output_path=output,
    )

    assert output.exists()
    assert captured["html"].count(narration) == 1
    assert '<span class="author-text">@Trendlume</span>' in captured["html"]


def test_template_css_rejects_remote_and_markup_injection():
    with pytest.raises(ValidationException):
        TemplateRenderer._validate_css("</style><script>alert(1)</script>")
    with pytest.raises(ValidationException):
        TemplateRenderer._validate_css(".x { background: url(https://example.com/x.png); }")


@pytest.mark.asyncio
async def test_template_api(client: AsyncClient):
    templates = await client.get("/api/v1/templates")
    assert templates.status_code == 200
    assert len(templates.json()["data"]) == 19

    # Filter by aspect ratio
    resp_9_16 = await client.get("/api/v1/templates?aspect_ratio=9:16")
    assert resp_9_16.status_code == 200
    assert len(resp_9_16.json()["data"]) == 7

    resp_16_9 = await client.get("/api/v1/templates?aspect_ratio=16:9")
    assert resp_16_9.status_code == 200
    assert len(resp_16_9.json()["data"]) == 6

    resp_1_1 = await client.get("/api/v1/templates?aspect_ratio=1:1")
    assert resp_1_1.status_code == 200
    assert len(resp_1_1.json()["data"]) == 6

    # Aspect ratio + content_mode filtered query
    resp_16_9_video = await client.get("/api/v1/templates?aspect_ratio=16:9&content_mode=generated_video")
    assert resp_16_9_video.status_code == 200
    video_items_16_9 = resp_16_9_video.json()["data"]
    assert len(video_items_16_9) == 2
    assert {item["id"] for item in video_items_16_9} == {"video_wide_full", "video_wide_cinema_scope"}

    # Portrait preview
    preview = await client.post(
        "/api/v1/templates/image_gallery_matted/preview",
        json={"title": "预览", "text": "上传图片或视频"},
    )
    assert preview.status_code == 200
    assert preview.json()["data"]["width"] == 1080
    assert preview.json()["data"]["height"] == 1920

@pytest.mark.asyncio
async def test_task_duplicate_and_rerender_api(client: AsyncClient):
    project = await client.post("/api/v1/projects", json={"name": "Phase 3 rerender", "aspect_ratio": "9:16"})
    project_id = project.json()["data"]["id"]
    task = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "原始任务", "template_id": "image_gallery_matted", "content_mode": "generated_image"},
    )
    task_id = task.json()["data"]["id"]
    scenes = await client.put(
        f"/api/v1/tasks/{task_id}/scenes",
        json={"scenes": [{"sequence_index": 0, "narration_text": "台词", "visual_prompt": "画面", "duration_seconds": 2}]},
    )
    assert scenes.status_code == 200

    duplicate = await client.post(f"/api/v1/tasks/{task_id}/duplicate", json={})
    assert duplicate.status_code == 201
    duplicate_data = duplicate.json()["data"]
    assert duplicate_data["id"] != task_id
    assert duplicate_data["scenes"][0]["audio_asset_id"] is None
    assert duplicate_data["scenes"][0]["media_asset_id"] is None

    # Incompatible content mode is rejected
    rerender = await client.post(
        f"/api/v1/tasks/{task_id}/rerender",
        json={"template_id": "static_editorial_quote"},
    )
    assert rerender.status_code == 422

    # Cross-aspect ratio template (16:9 template on 9:16 project) is rejected
    cross_aspect_rerender = await client.post(
        f"/api/v1/tasks/{task_id}/rerender",
        json={"template_id": "image_wide_minimal"},
    )
    assert cross_aspect_rerender.status_code == 422
    assert "画幅" in cross_aspect_rerender.json()["error"]["message"]

    # Adapted template (matching 9:16 aspect ratio & generated_image mode) succeeds
    valid_rerender = await client.post(
        f"/api/v1/tasks/{task_id}/rerender",
        json={"template_id": "image_editorial_warm"},
    )
    assert valid_rerender.status_code == 200
    assert valid_rerender.json()["data"]["job"]["job_type"] in ("composition", "full_pipeline")


@pytest.mark.asyncio
async def test_static_template_renders_without_media_provider(test_session, tmp_path):
    storage = LocalStorageService(base_storage_dir=tmp_path / "static-storage")
    project = ProjectModel(id="proj_static_template", name="Static", aspect_ratio="9:16")
    task = TaskModel(
        id="task_static_template",
        project_id=project.id,
        title="静态模板",
        job_type=JobType.FULL_PIPELINE.value,
        status=TaskStatus.PENDING.value,
        input_payload={"template_id": "static_editorial_quote", "content_mode": "static"},
    )
    scene = SceneModel(
        id="scene_static_template",
        task_id=task.id,
        sequence_index=0,
        narration_text="不会调用图片或视频 Provider",
        visual_prompt="",
        duration_seconds=1.0,
    )
    test_session.add_all([project, task, scene])
    await test_session.commit()

    rendered = await RenderingService(test_session, storage=storage).render_scene_clip(scene.id)
    clip = storage.get_path(rendered)
    assert clip.exists() and clip.stat().st_size > 1000


@pytest.mark.asyncio
async def test_video_template_keeps_dynamic_source_under_overlay(test_session, tmp_path):
    storage = LocalStorageService(base_storage_dir=tmp_path / "video-storage")
    source_path = tmp_path / "source.mp4"
    await asyncio.to_thread(subprocess.run,
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=12", "-t", "1", str(source_path)],
        timeout=30,
        check=True,
        capture_output=True,
    )
    project = ProjectModel(id="proj_video_template", name="Video", aspect_ratio="9:16")
    task = TaskModel(
        id="task_video_template",
        project_id=project.id,
        title="动态模板",
        job_type=JobType.FULL_PIPELINE.value,
        status=TaskStatus.PENDING.value,
        input_payload={"template_id": "video_full_overlay", "content_mode": "generated_video"},
    )
    asset = await AssetService(test_session, storage=storage).save_asset(
        content=source_path.read_bytes(),
        file_name="source.mp4",
        mime_type="video/mp4",
        asset_type=AssetType.VIDEO,
        project_id=project.id,
    )
    scene = SceneModel(
        id="scene_video_template",
        task_id=task.id,
        sequence_index=0,
        narration_text="动态画面",
        visual_prompt="",
        duration_seconds=1.0,
        media_asset_id=asset.id,
    )
    test_session.add_all([project, task, scene])
    await test_session.commit()
    clip = storage.get_path(await RenderingService(test_session, storage=storage).render_scene_clip(scene.id))
    assert clip.exists() and clip.stat().st_size > 1000

    # Verify metadata contains proper layout strategy and frame positioning
    await test_session.refresh(scene)
    from src.models.asset import AssetModel
    clip_asset = await test_session.get(AssetModel, scene.rendered_segment_asset_id)
    assert clip_asset is not None
    assert clip_asset.metadata_json["layout_strategy"] == "cover_blurred_background"
    assert clip_asset.metadata_json["media_frame"]["y"] == 0
    assert clip_asset.metadata_json["media_frame"]["height"] == 1920

    # Verify pixel in center of video slot (540, 960) preserves dynamic blue video
    proc = await asyncio.to_thread(subprocess.run,
        [
            "ffmpeg", "-y", "-ss", "0.5", "-i", str(clip),
            "-vf", "crop=2:2:540:960,format=rgb24",
            "-vframes", "1", "-f", "rawvideo", "-",
        ],
        timeout=30,
        check=True,
        capture_output=True,
    )
    assert len(proc.stdout) >= 3
    r, g, b = proc.stdout[0], proc.stdout[1], proc.stdout[2]
    assert b > 180, f"Expected vibrant blue video pixel in slot, got rgb=({r}, {g}, {b})"
    assert r < 50, f"Expected low red in blue video slot, got rgb=({r}, {g}, {b})"

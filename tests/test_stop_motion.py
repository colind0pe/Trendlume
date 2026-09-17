from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from src.api.routes import generation as generation_routes
from src.core.exceptions import ValidationException
from src.domain.enums import AssetType, JobType, TaskStatus
from src.models.asset import AssetModel
from src.models.project import ProjectModel
from src.models.scene import SceneModel
from src.models.task import TaskModel
from src.providers.image.protocol import ImageResult
from src.schemas.scene import SceneAnimationSpec, SceneMicroMotionSpec
from src.services.asset_service import AssetService
from src.services.generation_service import GenerationService
from src.services.rendering_service import RenderingService
from src.services.template_renderer import TemplateRenderer
from src.storage.local_storage import LocalStorageService
from src.tasks.executor import VideoWorkflowExecutor
from src.tasks.job import Job


def _animation(asset_ids: list[str], *, hold: float = 0.5, **overrides) -> dict:
    animation = {
        "mode": "enhanced_stop_motion",
        "pose_fps": 10,
        "output_fps": 30,
        "poses": [{"asset_id": asset_id, "hold": hold} for asset_id in asset_ids],
    }
    animation.update(overrides)
    return animation


def test_stop_motion_timeline_quantizes_and_fits_scene_duration():
    animation = SceneAnimationSpec.model_validate(
        _animation(["pose-a", "pose-b", "pose-c"], hold=0.4)
    )

    timeline = RenderingService._build_stop_motion_timeline(animation, 2.0)

    assert [item["asset_id"] for item in timeline] == ["pose-a", "pose-b", "pose-c"]
    assert [item["hold"] for item in timeline] == pytest.approx([0.4, 0.4, 1.2])
    assert sum(float(item["hold"]) for item in timeline) == pytest.approx(2.0)


def test_stop_motion_fixed_contain_frame_overrides_template_image_crop():
    animation = SceneAnimationSpec.model_validate(
        _animation(
            ["pose-a", "pose-b", "pose-c"],
            reference_frame={
                "enabled": True,
                "fit": "contain",
            },
        )
    )

    css = RenderingService._stop_motion_template_css(animation, ".custom { color: red; }")

    assert ".custom { color: red; }" in css
    assert "object-fit: contain" in css


def test_stop_motion_timeline_keeps_pose_hints_and_frame_boundaries():
    animation = SceneAnimationSpec.model_validate(
        _animation(
            ["pose-a", "pose-b", "pose-c"],
            hold=0.4,
            poses=[
                {
                    "asset_id": "pose-a",
                    "hold": 0.4,
                    "pose_description": "抬手",
                    "framing_hint": "半身",
                    "prop_hint": "纸张",
                    "expression_hint": "专注",
                },
                {"asset_id": "pose-b", "hold": 0.4},
                {"asset_id": "pose-c", "hold": 0.4},
            ],
        )
    )

    timeline = RenderingService._build_stop_motion_timeline(animation, 1.5)

    assert timeline[0]["description"] == "抬手"
    assert timeline[0]["framing"] == "半身"
    assert timeline[0]["prop"] == "纸张"
    assert timeline[0]["expression"] == "专注"
    assert [(item["start"], item["end"]) for item in timeline] == [
        (0.0, 0.4),
        (0.4, 0.8),
        (0.8, 1.5),
    ]
    assert [item["frame_count"] for item in timeline] == [12, 12, 21]


def test_stop_motion_micro_motion_filter_is_bounded_and_time_based():
    motion = SceneMicroMotionSpec.model_validate(
        {
            "enabled": True,
            "blink": True,
            "head_bob": 1.0,
            "breathing": 0.004,
            "jitter": 1.5,
            "scale": 0.01,
            "rotate": 0.5,
            "push": 0.02,
            "pan_x": 0.01,
        }
    )

    graph = RenderingService._stop_motion_motion_filter(
        2,
        output_label="pose_0",
        output_fps=30,
        canvas_width=1080,
        canvas_height=1920,
        frame_count=30,
        micro_motion=motion,
    )

    assert "zoompan=" in graph
    assert "s=1080x1920:fps=30" in graph
    assert "1.000000" in graph
    assert "rotate=" in graph
    assert "eq=brightness=" in graph
    assert "on/29" in graph


def test_stop_motion_state_landing_is_one_shot_and_bounded():
    graph = RenderingService._stop_motion_motion_filter(
        0,
        output_label="pose_0",
        output_fps=30,
        canvas_width=1080,
        canvas_height=1920,
        frame_count=30,
        micro_motion=SceneMicroMotionSpec(),
        landing_direction=1.0,
        landing_duration_seconds=RenderingService.STOP_MOTION_LANDING_SECONDS,
    )

    assert "if(lt(on\\,7)\\,on/7\\,1)" in graph
    assert "if(lt(n\\,7)\\,n/7\\,1)" in graph
    assert "0.008000" in graph
    assert "rotate=" in graph


def test_stop_motion_auto_enables_local_flow_for_marked_transition():
    animation = RenderingService._stop_motion_spec(
        {"animation": _animation(
            ["pose-a", "pose-b", "pose-c"],
            poses=[
                {"asset_id": "pose-a", "hold": 0.5, "transition": "stepped"},
                {"asset_id": "pose-b", "hold": 0.5, "transition": "expression"},
                {"asset_id": "pose-c", "hold": 0.5, "transition": "stepped"},
            ],
        )}
    )

    assert animation is not None
    assert animation.optical_flow is not None
    assert animation.optical_flow.enabled is True
    assert animation.optical_flow.region is not None


def test_stop_motion_explicit_optical_flow_setting_is_preserved():
    animation = RenderingService._stop_motion_spec(
        {
            "animation": _animation(
                ["pose-a", "pose-b", "pose-c"],
                poses=[
                    {"asset_id": "pose-a", "hold": 0.5, "transition": "stepped"},
                    {"asset_id": "pose-b", "hold": 0.5, "transition": "expression"},
                    {"asset_id": "pose-c", "hold": 0.5, "transition": "stepped"},
                ],
                optical_flow={"enabled": False},
            )
        }
    )

    assert animation is not None
    assert animation.optical_flow is not None
    assert animation.optical_flow.enabled is False


def test_stop_motion_optical_flow_only_selects_explicit_small_transitions():
    animation = SceneAnimationSpec.model_validate(
        _animation(
            ["pose-a", "pose-b", "pose-c"],
            hold=0.5,
            poses=[
                {"asset_id": "pose-a", "hold": 0.5, "transition": "stepped"},
                {"asset_id": "pose-b", "hold": 0.5, "transition": "mouth"},
                {"asset_id": "pose-c", "hold": 0.5, "transition": "stepped"},
            ],
            optical_flow={
                "enabled": True,
                "transition_seconds": 0.18,
                "max_transitions": 2,
                "region": {"x": 0.28, "y": 0.08, "width": 0.44, "height": 0.3},
            },
        )
    )

    timeline = RenderingService._build_stop_motion_timeline(animation, 1.5)

    assert RenderingService._stop_motion_optical_flow_transitions(animation, timeline) == [
        {"from_index": 0, "to_index": 1, "mode": "mouth", "duration": 0.18}
    ]


def test_stop_motion_optical_flow_rejects_unbounded_regions():
    with pytest.raises(ValueError, match="覆盖大范围"):
        SceneAnimationSpec.model_validate(
            _animation(
                ["pose-a", "pose-b", "pose-c"],
                optical_flow={
                    "enabled": True,
                    "region": {"x": 0.0, "y": 0.0, "width": 0.8, "height": 0.4},
                },
            )
        )


@pytest.mark.asyncio
async def test_stop_motion_renders_scene_clip_and_composes_task(
    test_session, tmp_path, monkeypatch
):
    storage = LocalStorageService(base_storage_dir=tmp_path / "stop-motion-storage")
    asset_service = AssetService(test_session, storage=storage)
    project = ProjectModel(id=f"project_{uuid4().hex}", name="Stop motion")
    task = TaskModel(
        id=f"task_{uuid4().hex}",
        project_id=project.id,
        title="Stop motion task",
        job_type=JobType.VIDEO_COMPOSITION.value,
        status=TaskStatus.RUNNING.value,
        input_payload={"template_id": "image_default", "content_mode": "generated_image"},
    )
    test_session.add(project)
    await test_session.flush()

    pose_assets: list[AssetModel] = []
    for index in range(3):
        pose_assets.append(
            await asset_service.save_asset(
                content=f"pose-{index}".encode(),
                file_name=f"pose-{index}.png",
                mime_type="image/png",
                asset_type=AssetType.IMAGE,
                project_id=project.id,
            )
        )
    scene = SceneModel(
        id=f"scene_{uuid4().hex}",
        task_id=task.id,
        sequence_index=0,
        narration_text="定格动画测试",
        duration_seconds=2.0,
        layout_params={"animation": _animation([asset.id for asset in pose_assets])},
    )
    test_session.add_all([task, scene])
    await test_session.commit()

    template_calls: list[Path] = []
    ffmpeg_calls: list[list[str]] = []
    fail_optical_flow = False

    async def fake_template_render(*_args, output_path, image_path=None, **_kwargs):
        template_calls.append(Path(image_path))
        output_path.write_bytes(b"template-frame")

    async def fake_ffmpeg_runner(cmd: list[str], output_path: Path) -> bool:
        ffmpeg_calls.append(cmd)
        filter_graph = cmd[cmd.index("-filter_complex") + 1] if "-filter_complex" in cmd else ""
        if fail_optical_flow and "minterpolate=" in filter_graph:
            raise RuntimeError("test optical-flow filter failure")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"rendered-stop-motion")
        return True

    monkeypatch.setattr(TemplateRenderer, "render", fake_template_render)
    rendering_service = RenderingService(
        test_session,
        storage=storage,
        ffmpeg_runner=fake_ffmpeg_runner,
    )

    clip_rel_path = await rendering_service.render_scene_clip(scene.id)
    clip_path = storage.get_path(clip_rel_path)
    assert clip_path.read_bytes() == b"rendered-stop-motion"
    assert len(template_calls) == 3
    assert len(ffmpeg_calls) == 1
    filter_graph = ffmpeg_calls[0][ffmpeg_calls[0].index("-filter_complex") + 1]
    assert "concat=n=3:v=1:a=0" in filter_graph
    assert "fps=30" in filter_graph

    await test_session.refresh(scene)
    clip_asset = await test_session.get(AssetModel, scene.rendered_segment_asset_id)
    assert clip_asset is not None
    assert clip_asset.metadata_json["layout_strategy"] == "enhanced_stop_motion"
    assert (
        clip_asset.metadata_json["scene_render_format_version"]
        == RenderingService.ENHANCED_STOP_MOTION_SCENE_RENDER_FORMAT_VERSION
    )
    assert [item["asset_id"] for item in clip_asset.metadata_json["animation"]["poses"]] == [
        asset.id for asset in pose_assets
    ]
    assert clip_asset.metadata_json["animation"]["micro_motion"]["enabled"] is False
    assert clip_asset.metadata_json["animation"]["parallax"]["enabled"] is False

    final_asset = await rendering_service.compose_task_video(task.id)
    assert final_asset is not None
    assert storage.get_path(final_asset.file_path).read_bytes() == b"rendered-stop-motion"
    assert len(ffmpeg_calls) == 2

    scene.layout_params = {
        "animation": _animation(
            [asset.id for asset in pose_assets],
            poses=[
                {"asset_id": pose_assets[0].id, "hold": 0.5, "transition": "stepped"},
                {"asset_id": pose_assets[1].id, "hold": 0.5, "transition": "mouth"},
                {"asset_id": pose_assets[2].id, "hold": 0.5, "transition": "stepped"},
            ],
            optical_flow={
                "enabled": True,
                "transition_seconds": 0.18,
                "max_transitions": 2,
                "region": {"x": 0.28, "y": 0.08, "width": 0.44, "height": 0.3},
            },
        )
    }
    await test_session.commit()

    applied_clip_rel_path = await rendering_service.render_scene_clip(scene.id)

    assert storage.get_path(applied_clip_rel_path).read_bytes() == b"rendered-stop-motion"
    assert len(ffmpeg_calls) == 3
    applied_filter_graph = ffmpeg_calls[-1][ffmpeg_calls[-1].index("-filter_complex") + 1]
    assert "minterpolate=" in applied_filter_graph
    assert "tpad=stop_mode=clone" in applied_filter_graph
    assert "setpts=PTS*5.400000" in applied_filter_graph
    await test_session.refresh(scene)
    applied_asset = await test_session.get(AssetModel, scene.rendered_segment_asset_id)
    assert applied_asset is not None
    assert applied_asset.id != clip_asset.id
    assert applied_asset.metadata_json["animation"]["optical_flow_render"]["status"] == "applied"

    fail_optical_flow = True

    refreshed_clip_rel_path = await rendering_service.render_scene_clip(scene.id)

    assert storage.get_path(refreshed_clip_rel_path).read_bytes() == b"rendered-stop-motion"
    assert len(ffmpeg_calls) == 5  # flow attempt, then stepped fallback
    flow_filter_graph = ffmpeg_calls[-2][ffmpeg_calls[-2].index("-filter_complex") + 1]
    fallback_filter_graph = ffmpeg_calls[-1][ffmpeg_calls[-1].index("-filter_complex") + 1]
    assert "minterpolate=" in flow_filter_graph
    assert "[v0]split=2" in flow_filter_graph
    assert "start_frame=" in flow_filter_graph
    assert "crop=475:576:302:154" in flow_filter_graph
    assert "minterpolate=" not in fallback_filter_graph

    await test_session.refresh(scene)
    refreshed_asset = await test_session.get(AssetModel, scene.rendered_segment_asset_id)
    assert refreshed_asset is not None
    assert refreshed_asset.id != applied_asset.id
    optical_flow_render = refreshed_asset.metadata_json["animation"]["optical_flow_render"]
    assert optical_flow_render["status"] == "fallback"
    assert optical_flow_render["fallback"] is True
    assert "stepped motion used" in optical_flow_render["fallback_reason"]


@pytest.mark.asyncio
async def test_stop_motion_reference_metadata_and_parallax_layers_are_rendered(
    test_session, tmp_path, monkeypatch
):
    storage = LocalStorageService(base_storage_dir=tmp_path / "stop-motion-parallax-storage")
    asset_service = AssetService(test_session, storage=storage)
    project = ProjectModel(id=f"project_{uuid4().hex}", name="Stop motion parallax")
    task = TaskModel(
        id=f"task_{uuid4().hex}",
        project_id=project.id,
        title="Parallax task",
        job_type=JobType.VIDEO_COMPOSITION.value,
        status=TaskStatus.RUNNING.value,
        input_payload={"template_id": "image_default", "content_mode": "generated_image"},
    )
    test_session.add(project)
    await test_session.flush()

    assets: list[AssetModel] = []
    for name in ("pose-0.png", "pose-1.png", "pose-2.png", "reference.png", "background.png", "foreground.png"):
        assets.append(
            await asset_service.save_asset(
                content=name.encode(),
                file_name=name,
                mime_type="image/png",
                asset_type=AssetType.IMAGE,
                project_id=project.id,
            )
        )
    pose_assets = assets[:3]
    scene = SceneModel(
        id=f"scene_{uuid4().hex}",
        task_id=task.id,
        sequence_index=0,
        narration_text="视差测试",
        duration_seconds=1.5,
        layout_params={
            "animation": _animation(
                [asset.id for asset in pose_assets],
                hold=0.5,
                reference_asset_id=assets[3].id,
                poses=[
                    {"asset_id": pose_assets[0].id, "hold": 0.5, "description": "抬手"},
                    {"asset_id": pose_assets[1].id, "hold": 0.5},
                    {"asset_id": pose_assets[2].id, "hold": 0.5},
                ],
                micro_motion={"enabled": True, "jitter": 1.0},
                parallax={
                    "enabled": True,
                    "strength": 0.4,
                    "layers": {
                        "background_asset_id": assets[4].id,
                        "foreground_asset_id": assets[5].id,
                    },
                },
            )
        },
    )
    test_session.add_all([task, scene])
    await test_session.commit()

    template_calls: list[dict] = []
    ffmpeg_calls: list[list[str]] = []

    async def fake_template_render(*_args, output_path, image_path=None, transparent=False, **_kwargs):
        template_calls.append({"image_path": Path(image_path), "transparent": transparent})
        output_path.write_bytes(b"template-frame")

    async def fake_ffmpeg_runner(cmd: list[str], output_path: Path) -> bool:
        ffmpeg_calls.append(cmd)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"rendered-parallax")
        return True

    monkeypatch.setattr(TemplateRenderer, "render", fake_template_render)
    rendering_service = RenderingService(
        test_session,
        storage=storage,
        ffmpeg_runner=fake_ffmpeg_runner,
    )

    await rendering_service.render_scene_clip(scene.id)

    assert len(template_calls) == 3
    assert all(call["transparent"] for call in template_calls)
    assert len(ffmpeg_calls) == 1
    command = ffmpeg_calls[0]
    assert command.count("-i") == 10  # 3 poses + 3 backgrounds + 3 foregrounds + silence
    filter_graph = command[command.index("-filter_complex") + 1]
    assert "background_0" in filter_graph
    assert "foreground_0" in filter_graph
    assert "overlay=0:0" in filter_graph
    assert "0.016000" in filter_graph

    await test_session.refresh(scene)
    clip_asset = await test_session.get(AssetModel, scene.rendered_segment_asset_id)
    assert clip_asset is not None
    animation_metadata = clip_asset.metadata_json["animation"]
    assert animation_metadata["reference_asset_id"] == assets[3].id
    assert animation_metadata["micro_motion"]["enabled"] is True
    assert animation_metadata["parallax"]["layers"]["background_asset_id"] == assets[4].id
    assert animation_metadata["poses"][0]["description"] == "抬手"


def test_stop_motion_motion_plan_supports_non_person_visual_states():
    plan = GenerationService.build_stop_motion_plan(
        narration_text="展示咖啡机的三档温控",
        visual_prompt="商品咖啡机旁的信息图依次高亮三档温度",
        duration_seconds=4.0,
    )

    assert plan.source == "template"
    assert 3 <= len(plan.states) <= 6
    assert [state.state_id for state in plan.states] == [
        "pose_1",
        "pose_2",
        "pose_3",
    ]
    assert all("咖啡机" in state.state_description for state in plan.states)
    assert all("人物" not in state.element_hint for state in plan.states)
    assert sum(state.recommended_hold_duration for state in plan.states) == pytest.approx(4.0)
    assert "poses" in plan.model_dump(by_alias=True)
    assert [state.transition for state in plan.states] == ["stepped", "expression", "stepped"]
    assert GenerationService._stop_motion_default_optical_flow(plan) is not None


class _StopMotionImageProvider:
    name = "stop-motion-test"

    def __init__(self, fail_pose: str | None = None):
        self.fail_pose = fail_pose
        self.prompts: list[str] = []
        self.workflows: list[str | None] = []
        self.reference_image_paths: list[str | None] = []
        self.reference_image_options: list[dict[str, Any] | None] = []

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "9:16",
        workflow: str | None = None,
        width: int | None = None,
        height: int | None = None,
        reference_image_path: str | None = None,
        reference_image_options: dict[str, Any] | None = None,
    ) -> ImageResult:
        self.prompts.append(prompt)
        self.workflows.append(workflow)
        self.reference_image_paths.append(reference_image_path)
        self.reference_image_options.append(reference_image_options)
        if self.fail_pose and self.fail_pose in prompt:
            raise RuntimeError(f"provider failure for {self.fail_pose}")
        return ImageResult(
            image_bytes=b"generated-pose-image",
            width=width or 720,
            height=height or 1280,
        )


async def _make_generation_scene(test_session, storage, *, layout_params=None):
    project = ProjectModel(id=f"project_{uuid4().hex}", name="Generated stop motion")
    task = TaskModel(
        id=f"task_{uuid4().hex}",
        project_id=project.id,
        title="Generated stop motion task",
        job_type=JobType.VIDEO_COMPOSITION.value,
        status=TaskStatus.RUNNING.value,
        input_payload={
            "template_id": "image_default",
            "content_mode": "generated_image",
            "style_preset": "cinematic_real",
        },
    )
    scene = SceneModel(
        id=f"scene_{uuid4().hex}",
        task_id=task.id,
        sequence_index=0,
        narration_text="角色走进实验室",
        visual_prompt="角色走进实验室并拿起发光装置",
        duration_seconds=4.0,
        layout_params=(
            {"animation_mode": "enhanced_stop_motion"}
            if layout_params is None
            else layout_params
        ),
    )
    test_session.add_all([project, task, scene])
    await test_session.commit()
    return task, scene


@pytest.mark.asyncio
async def test_stop_motion_pose_generation_persists_plan_and_asset_ids(
    test_session, tmp_path, monkeypatch
):
    storage = LocalStorageService(base_storage_dir=tmp_path / "generated-stop-motion-storage")
    _, scene = await _make_generation_scene(test_session, storage)
    provider = _StopMotionImageProvider()
    service = GenerationService(test_session, storage=storage)

    async def get_provider():
        return provider

    monkeypatch.setattr(service, "_get_image_provider", get_provider)
    generated = await service.generate_scene_stop_motion_poses(
        scene.id,
        use_llm=False,
    )

    plan = generated.layout_params["animation_plan"]
    animation = generated.layout_params["animation"]
    assert plan["status"] == "completed"
    assert len(plan["poses"]) == 3
    assert [pose["asset_id"] for pose in plan["poses"]] == [
        pose["asset_id"] for pose in animation["poses"]
    ]
    assert all(pose["asset_id"] for pose in animation["poses"])
    assert len(provider.prompts) == 3

    for pose in animation["poses"]:
        asset = await test_session.get(AssetModel, pose["asset_id"])
        assert asset is not None
        assert asset.metadata_json["source_kind"] == "generated_stop_motion_pose"
        assert asset.metadata_json["pose_id"] == pose["pose_id"]


@pytest.mark.asyncio
async def test_stop_motion_reuses_one_scene_base_with_selected_img2img_workflow(
    test_session, tmp_path, monkeypatch
):
    storage = LocalStorageService(base_storage_dir=tmp_path / "two-stage-stop-motion-storage")
    task, scene = await _make_generation_scene(test_session, storage)
    img2img_workflow = "image/image_flux2_img2img.json"
    task.input_payload = {
        **(task.input_payload or {}),
        "image_img2img_workflow_id": img2img_workflow,
        "image_img2img_workflow_snapshot": {"path": img2img_workflow},
    }
    await test_session.commit()

    provider = _StopMotionImageProvider()
    service = GenerationService(test_session, storage=storage)

    async def get_provider():
        return provider

    monkeypatch.setattr(service, "_get_image_provider", get_provider)
    generated = await service.generate_scene_stop_motion_poses(scene.id, use_llm=False)

    assert len(provider.workflows) == 3
    assert provider.workflows == [None, img2img_workflow, img2img_workflow]
    assert provider.reference_image_paths[0] is None
    assert all(path for path in provider.reference_image_paths[1:])

    pose_asset = await test_session.get(
        AssetModel, generated.layout_params["animation"]["poses"][0]["asset_id"]
    )
    assert pose_asset is not None
    assert pose_asset.metadata_json["image_generation_mode"] == "txt2img_scene_base"
    assert pose_asset.metadata_json["image_generation_stages"]["reference_source"] == "scene_base"
    assert pose_asset.metadata_json["img2img_workflow"] is None

    refined_asset = await test_session.get(
        AssetModel, generated.layout_params["animation"]["poses"][1]["asset_id"]
    )
    assert refined_asset is not None
    assert refined_asset.metadata_json["image_generation_mode"] == "img2img_from_scene_base"
    assert refined_asset.metadata_json["image_generation_stages"]["base_asset_id"] == pose_asset.id
    assert refined_asset.metadata_json["img2img_workflow"] == img2img_workflow

    provider.workflows.clear()
    provider.reference_image_paths.clear()
    first_asset_id = pose_asset.id
    await service.generate_scene_stop_motion_poses(
        scene.id,
        pose_id="pose_2",
        force=True,
        use_llm=False,
    )
    assert provider.workflows == [img2img_workflow]
    assert provider.reference_image_paths == [str(storage.get_path(pose_asset.file_path))]
    await test_session.refresh(scene)
    assert scene.layout_params["animation"]["poses"][0]["asset_id"] == first_asset_id


@pytest.mark.asyncio
async def test_stop_motion_forwards_reference_asset_path_to_image_provider(
    test_session, tmp_path, monkeypatch
):
    storage = LocalStorageService(base_storage_dir=tmp_path / "reference-stop-motion-storage")
    task, scene = await _make_generation_scene(test_session, storage)
    reference_asset = await AssetService(test_session, storage=storage).save_asset(
        content=b"reference-image",
        file_name="character.png",
        mime_type="image/png",
        asset_type=AssetType.IMAGE,
        project_id=task.project_id,
    )
    scene.layout_params = {
        "animation_mode": "enhanced_stop_motion",
        "animation_reference_asset_id": reference_asset.id,
    }
    await test_session.commit()

    provider = _StopMotionImageProvider()
    service = GenerationService(test_session, storage=storage)

    async def get_provider():
        return provider

    monkeypatch.setattr(service, "_get_image_provider", get_provider)
    await service.generate_scene_stop_motion_poses(scene.id, use_llm=False)

    expected_path = str(storage.get_path(reference_asset.file_path))
    assert provider.reference_image_paths == [expected_path] * 3
    assert all(item and item["enabled"] for item in provider.reference_image_options)
    assert all(item["width"] == 1024 and item["height"] == 1024 for item in provider.reference_image_options)


@pytest.mark.asyncio
async def test_stop_motion_forwards_manual_face_alignment_and_fixed_frame(
    test_session, tmp_path, monkeypatch
):
    storage = LocalStorageService(base_storage_dir=tmp_path / "aligned-stop-motion-storage")
    task, scene = await _make_generation_scene(test_session, storage)
    reference_asset = await AssetService(test_session, storage=storage).save_asset(
        content=b"reference-image",
        file_name="full-body-character.png",
        mime_type="image/png",
        asset_type=AssetType.IMAGE,
        project_id=task.project_id,
    )
    scene.layout_params = {
        "animation_mode": "enhanced_stop_motion",
        "animation_reference_asset_id": reference_asset.id,
        "animation": {
            "reference_frame": {
                "enabled": True,
                "width": 720,
                "height": 1280,
                "fit": "contain",
                "face_alignment": {
                    "enabled": True,
                    "source_box": {"x": 0.42, "y": 0.08, "width": 0.16, "height": 0.12},
                    "target_center_x": 0.5,
                    "target_center_y": 0.18,
                    "target_width": 0.12,
                },
            }
        },
    }
    await test_session.commit()

    provider = _StopMotionImageProvider()
    service = GenerationService(test_session, storage=storage)

    async def get_provider():
        return provider

    monkeypatch.setattr(service, "_get_image_provider", get_provider)
    generated = await service.generate_scene_stop_motion_poses(scene.id, use_llm=False)

    options = provider.reference_image_options[0]
    assert options["width"] == 720
    assert options["height"] == 1280
    assert options["face_alignment"]["source_box"]["x"] == pytest.approx(0.42)
    assert all("固定构图约束" in prompt for prompt in provider.prompts)
    assert generated.layout_params["animation"]["reference_frame"] == options


@pytest.mark.asyncio
async def test_stop_motion_single_pose_retry_keeps_completed_assets(
    test_session, tmp_path, monkeypatch
):
    storage = LocalStorageService(base_storage_dir=tmp_path / "retry-stop-motion-storage")
    _, scene = await _make_generation_scene(test_session, storage)
    provider = _StopMotionImageProvider(fail_pose="第 2/3")
    service = GenerationService(test_session, storage=storage)

    async def get_provider():
        return provider

    monkeypatch.setattr(service, "_get_image_provider", get_provider)
    with pytest.raises(ValidationException, match="pose_2"):
        await service.generate_scene_stop_motion_poses(scene.id, use_llm=False)

    await test_session.refresh(scene)
    partial_plan = scene.layout_params["animation_plan"]
    first_asset_id = next(
        pose["asset_id"]
        for pose in partial_plan["poses"]
        if pose["pose_id"] == "pose_1"
    )
    assert partial_plan["status"] == "partial"
    assert next(pose for pose in partial_plan["poses"] if pose["pose_id"] == "pose_2")["status"] == "failed"
    assert next(pose for pose in partial_plan["poses"] if pose["pose_id"] == "pose_3")["status"] == "pending"

    provider.fail_pose = None
    await service.generate_scene_stop_motion_poses(
        scene.id,
        pose_id="pose_2",
        force=True,
        use_llm=False,
    )
    await test_session.refresh(scene)
    retry_plan = scene.layout_params["animation_plan"]
    assert next(pose for pose in retry_plan["poses"] if pose["pose_id"] == "pose_1")["asset_id"] == first_asset_id
    assert next(pose for pose in retry_plan["poses"] if pose["pose_id"] == "pose_2")["status"] == "completed"
    assert "animation" not in scene.layout_params

    completed = await service.generate_scene_stop_motion_poses(
        scene.id,
        use_llm=False,
    )
    assert completed.layout_params["animation_plan"]["status"] == "completed"
    assert len(completed.layout_params["animation"]["poses"]) == 3


@pytest.mark.asyncio
async def test_stop_motion_scene_render_route_refreshes_only_requested_scene(
    test_session, tmp_path, monkeypatch
):
    storage = LocalStorageService(base_storage_dir=tmp_path / "scene-render-route-storage")
    _, scene = await _make_generation_scene(
        test_session,
        storage,
        layout_params={"animation": _animation(["pose-a", "pose-b", "pose-c"])},
    )
    calls: list[str] = []

    async def fake_render_scene_clip(_renderer, scene_id):
        calls.append(scene_id)

    monkeypatch.setattr(RenderingService, "render_scene_clip", fake_render_scene_clip)
    service = GenerationService(test_session, storage=storage)

    response = await generation_routes.render_scene_stop_motion(scene.id, service=service)

    assert response.data.id == scene.id
    assert calls == [scene.id]


@pytest.mark.asyncio
async def test_ordinary_image_generation_keeps_legacy_provider_signature(
    test_session, tmp_path, monkeypatch
):
    storage = LocalStorageService(base_storage_dir=tmp_path / "ordinary-image-storage")
    _, scene = await _make_generation_scene(test_session, storage, layout_params={})
    provider = _StopMotionImageProvider()
    service = GenerationService(test_session, storage=storage)

    async def get_provider():
        return provider

    monkeypatch.setattr(service, "_get_image_provider", get_provider)
    generated = await service.generate_scene_image(scene.id)

    assert generated.media_asset_id
    asset = await test_session.get(AssetModel, generated.media_asset_id)
    assert asset is not None
    assert asset.metadata_json["scene_id"] == scene.id


@pytest.mark.asyncio
async def test_durable_pipeline_generates_stop_motion_poses_before_rendering(
    test_session, tmp_path, monkeypatch
):
    media = Path(__file__).parent / "fixtures" / "mock.mp4"
    storage = LocalStorageService(base_storage_dir=tmp_path / "durable-stop-motion-storage")
    project = ProjectModel(
        id=f"project_{uuid4().hex}",
        name="Durable stop motion",
        aspect_ratio="9:16",
    )
    task = TaskModel(
        id=f"task_{uuid4().hex}",
        project_id=project.id,
        title="Durable stop motion task",
        job_type=JobType.VIDEO_COMPOSITION.value,
        input_payload={
            "template_id": "image_default",
            "content_mode": "generated_image",
            "animation_mode": "enhanced_stop_motion",
            "enable_research": False,
        },
    )
    scene = SceneModel(
        id=f"scene_{uuid4().hex}",
        task_id=task.id,
        sequence_index=0,
        narration_text="",
        visual_prompt="角色走进实验室并拿起发光装置",
        duration_seconds=2.0,
        layout_params={"animation_mode": "enhanced_stop_motion"},
    )
    test_session.add_all([project, task, scene])
    await test_session.commit()

    async def render_frame(*_args, output_path, **_kwargs):
        output_path.write_bytes(b"frame")

    async def render_video(_command, output_path):
        output_path.write_bytes(media.read_bytes())
        return True

    monkeypatch.setattr(TemplateRenderer, "render", render_frame)

    @asynccontextmanager
    async def sessions():
        yield test_session

    executor = VideoWorkflowExecutor(
        sessions,
        lambda db: RenderingService(db, storage=storage, ffmpeg_runner=render_video),
    )
    await executor.execute(Job(task_id=task.id))

    await test_session.refresh(scene)
    animation = scene.layout_params["animation"]
    assert len(animation["poses"]) == 3
    for pose in animation["poses"]:
        asset = await test_session.get(AssetModel, pose["asset_id"])
        assert asset is not None
        assert asset.metadata_json["source_kind"] == "generated_stop_motion_pose"
    assert scene.rendered_segment_asset_id


@pytest.mark.asyncio
async def test_stop_motion_rejects_insufficient_or_missing_pose_assets(
    test_session, tmp_path
):
    storage = LocalStorageService(base_storage_dir=tmp_path / "stop-motion-invalid-storage")
    project = ProjectModel(id=f"project_{uuid4().hex}", name="Stop motion invalid")
    task = TaskModel(
        id=f"task_{uuid4().hex}",
        project_id=project.id,
        title="Invalid stop motion",
        job_type=JobType.VIDEO_COMPOSITION.value,
        status=TaskStatus.RUNNING.value,
        input_payload={"template_id": "image_default", "content_mode": "generated_image"},
    )
    too_few = SceneModel(
        id=f"scene_{uuid4().hex}",
        task_id=task.id,
        duration_seconds=2.0,
        layout_params={"animation": _animation(["pose-a", "pose-b"])},
    )
    test_session.add_all([project, task, too_few])
    await test_session.commit()
    rendering_service = RenderingService(test_session, storage=storage, ffmpeg_runner=None)

    with pytest.raises(ValidationException, match="动画参数无效"):
        await rendering_service.render_scene_clip(too_few.id)

    too_few.layout_params = {"animation": _animation(["pose-a", "pose-b", "pose-c"])}
    await test_session.commit()
    with pytest.raises(ValidationException, match="姿态图素材不存在"):
        await rendering_service.render_scene_clip(too_few.id)


@pytest.mark.asyncio
async def test_scene_api_normalizes_animation_into_layout_params(client):
    project_response = await client.post(
        "/api/v1/projects",
        json={"name": f"Stop motion API {uuid4().hex}", "aspect_ratio": "9:16"},
    )
    project_id = project_response.json()["data"]["id"]
    task_response = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Stop motion API task", "template_id": "image_default"},
    )
    task_id = task_response.json()["data"]["id"]

    response = await client.put(
        f"/api/v1/tasks/{task_id}/scenes",
        json={
            "scenes": [
                {
                    "sequence_index": 0,
                    "narration_text": "姿态图",
                    "visual_prompt": "",
                    "duration_seconds": 2,
                    "animation": _animation(
                        ["pose-a", "pose-b", "pose-c"],
                        reference_image_asset_id="pose-a",
                        poses=[
                            {
                                "asset_id": "pose-a",
                                "hold": 0.4,
                                "pose_description": "站立",
                            },
                            {"asset_id": "pose-b", "hold": 0.4},
                            {"asset_id": "pose-c", "hold": 0.4},
                        ],
                    ),
                }
            ]
        },
    )

    assert response.status_code == 200
    saved = response.json()["data"][0]
    assert saved["layout_params"]["animation"]["mode"] == "enhanced_stop_motion"
    assert len(saved["layout_params"]["animation"]["poses"]) == 3
    assert saved["layout_params"]["animation"]["reference_asset_id"] == "pose-a"
    assert saved["layout_params"]["animation"]["poses"][0]["description"] == "站立"


@pytest.mark.asyncio
async def test_task_creation_persists_stop_motion_mode(client):
    project_response = await client.post(
        "/api/v1/projects",
        json={"name": f"Stop motion task {uuid4().hex}", "aspect_ratio": "9:16"},
    )
    project_id = project_response.json()["data"]["id"]

    response = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={
            "title": "Enhanced stop motion task",
            "template_id": "image_default",
            "content_mode": "generated_image",
            "animation_mode": "enhanced_stop_motion",
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["input_payload"]["animation_mode"] == "enhanced_stop_motion"

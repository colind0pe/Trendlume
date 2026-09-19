from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_generation_service, request_session_factory
from src.schemas.common import APIResponse
from src.schemas.generation import (
    PlatformMetadata,
    ResearchRequest,
    ResearchResponse,
    SceneMediaGenerateRequest,
    ScriptGenerateRequest,
    StructuredScript,
)
from src.schemas.scene import SceneResponse
from src.schemas.task import TaskDetailResponse
from src.services.generation_service import GenerationService
from src.tasks.manager import task_manager

router = APIRouter(prefix="/generation", tags=["Generation"])


@router.post("/tasks/{task_id}/metadata/regenerate", response_model=APIResponse[PlatformMetadata])
async def regenerate_task_metadata(
    task_id: str,
    service: GenerationService = Depends(get_generation_service),
):
    return APIResponse(data=await service.regenerate_task_metadata(task_id))


@router.post("/research", response_model=APIResponse[ResearchResponse])
async def research_topic(
    payload: ResearchRequest,
    service: GenerationService = Depends(get_generation_service),
):
    if not payload.enable_research:
        result = ResearchResponse(
            topic=payload.topic,
            status="skipped",
            summary="已关闭实时资料检索。",
        )
    else:
        result = await service.research_topic(
            payload.topic,
            max_results=payload.max_results,
            max_queries=payload.max_queries,
            search_provider_id=payload.search_provider_id,
            prompt_versions=payload.prompt_versions,
        )
    return APIResponse(data=result)


@router.post("/script", response_model=APIResponse[StructuredScript])
async def generate_script(
    payload: ScriptGenerateRequest,
    service: GenerationService = Depends(get_generation_service),
):
    # The standalone topic endpoint follows the same two-call contract as the
    # video workflow.  The workflow already supplies the completed context, so
    # this guard avoids researching the same topic twice there.
    if (
        payload.mode == "generate"
        and payload.topic.strip()
        and not payload.research_context
        and payload.enable_research
    ):
        research = await service.research_topic(
            payload.topic,
            max_results=payload.research_max_results,
            max_queries=payload.research_max_queries,
            search_provider_id=payload.search_provider_id,
            prompt_versions=payload.prompt_versions,
        )
        payload = payload.model_copy(
            update={
                "research_context": (
                    research.format_for_prompt()
                    if research.status == "completed" and research.sources
                    else None
                )
            }
        )
    script = await service.generate_script(payload)
    return APIResponse(data=script)


@router.post("/tasks/{task_id}/research", response_model=APIResponse[ResearchResponse])
async def research_task(
    task_id: str,
    service: GenerationService = Depends(get_generation_service),
):
    result = await task_manager.run_inline(task_id, {"single_step": "research", "force_step": "research"}, session_factory=request_session_factory(service.session))
    return APIResponse(data=ResearchResponse.model_validate(result))


@router.post("/tasks/{task_id}/apply-script", response_model=APIResponse[TaskDetailResponse])
async def apply_script_to_task(
    task_id: str,
    script: StructuredScript,
    service: GenerationService = Depends(get_generation_service),
):
    await task_manager.run_inline(task_id, {"single_step": "script", "script": script.model_dump(), "force_step": "script"}, session_factory=request_session_factory(service.session))
    task = await service.task_repo.get_by_id(task_id)
    return APIResponse(
        data=TaskDetailResponse(
            id=task.id,
            project_id=task.project_id,
            product_id=task.product_id,
            creative_angle=task.creative_angle,
            title=task.title,
            description=task.description,
            job_type=task.job_type,
            production_mode=task.production_mode,
            status=task.status,
            progress_percentage=task.progress_percentage,
            input_payload=task.input_payload,
            result_payload=task.result_payload,
            error_message=task.error_message,
            scenes_count=len(task.scenes) if task.scenes else 0,
            scenes=[SceneResponse.model_validate(s) for s in task.scenes],
            started_at=task.started_at,
            completed_at=task.completed_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
            scheduled_publish=(task.input_payload or {}).get("scheduled_publish"),
        )
    )


@router.post("/scenes/{scene_id}/tts", response_model=APIResponse[SceneResponse])
async def generate_scene_tts(
    scene_id: str,
    payload: SceneMediaGenerateRequest | None = None,
    service: GenerationService = Depends(get_generation_service),
):
    voice_id = payload.voice_id if payload else None
    speed = payload.speed if payload else None
    scene = await _run_scene(service, scene_id, "voice", voice_id=voice_id, speed=speed)
    return APIResponse(data=SceneResponse.model_validate(scene))


@router.post("/scenes/{scene_id}/image", response_model=APIResponse[SceneResponse])
async def generate_scene_image(
    scene_id: str,
    payload: SceneMediaGenerateRequest | None = None,
    service: GenerationService = Depends(get_generation_service),
):
    prompt_override = payload.prompt_override if payload else None
    scene = await _run_scene(service, scene_id, "assets", media_kind="image", prompt_override=prompt_override)
    return APIResponse(data=SceneResponse.model_validate(scene))


@router.post("/scenes/{scene_id}/video", response_model=APIResponse[SceneResponse])
async def generate_scene_video(
    scene_id: str,
    payload: SceneMediaGenerateRequest | None = None,
    service: GenerationService = Depends(get_generation_service),
):
    prompt_override = payload.prompt_override if payload else None
    scene = await _run_scene(service, scene_id, "assets", media_kind="video", prompt_override=prompt_override)
    return APIResponse(data=SceneResponse.model_validate(scene))


@router.post("/scenes/{scene_id}/online-material", response_model=APIResponse[SceneResponse])
async def generate_scene_online_material(
    scene_id: str,
    payload: SceneMediaGenerateRequest | None = None,
    service: GenerationService = Depends(get_generation_service),
):
    prompt_override = payload.prompt_override if payload else None
    scene = await _run_scene(
        service,
        scene_id,
        "assets",
        content_mode_override="online_asset",
        prompt_override=prompt_override,
    )
    return APIResponse(data=SceneResponse.model_validate(scene))


async def _run_scene(service, scene_id, step, **params):
    scene = await service.scene_repo.get_by_id(scene_id)
    if scene is None:
        raise HTTPException(404, "Scene not found")
    await task_manager.run_inline(scene.task_id, {"single_step": step, "single_unit": scene_id, "force_step": step, "force_unit": scene_id, **params}, session_factory=request_session_factory(service.session))
    return await service.scene_repo.get_by_id(scene_id)

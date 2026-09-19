from fastapi import APIRouter, Depends, status

from src.api.dependencies import get_drama_service, request_session_factory
from src.core.exceptions import ValidationException
from src.schemas.common import APIResponse
from src.schemas.drama import (
    DramaApprovalRequest,
    DramaApprovalResponse,
    DramaBibleCreate,
    DramaBibleResponse,
    DramaBibleUpdate,
    DramaCharacterUpdate,
    DramaDetailResponse,
    DramaEpisodeUpdate,
    DramaLocationUpdate,
    DramaPlanRequest,
    DramaPreflightResponse,
    DramaProductionResponse,
    DramaProductionRetryRequest,
    DramaProductionStartRequest,
    DramaSceneUpdate,
    DramaShotUpdate,
)
from src.services.drama_production_service import DramaProductionService
from src.tasks.manager import task_manager

router = APIRouter(tags=["Drama"])


@router.get(
    "/projects/{project_id}/dramas",
    response_model=APIResponse[list[DramaBibleResponse]],
)
async def list_project_dramas(
    project_id: str,
    service: DramaProductionService = Depends(get_drama_service),
):
    dramas = await service.list_bibles(project_id)
    return APIResponse(data=[DramaBibleResponse.model_validate(drama) for drama in dramas])


@router.post(
    "/projects/{project_id}/dramas",
    response_model=APIResponse[DramaDetailResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_project_drama(
    project_id: str,
    payload: DramaBibleCreate,
    service: DramaProductionService = Depends(get_drama_service),
):
    drama = await service.create_bible(project_id, payload)
    detail = await service.get_detail(drama.id)
    return APIResponse(data=DramaDetailResponse.model_validate(detail))


@router.get("/dramas/{drama_id}/preflight", response_model=APIResponse[DramaPreflightResponse])
async def get_drama_preflight(
    drama_id: str,
    service: DramaProductionService = Depends(get_drama_service),
):
    return APIResponse(data=DramaPreflightResponse.model_validate(await service.storyboard_preflight(drama_id)))


@router.post("/dramas/{drama_id}/plan", response_model=APIResponse[DramaDetailResponse])
async def plan_drama(
    drama_id: str,
    payload: DramaPlanRequest | None = None,
    service: DramaProductionService = Depends(get_drama_service),
):
    detail = await service.plan(drama_id, payload or DramaPlanRequest())
    return APIResponse(data=DramaDetailResponse.model_validate(detail))


@router.patch("/dramas/{drama_id}", response_model=APIResponse[DramaDetailResponse])
async def update_drama(
    drama_id: str,
    payload: DramaBibleUpdate,
    service: DramaProductionService = Depends(get_drama_service),
):
    detail = await service.update_bible(drama_id, payload)
    return APIResponse(data=DramaDetailResponse.model_validate(detail))


@router.get("/dramas/{drama_id}", response_model=APIResponse[DramaDetailResponse])
async def get_drama(
    drama_id: str,
    service: DramaProductionService = Depends(get_drama_service),
):
    detail = await service.get_detail(drama_id)
    return APIResponse(data=DramaDetailResponse.model_validate(detail))


@router.patch(
    "/dramas/{drama_id}/characters/{character_id}",
    response_model=APIResponse[DramaDetailResponse],
)
async def update_drama_character(
    drama_id: str,
    character_id: str,
    payload: DramaCharacterUpdate,
    service: DramaProductionService = Depends(get_drama_service),
):
    detail = await service.update_character(drama_id, character_id, payload)
    return APIResponse(data=DramaDetailResponse.model_validate(detail))


@router.post(
    "/dramas/{drama_id}/characters/{character_id}/approve",
    response_model=APIResponse[DramaDetailResponse],
)
async def approve_drama_character(
    drama_id: str,
    character_id: str,
    payload: DramaApprovalRequest | None = None,
    service: DramaProductionService = Depends(get_drama_service),
):
    detail = await service.approve_character(drama_id, character_id, (payload or DramaApprovalRequest()).note)
    return APIResponse(data=DramaDetailResponse.model_validate(detail))


@router.patch(
    "/dramas/{drama_id}/locations/{location_id}",
    response_model=APIResponse[DramaDetailResponse],
)
async def update_drama_location(
    drama_id: str,
    location_id: str,
    payload: DramaLocationUpdate,
    service: DramaProductionService = Depends(get_drama_service),
):
    detail = await service.update_location(drama_id, location_id, payload)
    return APIResponse(data=DramaDetailResponse.model_validate(detail))


@router.post(
    "/dramas/{drama_id}/locations/{location_id}/approve",
    response_model=APIResponse[DramaDetailResponse],
)
async def approve_drama_location(
    drama_id: str,
    location_id: str,
    payload: DramaApprovalRequest | None = None,
    service: DramaProductionService = Depends(get_drama_service),
):
    detail = await service.approve_location(drama_id, location_id, (payload or DramaApprovalRequest()).note)
    return APIResponse(data=DramaDetailResponse.model_validate(detail))


@router.patch(
    "/dramas/{drama_id}/episodes/{episode_id}",
    response_model=APIResponse[DramaDetailResponse],
)
async def update_drama_episode(
    drama_id: str,
    episode_id: str,
    payload: DramaEpisodeUpdate,
    service: DramaProductionService = Depends(get_drama_service),
):
    detail = await service.update_episode(drama_id, episode_id, payload)
    return APIResponse(data=DramaDetailResponse.model_validate(detail))


@router.post(
    "/dramas/{drama_id}/episodes/{episode_id}/approve",
    response_model=APIResponse[DramaDetailResponse],
)
async def approve_drama_episode(
    drama_id: str,
    episode_id: str,
    payload: DramaApprovalRequest | None = None,
    service: DramaProductionService = Depends(get_drama_service),
):
    detail = await service.approve_episode(drama_id, episode_id, (payload or DramaApprovalRequest()).note)
    return APIResponse(data=DramaDetailResponse.model_validate(detail))


@router.patch(
    "/dramas/{drama_id}/scenes/{scene_id}",
    response_model=APIResponse[DramaDetailResponse],
)
async def update_drama_scene(
    drama_id: str,
    scene_id: str,
    payload: DramaSceneUpdate,
    service: DramaProductionService = Depends(get_drama_service),
):
    detail = await service.update_scene(drama_id, scene_id, payload)
    return APIResponse(data=DramaDetailResponse.model_validate(detail))


@router.post(
    "/dramas/{drama_id}/scenes/{scene_id}/approve",
    response_model=APIResponse[DramaDetailResponse],
)
async def approve_drama_scene(
    drama_id: str,
    scene_id: str,
    payload: DramaApprovalRequest | None = None,
    service: DramaProductionService = Depends(get_drama_service),
):
    detail = await service.approve_scene(drama_id, scene_id, (payload or DramaApprovalRequest()).note)
    return APIResponse(data=DramaDetailResponse.model_validate(detail))


@router.patch(
    "/dramas/{drama_id}/shots/{shot_id}",
    response_model=APIResponse[DramaDetailResponse],
)
async def update_drama_shot(
    drama_id: str,
    shot_id: str,
    payload: DramaShotUpdate,
    service: DramaProductionService = Depends(get_drama_service),
):
    detail = await service.update_shot(drama_id, shot_id, payload)
    return APIResponse(data=DramaDetailResponse.model_validate(detail))


@router.post(
    "/dramas/{drama_id}/shots/{shot_id}/approve",
    response_model=APIResponse[DramaDetailResponse],
)
async def approve_drama_shot(
    drama_id: str,
    shot_id: str,
    payload: DramaApprovalRequest | None = None,
    service: DramaProductionService = Depends(get_drama_service),
):
    detail = await service.approve_shot(drama_id, shot_id, (payload or DramaApprovalRequest()).note)
    return APIResponse(data=DramaDetailResponse.model_validate(detail))


@router.post(
    "/dramas/{drama_id}/approve-storyboard",
    response_model=APIResponse[DramaApprovalResponse],
)
async def approve_drama_storyboard(
    drama_id: str,
    payload: DramaApprovalRequest | None = None,
    service: DramaProductionService = Depends(get_drama_service),
):
    detail, preflight = await service.approve_storyboard(
        drama_id, (payload or DramaApprovalRequest()).note
    )
    return APIResponse(
        data=DramaApprovalResponse(
            drama=DramaDetailResponse.model_validate(detail),
            preflight=DramaPreflightResponse.model_validate(preflight),
        )
    )


@router.get(
    "/dramas/{drama_id}/production",
    response_model=APIResponse[DramaProductionResponse],
)
async def get_drama_production_status(
    drama_id: str,
    episode_id: str | None = None,
    service: DramaProductionService = Depends(get_drama_service),
):
    return APIResponse(data=await service.get_production_status(drama_id, episode_id))


@router.post(
    "/dramas/{drama_id}/production/start",
    response_model=APIResponse[DramaProductionResponse],
)
async def start_drama_production(
    drama_id: str,
    payload: DramaProductionStartRequest,
    service: DramaProductionService = Depends(get_drama_service),
):
    task = await service.create_production_task(drama_id, payload)
    factory = request_session_factory(service.session)
    latest = await task_manager.get_latest_job(task.id, session_factory=factory, exclude_publish=True)
    if not latest or latest.status in {"completed", "failed", "cancelled", "missed", "uncertain"}:
        await task_manager.submit_task(task.id, session_factory=factory)
    return APIResponse(data=await service.get_production_status(drama_id, payload.episode_id))


@router.post(
    "/dramas/{drama_id}/production/resume",
    response_model=APIResponse[DramaProductionResponse],
)
async def resume_drama_production(
    drama_id: str,
    service: DramaProductionService = Depends(get_drama_service),
):
    status_data = await service.get_production_status(drama_id)
    if not status_data.task_id:
        raise ValidationException("当前 Drama 尚未创建 Episode production task。")
    await task_manager.resume_task(
        status_data.task_id,
        status_data.job_id,
        session_factory=request_session_factory(service.session),
    )
    return APIResponse(data=await service.get_production_status(drama_id, status_data.episode_id))


@router.post(
    "/dramas/{drama_id}/production/shots/{shot_id}/retry",
    response_model=APIResponse[DramaProductionResponse],
)
async def retry_drama_shot_production(
    drama_id: str,
    shot_id: str,
    payload: DramaProductionRetryRequest,
    service: DramaProductionService = Depends(get_drama_service),
):
    status_data = await service.get_production_status(drama_id)
    if not status_data.task_id:
        raise ValidationException("当前 Drama 尚未创建 Episode production task。")
    shot = next((item for item in status_data.shots if item.source_shot_id == shot_id), None)
    if not shot:
        raise ValidationException("Shot 不属于当前 Episode production task。")
    await task_manager.submit_task(
        status_data.task_id,
        params={"force_step": payload.stage, "force_unit": shot.shot_id},
        session_factory=request_session_factory(service.session),
    )
    return APIResponse(data=await service.get_production_status(drama_id, status_data.episode_id))

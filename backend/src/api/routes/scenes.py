from fastapi import APIRouter, Depends

from src.api.dependencies import get_scene_service
from src.schemas.common import APIResponse
from src.schemas.scene import SceneResponse, SceneUpdate
from src.services.scene_service import SceneService

router = APIRouter(prefix="/scenes", tags=["Scenes"])


@router.patch("/{scene_id}", response_model=APIResponse[SceneResponse])
async def update_scene(
    scene_id: str,
    payload: SceneUpdate,
    service: SceneService = Depends(get_scene_service),
):
    scene = await service.update_scene(scene_id, payload)
    return APIResponse(data=SceneResponse.model_validate(scene))


@router.delete("/{scene_id}", response_model=APIResponse[bool])
async def delete_scene(
    scene_id: str,
    service: SceneService = Depends(get_scene_service),
):
    result = await service.delete_scene(scene_id)
    return APIResponse(data=result)

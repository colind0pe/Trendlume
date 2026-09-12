import mimetypes
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from src.api.dependencies import get_asset_service
from src.core.exceptions import StorageException, ValidationException
from src.domain.enums import AssetType
from src.models.project import ProjectModel
from src.schemas.asset import (
    AssetBatchRequest,
    AssetBatchResult,
    AssetBatchTagsRequest,
    AssetResponse,
)
from src.schemas.common import APIResponse
from src.services.asset_service import AssetService
from src.services.media_probe import media_probe_service
from src.storage.local_storage import local_storage

router = APIRouter(prefix="/assets", tags=["Assets"])


@router.post(
    "/upload", response_model=APIResponse[AssetResponse], status_code=status.HTTP_201_CREATED
)
async def upload_asset(
    file: UploadFile = File(...),
    asset_type: AssetType = Form(...),
    project_id: str | None = Form(None),
    service: AssetService = Depends(get_asset_service),
):
    if not project_id:
        raise ValidationException("用户上传素材必须绑定到项目。")
    if not await service.session.get(ProjectModel, project_id):
        raise ValidationException("项目不存在，无法上传素材。")
    content = await file.read()
    asset = await service.save_asset(
        content=content,
        file_name=file.filename or "upload.bin",
        mime_type=file.content_type or "application/octet-stream",
        asset_type=asset_type,
        project_id=project_id,
    )
    if asset_type in {AssetType.AUDIO, AssetType.BGM, AssetType.VIDEO}:
        try:
            probe = await media_probe_service.probe(service.storage.get_path(asset.file_path))
            if asset_type in {AssetType.AUDIO, AssetType.BGM}:
                if not probe.has_audio or not probe.audio_duration:
                    raise ValidationException("音频素材没有可用的音频流。")
                asset.duration_seconds = probe.audio_duration
            elif not probe.has_video or not probe.video_duration:
                raise ValidationException("视频素材没有可用的视频流。")
            else:
                asset.duration_seconds = probe.video_duration
                asset.width = probe.width
                asset.height = probe.height
            asset.metadata_json = {
                **(asset.metadata_json or {}),
                "duration_source": "ffprobe",
                "actual_duration_seconds": probe.duration_seconds,
            }
            await service.asset_repo.update(asset)
            await service.session.commit()
        except Exception:
            await service.delete_asset(asset.id)
            await service.session.commit()
            raise
    return APIResponse(data=AssetResponse.model_validate(asset))


@router.get("", response_model=APIResponse[list[AssetResponse]])
async def list_assets(
    project_id: str | None = Query(None),
    asset_type: AssetType | None = Query(None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: AssetService = Depends(get_asset_service),
):
    assets = await service.list_assets(
        project_id=project_id,
        asset_type=asset_type,
        limit=limit,
        offset=offset,
    )
    return APIResponse(data=[AssetResponse.model_validate(a) for a in assets])


@router.post("/batch/delete", response_model=APIResponse[AssetBatchResult])
async def batch_delete_assets(
    payload: AssetBatchRequest,
    service: AssetService = Depends(get_asset_service),
):
    result = await service.batch_delete_assets(payload.asset_ids)
    return APIResponse(data=result)


@router.post("/batch/tags", response_model=APIResponse[AssetBatchResult])
async def batch_tag_assets(
    payload: AssetBatchTagsRequest,
    service: AssetService = Depends(get_asset_service),
):
    result = await service.batch_tag_assets(payload.asset_ids, payload.tags)
    return APIResponse(data=result)


@router.post("/batch/download")
async def download_assets(
    payload: AssetBatchRequest,
    service: AssetService = Depends(get_asset_service),
):
    archive = await service.build_asset_archive(payload.asset_ids)
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=trendlume-assets.zip"},
    )


@router.get("/files/{file_path:path}")
async def get_raw_storage_file(file_path: str):
    """Serve stored asset / media files directly by relative storage path"""
    try:
        abs_path = local_storage.get_path(file_path)
    except StorageException as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc
    if not abs_path.exists() or not abs_path.is_file() or not os.access(abs_path, os.R_OK):
        raise HTTPException(status_code=404, detail="File not found")
    mime_type, _ = mimetypes.guess_type(str(abs_path))
    return FileResponse(abs_path, media_type=mime_type or "application/octet-stream")


@router.get("/{asset_id}", response_model=APIResponse[AssetResponse])
async def get_asset(
    asset_id: str,
    service: AssetService = Depends(get_asset_service),
):
    asset = await service.get_asset(asset_id)
    return APIResponse(data=AssetResponse.model_validate(asset))


@router.get("/{asset_id}/file")
async def get_asset_file(
    asset_id: str,
    service: AssetService = Depends(get_asset_service),
):
    asset = await service.get_asset(asset_id)
    try:
        abs_path = service.storage.get_path(asset.file_path)
        AssetType(asset.asset_type)
    except (StorageException, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Asset file not found") from exc
    if not abs_path.is_file() or not os.access(abs_path, os.R_OK):
        raise HTTPException(status_code=404, detail="Asset file not found")
    return FileResponse(abs_path, media_type=asset.mime_type, filename=asset.file_name)


@router.delete("/{asset_id}", response_model=APIResponse[bool])
async def delete_asset(
    asset_id: str,
    service: AssetService = Depends(get_asset_service),
):
    result = await service.delete_asset(asset_id)
    await service.session.commit()
    return APIResponse(data=result)

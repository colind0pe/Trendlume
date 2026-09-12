from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.core.exceptions import ValidationException
from src.models.asset import AssetModel
from src.schemas.common import APIResponse
from src.schemas.template import TemplateCatalogItem, TemplatePreviewRequest
from src.services.template_catalog import template_catalog
from src.services.template_renderer import TemplateRenderer
from src.storage.local_storage import local_storage

router = APIRouter(prefix="/templates", tags=["Templates"])


def _preview_file(item: dict) -> Path | None:
    if not item.get("preview_path"):
        return None
    candidate = template_catalog.root / item["preview_path"]
    if not candidate.is_file() and str(item["preview_path"]).startswith("cache/"):
        candidate = local_storage.get_path(item["preview_path"])
    return candidate if candidate.is_file() else None


@router.get("", response_model=APIResponse[list[TemplateCatalogItem]])
async def list_templates(
    aspect_ratio: str | None = None,
    content_mode: str | None = None,
):
    return APIResponse(
        data=[
            TemplateCatalogItem.model_validate(item)
            for item in template_catalog.scan(aspect_ratio=aspect_ratio, content_mode=content_mode)
        ]
    )


@router.get("/previews/{template_id}")
async def get_template_preview(template_id: str):
    item = template_catalog.get(template_id)
    if not item:
        raise HTTPException(status_code=404, detail="Template not found")
    preview = _preview_file(item)
    if not preview:
        # The upload-material template has no static Demo screenshot.  Generate
        # its neutral placeholder through the same Playwright renderer used by
        # production scene frames, then cache it for subsequent gallery loads.
        relative = f"cache/template_preview_{item['id']}_{item['version']}.png"
        output = local_storage.get_path(relative)
        try:
            await TemplateRenderer.render(
                item["id"],
                title="上传素材模板",
                text="绑定项目中的图片或视频素材",
                output_path=output,
            )
        except ValidationException as exc:
            raise HTTPException(status_code=422, detail=exc.message) from exc
        preview = output
    return FileResponse(preview, media_type="image/jpeg" if preview.suffix.lower() in {".jpg", ".jpeg"} else "image/png")


@router.get("/{template_id}", response_model=APIResponse[TemplateCatalogItem])
async def get_template(template_id: str):
    item = template_catalog.get(template_id)
    if not item:
        raise HTTPException(status_code=404, detail="Template not found")
    return APIResponse(data=TemplateCatalogItem.model_validate(item))


@router.post("/{template_id}/preview", response_model=APIResponse[dict], status_code=status.HTTP_200_OK)
async def render_template_preview(
    template_id: str,
    payload: TemplatePreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    item = template_catalog.get(template_id)
    if not item:
        raise HTTPException(status_code=404, detail="Template not found")

    image_path: Path | None = None
    asset_id = payload.image_asset_id or payload.video_asset_id
    if asset_id:
        asset = await db.get(AssetModel, asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail="Preview asset not found")
        media_path = local_storage.get_path(asset.file_path)
        if not media_path.exists():
            raise HTTPException(status_code=404, detail="Preview asset file missing")
        if asset.asset_type == "video" or media_path.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv", ".avi"}:
            frame_key = hashlib.sha256(f"video_preview:{asset.id}:{media_path.stat().st_mtime}".encode()).hexdigest()[:16]
            frame_path = local_storage.get_path(f"cache/video_preview_{frame_key}.png")
            if not frame_path.exists():
                import subprocess
                frame_path.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["ffmpeg", "-y", "-ss", "00:00:00.5", "-i", str(media_path), "-vframes", "1", str(frame_path)],
                    capture_output=True,
                    check=False,
                )
            if frame_path.exists():
                image_path = frame_path
            else:
                sample_candidate = template_catalog.root / "assets" / f"sample_real_render_{item['width']}x{item['height']}.png"
                if not sample_candidate.is_file():
                    sample_candidate = template_catalog.root / "assets" / "sample_real_render_1080x1920.png"
                if sample_candidate.is_file():
                    image_path = sample_candidate
        else:
            image_path = media_path
    else:
        sample_candidate = template_catalog.root / "assets" / f"sample_real_render_{item['width']}x{item['height']}.png"
        if not sample_candidate.is_file():
            sample_candidate = template_catalog.root / "assets" / "sample_real_render_1080x1920.png"
        if sample_candidate.is_file():
            image_path = sample_candidate

    key = hashlib.sha256(
        f"{item['id']}:{item['version']}:{payload.model_dump_json()}".encode()
    ).hexdigest()[:20]
    relative = f"cache/template_preview_{key}.png"
    output = local_storage.get_path(relative)
    try:
        await TemplateRenderer.render(
            item["id"],
            title=payload.title,
            text=payload.text,
            image_path=image_path,
            custom_params=payload.params,
            custom_css=payload.custom_css,
            output_path=output,
        )
    except ValidationException:
        raise
    return APIResponse(
        data={
            "template_id": item["id"],
            "width": item["width"],
            "height": item["height"],
            "preview_url": local_storage.get_url(relative),
        }
    )

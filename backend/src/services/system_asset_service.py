"""Idempotent initialization and discovery for system BGM assets."""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import (
    BGM_STORAGE_PREFIX,
    AssetType,
    is_bgm_storage_path,
    normalize_storage_path,
)
from src.models.asset import AssetModel
from src.services.media_probe import media_probe_service
from src.storage.local_storage import LocalStorageService, local_storage

DEFAULT_BGM_ASSET_ID = "asset_bgm_demo_default"
DEFAULT_BGM_FILE_NAME = "default.mp3"


def is_bgm_asset(asset: AssetModel | None) -> bool:
    """Return whether an asset is a legal BGM asset by type and path."""
    return bool(
        asset
        and asset.asset_type == AssetType.BGM.value
        and is_bgm_storage_path(asset.file_path)
    )


def is_system_asset(asset: AssetModel | None) -> bool:
    """Return whether an asset belongs to the read-only system catalog."""
    return bool(
        asset
        and asset.project_id is None
        and (asset.metadata_json or {}).get("scope") == "system"
    )


def default_bgm_resource_path() -> Path:
    return Path(__file__).resolve().parents[2] / "resources" / "bgm" / DEFAULT_BGM_FILE_NAME


async def ensure_default_bgm(
    session: AsyncSession,
    storage: LocalStorageService = local_storage,
) -> AssetModel | None:
    """Create or repair the Demo BGM asset without creating duplicates."""
    resource_path = default_bgm_resource_path()
    if not resource_path.is_file():
        logger.warning("Bundled Demo BGM is missing: {}", resource_path)
        return None

    probe = await media_probe_service.probe(resource_path)
    if not probe.has_audio or not probe.audio_duration:
        raise ValueError("Bundled Demo BGM does not contain a valid audio stream")

    asset = await session.get(AssetModel, DEFAULT_BGM_ASSET_ID)
    relative_path = f"audio/bgm/{DEFAULT_BGM_ASSET_ID}.mp3"
    absolute_path = storage.get_path(relative_path)
    if not absolute_path.exists() or absolute_path.stat().st_size == 0:
        await storage.save_file(resource_path.read_bytes(), relative_path)

    metadata = {
        "scope": "system",
        "source": "TrendlumeDemo",
        "read_only": True,
        "duration_source": "ffprobe",
    }
    if asset is None:
        asset = AssetModel(
            id=DEFAULT_BGM_ASSET_ID,
            project_id=None,
            asset_type=AssetType.BGM.value,
            file_name=DEFAULT_BGM_FILE_NAME,
            file_path=relative_path,
            mime_type="audio/mpeg",
            file_size_bytes=resource_path.stat().st_size,
            duration_seconds=probe.audio_duration,
            metadata_json=metadata,
        )
        session.add(asset)
    else:
        asset.project_id = None
        asset.asset_type = AssetType.BGM.value
        asset.file_path = relative_path
        asset.file_name = DEFAULT_BGM_FILE_NAME
        asset.mime_type = "audio/mpeg"
        asset.file_size_bytes = resource_path.stat().st_size
        asset.duration_seconds = probe.audio_duration
        asset.metadata_json = {**(asset.metadata_json or {}), **metadata}

    await session.flush()
    return asset


async def sync_bgm_directory_assets(
    session: AsyncSession,
    storage: LocalStorageService = local_storage,
) -> int:
    """Register valid, untracked files already present in ``audio/bgm``.

    The directory is a source of public/system BGM assets.  Discovery is
    deliberately conservative: temporary files and anything that cannot pass
    the shared FFprobe check are logged and skipped, while existing database
    rows are never converted in place.
    """
    bgm_directory = storage.get_path(BGM_STORAGE_PREFIX)
    bgm_directory.mkdir(parents=True, exist_ok=True)

    result = await session.execute(
        select(AssetModel.id, AssetModel.file_path)
        .where(AssetModel.file_path.is_not(None))
    )
    registered_paths = {
        normalize_storage_path(file_path)
        for _, file_path in result.all()
        if file_path
    }
    registered_ids = {
        asset_id
        for asset_id in (
            await session.execute(select(AssetModel.id))
        ).scalars().all()
    }

    created_count = 0
    for candidate in sorted(bgm_directory.rglob("*")):
        if not candidate.is_file():
            continue
        if (
            candidate.name.startswith(".")
            or ".tmp-" in candidate.name
            or candidate.name.endswith((".tmp", ".part", ".crdownload"))
        ):
            logger.warning("Skipping temporary BGM file during sync: {}", candidate)
            continue

        relative_path = candidate.relative_to(storage.base_dir).as_posix()
        if not is_bgm_storage_path(relative_path):
            continue
        normalized_path = normalize_storage_path(relative_path)
        if normalized_path in registered_paths:
            continue

        try:
            probe = await media_probe_service.probe(candidate)
            if not probe.has_audio or not probe.audio_duration:
                raise ValueError("file has no usable audio stream")
        except Exception as exc:
            logger.warning("Skipping invalid BGM file {}: {}", candidate, exc)
            continue

        content_sha256 = hashlib.sha256(candidate.read_bytes()).hexdigest()
        asset_id = f"asset_bgm_{hashlib.sha256(normalized_path.encode()).hexdigest()[:16]}"
        if asset_id in registered_ids:
            asset_id = f"asset_bgm_{content_sha256[:16]}"
        if asset_id in registered_ids:
            logger.warning("Skipping BGM file with an existing asset id: {}", candidate)
            continue

        asset = AssetModel(
            id=asset_id,
            project_id=None,
            asset_type=AssetType.BGM.value,
            file_name=candidate.name,
            file_path=normalized_path,
            mime_type=mimetypes.guess_type(candidate.name)[0] or "audio/mpeg",
            file_size_bytes=candidate.stat().st_size,
            duration_seconds=probe.audio_duration,
            metadata_json={
                "scope": "system",
                "source": "storage_directory",
                "read_only": True,
                "duration_source": "ffprobe",
                "content_sha256": content_sha256,
            },
        )
        session.add(asset)
        registered_paths.add(normalized_path)
        registered_ids.add(asset_id)
        created_count += 1

    if created_count:
        await session.flush()
    return created_count

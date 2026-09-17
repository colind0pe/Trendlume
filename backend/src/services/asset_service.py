import asyncio
import io
import json
import uuid
import zipfile
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException, ValidationException
from src.domain.enums import BGM_STORAGE_PREFIX, AssetType
from src.models.asset import AssetModel
from src.models.project import ProjectModel
from src.models.publishing import PublishingJobModel
from src.models.scene import SceneModel
from src.models.task import TaskModel
from src.models.workflow import WorkflowArtifactModel
from src.repositories.asset_repository import AssetRepository
from src.services.system_asset_service import is_system_asset
from src.services.workflow_execution import WorkflowExecutionContext
from src.storage.local_storage import LocalStorageService


class AssetService:
    """Application service for media assets and local storage"""

    MAX_BATCH_SIZE = 100

    def __init__(self, session: AsyncSession, storage: LocalStorageService | None = None,
                 execution_context: WorkflowExecutionContext | None = None):
        self.session = session
        self.execution_context = execution_context
        self.asset_repo = AssetRepository(session)
        self.storage = storage or LocalStorageService()

    @staticmethod
    def _relative_asset_path(
        asset_id: str,
        file_name: str,
        asset_type: AssetType,
        project_id: str | None,
    ) -> str:
        extension = file_name.split(".")[-1] if "." in file_name else "bin"
        subfolder = (
            BGM_STORAGE_PREFIX.rstrip("/")
            if asset_type == AssetType.BGM
            else f"projects/{project_id}" if project_id else "assets"
        )
        return f"{subfolder}/{asset_id}.{extension}"

    async def save_asset(
        self,
        content: bytes,
        file_name: str,
        mime_type: str,
        asset_type: AssetType,
        project_id: str | None = None,
        duration_seconds: float | None = None,
        width: int | None = None,
        height: int | None = None,
        metadata: dict | None = None,
    ) -> AssetModel:
        asset_id = f"ast_{uuid.uuid4().hex[:12]}"
        relative_path = self._relative_asset_path(asset_id, file_name, asset_type, project_id)

        saved_path = await self.storage.save_file(content, relative_path)

        asset = AssetModel(
            id=asset_id,
            project_id=project_id,
            asset_type=asset_type.value,
            file_name=file_name,
            file_path=saved_path,
            mime_type=mime_type,
            file_size_bytes=len(content),
            duration_seconds=duration_seconds,
            width=width,
            height=height,
            metadata_json=metadata or {},
        )
        if self.execution_context:
            await self.execution_context.fence(self.session)
        return await self.asset_repo.create(asset)

    async def save_asset_from_file(
        self,
        file_path: Path,
        file_name: str,
        mime_type: str,
        asset_type: AssetType,
        project_id: str | None = None,
        duration_seconds: float | None = None,
        width: int | None = None,
        height: int | None = None,
        metadata: dict | None = None,
    ) -> AssetModel:
        """Register a verified local media file as a project asset.

        Callers should probe and fence the file before using this helper. The
        storage layer remains the single place that chooses the final asset
        path, so temporary/download paths never leak into asset metadata.
        """
        if not file_path.is_file() or file_path.stat().st_size <= 0:
            raise ValidationException(f"媒体文件不存在或为空: {file_path.name}")
        asset_id = f"ast_{uuid.uuid4().hex[:12]}"
        relative_path = self._relative_asset_path(asset_id, file_name, asset_type, project_id)
        temporary_path = self.storage.get_path(f"{relative_path}.tmp-{uuid.uuid4().hex}")
        final_path = self.storage.get_path(relative_path)
        file_size = file_path.stat().st_size
        persisted = False

        def _copy_file() -> None:
            temporary_path.parent.mkdir(parents=True, exist_ok=True)
            with file_path.open("rb") as source, temporary_path.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
                target.flush()

        try:
            if self.execution_context:
                await self.execution_context.fence(self.session)
                await self.session.commit()
            await asyncio.to_thread(_copy_file)
            if temporary_path.stat().st_size != file_size:
                raise ValidationException("媒体文件复制后大小不一致。")
            if self.execution_context:
                await self.execution_context.fence(self.session)
            temporary_path.replace(final_path)
            asset = AssetModel(
                id=asset_id,
                project_id=project_id,
                asset_type=asset_type.value,
                file_name=file_name,
                file_path=relative_path,
                mime_type=mime_type,
                file_size_bytes=file_size,
                duration_seconds=duration_seconds,
                width=width,
                height=height,
                metadata_json=metadata or {},
            )
            if self.execution_context:
                await self.execution_context.fence(self.session)
            result = await self.asset_repo.create(asset)
            persisted = True
            return result
        except BaseException:
            if not persisted:
                final_path.unlink(missing_ok=True)
            raise
        finally:
            temporary_path.unlink(missing_ok=True)

    async def get_asset(self, asset_id: str) -> AssetModel:
        asset = await self.asset_repo.get_by_id(asset_id)
        if not asset:
            raise NotFoundException("Asset", asset_id)
        return asset

    async def list_assets(
        self,
        project_id: str | None = None,
        asset_type: AssetType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[AssetModel]:
        type_val = asset_type.value if asset_type else None
        return await self.asset_repo.list_by_project(
            project_id=project_id,
            asset_type=type_val,
            limit=limit,
            offset=offset,
        )

    async def list_project_bgm(self, project_id: str) -> Sequence[AssetModel]:
        return await self.asset_repo.list_project_bgm(project_id)

    async def delete_asset(self, asset_id: str) -> bool:
        if self.execution_context:
            await self.execution_context.fence(self.session)
        asset = await self.get_asset(asset_id)
        reason = await self._asset_reference_reason(asset)
        if reason:
            raise ValidationException(self._reference_message(reason))
        # Delete from filesystem
        await self.storage.delete_file(asset.file_path)
        # Delete record
        return await self.asset_repo.delete_by_id(asset_id)

    @staticmethod
    def _reference_message(reason: str) -> str:
        return {
            "workflow_reference": "素材已被工作流制品引用，不能删除。",
            "system_asset": "系统素材为只读资产，不能删除。",
            "project_reference": "素材正在作为项目封面或背景音乐使用，不能删除。",
            "scene_reference": "素材正在被分镜使用，不能删除。",
            "publishing_reference": "素材正在被发布作业使用，不能删除。",
            "task_reference": "素材正在被任务结果或输入配置引用，不能删除。",
        }.get(reason, "素材当前被引用，不能删除。")

    async def _asset_reference_reason(self, asset: AssetModel) -> str | None:
        """Return a stable protection reason before removing an asset."""
        if await self.session.scalar(select(WorkflowArtifactModel.id).where(WorkflowArtifactModel.asset_id == asset.id).limit(1)):
            return "workflow_reference"
        if is_system_asset(asset):
            return "system_asset"

        project_filter = asset.project_id
        project_stmt = select(ProjectModel.id).where(
            or_(ProjectModel.cover_asset_id == asset.id, ProjectModel.bgm_asset_id == asset.id)
        )
        if project_filter is not None:
            project_stmt = project_stmt.where(ProjectModel.id == project_filter)
        if (await self.session.execute(project_stmt.limit(1))).scalar_one_or_none():
            return "project_reference"

        scene_stmt = select(
            SceneModel.id,
            SceneModel.audio_asset_id,
            SceneModel.media_asset_id,
            SceneModel.rendered_segment_asset_id,
            SceneModel.layout_params,
        )
        if project_filter is not None:
            scene_stmt = scene_stmt.join(TaskModel, SceneModel.task_id == TaskModel.id).where(
                TaskModel.project_id == project_filter
            )
        for scene_row in (await self.session.execute(scene_stmt)).all():
            if asset.id in {
                scene_row.audio_asset_id,
                scene_row.media_asset_id,
                scene_row.rendered_segment_asset_id,
            }:
                return "scene_reference"
            animation = (scene_row.layout_params or {}).get("animation") or {}
            reference_asset_id = (
                animation.get("reference_asset_id") or animation.get("reference_image_asset_id")
                if isinstance(animation, dict)
                else None
            )
            if reference_asset_id == asset.id:
                return "scene_reference"
            poses = animation.get("poses") if isinstance(animation, dict) else None
            if any(
                isinstance(pose, dict) and pose.get("asset_id") == asset.id
                for pose in poses or []
            ):
                return "scene_reference"
            motion_plan = (scene_row.layout_params or {}).get("animation_plan")
            if isinstance(motion_plan, dict):
                if motion_plan.get("reference_asset_id") == asset.id:
                    return "scene_reference"
                planned_poses = motion_plan.get("poses") or []
                if any(
                    isinstance(pose, dict) and pose.get("asset_id") == asset.id
                    for pose in planned_poses
                ):
                    return "scene_reference"
            parallax = animation.get("parallax") if isinstance(animation, dict) else None
            layers = (
                parallax.get("layers")
                if isinstance(parallax, dict) and isinstance(parallax.get("layers"), dict)
                else animation.get("layers")
                if isinstance(animation, dict)
                else {}
            )
            layer_asset_ids: set[str] = set()
            if isinstance(layers, dict):
                for key in (
                    "foreground_asset_id",
                    "background_asset_id",
                    "foreground",
                    "background",
                ):
                    value = layers.get(key)
                    if isinstance(value, dict):
                        value = value.get("asset_id")
                    if isinstance(value, str):
                        layer_asset_ids.add(value)
            if asset.id in layer_asset_ids:
                return "scene_reference"

        publishing_stmt = select(PublishingJobModel.id).where(
            or_(
                PublishingJobModel.video_asset_id == asset.id,
                PublishingJobModel.cover_asset_id == asset.id,
            )
        )
        if project_filter is not None:
            publishing_stmt = publishing_stmt.where(PublishingJobModel.project_id == project_filter)
        if (await self.session.execute(publishing_stmt.limit(1))).scalar_one_or_none():
            return "publishing_reference"

        task_stmt = select(TaskModel.input_payload, TaskModel.result_payload)
        if project_filter is not None:
            task_stmt = task_stmt.where(TaskModel.project_id == project_filter)
        task_rows = (await self.session.execute(task_stmt)).all()
        for input_payload, result_payload in task_rows:
            input_payload = input_payload or {}
            if asset.id in {
                input_payload.get("source_asset_id"),
                input_payload.get("bgm_asset_id"),
            }:
                return "task_reference"
            result_payload = result_payload or {}
            if result_payload.get("final_video_asset_id") == asset.id:
                return "task_reference"
            if any(
                isinstance(version, dict) and version.get("asset_id") == asset.id
                for version in result_payload.get("final_video_versions", [])
            ):
                return "task_reference"
        return None

    @staticmethod
    def _normalize_tags(tags: object) -> list[str]:
        if isinstance(tags, str):
            tags = [tags]
        elif not isinstance(tags, (list, tuple, set)):
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for value in tags:
            tag = str(value or "").strip().lstrip("#").strip()
            if not tag:
                continue
            key = tag.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(tag)
        return normalized

    @classmethod
    def _dedupe_ids(cls, asset_ids: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for asset_id in asset_ids:
            value = str(asset_id or "").strip()
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return result

    async def batch_delete_assets(self, asset_ids: list[str]) -> dict:
        ids = self._dedupe_ids(asset_ids)
        if not ids or len(ids) > self.MAX_BATCH_SIZE:
            raise ValidationException(f"一次最多处理 {self.MAX_BATCH_SIZE} 个素材。")

        deleted_ids: list[str] = []
        skipped: list[dict[str, str]] = []
        for asset_id in ids:
            asset = await self.asset_repo.get_by_id(asset_id)
            if not asset:
                skipped.append({"id": asset_id, "reason": "not_found"})
                continue
            reason = await self._asset_reference_reason(asset)
            if reason:
                skipped.append({"id": asset_id, "reason": reason})
                continue
            if not await self.storage.exists(asset.file_path):
                skipped.append({"id": asset_id, "reason": "file_missing"})
                continue
            await self.storage.delete_file(asset.file_path)
            await self.asset_repo.delete_by_id(asset_id)
            deleted_ids.append(asset_id)
        await self.session.commit()
        return {"deleted_ids": deleted_ids, "skipped": skipped}

    async def batch_tag_assets(self, asset_ids: list[str], tags: list[str]) -> dict:
        ids = self._dedupe_ids(asset_ids)
        if not ids or len(ids) > self.MAX_BATCH_SIZE:
            raise ValidationException(f"一次最多处理 {self.MAX_BATCH_SIZE} 个素材。")
        tags_to_add = self._normalize_tags(tags)
        if not tags_to_add:
            raise ValidationException("至少输入一个有效标签。")

        updated_ids: list[str] = []
        skipped: list[dict[str, str]] = []
        for asset_id in ids:
            asset = await self.asset_repo.get_by_id(asset_id)
            if not asset:
                skipped.append({"id": asset_id, "reason": "not_found"})
                continue
            if is_system_asset(asset):
                skipped.append({"id": asset_id, "reason": "system_asset"})
                continue
            metadata = dict(asset.metadata_json or {})
            current_tags = self._normalize_tags(metadata.get("tags", []))
            metadata["tags"] = self._normalize_tags(current_tags + tags_to_add)
            asset.metadata_json = metadata
            updated_ids.append(asset_id)
        await self.session.commit()
        return {"updated_ids": updated_ids, "skipped": skipped}

    async def build_asset_archive(self, asset_ids: list[str]) -> io.BytesIO:
        ids = self._dedupe_ids(asset_ids)
        if not ids or len(ids) > self.MAX_BATCH_SIZE:
            raise ValidationException(f"一次最多下载 {self.MAX_BATCH_SIZE} 个素材。")

        archive_buffer = io.BytesIO()
        manifest: list[dict[str, str | None]] = []
        written_files = 0
        used_names: set[str] = set()
        with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for asset_id in ids:
                asset = await self.asset_repo.get_by_id(asset_id)
                if not asset:
                    manifest.append({"asset_id": asset_id, "status": "skipped", "reason": "not_found"})
                    continue
                path = self.storage.get_path(asset.file_path)
                if not path.exists() or not path.is_file():
                    manifest.append({"asset_id": asset.id, "status": "skipped", "reason": "file_missing"})
                    continue
                base_name = Path(asset.file_name).name or f"{asset.id}.bin"
                archive_name = f"{asset.id}_{base_name}"
                suffix = 2
                while archive_name in used_names:
                    stem = Path(base_name).stem
                    ext = Path(base_name).suffix
                    archive_name = f"{asset.id}_{stem}_{suffix}{ext}"
                    suffix += 1
                used_names.add(archive_name)
                archive.write(path, archive_name)
                manifest.append(
                    {"asset_id": asset.id, "status": "included", "file_name": archive_name}
                )
                written_files += 1
            if written_files == 0:
                raise ValidationException("所选素材没有可下载的文件。")
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive_buffer.seek(0)
        return archive_buffer

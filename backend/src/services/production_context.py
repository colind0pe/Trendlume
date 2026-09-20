from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidationException
from src.models.asset import AssetModel
from src.models.drama import DramaCharacterModel, DramaLocationModel, DramaPropModel
from src.models.product import ProductModel
from src.models.production_context import ProductionContextSnapshotModel
from src.models.project import ProjectAssetBindingModel, ProjectModel
from src.models.task import TaskModel
from src.models.task_detail import DramaTaskSceneModel, DramaTaskShotModel


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stable(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value


class ProductionContextCompiler:
    """The only boundary that turns editable project/task state into execution input."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def compile(
        self,
        task_id: str,
        *,
        provider_snapshot: dict[str, Any],
        workflow_config: dict[str, Any] | None = None,
    ) -> ProductionContextSnapshotModel:
        task = await self.session.get(TaskModel, task_id)
        if task is None:
            raise ValidationException("任务不存在。")
        project = await self.session.get(ProjectModel, task.project_id)
        if project is None:
            raise ValidationException("任务所属项目不存在。")

        detail = self._detail(project, task)
        asset_rows = (
            await self.session.execute(
                select(ProjectAssetBindingModel, AssetModel)
                .join(AssetModel, AssetModel.id == ProjectAssetBindingModel.asset_id)
                .where(ProjectAssetBindingModel.project_id == project.id)
            )
        ).all()
        mode_context: dict[str, Any]
        if project.mode == "knowledge":
            mode_context = self._columns(project.knowledge_profile)
        elif project.mode == "commerce":
            products = list(
                (
                    await self.session.scalars(
                        select(ProductModel).where(ProductModel.project_id == project.id)
                    )
                ).all()
            )
            if len(products) != 1:
                raise ValidationException("Commerce Project 必须且只能配置一个主商品。")
            mode_context = {
                "profile": self._columns(project.commerce_profile),
                "product": self._columns(products[0]),
            }
        elif project.mode == "drama":
            characters = list(
                (
                    await self.session.scalars(
                        select(DramaCharacterModel).where(
                            DramaCharacterModel.project_id == project.id
                        )
                    )
                ).all()
            )
            locations = list(
                (
                    await self.session.scalars(
                        select(DramaLocationModel).where(
                            DramaLocationModel.project_id == project.id
                        )
                    )
                ).all()
            )
            props = list(
                (
                    await self.session.scalars(
                        select(DramaPropModel).where(DramaPropModel.project_id == project.id)
                    )
                ).all()
            )
            unapproved = [
                item.name
                for item in [*characters, *locations, *props]
                if item.approval_status != "approved"
            ]
            if unapproved:
                raise ValidationException(
                    "Drama 人物、地点和道具必须先通过审批：" + "、".join(unapproved)
                )
            drama_scenes = list((await self.session.scalars(
                select(DramaTaskSceneModel).where(DramaTaskSceneModel.task_id == task.id)
            )).all())
            scene_ids = [scene.id for scene in drama_scenes]
            drama_shots = list((await self.session.scalars(
                select(DramaTaskShotModel).where(DramaTaskShotModel.scene_id.in_(scene_ids))
            )).all()) if scene_ids else []
            project_location_ids = {item.id for item in locations}
            project_character_ids = {item.id for item in characters}
            if any(
                scene.location_id and scene.location_id not in project_location_ids
                for scene in drama_scenes
            ) or any(
                shot.location_id and shot.location_id not in project_location_ids
                for shot in drama_shots
            ) or any(
                character_id not in project_character_ids
                for shot in drama_shots for character_id in shot.character_ids
            ):
                raise ValidationException("Drama Scene/Shot 不能引用其他 Project 的资源。")
            if any(item.approval_status != "approved" for item in [*drama_scenes, *drama_shots]):
                raise ValidationException("Drama Scene 和 Shot 必须先通过审批。")
            mode_context = {
                "profile": self._columns(project.drama_profile),
                "style_guide": self._columns(project.drama_style_guide),
                "characters": [self._columns(item) for item in characters],
                "locations": [self._columns(item) for item in locations],
                "props": [self._columns(item) for item in props],
                "scenes": [self._columns(item) for item in drama_scenes],
                "shots": [self._columns(item) for item in drama_shots],
            }
        else:
            raise ValidationException("项目生产模式无效。")

        payload = _stable(
            {
                "schema_version": 1,
                "mode": project.mode,
                "project": {
                    "id": project.id,
                    "name": project.name,
                    "description": project.description,
                    "aspect_ratio": project.aspect_ratio,
                    "status": project.status,
                    "default_production_settings": project.default_production_settings,
                },
                "project_profile": mode_context,
                "project_assets": [
                    {
                        "binding": self._columns(binding),
                        "asset": self._columns(asset),
                    }
                    for binding, asset in asset_rows
                ],
                "task": {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "editorial_status": task.editorial_status,
                    "generation_settings": task.generation_settings,
                    "publishing_settings": task.publishing_settings,
                    "detail": self._columns(detail),
                },
                "providers": provider_snapshot,
                "workflows": workflow_config or {},
            }
        )
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        snapshot = ProductionContextSnapshotModel(
            task_id=task.id,
            project_id=project.id,
            mode=project.mode,
            context_hash=hashlib.sha256(encoded).hexdigest(),
            context_payload=payload,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    @staticmethod
    def _detail(project: ProjectModel, task: TaskModel):
        values = {
            "knowledge": task.knowledge_detail,
            "commerce": task.commerce_detail,
            "drama": task.drama_episode,
        }
        detail = values.get(project.mode)
        if detail is None or sum(value is not None for value in values.values()) != 1:
            raise ValidationException("Task Detail 必须且只能与 Project 模式匹配。")
        return detail

    @staticmethod
    def _columns(model) -> dict[str, Any] | None:
        if model is None:
            return None
        return {
            column.name: getattr(model, column.name)
            for column in model.__table__.columns
            if column.name not in {"created_at", "updated_at"}
        }

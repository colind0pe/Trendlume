import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.models.scene import SceneModel
from src.repositories.scene_repository import SceneRepository
from src.repositories.task_repository import TaskRepository
from src.schemas.scene import SceneCreate, SceneUpdate
from src.services.workflow_execution import (
    WorkflowExecutionContext,
    assert_task_editable,
    mark_manual_storyboard,
    mark_steps_stale,
)


class SceneService:
    """Application service for Task Storyboard Scenes"""

    def __init__(self, session: AsyncSession, execution_context: WorkflowExecutionContext | None = None):
        self.execution_context = execution_context
        self.session = session
        self.scene_repo = SceneRepository(session)
        self.task_repo = TaskRepository(session)

    async def _before_edit(self, task_id: str, steps: set[str], unit_key: str | None = None) -> None:
        if self.execution_context:
            await self.execution_context.fence(self.session)
            return
        await assert_task_editable(self.session, task_id)
        await mark_manual_storyboard(self.session, task_id)
        await mark_steps_stale(self.session, task_id, steps, "分镜输入已修改", unit_key)

    def _manual_sources(self, layout: dict, audio_id=None, media_id=None) -> dict:
        if self.execution_context:
            return layout
        return {**layout, "input_source": "manual",
                **({"audio_source": "manual"} if audio_id else {}),
                **({"media_source": "manual"} if media_id else {})}

    async def list_scenes_by_task(self, task_id: str) -> Sequence[SceneModel]:
        # Ensure task exists
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            raise NotFoundException("Task", task_id)
        return await self.scene_repo.list_by_task_id(task_id)

    async def create_scene(self, task_id: str, data: SceneCreate) -> SceneModel:
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            raise NotFoundException("Task", task_id)

        await self._before_edit(task_id, {"storyboard", "assets", "voice", "subtitles", "composition", "export"})
        scene_id = f"scene_{uuid.uuid4().hex[:12]}"
        scene = SceneModel(
            id=scene_id,
            task_id=task_id,
            sequence_index=data.sequence_index,
            narration_text=data.narration_text,
            visual_prompt=data.visual_prompt,
            duration_seconds=data.duration_seconds,
            layout_params=self._manual_sources(data.layout_params, data.audio_asset_id, data.media_asset_id),
            visual_role=data.visual_role.value,
            claim_refs=list(data.claim_refs),
            source_refs=list(data.source_refs),
            production_metadata=dict(data.production_metadata),
            audio_asset_id=data.audio_asset_id,
            media_asset_id=data.media_asset_id,
        )
        return await self.scene_repo.create(scene)

    async def replace_task_scenes(
        self, task_id: str, scenes_data: list[SceneCreate]
    ) -> Sequence[SceneModel]:
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            raise NotFoundException("Task", task_id)

        await self._before_edit(task_id, {"storyboard", "assets", "voice", "subtitles", "composition", "export"})
        # Delete old scenes
        await self.scene_repo.delete_by_task_id(task_id)

        # Insert new scenes
        created_scenes: list[SceneModel] = []
        for idx, sc in enumerate(scenes_data):
            scene_id = f"scene_{uuid.uuid4().hex[:12]}"
            scene = SceneModel(
                id=scene_id,
                task_id=task_id,
                sequence_index=sc.sequence_index if sc.sequence_index is not None else idx,
                narration_text=sc.narration_text,
                visual_prompt=sc.visual_prompt,
                duration_seconds=sc.duration_seconds,
                layout_params=self._manual_sources(sc.layout_params, sc.audio_asset_id, sc.media_asset_id),
                visual_role=sc.visual_role.value,
                claim_refs=list(sc.claim_refs),
                source_refs=list(sc.source_refs),
                production_metadata=dict(sc.production_metadata),
                audio_asset_id=sc.audio_asset_id,
                media_asset_id=sc.media_asset_id,
            )
            await self.scene_repo.create(scene)
            created_scenes.append(scene)

        return created_scenes

    async def update_scene(self, scene_id: str, data: SceneUpdate) -> SceneModel:
        scene = await self.scene_repo.get_by_id(scene_id)
        if not scene:
            raise NotFoundException("Scene", scene_id)

        changed = data.model_dump(exclude_unset=True)
        steps = {"storyboard", "export"}
        if {"narration_text", "audio_asset_id", "duration_seconds", "sequence_index"} & changed.keys():
            steps.update({"voice", "subtitles", "composition"})
        if {"visual_prompt", "media_asset_id"} & changed.keys():
            steps.update({"assets", "composition"})
        if {"layout_params", "visual_role", "claim_refs", "source_refs", "production_metadata"} & changed.keys():
            steps.update({"assets", "composition"})
        if "layout_params" in changed:
            steps.add("composition")
        await self._before_edit(scene.task_id, steps, scene.id)
        if not self.execution_context:
            scene.layout_params = {**(scene.layout_params or {}), "input_source": "manual"}
        if data.sequence_index is not None:
            scene.sequence_index = data.sequence_index
        if data.narration_text is not None:
            scene.narration_text = data.narration_text
        if data.visual_prompt is not None:
            scene.visual_prompt = data.visual_prompt
        if data.duration_seconds is not None:
            scene.duration_seconds = data.duration_seconds
        if data.layout_params is not None:
            scene.layout_params = {**data.layout_params, **({"input_source": "manual"} if not self.execution_context else {})}
        if data.visual_role is not None:
            scene.visual_role = data.visual_role.value
        if data.claim_refs is not None:
            scene.claim_refs = list(data.claim_refs)
        if data.source_refs is not None:
            scene.source_refs = list(data.source_refs)
        if data.production_metadata is not None:
            scene.production_metadata = dict(data.production_metadata)
        if data.audio_asset_id is not None:
            scene.audio_asset_id = data.audio_asset_id
        if data.media_asset_id is not None:
            scene.media_asset_id = data.media_asset_id

        scene.layout_params = self._manual_sources(scene.layout_params or {}, data.audio_asset_id, data.media_asset_id)

        return await self.scene_repo.update(scene)

    async def delete_scene(self, scene_id: str) -> bool:
        scene = await self.scene_repo.get_by_id(scene_id)
        if not scene:
            raise NotFoundException("Scene", scene_id)
        await self._before_edit(scene.task_id, {"storyboard", "assets", "voice", "subtitles", "composition", "export"})
        return await self.scene_repo.delete_by_id(scene_id)

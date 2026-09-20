from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.domain.content_modes import ContentMode
from src.domain.enums import CreativeAngle, JobType, ProductionMode, TaskStatus
from src.schemas.generation import KnowledgeBrief
from src.schemas.scene import SceneResponse
from src.schemas.workflow import WorkflowJobResponse


class ScheduledPublishConfig(BaseModel):
    """User-facing schedule captured when a task is created."""

    account_id: str = Field(min_length=1, max_length=36)
    scheduled_at: datetime
    timezone: str = Field(min_length=1, max_length=64)


class TaskCreate(BaseModel):
    title: str = Field(default="新视频生成任务", min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    job_type: JobType = JobType.VIDEO_COMPOSITION
    production_mode: ProductionMode | None = None
    product_id: str | None = None
    creative_plan_id: str | None = None
    creative_angle: CreativeAngle | None = None
    knowledge_item_id: str | None = None
    drama_episode_id: str | None = None
    knowledge_brief: KnowledgeBrief | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    template_id: str = "image_gallery_matted"
    bgm_asset_id: str | None = None
    bgm_enabled: bool = True
    bgm_volume: float = Field(default=0.20, ge=0.0, le=0.5)
    voice_id: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    content_mode: ContentMode | None = None
    target_scene_count: int = Field(default=8, ge=8, le=20, description="目标分镜数量")
    scheduled_publish: ScheduledPublishConfig | None = None
    template_params: dict[str, Any] = Field(default_factory=dict)
    source_asset_id: str | None = None
    enable_research: bool = True
    search_provider_id: str | None = None
    material_provider_id: str | None = None
    research_max_queries: int = Field(default=3, ge=1, le=3)
    research_max_results: int = Field(default=5, ge=1, le=5)
    image_workflow_id: str | None = None
    video_workflow_id: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    production_mode: ProductionMode | None = None
    product_id: str | None = None
    creative_plan_id: str | None = None
    creative_angle: CreativeAngle | None = None
    knowledge_item_id: str | None = None
    status: TaskStatus | None = None
    input_payload: dict[str, Any] | None = None
    result_payload: dict[str, Any] | None = None
    error_message: str | None = None


class TaskDuplicateRequest(BaseModel):
    mode: str = Field(default="settings_and_script", pattern="^(settings_only|settings_and_script)$")
    title: str | None = Field(default=None, max_length=255)


class TaskRerenderRequest(BaseModel):
    template_id: str | None = None
    template_params: dict[str, Any] | None = None
    bgm_enabled: bool | None = None
    bgm_asset_id: str | None = None
    bgm_volume: float | None = Field(default=None, ge=0.0, le=0.5)


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    product_id: str | None = None
    creative_plan_id: str | None = None
    creative_angle: str | None = None
    project_context_version_id: str | None = None
    context_hash: str | None = None
    knowledge_item_id: str | None = None
    drama_episode_id: str | None = None
    title: str
    description: str
    job_type: str
    production_mode: str
    status: str
    progress_percentage: int
    input_payload: dict[str, Any]
    result_payload: dict[str, Any] | None = None
    error_message: str | None = None
    scenes_count: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    active_job: WorkflowJobResponse | None = None
    current_stage: str | None = None
    current_stage_label: str | None = None
    resume_count: int = 0
    last_heartbeat_at: datetime | None = None
    can_resume: bool = False
    scheduled_publish: dict[str, Any] | None = None


class TaskDetailResponse(TaskResponse):
    scenes: list[SceneResponse] = Field(default_factory=list)

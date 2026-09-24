from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_project_service, get_task_service, get_template_service
from src.core.database import get_db
from src.core.exceptions import NotFoundException, ValidationException
from src.domain.enums import AssetType
from src.models.asset import AssetModel
from src.models.drama import DramaCharacterModel, DramaLocationModel, DramaPropModel
from src.models.product import ProductAssetModel, ProductModel
from src.models.project import ProjectAssetBindingModel, ProjectModel
from src.models.task_detail import (
    DramaTaskDialogueLineModel,
    DramaTaskEpisodeModel,
    DramaTaskSceneModel,
    DramaTaskShotModel,
)
from src.models.workflow import WorkflowJobModel
from src.schemas.common import APIResponse
from src.schemas.drama import (
    DramaCharacterCreate,
    DramaCharacterResponse,
    DramaCharacterUpdate,
    DramaLocationCreate,
    DramaLocationResponse,
    DramaLocationUpdate,
    DramaPropCreate,
    DramaPropResponse,
    DramaPropUpdate,
)
from src.schemas.product import ProductCreate, ProductResponse, ProductUpdate
from src.schemas.project import ProjectCreate, ProjectDetailResponse, ProjectResponse, ProjectUpdate
from src.schemas.task import TaskCreate, TaskResponse
from src.schemas.template import ProjectTemplateResponse, ProjectTemplateUpdate
from src.services.project_service import ProjectService
from src.services.task_service import TaskService
from src.services.template_service import ProjectTemplateService

router = APIRouter(prefix="/projects", tags=["Projects"])


class ProjectAssetBindingInput(BaseModel):
    asset_id: str
    purpose: str = Field(min_length=1, max_length=40)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductAssetInput(BaseModel):
    asset_id: str
    role: str = Field(default="gallery", min_length=1, max_length=30)
    alt_text: str = Field(default="", max_length=500)


def _columns(model):
    return {
        attribute.key: getattr(model, attribute.key)
        for attribute in inspect(model).mapper.column_attrs
    }


def _task(task):
    details = {
        "knowledge": task.knowledge_detail,
        "commerce": task.commerce_detail,
        "drama": task.drama_episode,
    }
    kind, detail = next((key, value) for key, value in details.items() if value is not None)
    return {**_columns(task), "detail": {"type": kind, **_columns(detail)}}


def _project(project, include_tasks=False):
    profile = getattr(project, f"{project.mode}_profile")
    data = {**_columns(project), "profile": _columns(profile)}
    if include_tasks:
        data["tasks"] = [_task(task) for task in project.tasks]
    return data


async def _drama_project(db: AsyncSession, project_id: str) -> ProjectModel:
    project = await db.get(ProjectModel, project_id)
    if project is None:
        raise NotFoundException("Project", project_id)
    if project.mode != "drama":
        raise ValidationException("只有 Drama Project 可以管理人物、地点和道具。")
    return project


async def _owned_drama_resource(db, model, project_id: str, resource_id: str):
    resource = await db.scalar(
        select(model).where(model.id == resource_id, model.project_id == project_id)
    )
    if resource is None:
        raise NotFoundException(model.__name__.removesuffix("Model"), resource_id)
    return resource


async def _update_drama_resource(db, resource, payload):
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(resource, key, value)
    resource.approval_status = "draft"
    await db.commit()
    await db.refresh(resource)
    return resource


async def _approve_drama_resource(db, resource):
    resource.approval_status = "approved"
    await db.commit()
    await db.refresh(resource)
    return resource


@router.post("", response_model=APIResponse[ProjectResponse], status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, service: ProjectService = Depends(get_project_service)
):
    return APIResponse(data=_project(await service.create_project(payload)))


@router.get("", response_model=APIResponse[list[ProjectResponse]])
async def list_projects(service: ProjectService = Depends(get_project_service)):
    return APIResponse(data=[_project(item) for item in await service.list_projects()])


@router.get("/{project_id}", response_model=APIResponse[ProjectDetailResponse])
async def get_project(project_id: str, service: ProjectService = Depends(get_project_service)):
    return APIResponse(data=_project(await service.get_project(project_id), True))


@router.patch("/{project_id}", response_model=APIResponse[ProjectResponse])
async def update_project(
    project_id: str, payload: ProjectUpdate, service: ProjectService = Depends(get_project_service)
):
    return APIResponse(data=_project(await service.update_project(project_id, payload)))


@router.delete("/{project_id}", response_model=APIResponse[bool])
async def delete_project(project_id: str, service: ProjectService = Depends(get_project_service)):
    return APIResponse(data=await service.delete_project(project_id))


@router.post(
    "/{project_id}/tasks",
    response_model=APIResponse[TaskResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_project_task(
    project_id: str, payload: TaskCreate, service: TaskService = Depends(get_task_service)
):
    return APIResponse(data=_task(await service.create_task(project_id, payload)))


@router.get("/{project_id}/tasks", response_model=APIResponse[list[TaskResponse]])
async def list_project_tasks(project_id: str, service: TaskService = Depends(get_task_service)):
    tasks = await service.list_tasks(project_id)
    latest: dict[str, WorkflowJobModel] = {}
    if tasks:
        jobs = (await service.session.scalars(
            select(WorkflowJobModel)
            .where(
                WorkflowJobModel.task_id.in_([task.id for task in tasks]),
                WorkflowJobModel.job_type == "full_pipeline",
            )
            .order_by(WorkflowJobModel.created_at.desc())
        )).all()
        for job in jobs:
            latest.setdefault(job.task_id, job)
    return APIResponse(data=[{**_task(task), "latest_job": latest.get(task.id)} for task in tasks])


@router.get(
    "/{project_id}/characters", response_model=APIResponse[list[DramaCharacterResponse]]
)
async def list_drama_characters(project_id: str, db: AsyncSession = Depends(get_db)):
    await _drama_project(db, project_id)
    rows = await db.scalars(
        select(DramaCharacterModel)
        .where(DramaCharacterModel.project_id == project_id)
        .order_by(DramaCharacterModel.created_at, DramaCharacterModel.name)
    )
    return APIResponse(data=list(rows))


@router.post(
    "/{project_id}/characters",
    response_model=APIResponse[DramaCharacterResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_drama_character(
    project_id: str, payload: DramaCharacterCreate, db: AsyncSession = Depends(get_db)
):
    await _drama_project(db, project_id)
    row = DramaCharacterModel(
        id=f"character_{uuid4().hex[:12]}", project_id=project_id, **payload.model_dump()
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return APIResponse(data=row)


@router.patch(
    "/{project_id}/characters/{resource_id}",
    response_model=APIResponse[DramaCharacterResponse],
)
async def update_drama_character(
    project_id: str,
    resource_id: str,
    payload: DramaCharacterUpdate,
    db: AsyncSession = Depends(get_db),
):
    row = await _owned_drama_resource(db, DramaCharacterModel, project_id, resource_id)
    return APIResponse(data=await _update_drama_resource(db, row, payload))


@router.post(
    "/{project_id}/characters/{resource_id}/approve",
    response_model=APIResponse[DramaCharacterResponse],
)
async def approve_drama_character(
    project_id: str, resource_id: str, db: AsyncSession = Depends(get_db)
):
    row = await _owned_drama_resource(db, DramaCharacterModel, project_id, resource_id)
    return APIResponse(data=await _approve_drama_resource(db, row))


@router.delete("/{project_id}/characters/{resource_id}", response_model=APIResponse[bool])
async def delete_drama_character(
    project_id: str, resource_id: str, db: AsyncSession = Depends(get_db)
):
    row = await _owned_drama_resource(db, DramaCharacterModel, project_id, resource_id)
    if await db.scalar(
        select(DramaTaskDialogueLineModel.id).where(
            DramaTaskDialogueLineModel.character_id == resource_id
        ).limit(1)
    ):
        raise ValidationException("人物已被剧集对白引用，不能删除。")
    shots = await db.scalars(select(DramaTaskShotModel.character_ids))
    episodes = await db.scalars(
        select(DramaTaskEpisodeModel.continuity_data).where(
            DramaTaskEpisodeModel.project_id == project_id
        )
    )
    if any(resource_id in (ids or []) for ids in shots) or any(
        resource_id in (data or {}).get("character_ids", []) for data in episodes
    ):
        raise ValidationException("人物已被剧集镜头引用，不能删除。")
    await db.delete(row)
    await db.commit()
    return APIResponse(data=True)


@router.get(
    "/{project_id}/locations", response_model=APIResponse[list[DramaLocationResponse]]
)
async def list_drama_locations(project_id: str, db: AsyncSession = Depends(get_db)):
    await _drama_project(db, project_id)
    rows = await db.scalars(
        select(DramaLocationModel)
        .where(DramaLocationModel.project_id == project_id)
        .order_by(DramaLocationModel.name)
    )
    return APIResponse(data=list(rows))


@router.post(
    "/{project_id}/locations",
    response_model=APIResponse[DramaLocationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_drama_location(
    project_id: str, payload: DramaLocationCreate, db: AsyncSession = Depends(get_db)
):
    await _drama_project(db, project_id)
    row = DramaLocationModel(
        id=f"location_{uuid4().hex[:12]}", project_id=project_id, **payload.model_dump()
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return APIResponse(data=row)


@router.patch(
    "/{project_id}/locations/{resource_id}",
    response_model=APIResponse[DramaLocationResponse],
)
async def update_drama_location(
    project_id: str,
    resource_id: str,
    payload: DramaLocationUpdate,
    db: AsyncSession = Depends(get_db),
):
    row = await _owned_drama_resource(db, DramaLocationModel, project_id, resource_id)
    return APIResponse(data=await _update_drama_resource(db, row, payload))


@router.post(
    "/{project_id}/locations/{resource_id}/approve",
    response_model=APIResponse[DramaLocationResponse],
)
async def approve_drama_location(
    project_id: str, resource_id: str, db: AsyncSession = Depends(get_db)
):
    row = await _owned_drama_resource(db, DramaLocationModel, project_id, resource_id)
    return APIResponse(data=await _approve_drama_resource(db, row))


@router.delete("/{project_id}/locations/{resource_id}", response_model=APIResponse[bool])
async def delete_drama_location(
    project_id: str, resource_id: str, db: AsyncSession = Depends(get_db)
):
    row = await _owned_drama_resource(db, DramaLocationModel, project_id, resource_id)
    in_use = await db.scalar(
        select(DramaTaskSceneModel.id)
        .outerjoin(DramaTaskShotModel, DramaTaskShotModel.scene_id == DramaTaskSceneModel.id)
        .where(
            or_(
                DramaTaskSceneModel.location_id == resource_id,
                DramaTaskShotModel.location_id == resource_id,
            )
        )
        .limit(1)
    )
    episodes = await db.scalars(
        select(DramaTaskEpisodeModel.continuity_data).where(
            DramaTaskEpisodeModel.project_id == project_id
        )
    )
    if in_use or any(
        resource_id in (data or {}).get("location_ids", []) for data in episodes
    ):
        raise ValidationException("地点已被剧集场景或镜头引用，不能删除。")
    await db.delete(row)
    await db.commit()
    return APIResponse(data=True)


@router.get("/{project_id}/props", response_model=APIResponse[list[DramaPropResponse]])
async def list_drama_props(project_id: str, db: AsyncSession = Depends(get_db)):
    await _drama_project(db, project_id)
    rows = await db.scalars(
        select(DramaPropModel)
        .where(DramaPropModel.project_id == project_id)
        .order_by(DramaPropModel.name)
    )
    return APIResponse(data=list(rows))


@router.post(
    "/{project_id}/props",
    response_model=APIResponse[DramaPropResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_drama_prop(
    project_id: str, payload: DramaPropCreate, db: AsyncSession = Depends(get_db)
):
    await _drama_project(db, project_id)
    row = DramaPropModel(
        id=f"prop_{uuid4().hex[:12]}", project_id=project_id, **payload.model_dump()
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return APIResponse(data=row)


@router.patch(
    "/{project_id}/props/{resource_id}", response_model=APIResponse[DramaPropResponse]
)
async def update_drama_prop(
    project_id: str,
    resource_id: str,
    payload: DramaPropUpdate,
    db: AsyncSession = Depends(get_db),
):
    row = await _owned_drama_resource(db, DramaPropModel, project_id, resource_id)
    return APIResponse(data=await _update_drama_resource(db, row, payload))


@router.post(
    "/{project_id}/props/{resource_id}/approve",
    response_model=APIResponse[DramaPropResponse],
)
async def approve_drama_prop(
    project_id: str, resource_id: str, db: AsyncSession = Depends(get_db)
):
    row = await _owned_drama_resource(db, DramaPropModel, project_id, resource_id)
    return APIResponse(data=await _approve_drama_resource(db, row))


@router.delete("/{project_id}/props/{resource_id}", response_model=APIResponse[bool])
async def delete_drama_prop(
    project_id: str, resource_id: str, db: AsyncSession = Depends(get_db)
):
    row = await _owned_drama_resource(db, DramaPropModel, project_id, resource_id)
    episodes = await db.scalars(
        select(DramaTaskEpisodeModel.continuity_data).where(
            DramaTaskEpisodeModel.project_id == project_id
        )
    )
    if any(resource_id in (data or {}).get("prop_ids", []) for data in episodes):
        raise ValidationException("道具已被剧集连续性简报引用，不能删除。")
    await db.delete(row)
    await db.commit()
    return APIResponse(data=True)


@router.get("/{project_id}/template", response_model=APIResponse[ProjectTemplateResponse])
async def get_project_template(
    project_id: str,
    service: ProjectTemplateService = Depends(get_template_service),
):
    return APIResponse(data=await service.get_template_by_project(project_id))


@router.put("/{project_id}/template", response_model=APIResponse[ProjectTemplateResponse])
async def update_project_template(
    project_id: str,
    payload: ProjectTemplateUpdate,
    service: ProjectTemplateService = Depends(get_template_service),
):
    return APIResponse(data=await service.update_template(project_id, payload))


@router.get("/{project_id}/assets", response_model=APIResponse[list[dict[str, Any]]])
async def list_project_assets(
    project_id: str,
    purpose: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if await db.get(ProjectModel, project_id) is None:
        raise NotFoundException("Project", project_id)
    statement = (
        select(ProjectAssetBindingModel, AssetModel)
        .join(AssetModel, AssetModel.id == ProjectAssetBindingModel.asset_id)
        .where(ProjectAssetBindingModel.project_id == project_id)
    )
    if purpose:
        statement = statement.where(ProjectAssetBindingModel.purpose == purpose)
    rows = (await db.execute(statement)).all()
    return APIResponse(data=[{
        "binding_id": binding.id,
        "purpose": binding.purpose,
        "metadata": binding.metadata_json,
        "asset": _columns(asset),
    } for binding, asset in rows])


@router.get("/{project_id}/bgm-candidates", response_model=APIResponse[list[dict[str, Any]]])
async def list_project_bgm_candidates(project_id: str, db: AsyncSession = Depends(get_db)):
    if await db.get(ProjectModel, project_id) is None:
        raise NotFoundException("Project", project_id)
    project_asset_ids = select(ProjectAssetBindingModel.asset_id).where(
        ProjectAssetBindingModel.project_id == project_id
    )
    rows = (await db.scalars(select(AssetModel).where(
        AssetModel.asset_type.in_([AssetType.BGM.value, AssetType.AUDIO.value]),
        (AssetModel.id.in_(project_asset_ids))
        | (AssetModel.metadata_json["scope"].as_string() == "system"),
    ).order_by(AssetModel.created_at.desc()))).all()
    return APIResponse(data=[_columns(asset) for asset in rows])


@router.post("/{project_id}/assets", response_model=APIResponse[dict[str, Any]], status_code=201)
async def bind_project_asset(
    project_id: str,
    payload: ProjectAssetBindingInput,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(ProjectModel, project_id)
    asset = await db.get(AssetModel, payload.asset_id)
    if project is None:
        raise NotFoundException("Project", project_id)
    if asset is None:
        raise NotFoundException("Asset", payload.asset_id)
    foreign_binding = await db.scalar(select(ProjectAssetBindingModel.id).where(
        ProjectAssetBindingModel.asset_id == asset.id,
        ProjectAssetBindingModel.project_id != project_id,
    ))
    if foreign_binding and (asset.metadata_json or {}).get("scope") != "system":
        raise ValidationException("不能绑定其他 Project 的素材。")
    if payload.purpose == "bgm" and asset.asset_type not in {
        AssetType.BGM.value,
        AssetType.AUDIO.value,
    }:
        raise ValidationException("BGM 绑定只能使用音频素材。")
    binding = ProjectAssetBindingModel(
        id=f"binding_{uuid4().hex[:12]}",
        project_id=project_id,
        asset_id=asset.id,
        purpose=payload.purpose,
        metadata_json=payload.metadata,
    )
    db.add(binding)
    await db.commit()
    return APIResponse(data={
        "binding_id": binding.id,
        "purpose": binding.purpose,
        "metadata": binding.metadata_json,
        "asset": _columns(asset),
    })


@router.delete("/{project_id}/assets/{binding_id}", response_model=APIResponse[bool])
async def unbind_project_asset(
    project_id: str,
    binding_id: str,
    db: AsyncSession = Depends(get_db),
):
    binding = await db.get(ProjectAssetBindingModel, binding_id)
    if binding is None or binding.project_id != project_id:
        raise NotFoundException("ProjectAssetBinding", binding_id)
    await db.delete(binding)
    await db.commit()
    return APIResponse(data=True)


@router.get("/{project_id}/product", response_model=APIResponse[ProductResponse])
async def get_project_product(project_id: str, db: AsyncSession = Depends(get_db)):
    product = await db.scalar(select(ProductModel).where(ProductModel.project_id == project_id))
    if product is None:
        raise NotFoundException("Product", project_id)
    return APIResponse(data=product)


@router.put("/{project_id}/product", response_model=APIResponse[ProductResponse])
async def put_project_product(
    project_id: str,
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(ProjectModel, project_id)
    if project is None:
        raise NotFoundException("Project", project_id)
    if project.mode != "commerce":
        raise ValidationException("只有 Commerce Project 可以配置主商品。")
    product = await db.scalar(select(ProductModel).where(ProductModel.project_id == project_id))
    values = payload.model_dump(exclude={"name", "selling_points"})
    if product is None:
        product = ProductModel(id=f"product_{uuid4().hex[:12]}", project_id=project_id, **values)
        db.add(product)
    else:
        for key, value in values.items():
            setattr(product, key, value)
    await db.commit()
    await db.refresh(product)
    return APIResponse(data=product)


@router.patch("/{project_id}/product", response_model=APIResponse[ProductResponse])
async def patch_project_product(
    project_id: str,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
):
    product = await db.scalar(select(ProductModel).where(ProductModel.project_id == project_id))
    if product is None:
        raise NotFoundException("Product", project_id)
    for key, value in payload.model_dump(exclude_unset=True, exclude={"selling_points"}).items():
        setattr(product, key, value)
    await db.commit()
    return APIResponse(data=product)


@router.post("/{project_id}/product/assets", response_model=APIResponse[dict[str, Any]], status_code=201)
async def add_project_product_asset(
    project_id: str,
    payload: ProductAssetInput,
    db: AsyncSession = Depends(get_db),
):
    product = await db.scalar(select(ProductModel).where(ProductModel.project_id == project_id))
    asset = await db.get(AssetModel, payload.asset_id)
    bound = await db.scalar(select(ProjectAssetBindingModel.id).where(
        ProjectAssetBindingModel.project_id == project_id,
        ProjectAssetBindingModel.asset_id == payload.asset_id,
    ))
    if product is None:
        raise NotFoundException("Product", project_id)
    if asset is None or not bound:
        raise ValidationException("商品素材必须先属于当前 Project。")
    if asset.asset_type not in {AssetType.IMAGE.value, AssetType.VIDEO.value}:
        raise ValidationException("商品素材只能使用图片或视频。")
    row = ProductAssetModel(
        id=f"product_asset_{uuid4().hex[:12]}", product_id=product.id,
        asset_id=asset.id, asset_type=asset.asset_type, role=payload.role,
        source_kind="upload", alt_text=payload.alt_text,
        sort_order=len(product.assets), metadata_json={},
    )
    db.add(row)
    await db.commit()
    return APIResponse(data=_columns(row))

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_project_service, get_task_service
from src.core.database import get_db
from src.core.exceptions import NotFoundException, ValidationException
from src.models.drama import DramaCharacterModel, DramaLocationModel, DramaPropModel
from src.models.product import ProductModel
from src.models.project import ProjectModel
from src.schemas.common import APIResponse
from src.schemas.product import ProductCreate, ProductResponse, ProductUpdate
from src.schemas.project import ProjectCreate, ProjectDetailResponse, ProjectResponse, ProjectUpdate
from src.schemas.task import TaskCreate, TaskResponse
from src.services.project_service import ProjectService
from src.services.task_service import TaskService

router = APIRouter(prefix="/projects", tags=["Projects"])


class DramaResourceInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    visual_description: str = ""
    continuity_data: dict[str, Any] = Field(default_factory=dict)
    approval_status: str = "draft"


def _columns(model):
    return {column.name: getattr(model, column.name) for column in model.__table__.columns}


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
    return APIResponse(data=[_task(item) for item in await service.list_tasks(project_id)])


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


async def _drama_project(db: AsyncSession, project_id: str) -> ProjectModel:
    project = await db.get(ProjectModel, project_id)
    if project is None:
        raise NotFoundException("Project", project_id)
    if project.mode != "drama":
        raise ValidationException("Drama 资源只能归属 Drama Project。")
    return project


@router.get("/{project_id}/characters", response_model=APIResponse[list[dict[str, Any]]])
async def list_project_characters(project_id: str, db: AsyncSession = Depends(get_db)):
    await _drama_project(db, project_id)
    rows = (await db.scalars(select(DramaCharacterModel).where(
        DramaCharacterModel.project_id == project_id
    ))).all()
    return APIResponse(data=[_columns(row) for row in rows])


@router.post("/{project_id}/characters", response_model=APIResponse[dict[str, Any]], status_code=201)
async def create_project_character(
    project_id: str, payload: DramaResourceInput, db: AsyncSession = Depends(get_db)
):
    await _drama_project(db, project_id)
    row = DramaCharacterModel(
        id=f"character_{uuid4().hex[:12]}", project_id=project_id,
        name=payload.name, description=payload.description,
        approval_status=payload.approval_status,
    )
    db.add(row)
    await db.commit()
    return APIResponse(data=_columns(row))


@router.get("/{project_id}/locations", response_model=APIResponse[list[dict[str, Any]]])
async def list_project_locations(project_id: str, db: AsyncSession = Depends(get_db)):
    await _drama_project(db, project_id)
    rows = (await db.scalars(select(DramaLocationModel).where(
        DramaLocationModel.project_id == project_id
    ))).all()
    return APIResponse(data=[_columns(row) for row in rows])


@router.post("/{project_id}/locations", response_model=APIResponse[dict[str, Any]], status_code=201)
async def create_project_location(
    project_id: str, payload: DramaResourceInput, db: AsyncSession = Depends(get_db)
):
    await _drama_project(db, project_id)
    row = DramaLocationModel(
        id=f"location_{uuid4().hex[:12]}", project_id=project_id,
        name=payload.name, visual_description=payload.visual_description or payload.description,
        continuity_data=payload.continuity_data, approval_status=payload.approval_status,
    )
    db.add(row)
    await db.commit()
    return APIResponse(data=_columns(row))


@router.get("/{project_id}/props", response_model=APIResponse[list[dict[str, Any]]])
async def list_project_props(project_id: str, db: AsyncSession = Depends(get_db)):
    await _drama_project(db, project_id)
    rows = (await db.scalars(select(DramaPropModel).where(
        DramaPropModel.project_id == project_id
    ))).all()
    return APIResponse(data=[_columns(row) for row in rows])


@router.post("/{project_id}/props", response_model=APIResponse[dict[str, Any]], status_code=201)
async def create_project_prop(
    project_id: str, payload: DramaResourceInput, db: AsyncSession = Depends(get_db)
):
    await _drama_project(db, project_id)
    row = DramaPropModel(
        id=f"prop_{uuid4().hex[:12]}", project_id=project_id,
        name=payload.name, description=payload.description,
        continuity_data=payload.continuity_data, approval_status=payload.approval_status,
    )
    db.add(row)
    await db.commit()
    return APIResponse(data=_columns(row))

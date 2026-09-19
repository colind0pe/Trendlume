from __future__ import annotations

import pytest

from src.core.exceptions import ValidationException
from src.domain.enums import CreativeAngle, ProductionMode
from src.domain.production_workflows import get_production_workflow
from src.schemas.product import ProductCreate
from src.schemas.project import ProjectCreate
from src.schemas.task import TaskCreate, TaskUpdate
from src.services.product_service import ProductService
from src.services.production_pipeline import ProductionPipelineRegistry
from src.services.project_service import ProjectService
from src.services.task_service import TaskService


def test_knowledge_workflow_is_ordered_and_commerce_is_registered():
    workflow = get_production_workflow(ProductionMode.KNOWLEDGE)

    assert workflow.stage_keys == (
        "topic",
        "research",
        "planning",
        "script",
        "storyboard",
        "assets",
        "voice",
        "subtitles",
        "composition",
        "export",
    )
    assert workflow.unit_stage_keys == frozenset({"assets", "voice", "composition"})
    assert ProductionPipelineRegistry().available_modes() == (
        ProductionMode.KNOWLEDGE,
        ProductionMode.COMMERCE,
        ProductionMode.DRAMA,
    )


@pytest.mark.asyncio
async def test_project_and_task_persist_knowledge_production_mode_by_default(test_session):
    project = await ProjectService(test_session).create_project(
        ProjectCreate(name="Production mode project")
    )
    task = await TaskService(test_session).create_task(
        project.id,
        TaskCreate(title="Knowledge task"),
    )

    assert project.primary_production_mode == ProductionMode.KNOWLEDGE.value
    assert task.production_mode == ProductionMode.KNOWLEDGE.value
    assert "production_mode" not in task.input_payload


@pytest.mark.asyncio
async def test_commerce_task_requires_and_persists_product_context(test_session):
    project = await ProjectService(test_session).create_project(
        ProjectCreate(name="Commerce mode project", primary_production_mode=ProductionMode.COMMERCE)
    )

    with pytest.raises(ValidationException, match="必须选择商品"):
        await TaskService(test_session).create_task(
            project.id,
            TaskCreate(title="Commerce task", production_mode=ProductionMode.COMMERCE),
        )

    from src.services.product_service import ProductService

    product = await ProductService(test_session).create_product(
        ProductCreate(title="可追溯商品", brand="Demo")
    )
    task = await TaskService(test_session).create_task(
        project.id,
        TaskCreate(
            title="Commerce task",
            production_mode=ProductionMode.COMMERCE,
            product_id=product.id,
            creative_angle=CreativeAngle.DEMO,
        ),
    )

    assert task.product_id == product.id
    assert task.creative_angle == CreativeAngle.DEMO.value
    assert not {"product_id", "creative_plan_id", "creative_angle"} & task.input_payload.keys()
    assert "knowledge_brief" not in task.input_payload
    assert "genre" not in task.input_payload
    assert "enable_research" not in task.input_payload
    assert "target_scene_count" not in task.input_payload


@pytest.mark.asyncio
async def test_task_can_override_project_mode_without_mutating_project(test_session):
    project = await ProjectService(test_session).create_project(
        ProjectCreate(name="Commerce project", primary_production_mode=ProductionMode.COMMERCE)
    )

    task = await TaskService(test_session).create_task(
        project.id,
        TaskCreate(title="Knowledge override", production_mode=ProductionMode.KNOWLEDGE),
    )

    assert project.primary_production_mode == ProductionMode.COMMERCE.value
    assert task.production_mode == ProductionMode.KNOWLEDGE.value
    assert "production_mode" not in task.input_payload
    assert task.input_payload["knowledge_brief"]["genre"] == "auto"


@pytest.mark.asyncio
async def test_generic_task_creation_cannot_bypass_drama_approval_workspace(test_session):
    project = await ProjectService(test_session).create_project(
        ProjectCreate(name="Drama project", primary_production_mode=ProductionMode.DRAMA)
    )

    with pytest.raises(ValidationException, match="Drama workspace"):
        await TaskService(test_session).create_task(project.id, TaskCreate(title="Invalid Drama task"))


@pytest.mark.asyncio
async def test_mode_update_removes_previous_mode_payload(test_session):
    project = await ProjectService(test_session).create_project(
        ProjectCreate(name="Mode update project")
    )
    task_service = TaskService(test_session)
    task = await task_service.create_task(
        project.id,
        TaskCreate(title="切换模式", knowledge_brief={"thesis": "知识主张"}),
    )
    product = await ProductService(test_session).create_product(
        ProductCreate(title="模式切换商品", brand="Demo")
    )

    updated = await task_service.update_task(
        task.id,
        TaskUpdate(
            production_mode=ProductionMode.COMMERCE,
            product_id=product.id,
            creative_angle=CreativeAngle.DEMO,
        ),
    )

    assert updated.production_mode == ProductionMode.COMMERCE.value
    assert not {"product_id", "creative_plan_id", "creative_angle"} & updated.input_payload.keys()
    assert "knowledge_brief" not in updated.input_payload
    assert "enable_research" not in updated.input_payload

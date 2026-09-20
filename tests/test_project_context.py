
import pytest

from src.core.exceptions import ValidationException
from src.domain.drama import ApprovalStatus, DramaSourceType
from src.domain.enums import ProductionMode
from src.models.drama import DramaEpisodeModel
from src.schemas.drama import DramaBibleCreate
from src.schemas.product import ProductCreate
from src.schemas.project import ProjectCreate, ProjectUpdate
from src.schemas.project_context import CommerceProfileInput, KnowledgeContentItemCreate
from src.schemas.task import TaskCreate, TaskUpdate
from src.services.drama_production_service import DramaProductionService
from src.services.product_service import ProductService
from src.services.project_context import create_knowledge_item, list_context_versions
from src.services.project_service import ProjectService
from src.services.task_service import TaskService


@pytest.mark.asyncio
async def test_context_versions_are_immutable_and_tasks_pin_the_latest(test_session):
    project = await ProjectService(test_session).create_project(
        ProjectCreate(name="Context project")
    )
    initial = await list_context_versions(test_session, project.id)
    assert initial == []

    item = await create_knowledge_item(
        test_session,
        project.id,
        KnowledgeContentItemCreate(topic="版本化主题", thesis="初始主张"),
    )
    versions = await list_context_versions(test_session, project.id)
    assert versions == []

    task = await TaskService(test_session).create_task(
        project.id,
        TaskCreate(title="固定上下文", knowledge_item_id=item.id),
    )
    versions = await list_context_versions(test_session, project.id)
    assert len(versions) == 1
    assert versions[0].context_payload["content_item"]["id"] == item.id
    assert task.project_context_version_id == versions[0].id
    assert task.context_hash == versions[0].context_hash
    assert task.input_payload["knowledge_brief"]["thesis"] == item.thesis
    assert task.production_mode == ProductionMode.KNOWLEDGE.value
    original_context_id = task.project_context_version_id
    original_context_hash = task.context_hash

    other_item = await create_knowledge_item(
        test_session,
        project.id,
        KnowledgeContentItemCreate(topic="无关主题", thesis="不会改写已有任务上下文"),
    )
    unchanged = await list_context_versions(test_session, project.id)
    assert len(unchanged) == 1
    assert unchanged[0].context_hash == original_context_hash

    rebound = await TaskService(test_session).update_task(
        task.id,
        TaskUpdate(knowledge_item_id=other_item.id),
    )
    assert rebound.input_payload["knowledge_brief"]["thesis"] == other_item.thesis
    assert rebound.context_hash != versions[0].context_hash

    await ProjectService(test_session).update_project(
        project.id,
        ProjectUpdate(description="临时项目说明"),
    )
    changed_task = await TaskService(test_session).create_task(
        project.id,
        TaskCreate(title="修改后的上下文", knowledge_item_id=item.id),
    )
    assert changed_task.context_hash != original_context_hash

    await ProjectService(test_session).update_project(
        project.id,
        ProjectUpdate(description=""),
    )
    restored_task = await TaskService(test_session).create_task(
        project.id,
        TaskCreate(title="恢复已有上下文", knowledge_item_id=item.id),
    )
    assert restored_task.project_context_version_id == original_context_id


@pytest.mark.asyncio
async def test_project_mode_is_immutable(test_session):
    project = await ProjectService(test_session).create_project(
        ProjectCreate(name="Mode project", primary_production_mode=ProductionMode.COMMERCE)
    )

    with pytest.raises(ValidationException, match="创建时确定"):
        await ProjectService(test_session).update_project(
            project.id,
            ProjectUpdate(primary_production_mode=ProductionMode.KNOWLEDGE),
        )


@pytest.mark.asyncio
async def test_commerce_profile_is_project_context(test_session):
    project = await ProjectService(test_session).create_project(
        ProjectCreate(
            name="Commerce context project",
            primary_production_mode=ProductionMode.COMMERCE,
            commerce_profile=CommerceProfileInput(brand="上下文品牌", default_cta="立即了解"),
        )
    )

    assert project.commerce_profile is not None
    assert project.commerce_profile.default_cta == "立即了解"

    product = await ProductService(test_session).create_product(
        ProductCreate(title="上下文商品", brand="上下文品牌")
    )
    task = await TaskService(test_session).create_task(
        project.id,
        TaskCreate(title="商品任务", product_id=product.id),
    )
    versions = await list_context_versions(test_session, project.id)
    assert versions[0].context_payload["profile"]["brand"] == "上下文品牌"
    assert versions[0].context_payload["product"]["id"] == product.id
    assert task.project_context_version_id == versions[0].id


@pytest.mark.asyncio
async def test_drama_task_requires_an_approved_project_episode(test_session):
    project = await ProjectService(test_session).create_project(
        ProjectCreate(name="Drama context project", primary_production_mode=ProductionMode.DRAMA)
    )
    bible = await DramaProductionService(test_session).create_bible(
        project.id,
        DramaBibleCreate(
            source_type=DramaSourceType.IDEA,
            title="待审批故事",
            source_text="一个人在雨夜等待答案。",
        ),
    )
    with pytest.raises(ValidationException, match="只能包含一个"):
        await DramaProductionService(test_session).create_bible(
            project.id,
            DramaBibleCreate(
                source_type=DramaSourceType.IDEA,
                title="重复故事",
                source_text="不应创建第二个 Bible。",
            ),
        )
    episode = DramaEpisodeModel(
        bible_id=bible.id,
        episode_number=1,
        title="第一集",
        approval_status=ApprovalStatus.DRAFT.value,
    )
    test_session.add(episode)
    await test_session.flush()

    with pytest.raises(ValidationException, match="审批通过"):
        await TaskService(test_session).create_task(
            project.id,
            TaskCreate(title="待审批任务", drama_episode_id=episode.id),
        )

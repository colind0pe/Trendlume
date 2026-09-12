import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.project import ProjectModel
from src.models.scene import SceneModel
from src.models.task import TaskModel
from src.repositories.project_repository import ProjectRepository
from src.repositories.scene_repository import SceneRepository
from src.repositories.task_repository import TaskRepository


@pytest.mark.asyncio
async def test_task_and_scenes_cascade(test_session: AsyncSession):
    proj_repo = ProjectRepository(test_session)
    task_repo = TaskRepository(test_session)
    scene_repo = SceneRepository(test_session)

    # Create project
    project = ProjectModel(
        id="proj_task_test",
        name="Task Test Project",
        settings={},
    )
    await proj_repo.create(project)

    # Create task
    task = TaskModel(
        id="task_cascade_test",
        project_id="proj_task_test",
        title="Episode 1: Science Video",
        description="A cool video",
        job_type="video_composition",
        status="pending",
        input_payload={},
    )
    await task_repo.create(task)

    # Create scenes under task
    scene1 = SceneModel(
        id="scene_1",
        task_id="task_cascade_test",
        sequence_index=0,
        narration_text="Intro",
        visual_prompt="Close up camera",
        duration_seconds=3.5,
        layout_params={},
    )
    scene2 = SceneModel(
        id="scene_2",
        task_id="task_cascade_test",
        sequence_index=1,
        narration_text="Outro",
        visual_prompt="Fade to black",
        duration_seconds=4.0,
        layout_params={},
    )
    await scene_repo.create(scene1)
    await scene_repo.create(scene2)

    # Fetch task with scenes
    task_with_scenes = await task_repo.get_with_scenes("task_cascade_test")
    assert task_with_scenes is not None
    assert len(task_with_scenes.scenes) == 2
    assert task_with_scenes.scenes[0].narration_text == "Intro"

    # Delete task
    await task_repo.delete_by_id("task_cascade_test")

    # Verify scenes cascaded
    scenes = await scene_repo.list_by_task_id("task_cascade_test")
    assert len(scenes) == 0

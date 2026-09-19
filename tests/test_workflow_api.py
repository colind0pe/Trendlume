import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient

from src.core.config import settings
from src.models.project import ProjectModel
from src.models.scene import SceneModel
from src.models.task import TaskModel
from src.models.workflow import (
    WorkflowArtifactModel,
    WorkflowJobModel,
    WorkflowStepArtifactModel,
    WorkflowStepRunModel,
)


async def _create_artifact_fixture(test_session, storage: Path):
    storage.mkdir(parents=True, exist_ok=True)
    project = ProjectModel(id=f"project_{uuid4().hex}", name="Workflow API")
    task = TaskModel(
        id=f"task_{uuid4().hex}",
        project_id=project.id,
        title="Artifact verification",
        input_payload={},
    )
    job = WorkflowJobModel(
        id=f"job_{uuid4().hex}",
        task_id=task.id,
        job_type="full_pipeline",
        status="completed",
        current_stage="export",
        progress=100,
    )
    run = WorkflowStepRunModel(
        id=f"run_{uuid4().hex}",
        task_id=task.id,
        job_id=job.id,
        step_key="export",
        unit_key="",
        attempt=1,
        input_fingerprint="0" * 64,
        input_payload={},
        output_payload={},
        status="completed",
        started_at=datetime.now(UTC).replace(tzinfo=None),
        completed_at=datetime.now(UTC).replace(tzinfo=None),
        duration_ms=1,
    )
    source = Path(__file__).parent / "fixtures" / "mock.mp4"
    relative = f"workflow/{task.id}/{run.id}/output.mp4"
    target = storage / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    content = target.read_bytes()
    artifact = WorkflowArtifactModel(
        id=f"artifact_{uuid4().hex}",
        task_id=task.id,
        step_run_id=run.id,
        kind="final_video",
        relative_path=relative,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        media_info={"video_duration": 0.5},
        source="generated",
    )
    test_session.add_all([project, task, job, run, artifact])
    await test_session.flush()
    test_session.add(WorkflowStepArtifactModel(step_run_id=run.id, artifact_id=artifact.id, role="output"))
    await test_session.commit()
    return task, job, run, artifact, target


@pytest.mark.asyncio
async def test_workflow_queries_retry_and_download_validation(
    client: AsyncClient, test_session, tmp_path, monkeypatch
):
    storage = tmp_path / "storage"
    monkeypatch.setattr(settings, "storage_dir", storage)
    task, job, run, artifact, target = await _create_artifact_fixture(test_session, storage)

    snapshot = await client.get(f"/api/v1/tasks/{task.id}/workflow")
    assert snapshot.status_code == 200
    export = next(stage for stage in snapshot.json()["data"]["stages"] if stage["step_key"] == "export")
    assert export["label"] == "导出"
    assert export["status"] == "completed"
    assert export["validity"] == "valid"
    assert export["units"][0]["artifacts"][0]["id"] == artifact.id

    steps = await client.get(f"/api/v1/jobs/{job.id}/steps")
    assert steps.status_code == 200
    assert steps.json()["data"][0]["id"] == run.id

    invalid_stage = await client.post(f"/api/v1/tasks/{task.id}/steps/not-a-stage/retry")
    assert invalid_stage.status_code == 422

    other_project = ProjectModel(id=f"project_{uuid4().hex}", name="Other")
    other_task = TaskModel(id=f"task_{uuid4().hex}", project_id=other_project.id, title="Other")
    other_scene = SceneModel(id=f"scene_{uuid4().hex}", task_id=other_task.id)
    test_session.add_all([other_project, other_task, other_scene])
    await test_session.commit()
    cross_task_unit = await client.post(
        f"/api/v1/tasks/{task.id}/steps/assets/retry",
        json={"unit_key": other_scene.id},
    )
    assert cross_task_unit.status_code == 422

    valid = await client.get(f"/api/v1/artifacts/{artifact.id}/download", params={"task_id": task.id})
    assert valid.status_code == 200
    assert valid.content == target.read_bytes()

    wrong_task = await client.get(
        f"/api/v1/artifacts/{artifact.id}/download",
        params={"task_id": other_task.id},
    )
    assert wrong_task.status_code == 404

    original = target.read_bytes()
    target.write_bytes(bytes([original[0] ^ 0xFF]) + original[1:])
    same_size = await client.get(f"/api/v1/artifacts/{artifact.id}/download")
    assert same_size.status_code == 409

    artifact.relative_path = "../outside.mp4"
    await test_session.commit()
    traversal = await client.get(f"/api/v1/artifacts/{artifact.id}/download")
    assert traversal.status_code == 409

    other_job = WorkflowJobModel(
        id=f"job_{uuid4().hex}", task_id=other_task.id, job_type="full_pipeline", status="completed"
    )
    foreign_run = WorkflowStepRunModel(
        id=f"run_{uuid4().hex}", task_id=other_task.id, job_id=other_job.id,
        step_key="export", unit_key="", attempt=1, input_fingerprint="1" * 64,
        input_payload={}, status="completed", started_at=datetime.now(UTC).replace(tzinfo=None),
    )
    test_session.add_all([other_job, foreign_run])
    await test_session.commit()
    artifact.step_run_id = foreign_run.id
    await test_session.commit()
    producer_mismatch = await client.get(f"/api/v1/artifacts/{artifact.id}/download")
    assert producer_mismatch.status_code == 409

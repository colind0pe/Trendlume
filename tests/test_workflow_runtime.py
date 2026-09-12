from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from src.core.exceptions import ValidationException
from src.models import ProjectModel, TaskModel
from src.models.workflow import (
    WorkflowJobModel,
    WorkflowStepArtifactModel,
    WorkflowStepRunModel,
)
from src.services.workflow_runtime import (
    ArtifactSpec,
    LeaseLostError,
    WorkflowRuntime,
    fingerprint,
    safe_artifact_path,
    validate_artifact,
)


async def runtime(db, tmp_path):
    project = ProjectModel(id=str(uuid4()), name='runtime test')
    db.add(project)
    await db.flush()
    task = TaskModel(id=str(uuid4()), project_id=project.id)
    db.add(task)
    await db.flush()
    job = WorkflowJobModel(id=str(uuid4()), task_id=task.id, job_type='video_composition', status='running', lease_token=str(uuid4()))
    db.add(job)
    await db.commit()
    return WorkflowRuntime(db, tmp_path, job.id, job.lease_token), job


@pytest.mark.asyncio
async def test_verified_reuse_detects_same_size_corruption(test_session, tmp_path):
    rt, _ = await runtime(test_session, tmp_path)
    run = await rt.begin('topic', {'topic': 'test'})
    path = await rt.write_json(run, 'topic.json', {'value': 'aaa'})
    artifacts = await rt.complete(run, [ArtifactSpec(path, 'topic')], output_payload={'answer': 1})
    second = await rt.begin('topic', {'topic': 'test'})
    assert second.status == 'reused'
    assert second.output_payload == {'answer': 1}
    path.write_bytes(path.read_bytes().replace(b'aaa', b'bbb'))
    assert (await validate_artifact(tmp_path, artifacts[0]))[0] is False
    third = await rt.begin('topic', {'topic': 'test'})
    assert third.status == 'running' and third.attempt == 3
    assert run.validity == 'corrupt'


@pytest.mark.asyncio
async def test_dependency_and_skip_reuse(test_session, tmp_path):
    rt, _ = await runtime(test_session, tmp_path)
    run = await rt.begin('topic', {'value': 1})
    path = await rt.write_json(run, 'input.json', {'value': 1})
    artifacts = await rt.complete(run, [ArtifactSpec(path, 'input')])
    research = await rt.begin('research', {'enabled': False}, input_artifacts=artifacts)
    await rt.complete(research, [], skipped=True)
    research = await rt.begin('research', {'enabled': False}, input_artifacts=artifacts)
    assert research.status == 'reused'
    roles = (await test_session.scalars(select(WorkflowStepArtifactModel.role).where(WorkflowStepArtifactModel.step_run_id == research.id))).all()
    assert roles == ['input']


@pytest.mark.asyncio
async def test_marked_stale_run_is_not_reused(test_session, tmp_path):
    rt, _ = await runtime(test_session, tmp_path)
    run = await rt.begin('topic', {'topic': 'stale input'})
    path = await rt.write_json(run, 'topic.json', {'topic': 'stale input'})
    await rt.complete(run, [ArtifactSpec(path, 'topic')])
    run.validity = 'stale'
    run.invalid_reason = '任务输入已修改'
    await test_session.commit()

    replacement = await rt.begin('topic', {'topic': 'stale input'})
    assert replacement.status == 'running'
    assert replacement.attempt == 2


@pytest.mark.asyncio
async def test_lost_lease_rejects_completion_and_pending_mutation(test_session, tmp_path):
    rt, job = await runtime(test_session, tmp_path)
    run = await rt.begin('topic', {})
    path = await rt.write_json(run, 'topic.json', {'ok': True})
    await test_session.execute(update(WorkflowJobModel).where(WorkflowJobModel.id == job.id).values(lease_token='replacement'))
    await test_session.commit()
    task = await test_session.get(TaskModel, job.task_id)
    task.title = 'stale worker title'
    with pytest.raises(LeaseLostError):
        await rt.complete(run, [ArtifactSpec(path, 'topic')])
    await test_session.refresh(task)
    assert task.title != 'stale worker title'
    await test_session.refresh(run)
    assert run.status == 'running'


@pytest.mark.asyncio
async def test_unique_attempt_constraint(test_session, tmp_path):
    rt, job = await runtime(test_session, tmp_path)
    run = await rt.begin('topic', {})
    duplicate = WorkflowStepRunModel(id=str(uuid4()), task_id=run.task_id, job_id=job.id, step_key='topic', unit_key='', attempt=1, input_fingerprint='x')
    test_session.add(duplicate)
    with pytest.raises(IntegrityError):
        await test_session.commit()
    await test_session.rollback()


def test_fingerprint_redaction_and_path_boundary(tmp_path):
    assert fingerprint({'b': 2, 'a': 1, 'api_key': 'secret'}) == fingerprint({'a': 1, 'b': 2})
    with pytest.raises(ValueError):
        safe_artifact_path(tmp_path, '../escape')


@pytest.mark.asyncio
async def test_invalid_media_not_completed(test_session, tmp_path):
    rt, _ = await runtime(test_session, tmp_path)
    run = await rt.begin('voice', {})
    path = rt.attempt_dir(run) / 'bad.wav'
    path.write_bytes(b'not wave')
    with pytest.raises(ValidationException):
        await rt.complete(run, [ArtifactSpec(path, 'audio')])
    assert run.status == 'running'

@pytest.mark.asyncio
async def test_foreign_key_restricts_referenced_asset(test_session, tmp_path):
    from sqlalchemy import delete, text
    from src.models.asset import AssetModel
    await test_session.commit()
    await test_session.execute(text('PRAGMA foreign_keys=ON'))
    rt, job = await runtime(test_session, tmp_path)
    task = await test_session.get(TaskModel, job.task_id)
    source = tmp_path / 'source.txt'
    source.write_text('durable asset')
    asset = AssetModel(id=str(uuid4()), project_id=task.project_id, asset_type='text', file_name=source.name, file_path=source.name, mime_type='text/plain')
    test_session.add(asset)
    await test_session.commit()
    asset_id = asset.id
    run = await rt.begin('assets', {})
    artifacts = await rt.complete(run, [ArtifactSpec(source, 'text', asset_id=asset_id)])
    assert asset.file_path == artifacts[0].relative_path
    with pytest.raises(IntegrityError):
        await test_session.execute(delete(AssetModel).where(AssetModel.id == asset_id))
        await test_session.commit()
    await test_session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize('owner', ['task', 'project'])
async def test_owner_delete_cascades_reused_artifact_history(test_session, tmp_path, owner):
    from sqlalchemy import delete, text
    from src.models.workflow import WorkflowArtifactModel
    await test_session.commit()
    await test_session.execute(text('PRAGMA foreign_keys=ON'))
    rt, job = await runtime(test_session, tmp_path)
    task = await test_session.get(TaskModel, job.task_id)
    task_id, project_id = task.id, task.project_id
    run = await rt.begin('topic', {'topic': 'delete test'})
    path = await rt.write_json(run, 'topic.json', {'topic': 'delete test'})
    await rt.complete(run, [ArtifactSpec(path, 'topic')])
    await rt.begin('topic', {'topic': 'delete test'})
    model, record_id = (TaskModel, task_id) if owner == 'task' else (ProjectModel, project_id)
    await test_session.execute(delete(model).where(model.id == record_id))
    await test_session.commit()
    assert not (await test_session.scalars(select(WorkflowStepRunModel))).all()
    assert not (await test_session.scalars(select(WorkflowArtifactModel))).all()

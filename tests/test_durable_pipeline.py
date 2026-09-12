import json
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from src.models import ProjectModel, SceneModel, TaskModel
from src.models.workflow import WorkflowArtifactModel, WorkflowStepRunModel
from src.services.durable_pipeline import subtitle_documents
from src.services.rendering_service import RenderingService
from src.storage.local_storage import LocalStorageService
from src.tasks.executor import VideoWorkflowExecutor
from src.tasks.job import Job


def test_subtitle_time_and_escaping():
    srt, ass = subtitle_documents([{'text': '{hello}\nworld', 'start': 61.25, 'end': 63.5}])
    assert '00:01:01,250 --> 00:01:03,500' in srt
    assert r'\{hello\}\Nworld' in ass
    assert '0:01:01.25,0:01:03.50' in ass


@pytest.mark.asyncio
async def test_pipeline_real_media_reuse_corruption_and_manifest(test_session, tmp_path, monkeypatch):
    # A valid fixture keeps this test focused on durable reuse and invalidation.
    media = Path(__file__).parent / 'fixtures' / 'mock.mp4'
    storage = LocalStorageService(tmp_path / 'storage')
    project = ProjectModel(id=str(uuid4()), name='pipeline')
    test_session.add(project)
    await test_session.flush()
    task = TaskModel(id=str(uuid4()), project_id=project.id, title='Fixed',
        input_payload={'topic': 'Fixed', 'enable_research': False, 'content_mode': 'static', 'template_id': 'static_default'})
    test_session.add(task)
    await test_session.flush()
    scene = SceneModel(id=str(uuid4()), task_id=task.id, narration_text='', duration_seconds=.4)
    test_session.add(scene)
    await test_session.commit()
    calls = []
    async def render_frame(*args, output_path, **kwargs):
        output_path.write_bytes(b'frame')
    monkeypatch.setattr('src.services.rendering_service.TemplateRenderer.render', render_frame)
    async def render(cmd, output):
        calls.append(cmd)
        output.write_bytes(media.read_bytes())
        return True
    @asynccontextmanager
    async def sessions():
        yield test_session
    executor = VideoWorkflowExecutor(sessions, lambda db: RenderingService(db, storage, ffmpeg_runner=render))
    first = await executor.execute(Job(task_id=task.id))
    assert first['total_duration_seconds'] > 0
    assert len(calls) == 2
    runs = (await test_session.scalars(select(WorkflowStepRunModel))).all()
    assert {r.step_key for r in runs} == {'topic','research','planning','script','storyboard','assets','voice','subtitles','composition','export'}
    final_composition_runs = [r for r in runs if r.step_key == 'composition' and r.unit_key == '']
    assert final_composition_runs[-1].input_payload['composition_format_version'] == RenderingService.COMPOSITION_FORMAT_VERSION
    manifest_artifact = await test_session.get(WorkflowArtifactModel, first['render_manifest_artifact_id'])
    manifest = json.loads(storage.get_path(manifest_artifact.relative_path).read_text(encoding='utf-8'))
    assert manifest['timeline'][0]['duration_source'] == 'scene_duration'
    assert manifest['final_video']['media_info']['video_duration'] > 0
    await executor.execute(Job(task_id=task.id))
    assert len(calls) == 2
    # A changed composition format must invalidate the final stage while
    # retaining reusable scene artifacts.
    monkeypatch.setattr(RenderingService, 'COMPOSITION_FORMAT_VERSION', 'test-next')
    await executor.execute(Job(task_id=task.id))
    assert len(calls) == 3
    runs = (await test_session.scalars(select(WorkflowStepRunModel))).all()
    final_composition_runs = [r for r in runs if r.step_key == 'composition' and r.unit_key == '']
    assert final_composition_runs[-1].input_payload['composition_format_version'] == 'test-next'
    # Task-level composition forces only the final mux; valid scene clips are
    # reused instead of being rendered again.
    await executor.execute(Job(
        task_id=task.id,
        params={'single_step': 'composition', 'force_step': 'composition'},
    ))
    assert len(calls) == 4
    # Only the damaged subtitles and fresh export run again, with no video rendering.
    subtitle = await test_session.get(WorkflowArtifactModel, first['subtitle_artifact_ids'][0])
    storage.get_path(subtitle.relative_path).write_bytes(b'corrupted')
    await executor.execute(Job(task_id=task.id))
    assert len(calls) == 4
    await test_session.refresh(subtitle)
    runs = (await test_session.scalars(select(WorkflowStepRunModel).where(WorkflowStepRunModel.step_key == 'subtitles').order_by(WorkflowStepRunModel.attempt))).all()
    assert runs[-1].status == 'completed'
    # A layout edit rerenders only the affected scene and final composition.
    scene.layout_params = {'template_params': {'accent': '#ff0000'}}
    await test_session.commit()
    await executor.execute(Job(task_id=task.id))
    assert len(calls) == 6

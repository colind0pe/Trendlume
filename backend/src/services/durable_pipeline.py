"""Dependency-aware production execution with verified, immutable stage outputs."""
from __future__ import annotations

import asyncio
import hashlib
import json
from uuid import uuid4

from loguru import logger
from sqlalchemy import select

from src.core.exceptions import ValidationException
from src.domain.content_modes import resolve_content_mode
from src.domain.enums import ProductionMode
from src.domain.production_recipes import MediaPlan, MediaStrategy
from src.domain.production_workflows import KNOWLEDGE_PRODUCTION_WORKFLOW
from src.models.asset import AssetModel
from src.models.production_context import ProductionContextSnapshotModel
from src.models.scene import SceneModel
from src.models.workflow import WorkflowJobModel, WorkflowStepRunModel
from src.repositories.project_repository import ProjectRepository
from src.repositories.scene_repository import SceneRepository
from src.repositories.task_repository import TaskRepository
from src.schemas.generation import ResearchResponse, ScriptGenerateRequest, StructuredScript
from src.services.generation_service import PROMPT_CALL_BUDGETS, GenerationService
from src.services.material_service import MaterialService
from src.services.production_pipeline import BaseProductionPipeline
from src.services.prompt_registry import prompt_selection_snapshot, prompt_version_map
from src.services.provider_manager import ProviderManager
from src.services.rendering_service import RenderingService
from src.services.template_catalog import template_catalog
from src.services.workflow_execution import (
    WorkflowExecutionContext,
    assert_task_editable,
)
from src.services.workflow_runtime import (
    ArtifactSpec,
    WorkflowRuntime,
    probe_file,
    redact,
    sha256_file,
)
from src.services.workflow_service import workflow_service
from src.tasks.broadcaster import event_broadcaster


def build_script_generation_inputs(payload: dict, *, topic: str, project=None) -> dict:
    """Return every task/project field that can change script output."""
    project_settings = dict(getattr(project, 'settings', None) or {})
    knowledge_brief = payload.get('knowledge_brief')
    if knowledge_brief is None:
        knowledge_brief = project_settings.get('knowledge_brief')
    if knowledge_brief is None and str(getattr(project, 'description', '') or '').strip():
        knowledge_brief = {'thesis': str(project.description).strip()}
    aspect_ratio = payload.get('aspect_ratio') or getattr(project, 'aspect_ratio', None) or '9:16'
    language = payload.get('language') or project_settings.get('language')
    keys = (
        'mode', 'raw_script', 'split_mode', 'genre', 'hook_type', 'style_preset',
        'prompt_prefix', 'target_scene_count', 'content_mode',
    )
    result = {key: payload.get(key) for key in keys}
    result.update(
        topic=topic,
        knowledge_brief=knowledge_brief,
        research_sources=(payload.get('research') or {}).get('sources') or [],
        aspect_ratio=aspect_ratio,
        language=language,
        knowledge_brief_hash=(
            hashlib.sha256(
                json.dumps(knowledge_brief, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
            if knowledge_brief is not None
            else None
        ),
        prompt_call_budgets=PROMPT_CALL_BUDGETS,
        prompt_versions=prompt_version_map(payload.get("prompt_versions")),
        prompt_selection=prompt_selection_snapshot(payload.get("prompt_versions")),
    )
    return result


def _research_source_ids(payload: dict) -> list[str]:
    sources = ((payload.get("research") or {}).get("sources") or [])
    result = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        value = f"{source.get('url') or ''}|{source.get('title') or ''}"
        result.append(hashlib.sha256(value.encode()).hexdigest())
    return result


def scene_snapshot(scene):
    return {"id": scene.id, "sequence_index": scene.sequence_index,
        "narration_text": scene.narration_text, "visual_prompt": scene.visual_prompt,
        "visual_role": getattr(scene, "visual_role", "concept"),
        "claim_refs": list(getattr(scene, "claim_refs", None) or []),
        "source_refs": list(getattr(scene, "source_refs", None) or []),
        "production_metadata": dict(getattr(scene, "production_metadata", None) or {}),
        "layout_params": {k: v for k, v in (scene.layout_params or {}).items()
            if not k.endswith(("_status", "_error", "_duration_seconds")) and k not in {"duration_source", "tts_provider"}}}


def subtitle_documents(timeline):
    srt, dialogues = [], []
    for i, item in enumerate(timeline):
        text = item['text'].replace('\r\n', '\n').replace('\r', '\n')
        srt.append(f"{i+1}\n{RenderingService._srt_timestamp(item['start'])} --> {RenderingService._srt_timestamp(item['end'])}\n{text}\n")
        safe = text.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}').replace('\n', r'\N')
        dialogues.append(f"Dialogue: 0,{RenderingService._ass_timestamp(item['start'])},{RenderingService._ass_timestamp(item['end'])},Default,,0,0,0,,{safe}")
    header = RenderingService._ass_subtitle('', 0).split('Dialogue:')[0]
    return '\n'.join(srt), header + '\n'.join(dialogues) + '\n'


class DurableProductionPipeline(BaseProductionPipeline):
    production_mode = ProductionMode.KNOWLEDGE
    workflow = KNOWLEDGE_PRODUCTION_WORKFLOW
    retry_delays = (30, 120, 300)

    def __init__(self, session, job, rendering_service_factory=None):
        self.db, self.job = session, job
        self.rendering_factory = rendering_service_factory
        self.params = job.params or {}

    async def prepare_mode_pipeline(
        self,
        task,
        project,
        payload,
        generator,
        provider_inputs,
        prompt_selection,
        single,
    ):
        """Mode extension point before the shared media stages.

        Knowledge needs no projection. Commerce overrides this hook to build
        product facts and its reviewed storyboard without teaching the shared
        durable pipeline about Commerce stage names.
        """
        del task, project, generator, provider_inputs, prompt_selection
        return payload, single, False

    async def save(self):
        await self.runtime.assert_lease()
        await self.db.commit()

    async def emit(self, event, run):
        await self.runtime.assert_lease()
        db_job = await self.db.get(WorkflowJobModel, self.job.id)
        db_job.current_stage = run.step_key
        db_job.progress = self.workflow.progress_for(run.step_key, running=run.status == 'running')
        db_job.checkpoint = {'stage': run.step_key, 'step_run_id': run.id, 'unit_key': run.unit_key}
        await self.db.commit()
        artifacts = await self.runtime.outputs(run)
        await event_broadcaster.broadcast(event, {'task_id': self.job.task_id, 'job_id': self.job.id,
            'stage': run.step_key, 'step_run_id': run.id, 'unit_key': run.unit_key,
            'attempt': run.attempt, 'status': run.status, 'progress': db_job.progress,
            'artifact_ids': [a.id for a in artifacts]},
            task_id=self.job.task_id, job_id=self.job.id, lease_token=self.runtime.lease_token)
        if event == 'step.completed' and run.unit_key:
            await event_broadcaster.broadcast('scene.status_changed', {
                'task_id': self.job.task_id, 'job_id': self.job.id, 'scene_id': run.unit_key,
                'unit_key': run.unit_key, 'stage': run.step_key, 'status': run.status,
                'progress': db_job.progress,
            }, task_id=self.job.task_id, job_id=self.job.id, lease_token=self.runtime.lease_token)
        if event == 'step.completed':
            for artifact in artifacts:
                if artifact.asset_id:
                    await event_broadcaster.broadcast('asset.created', {
                        'task_id': self.job.task_id, 'job_id': self.job.id, 'stage': run.step_key,
                        'step_run_id': run.id, 'artifact_id': artifact.id, 'asset_id': artifact.asset_id,
                        'kind': artifact.kind, 'source': artifact.source,
                    }, task_id=self.job.task_id, job_id=self.job.id, lease_token=self.runtime.lease_token)

    async def stage(self, key, inputs, action, unit='', dependencies=None, force=False):
        requested = self.params.get('force_step') or self.params.get('retry_step') or self.params.get('step_key')
        requested_unit = self.params.get('force_unit') or self.params.get('unit_key') or self.params.get('retry_unit')
        requested_force = requested == key and (not requested_unit or requested_unit == unit)
        # The task-level compose endpoint forces the final composition stage.
        # Scene clips are independent durable artifacts and should be reused
        # when their inputs remain valid; single-scene retries still use the
        # explicit force_unit path above.
        if self.params.get('single_step') == 'composition' and key == 'composition' and unit:
            requested_force = False
        force = force or requested_force
        for retry in range(4):
            run = await self.runtime.begin(key, inputs, unit, dependencies, force=force)
            if run.status != 'reused':
                await self.emit('step.started', run)
                run_id = run.id
                try:
                    specs, payload, warning, skipped = await action(run)
                    await self.runtime.complete(run, specs, warning=warning, skipped=skipped, output_payload=payload)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    await self.db.rollback()
                    # Rollback expires every dirty ORM object. Do not refresh
                    # the whole identity map: it may contain deleted or
                    # partially-loaded objects and can raise MissingGreenlet.
                    # Scene/task actions resolve their current row by ID before
                    # retrying; the run itself is the only object needed here.
                    run = await self.db.get(WorkflowStepRunModel, run_id)
                    await self.runtime.fail(run, exc)
                    await self.emit('step.failed', run)
                    # Validation and damaged user inputs cannot heal through retry.
                    if (isinstance(exc, (ValidationException, ValueError, FileNotFoundError)) and exc.__cause__ is None) or retry == 3:
                        raise
                    await asyncio.sleep(self.retry_delays[retry])
                    continue
            artifacts = await self.runtime.outputs(run)
            await self.emit('step.completed', run)
            return run, artifacts
        raise RuntimeError('Retry budget exhausted')

    async def json_stage(self, key, inputs, payload, *, unit='', dependencies=None, source='generated', skipped=False):
        async def action(run):
            path = await self.runtime.write_json(run, key + '.json', payload)
            return [ArtifactSpec(path, key, source=source)], payload, None, skipped
        return await self.stage(key, inputs, action, unit, dependencies)

    async def asset(self, asset_id):
        asset = await self.db.get(AssetModel, asset_id) if asset_id else None
        if not asset:
            raise ValidationException('前置素材不存在，请修复或重新上传。')
        path = self.storage.get_path(asset.file_path)
        await self.runtime.assert_lease()
        await self.db.commit()
        await probe_file(path)
        return asset, await sha256_file(path)

    async def bind(self, scene, field, artifacts):
        if artifacts:
            artifact = artifacts[0]
            if artifact.asset_id:
                await self.runtime.assert_lease()
                setattr(scene, field, artifact.asset_id)
                asset = await self.db.get(AssetModel, artifact.asset_id)
                # Consume the exact immutable copy whose hash was verified.
                if artifact.source == 'generated':
                    asset.file_path = artifact.relative_path
                else:
                    _, digest = await self.asset(artifact.asset_id)
                    if digest != artifact.sha256:
                        raise ValidationException('用户素材已改变，请重新登记或上传。')
                if field == 'audio_asset_id' and artifact.media_info:
                    scene.duration_seconds = artifact.media_info.get('audio_duration') or artifact.media_info.get('duration_seconds') or scene.duration_seconds
                await self.save()

    async def finish_partial(self, task_id, result):
        """Close a single-stage job without claiming that the film is done."""
        await self.runtime.assert_lease()
        task = await TaskRepository(self.db).get_by_id(task_id)
        if not task:
            raise ValidationException('任务不存在')
        task.production_status = 'needs_review'
        await self.db.commit()
        return result

    async def execute(self):
        job_id, task_id = self.job.id, self.job.task_id
        db_job = await self.db.get(WorkflowJobModel, self.job.id)
        if db_job is None:
            # Direct callers still receive durable records; no unverified alternate executor.
            await assert_task_editable(self.db, self.job.task_id)
            token = str(uuid4())
            self.job.lease_token = token
            self.owns_job = True
            db_job = WorkflowJobModel(id=self.job.id, task_id=self.job.task_id, job_type=self.job.job_type,
                status='running', lease_token=token, params=self.params)
            self.db.add(db_job)
            await self.db.commit()
        token = getattr(self.job, 'lease_token', None)
        if not token or token != db_job.lease_token:
            raise ValidationException('任务缺少有效执行租约。')
        self.context = WorkflowExecutionContext(self.job.id, token)
        renderer = self.rendering_factory(self.db) if self.rendering_factory else RenderingService(self.db, execution_context=self.context, durable=True)
        renderer.execution_context, renderer.durable = self.context, True
        renderer.asset_service.execution_context = self.context
        self.storage = renderer.storage
        self.runtime = WorkflowRuntime(
            self.db, self.storage.base_dir, self.job.id, token, self.workflow
        )
        await self.runtime.assert_lease()
        task = await TaskRepository(self.db).get_by_id(self.job.task_id)
        if not task:
            raise ValidationException('任务不存在')
        project = await ProjectRepository(self.db).get_by_id(task.project_id)
        task.production_status = 'running'
        await self.save()
        await event_broadcaster.broadcast('task.started', {'task_id': task.id, 'job_id': self.job.id, 'status': 'running', 'progress': 0}, task_id=task.id, job_id=self.job.id, lease_token=token)
        snapshot = await self.db.get(
            ProductionContextSnapshotModel, db_job.production_context_snapshot_id
        )
        if snapshot is None:
            raise ValidationException('WorkflowJob 缺少生产上下文快照。')
        snapshot_task = dict(snapshot.context_payload.get('task') or {})
        production_plan = dict(snapshot.context_payload.get('production_plan') or {})
        payload = dict(snapshot_task.get('generation_settings') or {})
        payload.update(snapshot_task.get('detail') or {})
        renderer.production_settings = payload
        pm = ProviderManager(self.db)
        provider_snapshot = snapshot.context_payload.get('providers') or {}
        pm = ProviderManager(self.db, snapshot=provider_snapshot)
        await pm.capture_snapshot(
            search_provider_id=payload.get('search_provider_id'),
            material_provider_id=payload.get('material_provider_id'),
        )
        provider_inputs = pm.snapshot_fingerprint_payload()
        prompt_selection = prompt_selection_snapshot(payload.get("prompt_versions"))
        payload["prompt_versions"] = {
            prompt_id: item["prompt_version"]
            for prompt_id, item in prompt_selection.items()
        }
        payload["prompt_selection"] = prompt_selection
        gen = GenerationService(
            self.db,
            storage=self.storage,
            provider_manager=pm,
            execution_context=self.context,
            task_id=task_id,
            job_id=job_id,
            production_settings=payload,
        )
        topic = str(payload.get('topic') or task.title or '短视频创作')
        single = self.params.get('single_step')
        if single == 'compose':
            single = 'composition'
        if single not in {None, 'assets', 'voice', 'script', 'research', 'composition'}:
            raise ValidationException('不支持的单步生产阶段。')
        render_only = bool(self.params.get('rerender')) or single == 'composition'
        if single in {'assets', 'voice'}:
            render_only = True
        if single == 'assets' and self.params.get('media_kind'):
            payload['content_mode'] = 'generated_' + self.params['media_kind']
        if single == 'assets' and self.params.get('content_mode_override'):
            payload['content_mode'] = self.params['content_mode_override']
        template_id = payload.get('template_id') or 'image_gallery_matted'
        template_item = template_catalog.get(template_id)
        mode = resolve_content_mode(
            payload.get('content_mode'),
            template_type=(template_item or {}).get('template_type'),
        )
        if payload.get('content_mode') != mode:
            payload['content_mode'] = mode
        payload, single, mode_prepared = await self.prepare_mode_pipeline(
            task,
            project,
            payload,
            gen,
            provider_inputs,
            prompt_selection,
            single,
        )
        if snapshot.mode == ProductionMode.DRAMA.value:
            mode_prepared = True
            drama_profile = snapshot.context_payload.get('project_profile') or {}
            shots = list(drama_profile.get('shots') or [])
            dialogue = list(drama_profile.get('dialogue') or [])
            existing = {
                scene.id: scene for scene in await SceneRepository(self.db).list_by_task_id(task_id)
            }
            for index, shot in enumerate(shots):
                shot_id = str(shot['id'])
                lines = sorted(
                    (item for item in dialogue if item.get('shot_id') == shot_id),
                    key=lambda item: item.get('sequence_index', 0),
                )
                narration = '\n'.join(
                    f"{item.get('speaker_name')}: {item.get('text')}" for item in lines
                ) or str(shot.get('action') or '')
                values = {
                    'sequence_index': index,
                    'narration_text': narration,
                    'visual_prompt': str(shot.get('visual_prompt') or shot.get('action') or ''),
                    'duration_seconds': float(shot.get('duration_hint') or 4),
                    'visual_role': 'concept',
                    'production_metadata': {
                        'drama_shot_id': shot_id,
                        'camera': shot.get('camera'),
                        'framing': shot.get('framing'),
                        'movement': shot.get('movement'),
                        'dialogue': lines,
                    },
                }
                if shot_id in existing:
                    for key, value in values.items():
                        setattr(existing[shot_id], key, value)
                else:
                    self.db.add(SceneModel(
                        id=shot_id,
                        task_id=task_id,
                        layout_params={'input_source': 'drama_snapshot'},
                        claim_refs=[],
                        source_refs=[],
                        **values,
                    ))
            await self.save()
        task = await TaskRepository(self.db).get_by_id(task_id)
        scenes = await SceneRepository(self.db).list_by_task_id(task.id)
        prior_script = await self.db.scalar(select(WorkflowStepRunModel).where(WorkflowStepRunModel.task_id == task.id, WorkflowStepRunModel.step_key == 'script').limit(1))
        has_storyboard = bool(scenes)
        manual_marker = bool(payload.get('manual_storyboard_version'))
        if manual_marker and not has_storyboard:
            # A manual marker without scenes can be left behind when a user
            # clears a storyboard or an earlier replacement is interrupted.
            # An empty storyboard is not an authoritative user input: allow a
            # normal retry to regenerate it instead of reusing an empty step.
            logger.warning(
                'Manual storyboard marker found without scenes for task {}; '
                'rebuilding storyboard from script',
                task_id,
            )
        manual = manual_marker and has_storyboard
        adopted_script = (
            has_storyboard
            and bool(prior_script and (prior_script.output_payload or {}).get('adopted'))
        )
        if single == 'research':
            research_inputs = {k: payload.get(k) for k in ('enable_research', 'search_provider_id', 'research_max_queries', 'research_max_results')}
            research_inputs['prompt_selection'] = prompt_selection
            research_inputs['research_source_ids'] = _research_source_ids(payload)
            research_inputs['prompt_call_budgets'] = {
                'research_query': PROMPT_CALL_BUDGETS['research_query']
            }
            research_inputs['llm_structured_mode'] = False
            research_inputs.update(topic=topic, provider=provider_inputs.get('search'), planner=provider_inputs.get('llm'))

            async def research_action(run):
                result = await gen.research_task(task_id, force=True)
                data = result.model_dump()
                path = await self.runtime.write_json(run, 'research.json', data)
                return [ArtifactSpec(path, 'research')], data, result.error_message if result.status == 'failed' else None, result.status == 'skipped'

            self.runtime_stage = 'research'
            research_run, _ = await self.stage('research', research_inputs, research_action, force=True)
            return await self.finish_partial(task_id, ResearchResponse.model_validate(research_run.output_payload).model_dump())

        if single == 'script':
            manual_script = self.params.get('script')
            if not isinstance(manual_script, dict):
                raise ValidationException('脚本单步生产缺少有效脚本内容。')
            script_inputs = {'manual_script': manual_script}

            async def script_action(run):
                data = StructuredScript.model_validate(manual_script).model_dump()
                path = await self.runtime.write_json(run, 'script.json', data)
                return [ArtifactSpec(path, 'script', source='manual')], data, None, False

            self.runtime_stage = 'script'
            script_run, script_artifacts = await self.stage('script', script_inputs, script_action, force=True)

            async def storyboard_action(run):
                await gen.apply_script_to_task(task_id, StructuredScript.model_validate(script_run.output_payload))
                await self.save()
                current = await SceneRepository(self.db).list_by_task_id(task_id)
                data = {'scenes': [scene_snapshot(s) for s in current]}
                path = await self.runtime.write_json(run, 'storyboard.json', data)
                return [ArtifactSpec(path, 'storyboard', source='manual')], data, None, False

            self.runtime_stage = 'storyboard'
            await self.stage('storyboard', {'manual_script': manual_script}, storyboard_action, dependencies=script_artifacts, force=True)
            return await self.finish_partial(task_id, {'task_id': task_id})

        skip_preparation = single in {'assets', 'voice', 'composition'} or mode_prepared
        if not skip_preparation:
            await self.json_stage('topic', {'topic': topic, 'mode': payload.get('mode'), 'raw_script': payload.get('raw_script')}, {'topic': topic})
            research_inputs = {k: payload.get(k) for k in ('enable_research', 'search_provider_id', 'research_max_queries', 'research_max_results')}
            research_inputs['prompt_selection'] = prompt_selection
            research_inputs['research_source_ids'] = _research_source_ids(payload)
            research_inputs['prompt_call_budgets'] = {
                'research_query': PROMPT_CALL_BUDGETS['research_query']
            }
            research_inputs['llm_structured_mode'] = False
            research_inputs.update(topic=topic, provider=provider_inputs.get('search'), planner=provider_inputs.get('llm'))

            async def research_action(run):
                if render_only:
                    data = payload.get('research') or {'topic': topic, 'status': 'skipped', 'summary': '仅重新渲染，保留已有研究'}
                    result = ResearchResponse.model_validate(data)
                else:
                    result = await gen.research_task(task_id, force=True)
                data = result.model_dump()
                path = await self.runtime.write_json(run, 'research.json', data)
                return [ArtifactSpec(path, 'research')], data, result.error_message if result.status == 'failed' else None, result.status == 'skipped'

            research_run, research_artifacts = await self.stage('research', research_inputs, research_action)
            research = ResearchResponse.model_validate(research_run.output_payload)
            # ``research_task`` persists into the database, but this local
            # snapshot predates that stage. Carry the durable result forward
            # so the following script stage uses the same-run research.
            payload['research'] = research.model_dump()
            resolved_script_inputs = build_script_generation_inputs(payload, topic=topic, project=project)
            resolved_script_inputs['research_source_ids'] = [
                hashlib.sha256(
                    f"{source.url}|{source.title}".encode()
                ).hexdigest()
                for source in research.sources
            ]
            resolved_script_inputs['research_sources'] = [
                source.model_dump() for source in research.sources
            ]
            plan = {k: payload.get(k) for k in ('style_preset', 'target_scene_count', 'template_id', 'template_params', 'content_mode', 'material_provider_id', 'voice_id', 'speed')}
            plan.update(
                knowledge_brief=resolved_script_inputs.get('knowledge_brief'),
                aspect_ratio=resolved_script_inputs['aspect_ratio'],
                language=resolved_script_inputs.get('language'),
            )
            await self.json_stage('planning', plan, plan)
            script_inputs = resolved_script_inputs
            llm_snapshot = provider_inputs.get('llm') or {}
            llm_config = llm_snapshot.get('config') or {}
            script_inputs.update(
                llm=llm_snapshot,
                llm_call_config={
                    'native_json_schema': llm_config.get('supports_native_json_schema') is True,
                    'temperature_and_max_tokens': {
                        key: value
                        for key, value in PROMPT_CALL_BUDGETS.items()
                    },
                },
            )
            if manual or adopted_script or render_only:
                script_inputs = {'adopted_scenes': [scene_snapshot(s) for s in scenes], 'manual_version': payload.get('manual_storyboard_version')}

            async def script_action(run):
                if manual or adopted_script or render_only:
                    current_task = await TaskRepository(self.db).get_by_id(task_id)
                    current_scenes = await SceneRepository(self.db).list_by_task_id(task_id)
                    data = {'adopted': True, 'scenes': [scene_snapshot(s) for s in current_scenes], 'title': current_task.title}
                    source = 'manual' if manual else 'adopted'
                else:
                    request = {k: v for k, v in script_inputs.items() if k in ScriptGenerateRequest.model_fields and v is not None}
                    request['research_context'] = research.format_for_prompt() if research.status == 'completed' and research.sources else None
                    request['enable_research'] = False
                    data = (await gen.generate_script(ScriptGenerateRequest(**request))).model_dump()
                    source = 'generated'
                path = await self.runtime.write_json(run, 'script.json', data)
                return [ArtifactSpec(path, 'script', source=source)], data, None, False

            script_run, script_artifacts = await self.stage('script', script_inputs, script_action, dependencies=[] if manual or adopted_script or render_only else research_artifacts)

            async def storyboard_action(run):
                if not (script_run.output_payload or {}).get('adopted'):
                    await gen.apply_script_to_task(task_id, StructuredScript.model_validate(script_run.output_payload))
                    await self.save()
                current = await SceneRepository(self.db).list_by_task_id(task_id)
                data = {'scenes': [scene_snapshot(s) for s in current]}
                path = await self.runtime.write_json(run, 'storyboard.json', data)
                return [ArtifactSpec(path, 'storyboard', source='manual' if manual else 'generated')], data, None, False

            self.runtime_stage = 'storyboard'
            await self.stage('storyboard', {'manual_version': payload.get('manual_storyboard_version')}, storyboard_action, dependencies=script_artifacts)
        # A retry may have rolled back and expired the task/scene instances
        # captured before the action. Use fresh rows for all subsequent input
        # snapshots and bindings.
        task = await TaskRepository(self.db).get_by_id(task_id)
        all_scenes = await SceneRepository(self.db).list_by_task_id(task_id)
        scenes = all_scenes
        if single in {'assets', 'voice'} and self.params.get('single_unit'):
            scenes = [s for s in scenes if s.id == self.params.get('single_unit')]
        if not scenes:
            raise ValidationException('任务没有分镜，无法生产视频。')
        template_path = template_catalog.resolve_path(template_id)
        template_hash = await sha256_file(template_path)
        workflow_hashes = {}
        for kind in ('image', 'video'):
            reference = (payload.get(kind + '_workflow_snapshot') or {}).get('path') or payload.get(kind + '_workflow_id')
            path = workflow_service.resolve_workflow_file(reference) if reference else None
            workflow_hashes[kind] = await sha256_file(path) if path else None
        visuals, voices, clips = {}, {}, []
        material_service = MaterialService(
            self.db,
            storage=self.storage,
            provider_manager=pm,
            execution_context=self.context,
        ) if any(
            item.get('strategy') == MediaStrategy.ONLINE_ASSET.value
            for item in (production_plan.get('scene_plans') or {}).values()
        ) or MediaStrategy.ONLINE_ASSET.value in (
            production_plan.get('planning_rules') or {}
        ).values() or mode == 'online_asset' else None
        online_external_ids: set[str] = set()
        if mode == 'online_asset':
            for bound_scene in all_scenes:
                if not bound_scene.media_asset_id:
                    continue
                bound_asset = await self.db.get(AssetModel, bound_scene.media_asset_id)
                bound_metadata = (bound_asset.metadata_json or {}) if bound_asset else {}
                external_id = bound_metadata.get('external_id')
                if bound_metadata.get('source_kind') == 'online_asset' and external_id:
                    online_external_ids.add(str(external_id))

        for scene in scenes if single != 'voice' else []:
            scene_id = scene.id
            raw_media_plan = (production_plan.get('scene_plans') or {}).get(scene_id)
            if raw_media_plan is None:
                strategy = (production_plan.get('planning_rules') or {}).get(
                    getattr(scene, 'visual_role', 'concept')
                ) or (production_plan.get('recipe') or {}).get('default_strategy')
                if not strategy:
                    raise ValidationException(f'分镜 {scene_id} 缺少快照化 MediaPlan。')
                raw_media_plan = {
                    'strategy': strategy,
                    'reference_asset_ids': (
                        production_plan.get('default_reference_asset_ids') or []
                    ) if strategy in {'image_to_image', 'image_to_video'} else [],
                    'source_asset_id': (
                        (production_plan.get('default_reference_asset_ids') or [None])[0]
                    ) if strategy == 'uploaded_asset' else None,
                    'image_workflow_id': payload.get('image_workflow_id'),
                    'video_workflow_id': payload.get('video_workflow_id'),
                    'cost_tier': (production_plan.get('recipe') or {}).get('cost_tier', 'low'),
                }
            media_plan = MediaPlan.model_validate(raw_media_plan)
            scene_mode = {
                MediaStrategy.STATIC_CARD: 'static',
                MediaStrategy.ONLINE_ASSET: 'online_asset',
                MediaStrategy.UPLOADED_ASSET: 'uploaded_asset',
                MediaStrategy.TEXT_TO_IMAGE: 'generated_image',
                MediaStrategy.IMAGE_TO_IMAGE: 'generated_image',
                MediaStrategy.TEXT_TO_VIDEO: 'generated_video',
                MediaStrategy.IMAGE_TO_VIDEO: 'generated_video',
            }[media_plan.strategy]
            # Uploaded and manual assets are authoritative. Generated pointers are outputs, not inputs.
            layout_params = scene.layout_params or {}
            media_source = layout_params.get('media_source')
            production_metadata = scene.production_metadata or {}
            media_policy = production_metadata.get('media') or {}
            commerce_metadata = production_metadata.get('commerce') or {}
            locked_media = bool(
                media_policy.get('locked')
                or commerce_metadata.get('asset_locked')
                or layout_params.get('commerce_asset_locked')
            )
            locked_media_id = (
                scene.media_asset_id
                or media_policy.get('asset_id')
                or layout_params.get('commerce_asset_id')
            )
            user_media = (
                scene_mode == 'uploaded_asset'
                or media_source in {'manual', 'uploaded'}
                or (locked_media and bool(locked_media_id))
            )
            # A generated override is authoritative only while the task remains
            # in its external-material mode; ordinary generated tasks keep their
            # existing regeneration/reuse policy.
            force_online_refresh = single == 'assets' and self.params.get('content_mode_override') == 'online_asset'
            generated_media = (
                scene_mode == 'online_asset'
                and media_source == 'generated'
                and not force_online_refresh
            )
            existing_id = locked_media_id or scene.media_asset_id or (
                media_plan.source_asset_id if scene_mode == 'uploaded_asset' else None
            )
            media_digest = None
            if user_media and existing_id:
                _, media_digest = await self.asset(existing_id)
            if scene_mode == 'online_asset':
                prompt = str(scene.narration_text or '').strip() or str(task.title or '').strip() or '通用实拍素材'
            else:
                prompt = self.params.get('prompt_override') or scene.visual_prompt or scene.narration_text
            if scene_mode == 'online_asset' and scene.media_asset_id:
                current_asset = await self.db.get(AssetModel, scene.media_asset_id)
                current_source = (current_asset.metadata_json or {}) if current_asset else {}
                if current_source.get('source_kind') == 'online_asset' and current_source.get('external_id'):
                    online_external_ids.add(str(current_source['external_id']))
            reference_digests = []
            for reference_asset_id in media_plan.reference_asset_ids:
                _, digest = await self.asset(reference_asset_id)
                reference_digests.append(digest)
            inputs = {'mode': scene_mode, 'strategy': media_plan.strategy.value, 'prompt': prompt,
                'style': payload.get('style_preset'), 'prompt_prefix': payload.get('prompt_prefix'),
                'provider': provider_inputs.get('material' if scene_mode == 'online_asset' else ('video' if scene_mode == 'generated_video' else 'image')),
                'media_size': template_catalog.get_media_size(template_id), 'uploaded_sha256': media_digest,
                'workflow_sha256': workflow_hashes['video' if scene_mode == 'generated_video' else 'image'] if scene_mode != 'online_asset' else None,
                'workflow_id': media_plan.video_workflow_id if scene_mode == 'generated_video' else media_plan.image_workflow_id,
                'reference_sha256': reference_digests,
                'continuity_inputs': media_plan.continuity_inputs,
                'fallback_policy': media_plan.fallback_policy,
                'material_provider_id': payload.get('material_provider_id') if scene_mode == 'online_asset' else None,
                # Existing task bindings are runtime exclusions. Keep them out
                # of the normal full-run fingerprint so a resumable stage can
                # still reuse its validated artifact; forced single-scene
                # refreshes include the current ID in their fingerprint.
                'excluded_external_ids': sorted(online_external_ids) if scene_mode == 'online_asset' and single == 'assets' else None,
                'duration_seconds': scene.duration_seconds if scene_mode in {'generated_video', 'online_asset'} else None,
                'locked_media_source': media_policy.get('source') or ('product' if commerce_metadata else None),
                'locked_media': locked_media,
                'locked_media_id': existing_id if locked_media else None}
            async def visual_action(
                run,
                scene_id=scene_id,
                existing_id=existing_id,
                user_media=user_media,
                generated_media=generated_media,
                media_plan=media_plan,
                scene_mode=scene_mode,
            ):
                current_scene = await SceneRepository(self.db).get_by_id(scene_id)
                if not current_scene:
                    raise ValidationException('分镜不存在，无法生成视觉素材。')
                if scene_mode == 'static':
                    return [], {'mode': scene_mode, 'strategy': media_plan.strategy.value}, None, True
                adopted = None
                if user_media or generated_media:
                    if not existing_id:
                        raise ValidationException('手工、上传或已生成分镜缺少画面素材。')
                    adopted, _ = await self.asset(existing_id)
                elif locked_media:
                    raise ValidationException(
                        '商业商品镜头缺少可用的真实商品素材，请先上传或下载商品素材；不会自动重绘商品主体。'
                    )
                elif render_only and single != 'assets':
                    try:
                        adopted, _ = await self.asset(existing_id)
                    except Exception:
                        if user_media or render_only:
                            raise
                if adopted is not None:
                    asset = adopted
                    source = (
                        'product'
                        if locked_media
                        else 'uploaded'
                        if user_media
                        else 'generated'
                        if generated_media
                        else 'existing'
                    )
                elif scene_mode == 'online_asset':
                    if material_service is None:
                        raise ValidationException('在线素材服务未初始化。')
                    asset, material_source, _ = await material_service.acquire_for_scene(
                        task.project_id,
                        task.id,
                        current_scene.id,
                        str(current_scene.narration_text or '').strip()
                        or str(task.title or '').strip()
                        or '通用实拍素材',
                        template_catalog.get_media_aspect_ratio(template_id),
                        payload.get('material_provider_id'),
                        min_duration_seconds=float(current_scene.duration_seconds or 0),
                        excluded_external_ids=online_external_ids,
                        target_size=template_catalog.get_media_size(template_id),
                        execution_context=self.context,
                    )
                    online_external_ids.add(material_source.external_id)
                    await self.save()
                    source = 'online'
                else:
                    reference_paths = []
                    for reference_asset_id in media_plan.reference_asset_ids:
                        reference_asset, _ = await self.asset(reference_asset_id)
                        reference_paths.append(str(self.storage.get_path(reference_asset.file_path)))
                    if scene_mode == 'generated_video':
                        source_asset_id = media_plan.source_asset_id
                        if media_plan.strategy == MediaStrategy.IMAGE_TO_VIDEO and not source_asset_id:
                            source_asset_id = media_plan.reference_asset_ids[0]
                        if source_asset_id:
                            current_scene.media_asset_id = source_asset_id
                            await self.db.flush()
                        gen.production_settings = {
                            **payload,
                            'video_workflow_id': media_plan.video_workflow_id
                            or payload.get('video_workflow_id'),
                        }
                        await gen.generate_scene_video(
                            current_scene.id,
                            prompt_override=self.params.get('prompt_override'),
                            continuity_input={
                                **media_plan.continuity_inputs,
                                'reference_image_paths': reference_paths,
                            },
                        )
                    else:
                        gen.production_settings = {
                            **payload,
                            'image_workflow_id': media_plan.image_workflow_id
                            or payload.get('image_workflow_id'),
                        }
                        await gen.generate_scene_image(
                            current_scene.id,
                            prompt_override=self.params.get('prompt_override'),
                            reference_image_paths=reference_paths or None,
                        )
                    await self.save()
                    asset, _ = await self.asset(current_scene.media_asset_id)
                    source = 'generated'
                return [ArtifactSpec(self.storage.get_path(asset.file_path), 'visual', asset.id, source)], {
                    'asset_id': asset.id, 'strategy': media_plan.strategy.value,
                }, None, False
            _, visuals[scene_id] = await self.stage('assets', inputs, visual_action, scene_id, force=single == 'assets')
            scene = await SceneRepository(self.db).get_by_id(scene_id)
            await self.bind(scene, 'media_asset_id', visuals[scene.id])
            if not visuals[scene.id]:
                await self.runtime.assert_lease()
                scene.media_asset_id = None
                await self.db.commit()
        if single == 'assets':
            current_scene = await SceneRepository(self.db).get_by_id(scenes[0].id)
            self.runtime_stage = 'assets'
            return await self.finish_partial(task_id, {'scene_id': current_scene.id, 'asset_id': current_scene.media_asset_id})
        for scene in scenes:
            scene = await SceneRepository(self.db).get_by_id(scene.id)
            scene_id = scene.id
            user_audio = (scene.layout_params or {}).get('audio_source') in {'manual', 'uploaded'}
            audio_digest = (await self.asset(scene.audio_asset_id))[1] if user_audio else None
            async def voice_action(run, scene_id=scene_id, user_audio=user_audio):
                current_scene = await SceneRepository(self.db).get_by_id(scene_id)
                if not current_scene:
                    raise ValidationException('分镜不存在，无法生成配音。')
                if not current_scene.narration_text.strip() and not user_audio:
                    if not current_scene.duration_seconds or current_scene.duration_seconds <= 0:
                        raise ValidationException('无旁白分镜需要明确的场景时长。')
                    return [], {'duration_seconds': current_scene.duration_seconds, 'duration_source': 'scene_duration'}, None, True
                adopted = None
                if user_audio:
                    if not current_scene.audio_asset_id:
                        raise ValidationException('手工或上传分镜缺少配音素材。')
                    adopted, _ = await self.asset(current_scene.audio_asset_id)
                elif render_only and current_scene.audio_asset_id and single != 'voice':
                    try:
                        adopted, _ = await self.asset(current_scene.audio_asset_id)
                    except Exception:
                        if user_audio or render_only:
                            raise
                if adopted is not None:
                    asset, source = adopted, 'manual' if user_audio else 'existing'
                elif render_only and single != 'voice':
                    raise ValidationException('配音缺失，请先生成配音再重新渲染。')
                else:
                    await gen.generate_scene_audio(current_scene.id, voice_id=self.params.get('voice_id'), speed=self.params.get('speed'))
                    await self.save()
                    asset, _ = await self.asset(current_scene.audio_asset_id)
                    source = 'generated'
                return [ArtifactSpec(self.storage.get_path(asset.file_path), 'voice', asset.id, source)], {'asset_id': asset.id}, None, False
            _, voices[scene_id] = await self.stage('voice', {'text': scene.narration_text, 'voice_id': self.params.get('voice_id') or payload.get('voice_id'),
                'speed': self.params.get('speed') or payload.get('speed', 1), 'provider': provider_inputs.get('tts'),
                'user_audio_sha256': audio_digest, 'silent_duration': scene.duration_seconds if not scene.narration_text.strip() else None}, voice_action, scene_id, force=single == 'voice')
            scene = await SceneRepository(self.db).get_by_id(scene_id)
            await self.bind(scene, 'audio_asset_id', voices[scene_id])
            if not voices[scene_id]:
                await self.runtime.assert_lease()
                scene.audio_asset_id = None
                await self.db.commit()
        if single == 'voice':
            current_scene = await SceneRepository(self.db).get_by_id(scenes[0].id)
            self.runtime_stage = 'voice'
            return await self.finish_partial(task_id, {'scene_id': current_scene.id, 'asset_id': current_scene.audio_asset_id})
        scenes = await SceneRepository(self.db).list_by_task_id(task_id)
        if single in {'assets', 'voice'} and self.params.get('single_unit'):
            scenes = [s for s in scenes if s.id == self.params.get('single_unit')]
        scene_ids = [scene.id for scene in scenes]
        timeline, offset = [], 0.0
        for scene in scenes:
            duration = float(scene.duration_seconds)
            timeline.append({'scene_id': scene.id, 'text': scene.narration_text, 'start': offset, 'end': offset + duration,
                'duration_source': 'audio_probe' if voices[scene.id] else 'scene_duration'})
            offset += duration
        async def subtitles_action(run):
            srt, ass = subtitle_documents(timeline)
            directory = self.runtime.attempt_dir(run)
            specs = []
            for name, data in [('subtitles.srt', srt), ('subtitles.ass', ass)]:
                target = directory / name
                temporary = target.with_suffix(target.suffix + '.tmp')
                await asyncio.to_thread(temporary.write_text, data, encoding='utf-8')
                temporary.replace(target)
                specs.append(ArtifactSpec(target, name.rsplit('.', 1)[-1]))
            path = await self.runtime.write_json(run, 'timeline.json', timeline)
            return [*specs, ArtifactSpec(path, 'timeline')], {'timeline': timeline}, None, False
        _, subtitle_artifacts = await self.stage('subtitles', {'timeline': timeline}, subtitles_action,
            dependencies=[a for values in voices.values() for a in values])
        for scene_id in scene_ids:
            current_scene = await SceneRepository(self.db).get_by_id(scene_id)
            current_task = await TaskRepository(self.db).get_by_id(task_id)
            raw_media_plan = (production_plan.get('scene_plans') or {}).get(scene_id) or {}
            scene_strategy = raw_media_plan.get('strategy') or (
                production_plan.get('planning_rules') or {}
            ).get(getattr(current_scene, 'visual_role', 'concept')) or (
                production_plan.get('recipe') or {}
            ).get('default_strategy')
            render_mode = {
                'static_card': 'static', 'online_asset': 'online_asset',
                'uploaded_asset': 'uploaded_asset', 'text_to_image': 'generated_image',
                'image_to_image': 'generated_image', 'text_to_video': 'generated_video',
                'image_to_video': 'generated_video',
            }.get(scene_strategy, mode)
            async def clip_action(run, scene_id=scene_id):
                current_scene = await SceneRepository(self.db).get_by_id(scene_id)
                if not current_scene:
                    raise ValidationException('分镜不存在，无法合成场景片段。')
                renderer.commands = []
                renderer.production_settings = {**payload, 'content_mode': render_mode}
                await renderer.render_scene_clip(current_scene.id)
                await self.save()
                current_scene = await SceneRepository(self.db).get_by_id(scene_id)
                asset, _ = await self.asset(current_scene.rendered_segment_asset_id)
                return [ArtifactSpec(self.storage.get_path(asset.file_path), 'scene_clip', asset.id)], {'asset_id': asset.id, 'ffmpeg_commands': renderer.commands}, None, False
            _, outputs = await self.stage('composition', {'template_sha256': template_hash, 'template_id': template_id,
                'title': current_task.title, 'text': current_scene.narration_text, 'duration': current_scene.duration_seconds,
                'sequence_index': current_scene.sequence_index, 'layout': scene_snapshot(current_scene)['layout_params'],
                'params': payload.get('template_params'), 'custom_css': payload.get('custom_css'), 'mode': render_mode,
                'scene_render_format_version': (
                    RenderingService.ONLINE_SCENE_RENDER_FORMAT_VERSION
                    if render_mode == 'online_asset' else None
                )},
                clip_action, scene_id, [*visuals[scene_id], *voices[scene_id]],
                force=render_only and single != 'composition')
            scene = await SceneRepository(self.db).get_by_id(scene_id)
            await self.bind(scene, 'rendered_segment_asset_id', outputs)
            clips.extend(outputs)
        bgm_id = self.params.get('bgm_asset_id') or (payload.get('bgm_asset_id') if payload.get('bgm_enabled') else None)
        bgm_hash = (await self.asset(bgm_id))[1] if bgm_id else None
        async def composition_action(run):
            renderer.commands = []
            asset = await renderer.compose_task_video(self.job.task_id, bgm_asset_id=self.params.get('bgm_asset_id'))
            await self.save()
            return [ArtifactSpec(self.storage.get_path(asset.file_path), 'final_video', asset.id)], {'asset_id': asset.id,
                'ffmpeg_commands': renderer.commands}, None, False
        final_run, final_artifacts = await self.stage('composition', {'clip_order': [a.sha256 for a in clips],
            'bgm_sha256': bgm_hash, 'bgm_volume': payload.get('bgm_volume'),
            'composition_format_version': RenderingService.COMPOSITION_FORMAT_VERSION},
            composition_action, dependencies=clips)
        final = final_artifacts[0]
        final_artifact_id = final.id
        final_asset_id, final_relative_path = final.asset_id, final.relative_path
        final_video_url = self.storage.get_url(final_relative_path)
        final_media_info = dict(final.media_info or {})
        subtitle_artifact_ids = [a.id for a in subtitle_artifacts if a.kind in {'srt', 'ass'}]
        scene_count = len(scene_ids)
        async def export_action(run):
            current_runs = list((await self.db.scalars(select(WorkflowStepRunModel).where(
                WorkflowStepRunModel.job_id == job_id).order_by(WorkflowStepRunModel.started_at, WorkflowStepRunModel.attempt))).all())
            unique = {}
            for current_run in current_runs:
                for artifact in await self.runtime.outputs(current_run):
                    unique[artifact.id] = artifact
            manifest = {'schema_version': 1, 'task_id': task_id, 'job_id': job_id, 'configuration': redact(payload),
                'timeline': timeline, 'final_video': {'artifact_id': final_artifact_id, 'media_info': final_media_info},
                'steps': [{'id': r.id, 'step': r.step_key, 'unit_key': r.unit_key, 'attempt': r.attempt,
                    'status': r.status, 'input_fingerprint': r.input_fingerprint, 'reused_from_id': r.reused_from_id,
                    'duration_ms': r.duration_ms, 'warning': r.warning, 'output': r.output_payload} for r in current_runs if r.id != run.id],
                'artifacts': [{'id': a.id, 'step_run_id': a.step_run_id, 'kind': a.kind, 'path': a.relative_path,
                    'size_bytes': a.size_bytes, 'sha256': a.sha256, 'media_info': a.media_info, 'source': a.source} for a in unique.values()]}
            path = await self.runtime.write_json(run, 'render_manifest.json', manifest)
            return [ArtifactSpec(path, 'render_manifest')], {'manifest_version': 1}, None, False
        current_run_ids = list((await self.db.scalars(select(WorkflowStepRunModel.id).where(
            WorkflowStepRunModel.job_id == job_id))).all())
        _, export_artifacts = await self.stage('export', {'configuration': redact(payload), 'timeline': timeline,
            'run_ids': current_run_ids}, export_action,
            dependencies=[*final_artifacts, *subtitle_artifacts])
        await self.runtime.assert_lease()
        task = await TaskRepository(self.db).get_by_id(task_id)
        if not task:
            raise ValidationException('任务不存在')
        task.production_status = 'completed'
        result = {'video_status': 'ready', 'job_id': job_id,
            'final_video_asset_id': final_asset_id, 'final_video_path': final_relative_path,
            'final_video_url': final_video_url, 'scenes_count': scene_count,
            'total_duration_seconds': max(final_media_info.get('audio_duration') or 0, final_media_info.get('video_duration') or 0),
            'render_manifest_artifact_id': export_artifacts[0].id,
            'subtitle_artifact_ids': subtitle_artifact_ids}
        await self.db.commit()
        for event in ('video.preview_ready', 'task.completed'):
            await event_broadcaster.broadcast(event, {**result, 'task_id': task_id, 'job_id': job_id, 'status': 'completed', 'progress': 100, 'preview_url': result['final_video_url']}, task_id=task_id, job_id=job_id, lease_token=token)
        return result

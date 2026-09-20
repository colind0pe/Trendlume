"""Durable stage records, verified reuse, and lease-fenced completion."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.production_workflows import ProductionWorkflow, get_production_workflow
from src.models.asset import AssetModel
from src.models.product import ProductAssetModel
from src.models.task import TaskModel
from src.models.workflow import (
    WorkflowArtifactModel,
    WorkflowJobModel,
    WorkflowStepArtifactModel,
    WorkflowStepRunModel,
)
from src.services.media_probe import MediaProbeService

SUCCESS_STATUSES = ('completed', 'completed_with_warning', 'skipped', 'reused')
_SECRET_KEYS = {
    'api_key', 'apikey', 'password', 'secret', 'token', 'access_token',
    'refresh_token', 'cookie', 'authorization', 'credentials',
    'credentials_encrypted', 'private_key', 'session_state', 'storage_state',
}
_SECRET_KEY_PARTS = ('api_key', 'apikey', 'password', 'secret', 'token', 'cookie', 'authorization', 'credential', 'private_key')
_SECRET_QUERY_PARTS = ('key', 'token', 'secret', 'password', 'auth', 'signature', 'cookie')


def redact(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            name = str(key).lower()
            if name in _SECRET_KEYS or any(part in name for part in _SECRET_KEY_PARTS):
                continue
            result[str(key)] = redact(item)
        return result
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, str) and value.startswith(('http://', 'https://')):
        try:
            parsed = urlsplit(value)
            host = parsed.hostname or ''
            if parsed.port:
                host = f'{host}:{parsed.port}'
            query = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)
                     if not any(part in key.lower() for part in _SECRET_QUERY_PARTS)]
            return urlunsplit((parsed.scheme, host, parsed.path, urlencode(query), ''))
        except ValueError:
            return '<invalid-url>'
    return value


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(redact(value), sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


async def sha256_file(path: Path) -> str:
    def digest():
        result = hashlib.sha256()
        with path.open('rb') as stream:
            while chunk := stream.read(1024 * 1024):
                result.update(chunk)
        return result.hexdigest()
    return await asyncio.to_thread(digest)


def safe_artifact_path(root: Path, relative_path: str) -> Path:
    candidate = (root.resolve() / relative_path).resolve()
    if not candidate.is_relative_to(root.resolve()) or candidate == root.resolve():
        raise ValueError('Artifact path escapes storage root')
    return candidate


async def probe_file(path: Path) -> dict | None:
    if path.suffix.lower() in {'.mp4', '.mov', '.webm', '.mkv', '.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac'}:
        facts = await MediaProbeService().probe(path)
        if not facts.has_audio and not facts.has_video:
            raise ValueError('Media contains no readable streams')
        return asdict(facts)
    if path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
        facts = await MediaProbeService().probe(path)
        if not facts.has_video or not facts.width or not facts.height:
            raise ValueError('Image has no readable visual stream')
        return asdict(facts)
    return None


async def validate_artifact(root: Path, artifact: WorkflowArtifactModel) -> tuple[bool, str | None]:
    try:
        path = safe_artifact_path(root, artifact.relative_path)
        if not path.is_file() or path.stat().st_size != artifact.size_bytes:
            return False, '文件缺失或大小改变'
        if await sha256_file(path) != artifact.sha256:
            return False, 'SHA-256 校验失败'
        await probe_file(path)
        return True, None
    except Exception as exc:
        return False, str(exc)


@dataclass
class ArtifactSpec:
    path: Path
    kind: str
    asset_id: str | None = None
    source: str = 'generated'
    media_info: dict | None = None


class LeaseLostError(asyncio.CancelledError):
    pass


class WorkflowRuntime:
    def __init__(
        self,
        db: AsyncSession,
        storage_root: Path,
        job_id: str,
        lease_token: str,
        workflow: ProductionWorkflow | None = None,
    ):
        self.db = db
        self.root = storage_root.resolve()
        self.job_id = job_id
        self.lease_token = lease_token
        self.workflow = workflow or get_production_workflow(None)

    async def assert_lease(self):
        # A conditional write serializes against reclaim/cancel in the same transaction.
        result = await self.db.execute(update(WorkflowJobModel).where(
            WorkflowJobModel.id == self.job_id,
            WorkflowJobModel.status == 'running',
            WorkflowJobModel.lease_token == self.lease_token,
            WorkflowJobModel.lease_token.is_not(None),
        ).values(updated_at=datetime.now(UTC)).execution_options(autoflush=False, synchronize_session=False))
        if result.rowcount != 1:
            await self.db.rollback()
            raise LeaseLostError('Workflow lease was cancelled or replaced')

    async def _release(self):
        if self.db.new or self.db.dirty or self.db.deleted:
            await self.assert_lease()
        await self.db.commit()

    async def outputs(self, run: WorkflowStepRunModel) -> list[WorkflowArtifactModel]:
        return list((await self.db.scalars(select(WorkflowArtifactModel).join(WorkflowStepArtifactModel, WorkflowStepArtifactModel.artifact_id == WorkflowArtifactModel.id).where(
            WorkflowStepArtifactModel.step_run_id == run.id,
            WorkflowStepArtifactModel.role.in_(('output', 'reuse')),
        ))).all())

    def attempt_dir(self, run: WorkflowStepRunModel) -> Path:
        directory = safe_artifact_path(self.root, f'workflow/{run.task_id}/{run.id}')
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    async def write_json(self, run: WorkflowStepRunModel, name: str, payload) -> Path:
        directory = self.attempt_dir(run)
        target = safe_artifact_path(directory, name)
        data = json.dumps(redact(payload), ensure_ascii=False, sort_keys=True, indent=2).encode()
        def write():
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + '.' + str(uuid4()) + '.tmp')
            with temporary.open('xb') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        await asyncio.to_thread(write)
        return target

    async def begin(self, step_key: str, inputs: dict, unit_key: str = '', input_artifacts=None, force: bool = False) -> WorkflowStepRunModel:
        if not self.workflow.has_stage(step_key):
            raise ValueError(f'Unknown workflow stage: {step_key}')
        dependencies = list(input_artifacts or [])
        job = await self.db.get(WorkflowJobModel, self.job_id)
        if job is None:
            raise LeaseLostError('Workflow job does not exist')
        task_id = job.task_id
        task = await self.db.get(TaskModel, task_id)
        context_hash = getattr(task, "context_hash", None)
        fingerprint_inputs = dict(inputs or {})
        if context_hash:
            fingerprint_inputs["_project_context_hash"] = context_hash
        payload = redact(fingerprint_inputs)
        # Preserve producer lineage even when a forced rerun emits identical
        # bytes. Downstream stages must still checkpoint against the new run.
        digest = fingerprint({'version': '1', 'inputs': payload,
                              'dependencies': sorted((a.kind, a.sha256, a.id) for a in dependencies)})
        candidates = list((await self.db.scalars(select(WorkflowStepRunModel).where(
            WorkflowStepRunModel.task_id == task_id, WorkflowStepRunModel.step_key == step_key,
            WorkflowStepRunModel.unit_key == unit_key, WorkflowStepRunModel.status.in_(SUCCESS_STATUSES),
        ).order_by(WorkflowStepRunModel.attempt.desc()))).all())
        # Release read transaction before filesystem and ffprobe work.
        await self._release()
        source = None
        source_outputs = []
        invalid = []
        for candidate in candidates:
            if candidate.validity != 'valid':
                invalid.append((candidate, candidate.validity or 'stale', candidate.invalid_reason or '阶段已标记为无效'))
                continue
            if candidate.input_fingerprint != digest:
                invalid.append((candidate, 'stale', '阶段输入或配置已改变'))
                continue
            if force:
                continue
            artifacts = await self.outputs(candidate)
            await self.db.commit()
            checks = [await validate_artifact(self.root, a) for a in artifacts]
            if candidate.status != 'skipped' and not (candidate.status == 'reused' and (candidate.output_payload or {}).get('_skipped')) and not artifacts:
                checks.append((False, '阶段没有可校验输出'))
            failure = next((reason for ok, reason in checks if not ok), None)
            if failure:
                invalid.append((candidate, 'corrupt', failure))
                continue
            source, source_outputs = candidate, artifacts
            break
        await self.assert_lease()
        for candidate, validity, reason in invalid:
            candidate.validity, candidate.invalid_reason = validity, reason
        attempt = (await self.db.scalar(select(func.max(WorkflowStepRunModel.attempt)).where(
            WorkflowStepRunModel.task_id == task_id, WorkflowStepRunModel.step_key == step_key, WorkflowStepRunModel.unit_key == unit_key,
        )) or 0) + 1
        run = WorkflowStepRunModel(id=str(uuid4()), task_id=task_id, job_id=self.job_id, step_key=step_key, unit_key=unit_key,
            attempt=attempt, input_fingerprint=digest, input_payload=payload, status='reused' if source else 'running',
            reused_from_id=source.id if source else None, output_payload=source.output_payload if source else None,
            warning=source.warning if source else None, completed_at=datetime.now(UTC) if source else None, duration_ms=0 if source else None)
        self.db.add(run)
        await self.db.flush()
        for artifact in dependencies:
            if artifact.task_id != task_id:
                raise ValueError('Input artifact belongs to another task')
            self.db.add(WorkflowStepArtifactModel(step_run_id=run.id, artifact_id=artifact.id, role='input'))
        for artifact in source_outputs:
            self.db.add(WorkflowStepArtifactModel(step_run_id=run.id, artifact_id=artifact.id, role='reuse'))
        await self.db.commit()
        return run

    async def complete(self, run: WorkflowStepRunModel, outputs: list[ArtifactSpec], warning: str | None = None, skipped: bool = False, output_payload: dict | None = None) -> list[WorkflowArtifactModel]:
        if run.job_id != self.job_id or run.status != 'running':
            raise ValueError('Only this job\'s running attempt can complete')
        if not outputs and not skipped:
            raise ValueError('Completed stages must have verifiable output')
        await self._release()
        artifacts = []
        for index, spec in enumerate(outputs):
            path = spec.path.resolve()
            # Copy external/provider mutable files into immutable attempt storage.
            directory = self.attempt_dir(run)
            if not path.is_relative_to(directory):
                target = directory / f'{index}_{path.name}'
                temporary = target.with_suffix(target.suffix + '.tmp')
                await asyncio.to_thread(shutil.copyfile, path, temporary)
                await asyncio.to_thread(os.replace, temporary, target)
                path = target
            relative = path.relative_to(self.root).as_posix()
            if not path.is_file() or not path.stat().st_size:
                raise ValueError('Artifact is missing or empty')
            media_info = await probe_file(path)
            artifacts.append(WorkflowArtifactModel(id=str(uuid4()), task_id=run.task_id, step_run_id=run.id,
                asset_id=spec.asset_id, kind=spec.kind, relative_path=relative, size_bytes=path.stat().st_size,
                sha256=await sha256_file(path), media_info=media_info or spec.media_info, source=spec.source))
        await self.assert_lease()
        task = await self.db.get(TaskModel, run.task_id)
        if task is None:
            await self.db.rollback()
            raise ValueError("Artifact task does not exist")
        for artifact in artifacts:
            if artifact.asset_id:
                asset = await self.db.get(AssetModel, artifact.asset_id)
                product_asset = None
                if asset is not None and artifact.source == "product" and task.product_id:
                    product_asset = await self.db.scalar(
                        select(ProductAssetModel.id).where(
                            ProductAssetModel.asset_id == asset.id,
                            ProductAssetModel.product_id == task.product_id,
                        ).limit(1)
                    )
                project_owned = asset is not None and asset.project_id == task.project_id
                product_owned = asset is not None and asset.project_id is None and product_asset is not None
                if not project_owned and not product_owned:
                    await self.db.rollback()
                    raise ValueError("Artifact asset does not belong to the task project")
                if artifact.source == "generated":
                    asset.file_path = artifact.relative_path
            self.db.add(artifact)
        await self.db.flush()
        for artifact in artifacts:
            self.db.add(WorkflowStepArtifactModel(step_run_id=run.id, artifact_id=artifact.id, role='output'))
        run.status = 'skipped' if skipped else ('completed_with_warning' if warning else 'completed')
        run.warning = warning
        run.output_payload = redact(output_payload) if output_payload is not None else None
        if skipped:
            run.output_payload = {**(run.output_payload or {}), '_skipped': True}
        self._finish(run)
        await self.db.commit()
        return artifacts

    @staticmethod
    def _finish(run):
        run.completed_at = datetime.now(UTC)
        start = run.started_at.replace(tzinfo=UTC) if run.started_at.tzinfo is None else run.started_at
        run.duration_ms = max(0, int((run.completed_at - start).total_seconds() * 1000))

    async def fail(self, run, error, status='failed'):
        if status not in {'failed', 'interrupted', 'cancelled'}:
            raise ValueError('Invalid failure status')
        await self.assert_lease()
        run.status, run.error_message = status, str(error)
        self._finish(run)
        await self.db.commit()

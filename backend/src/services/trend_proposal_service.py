from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import ConflictException, NotFoundException, ValidationException
from src.domain.content_modes import resolve_content_mode
from src.domain.enums import TaskStatus
from src.models.project import ProjectModel
from src.models.task import TaskModel
from src.models.trend import (
    TopicProposalModel,
    TrendItemModel,
    TrendObservationModel,
    TrendProjectMatchModel,
    TrendRunModel,
    TrendSourceRunModel,
)
from src.schemas.generation import ContentBrief
from src.schemas.task import TaskCreate
from src.schemas.trend import (
    TrendProposalApproveRequest,
    TrendProposalCreate,
    TrendProposalResponse,
    TrendProposalUpdate,
)
from src.services.task_service import TaskService
from src.services.template_catalog import template_catalog
from src.services.trend_common import as_utc, build_trend_snapshot


class TrendProposalServiceMixin:
    """Proposal lifecycle mixed into the TrendService facade."""

    async def create_proposal(self, payload: TrendProposalCreate) -> TrendProposalResponse:
        """Create or return the review record for one selected hotspot.

        Proposal creation only reads the latest persisted trend snapshot.  It
        never calls a source adapter or a generation provider, so selecting a
        hotspot remains a fast, deterministic review action.
        """

        project = await self.session.get(ProjectModel, payload.project_id)
        if project is None:
            raise NotFoundException("Project", payload.project_id)
        existing = await self.session.scalar(
            select(TopicProposalModel).where(
                TopicProposalModel.project_id == payload.project_id,
                TopicProposalModel.trend_item_id == payload.trend_item_id,
            )
        )
        if existing is not None:
            return self._proposal_response(existing)

        item = await self.session.get(TrendItemModel, payload.trend_item_id)
        if item is None:
            raise NotFoundException("Trend item", payload.trend_item_id)
        observation, source_run, latest_run = await self._latest_observation(item.id)
        if observation is None or source_run is None or latest_run is None:
            raise ValidationException("该热点不在最新可用快照中，请刷新热点列表后重试。")

        match = await self.session.scalar(
            select(TrendProjectMatchModel)
            .where(
                TrendProjectMatchModel.run_id == latest_run.id,
                TrendProjectMatchModel.project_id == project.id,
                TrendProjectMatchModel.trend_item_id == item.id,
            )
            .order_by(TrendProjectMatchModel.evaluated_at.desc())
            .limit(1)
        )
        source_snapshot = build_trend_snapshot(
            title=item.title,
            platform=observation.platform,
            rank=observation.rank,
            raw_metric=observation.raw_metric,
            metric_unit=observation.metric_unit,
            source_url=observation.source_url,
            fetched_at=observation.fetched_at,
            source_status=self._public_source_status(source_run.status),
            source_key=source_run.source_key,
            adapter_name=source_run.adapter_name,
            run_id=latest_run.id,
        )
        relation = match.relation if match else "unknown"
        match_reason = match.match_reason if match else "项目尚未配置趋势偏好关键词。"
        matched_keywords = list(match.matched_keywords or []) if match else []
        proposal_title = item.title.strip()[:255]
        angle = (payload.angle or "").strip() or self._default_angle(proposal_title, relation)
        brief = payload.content_brief or self._default_content_brief(
            proposal_title, angle, observation.source_url
        )
        options = self._normalize_generation_options(payload.generation_options)
        now = datetime.now(UTC)
        proposal = TopicProposalModel(
            id=f"proposal_{uuid.uuid4().hex[:12]}",
            project_id=project.id,
            trend_item_id=item.id,
            trend_run_id=latest_run.id,
            trend_observation_id=observation.id,
            revision=1,
            status="draft",
            title=proposal_title,
            angle=angle,
            match_reason=match_reason,
            matched_keywords=matched_keywords,
            trend_snapshot=source_snapshot,
            content_brief=brief.model_dump(),
            generation_options=options,
            created_at=now,
            updated_at=now,
        )
        self.session.add(proposal)
        try:
            await self.session.commit()
        except IntegrityError:
            # A double click or two browser tabs may race on the unique
            # project/item key.  Return the winner as an idempotent create.
            await self.session.rollback()
            existing = await self.session.scalar(
                select(TopicProposalModel).where(
                    TopicProposalModel.project_id == payload.project_id,
                    TopicProposalModel.trend_item_id == payload.trend_item_id,
                )
            )
            if existing is None:
                raise
            return self._proposal_response(existing)
        return self._proposal_response(proposal)

    async def update_proposal(
        self, proposal_id: str, payload: TrendProposalUpdate
    ) -> TrendProposalResponse:
        proposal = await self.session.get(TopicProposalModel, proposal_id)
        if proposal is None:
            raise NotFoundException("Topic proposal", proposal_id)
        if proposal.task_id:
            raise ValidationException("任务已经创建，不能再修改该提案。")
        self._assert_revision(proposal, payload.expected_revision)
        if proposal.status != "draft":
            raise ConflictException("该提案正在处理，请刷新后重试。")

        next_title = proposal.title
        next_angle = proposal.angle
        next_content_brief = dict(proposal.content_brief or {})
        next_options = dict(proposal.generation_options or {})
        if payload.title is not None and payload.title.strip() != proposal.title:
            next_title = payload.title.strip()
        if payload.angle is not None and payload.angle.strip() != proposal.angle:
            next_angle = payload.angle.strip()
        if payload.content_brief is not None:
            next_content_brief = payload.content_brief.model_dump()
        if payload.generation_options is not None:
            next_options = self._normalize_generation_options(payload.generation_options)

        values = {
            "title": next_title,
            "angle": next_angle,
            "content_brief": next_content_brief,
            "generation_options": next_options,
            "revision": TopicProposalModel.revision + 1,
            "updated_at": datetime.now(UTC),
        }
        result = await self.session.execute(
            update(TopicProposalModel)
            .where(
                TopicProposalModel.id == proposal_id,
                TopicProposalModel.revision == payload.expected_revision,
                TopicProposalModel.status == "draft",
                TopicProposalModel.task_id.is_(None),
            )
            .values(**values)
        )
        if result.rowcount != 1:
            await self.session.rollback()
            current = await self.session.get(TopicProposalModel, proposal_id)
            if current and current.task_id:
                raise ValidationException("任务已经创建，不能再修改该提案。")
            raise ConflictException("提案版本已发生变化，请刷新后重试。")
        await self.session.commit()
        proposal = await self.session.get(TopicProposalModel, proposal_id)
        if proposal is None:
            raise NotFoundException("Topic proposal", proposal_id)
        return self._proposal_response(proposal)

    async def approve_proposal(
        self, proposal_id: str, payload: TrendProposalApproveRequest
    ) -> tuple[TrendProposalResponse, Any]:
        """Atomically create exactly one normal Task for a proposal revision."""

        proposal = await self.session.get(TopicProposalModel, proposal_id)
        if proposal is None:
            raise NotFoundException("Topic proposal", proposal_id)
        if proposal.task_id:
            task = await self.session.get(TaskModel, proposal.task_id)
            if task is None:
                # A manually removed or otherwise orphaned task must not leave
                # the proposal permanently locked in task_created state.
                proposal.task_id = None
                proposal.status = "draft"
                proposal.updated_at = datetime.now(UTC)
                # Persist the repair before validating/building the replacement
                # Task.  Otherwise a later validation error rolls the repair
                # back together with the failed approval attempt.
                await self.session.commit()
                proposal = await self.session.get(TopicProposalModel, proposal_id)
                if proposal is None:
                    raise NotFoundException("Topic proposal", proposal_id)
            else:
                return self._proposal_response(proposal), task
        self._assert_revision(proposal, payload.expected_revision)
        if proposal.status != "draft":
            raise ConflictException("该提案正在处理，请刷新后重试。")
        result = await self.session.execute(
            update(TopicProposalModel)
            .where(
                TopicProposalModel.id == proposal.id,
                TopicProposalModel.revision == payload.expected_revision,
                TopicProposalModel.status == "draft",
                TopicProposalModel.task_id.is_(None),
            )
            .values(status="approving", updated_at=datetime.now(UTC))
        )
        if result.rowcount != 1:
            await self.session.rollback()
            current = await self.session.get(TopicProposalModel, proposal_id)
            if current and current.task_id:
                task = await self.session.get(TaskModel, current.task_id)
                if task:
                    return self._proposal_response(current), task
            raise ConflictException("提案版本已发生变化，请刷新后重试。")
        await self.session.flush()
        proposal = await self.session.get(TopicProposalModel, proposal_id)
        if proposal is None:
            raise NotFoundException("Topic proposal", proposal_id)

        project = await self.session.get(ProjectModel, proposal.project_id)
        if project is None:
            raise NotFoundException("Project", proposal.project_id)
        project_template = getattr(project, "template", None)
        project_template_item = template_catalog.get(getattr(project_template, "template_id", None))
        options = self._normalize_generation_options(
            proposal.generation_options,
            template_type=(project_template_item or {}).get("template_type"),
        )
        target_scene_count = options["target_scene_count"]
        enable_research = options["enable_research"]
        brief = ContentBrief.model_validate(proposal.content_brief or {})
        task_payload = {
            "topic": proposal.title,
            "content_brief": brief.model_dump(),
            "trend_provenance": {
                "proposal_id": proposal.id,
                "proposal_revision": proposal.revision,
                "trend_item_id": proposal.trend_item_id,
                "trend_run_id": proposal.trend_run_id,
                "trend_observation_id": proposal.trend_observation_id,
                "match_reason": proposal.match_reason,
                "matched_keywords": list(proposal.matched_keywords or []),
                "snapshot": dict(proposal.trend_snapshot or {}),
            },
            "target_scene_count": target_scene_count,
            "enable_research": enable_research,
            "research_max_queries": options["research_max_queries"],
            "research_max_results": options["research_max_results"],
        }
        for key in (
            "template_id",
            "content_mode",
            "genre",
            "hook_type",
            "style_preset",
            "prompt_prefix",
            "voice_id",
            "speed",
            "voice_speed",
            "bgm_enabled",
            "bgm_asset_id",
            "bgm_volume",
            "source_asset_id",
        ):
            if key in options:
                task_payload[key] = options[key]
        if options.get("search_provider_id"):
            task_payload["search_provider_id"] = str(options["search_provider_id"])[:100]

        try:
            task = await TaskService(self.session).build_task(
                project.id,
                TaskCreate(
                    title=proposal.title,
                    description=proposal.angle,
                    input_payload=task_payload,
                    target_scene_count=target_scene_count,
                    enable_research=enable_research,
                    research_max_queries=task_payload["research_max_queries"],
                    research_max_results=task_payload["research_max_results"],
                    search_provider_id=task_payload.get("search_provider_id"),
                ),
            )
        except Exception:
            # Do not leave an "approving" marker behind when task validation
            # rejects project/template/provider settings.
            await self.session.rollback()
            raise
        self.session.add(task)
        proposal.task_id = task.id
        proposal.status = "task_created"
        proposal.updated_at = datetime.now(UTC)
        await self.session.commit()
        return self._proposal_response(proposal), task

    async def reject_proposal(
        self, proposal_id: str, expected_revision: int
    ) -> TrendProposalResponse:
        proposal = await self.session.get(TopicProposalModel, proposal_id)
        if proposal is None:
            raise NotFoundException("Topic proposal", proposal_id)
        self._assert_revision(proposal, expected_revision)
        if proposal.task_id:
            raise ValidationException("任务已经创建，不能拒绝该提案。")
        if proposal.status != "draft":
            raise ConflictException("该提案正在处理，请刷新后重试。")
        result = await self.session.execute(
            update(TopicProposalModel)
            .where(
                TopicProposalModel.id == proposal_id,
                TopicProposalModel.revision == expected_revision,
                TopicProposalModel.status == "draft",
                TopicProposalModel.task_id.is_(None),
            )
            .values(status="rejected", updated_at=datetime.now(UTC))
        )
        if result.rowcount != 1:
            await self.session.rollback()
            raise ConflictException("提案版本已发生变化，请刷新后重试。")
        await self.session.commit()
        proposal = await self.session.get(TopicProposalModel, proposal_id)
        if proposal is None:
            raise NotFoundException("Topic proposal", proposal_id)
        return self._proposal_response(proposal)

    async def mark_proposal_queue_failed(
        self, proposal_id: str, error_message: str
    ) -> tuple[TrendProposalResponse, Any | None]:
        proposal = await self.session.get(TopicProposalModel, proposal_id)
        if proposal is None:
            raise NotFoundException("Topic proposal", proposal_id)
        task = await self.session.get(TaskModel, proposal.task_id) if proposal.task_id else None
        proposal.status = "queue_failed"
        if task is not None:
            task.status = TaskStatus.DRAFT.value
            task.error_message = error_message[:2000]
        proposal.updated_at = datetime.now(UTC)
        await self.session.commit()
        return self._proposal_response(proposal), task

    async def mark_proposal_queue_queued(self, proposal_id: str) -> TrendProposalResponse:
        proposal = await self.session.get(TopicProposalModel, proposal_id)
        if proposal is None:
            raise NotFoundException("Topic proposal", proposal_id)
        if proposal.task_id:
            proposal.status = "task_created"
            proposal.updated_at = datetime.now(UTC)
            await self.session.commit()
        return self._proposal_response(proposal)

    async def _latest_observation(self, trend_item_id: str):
        latest_run = await self.session.scalar(
            select(TrendRunModel).order_by(TrendRunModel.started_at.desc()).limit(1)
        )
        if latest_run is None:
            return None, None, None
        row = (
            await self.session.execute(
                select(TrendObservationModel, TrendSourceRunModel)
                .join(
                    TrendSourceRunModel,
                    TrendSourceRunModel.id == TrendObservationModel.source_run_id,
                )
                .where(
                    TrendObservationModel.run_id == latest_run.id,
                    TrendObservationModel.trend_item_id == trend_item_id,
                    TrendObservationModel.status.in_(["fresh", "stale"]),
                )
                .order_by(TrendObservationModel.fetched_at.desc(), TrendObservationModel.rank.asc())
                .limit(1)
            )
        ).first()
        if row is None:
            return None, None, latest_run
        return row[0], row[1], latest_run

    @staticmethod
    def _assert_revision(proposal: TopicProposalModel, expected_revision: int) -> None:
        if proposal.revision != expected_revision:
            raise ConflictException(
                f"提案版本已更新（当前 revision={proposal.revision}），请刷新后重试。"
            )

    @staticmethod
    def _default_angle(title: str, relation: str) -> str:
        if relation == "high":
            return f"从项目视角拆解“{title}”的关键变化与可执行启发"
        if relation == "medium":
            return f"用项目已有能力解释“{title}”为什么值得关注"
        return f"核验“{title}”的事实边界，再给出克制的背景解读"

    @staticmethod
    def _default_content_brief(title: str, angle: str, source_url: str | None) -> ContentBrief:
        return ContentBrief(
            audience="对科技和热点感兴趣的普通用户",
            goal=f"围绕“{title}”制作一条有来源、有边界的短视频",
            angle=angle,
            tone="清晰、克制、易懂",
            language="zh-CN",
            key_points=[title],
            uncertainty="热点信息可能快速变化，生成后请核验原始来源。",
            source_refs=[source_url] if source_url else [],
            production_constraints=["保留来源核验提示", "避免未经证实的绝对化结论"],
        )

    @staticmethod
    def _normalize_generation_options(
        options: dict[str, Any] | None,
        *,
        template_type: str | None = None,
    ) -> dict[str, Any]:
        values = dict(options or {})
        template_id = str(values.get("template_id") or "").strip()[:100] or None
        template = template_catalog.get(template_id) if template_id else None
        content_mode = resolve_content_mode(
            values.get("content_mode"),
            template_type=(template or {}).get("template_type") or template_type,
        )

        def bounded(key: str, default: int, minimum: int, maximum: int) -> int:
            if key not in values or values[key] is None:
                return default
            try:
                value = int(values[key])
            except (TypeError, ValueError) as exc:
                raise ValidationException(f"{key} 必须是数字。") from exc
            if not minimum <= value <= maximum:
                raise ValidationException(f"{key} 必须在 {minimum} 到 {maximum} 之间。")
            return value

        def bounded_float(
            key: str, value: Any, default: float, minimum: float, maximum: float
        ) -> float:
            if value is None:
                return default
            try:
                parsed = float(value)
            except (TypeError, ValueError) as exc:
                raise ValidationException(f"{key} 必须是数字。") from exc
            if not minimum <= parsed <= maximum:
                raise ValidationException(f"{key} 必须在 {minimum} 到 {maximum} 之间。")
            return round(parsed, 3)

        def as_bool(value: Any, default: bool) -> bool:
            if value is None:
                return default
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"false", "0", "no", "off"}:
                    return False
                if normalized in {"true", "1", "yes", "on"}:
                    return True
            return bool(value)

        def optional_text(key: str, maximum: int) -> str | None:
            value = values.get(key)
            if value is None or value == "":
                return None
            return str(value)[:maximum]

        speed = bounded_float(
            "voice_speed",
            values.get("voice_speed", values.get("speed", 1.0)),
            1.0,
            0.5,
            2.0,
        )

        normalized = {
            "target_scene_count": bounded("target_scene_count", 8, 8, 20),
            "enable_research": as_bool(values.get("enable_research"), True),
            "research_max_queries": bounded("research_max_queries", 3, 1, 3),
            "research_max_results": bounded("research_max_results", 5, 1, 5),
            "content_mode": content_mode[:100],
            "genre": str(values.get("genre") or "auto")[:100],
            "hook_type": str(values.get("hook_type") or "auto")[:100],
            "style_preset": str(values.get("style_preset") or "stick_figure")[:100],
            "prompt_prefix": str(values.get("prompt_prefix") or "")[:1000],
            "voice_id": optional_text("voice_id", 100),
            "speed": speed,
            "voice_speed": speed,
            "bgm_enabled": as_bool(values.get("bgm_enabled"), True),
            "bgm_asset_id": optional_text("bgm_asset_id", 100),
            "bgm_volume": bounded_float("bgm_volume", values.get("bgm_volume", 0.2), 0.2, 0.0, 0.5),
            "source_asset_id": optional_text("source_asset_id", 100),
        }
        if values.get("search_provider_id"):
            normalized["search_provider_id"] = str(values["search_provider_id"])[:100]
        if template_id:
            normalized["template_id"] = template_id
        return normalized

    @staticmethod
    def _proposal_response(proposal: TopicProposalModel) -> TrendProposalResponse:
        return TrendProposalResponse(
            id=proposal.id,
            project_id=proposal.project_id,
            trend_item_id=proposal.trend_item_id,
            trend_run_id=proposal.trend_run_id,
            trend_observation_id=proposal.trend_observation_id,
            task_id=proposal.task_id,
            revision=proposal.revision,
            status=proposal.status,
            title=proposal.title,
            angle=proposal.angle,
            match_reason=proposal.match_reason,
            matched_keywords=list(proposal.matched_keywords or []),
            trend_snapshot=dict(proposal.trend_snapshot or {}),
            content_brief=ContentBrief.model_validate(proposal.content_brief or {}),
            generation_options=TrendProposalServiceMixin._normalize_generation_options(
                proposal.generation_options
            ),
            created_at=as_utc(proposal.created_at),
            updated_at=as_utc(proposal.updated_at),
        )

from __future__ import annotations

import asyncio
import re
import unicodedata
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictException, NotFoundException, ValidationException
from src.models.project import ProjectModel
from src.models.trend import (
    TopicProposalModel,
    TrendItemModel,
    TrendObservationModel,
    TrendProjectMatchModel,
    TrendRunModel,
    TrendSourceRunModel,
)
from src.schemas.trend import (
    TrendFeedResponse,
    TrendItemResponse,
    TrendPreferencesResponse,
    TrendPreferencesUpdate,
    TrendRunResponse,
    TrendSourceRunResponse,
)
from src.services.trend_common import (
    PLATFORM_LABELS,
    as_utc,
    build_trend_snapshot,
    clean_terms,
    prefer_match,
    relation_priority,
)
from src.services.trend_proposal_service import TrendProposalServiceMixin
from src.services.trend_sources import TrendSourceAdapter, TrendSourceResult

FRESHNESS_WINDOWS = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "all": None,
}


def build_trend_run_response(
    run: TrendRunModel,
    sources: Sequence[TrendSourceRunModel] = (),
) -> TrendRunResponse:
    """Serialize a run consistently for feed and subscription responses."""

    return TrendRunResponse(
        id=run.id,
        status=run.status,
        requested_platforms=list(run.requested_platforms or []),
        source_count=run.source_count,
        success_count=run.success_count,
        stale_count=run.stale_count,
        error_count=run.error_count,
        error_summary=run.error_summary,
        fetched_at=as_utc(run.fetched_at),
        started_at=as_utc(run.started_at),
        completed_at=as_utc(run.completed_at),
        subscription_id=run.subscription_id,
        trigger_key=run.trigger_key,
        sources=[
            TrendSourceRunResponse(
                id=source.id,
                source_key=source.source_key,
                adapter_name=source.adapter_name,
                platform=source.platform,
                status=source.status,
                item_count=source.item_count,
                fetched_at=as_utc(source.fetched_at),
                source_updated_at=as_utc(source.source_updated_at),
                error_message=source.error_message,
            )
            for source in sources
        ],
    )


def normalize_trend_title(value: str) -> str:
    """Build a stable identity without pretending that platform metrics are comparable."""

    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    normalized = re.sub(r"\s+", " ", normalized)
    key = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized, flags=re.UNICODE)
    return (key or normalized)[:255]


def _project_trend_preferences(project: ProjectModel) -> dict[str, list[str]]:
    settings = (
        project.default_production_settings
        if isinstance(project.default_production_settings, dict)
        else {}
    )
    raw = settings.get("trends") if isinstance(settings.get("trends"), dict) else {}
    include = raw.get("include_keywords", raw.get("keywords", []))
    exclude = raw.get("exclude_keywords", [])
    platforms = raw.get("platforms", [])
    return {
        "include_keywords": clean_terms(include if isinstance(include, list) else [include]),
        "exclude_keywords": clean_terms(exclude if isinstance(exclude, list) else [exclude]),
        "platforms": clean_terms(platforms if isinstance(platforms, list) else [platforms]),
    }


class TrendService(TrendProposalServiceMixin):
    """Persist adapter results and expose conservative, explainable trend matching."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def collect(
        self,
        adapters: Sequence[TrendSourceAdapter],
        *,
        subscription_id: str | None = None,
        trigger_key: str | None = None,
        run_id: str | None = None,
        fetch_timeout_seconds: float | None = None,
    ) -> TrendRunResponse:
        async def fetch_one(adapter: TrendSourceAdapter) -> TrendSourceResult:
            try:
                fetch = adapter.fetch()
                result = (
                    await asyncio.wait_for(fetch, timeout=fetch_timeout_seconds)
                    if fetch_timeout_seconds is not None
                    else await fetch
                )
                return result
            except TimeoutError:
                timeout = max(0.1, float(fetch_timeout_seconds or 0))
                return TrendSourceResult(
                    source_key=getattr(adapter, "source_key", "unknown"),
                    adapter_name=adapter.__class__.__name__,
                    platform=getattr(adapter, "platform", "unknown"),
                    status="failed",
                    error_message=f"source fetch 超时（{timeout:g}s）。",
                )
            except Exception as exc:  # adapter failures are recorded, never hidden
                return TrendSourceResult(
                    source_key=getattr(adapter, "source_key", "unknown"),
                    adapter_name=adapter.__class__.__name__,
                    platform=getattr(adapter, "platform", "unknown"),
                    status="failed",
                    error_message=str(exc),
                )

        # Public hot-list sources are independent.  Fetching them together
        # keeps a seven-platform refresh bounded by the slowest source rather
        # than the sum of all source timeouts.
        results = list(await asyncio.gather(*(fetch_one(adapter) for adapter in adapters)))
        if not results and not adapters:
            results.append(
                TrendSourceResult(
                    source_key="trend-registry",
                    adapter_name="TrendSourceRegistry",
                    platform="unknown",
                    status="unavailable",
                    error_message="没有注册可用的趋势 source adapter。",
                )
            )
        return await self.persist_results(
            results,
            subscription_id=subscription_id,
            trigger_key=trigger_key,
            run_id=run_id,
        )

    async def get_preferences(self, project_id: str) -> TrendPreferencesResponse:
        project = await self.session.get(ProjectModel, project_id)
        if project is None:
            raise NotFoundException("Project", project_id)
        preferences = _project_trend_preferences(project)
        return TrendPreferencesResponse(project_id=project_id, **preferences)

    async def update_preferences(
        self, project_id: str, payload: TrendPreferencesUpdate
    ) -> TrendPreferencesResponse:
        project = await self.session.get(ProjectModel, project_id)
        if project is None:
            raise NotFoundException("Project", project_id)

        existing = (
            dict(project.default_production_settings)
            if isinstance(project.default_production_settings, dict)
            else {}
        )
        trend_settings = (
            dict(existing.get("trends")) if isinstance(existing.get("trends"), dict) else {}
        )
        if "include_keywords" in payload.model_fields_set:
            trend_settings["include_keywords"] = clean_terms(payload.include_keywords)
        if "exclude_keywords" in payload.model_fields_set:
            trend_settings["exclude_keywords"] = clean_terms(payload.exclude_keywords)
        if "platforms" in payload.model_fields_set:
            trend_settings["platforms"] = clean_terms(payload.platforms)

        # Preserve every unrelated project setting while replacing only this namespace.
        project.default_production_settings = {**existing, "trends": trend_settings}
        await self.session.flush()
        await self._refresh_project_matches(project)
        await self.session.commit()
        return TrendPreferencesResponse(
            project_id=project_id,
            **_project_trend_preferences(project),
        )

    async def _refresh_project_matches(self, project: ProjectModel) -> None:
        """Re-evaluate the latest run after a project preference change."""

        latest_run = await self.session.scalar(
            select(TrendRunModel).order_by(TrendRunModel.started_at.desc()).limit(1)
        )
        if latest_run is None:
            return

        rows = (
            await self.session.execute(
                select(TrendObservationModel, TrendItemModel)
                .join(TrendItemModel, TrendItemModel.id == TrendObservationModel.trend_item_id)
                .where(
                    TrendObservationModel.run_id == latest_run.id,
                    TrendObservationModel.status.in_(["fresh", "stale"]),
                )
            )
        ).all()
        if not rows:
            return

        existing = {
            match.trend_item_id: match
            for match in (
                await self.session.scalars(
                    select(TrendProjectMatchModel).where(
                        TrendProjectMatchModel.run_id == latest_run.id,
                        TrendProjectMatchModel.project_id == project.id,
                    )
                )
            ).all()
        }
        aggregated: dict[str, tuple[str, str, list[str]]] = {}
        for observation, item in rows:
            candidate = self._match_project(project, item.title, observation.platform)
            aggregated[item.id] = prefer_match(aggregated.get(item.id), candidate)

        evaluated_at = datetime.now(UTC)
        for item_id, (relation, reason, matched_keywords) in aggregated.items():
            match = existing.get(item_id)
            if match is None:
                self.session.add(
                    TrendProjectMatchModel(
                        id=f"trend_match_{uuid.uuid4().hex[:12]}",
                        run_id=latest_run.id,
                        project_id=project.id,
                        trend_item_id=item_id,
                        relation=relation,
                        match_reason=reason,
                        matched_keywords=matched_keywords,
                        evaluated_at=evaluated_at,
                    )
                )
                continue
            match.relation = relation
            match.match_reason = reason
            match.matched_keywords = matched_keywords
            match.evaluated_at = evaluated_at

    async def list_feed(
        self,
        *,
        project_id: str | None = None,
        platform: str | None = None,
        freshness: str = "24h",
    ) -> TrendFeedResponse:
        if freshness not in FRESHNESS_WINDOWS:
            raise ValidationException("热点新鲜度必须是 15m、1h、6h、24h 或 all。")
        if project_id and await self.session.get(ProjectModel, project_id) is None:
            raise NotFoundException("Project", project_id)

        latest_run = await self.session.scalar(
            select(TrendRunModel).order_by(TrendRunModel.started_at.desc()).limit(1)
        )
        if latest_run is None:
            return TrendFeedResponse(
                status="unavailable",
                source_message="暂无采集运行；请先接入一个趋势 source adapter。",
            )

        cutoff = None
        if FRESHNESS_WINDOWS[freshness] is not None:
            cutoff = datetime.now(UTC) - FRESHNESS_WINDOWS[freshness]

        stmt = (
            select(TrendObservationModel, TrendSourceRunModel, TrendItemModel)
            .join(
                TrendSourceRunModel,
                TrendSourceRunModel.id == TrendObservationModel.source_run_id,
            )
            .join(TrendItemModel, TrendItemModel.id == TrendObservationModel.trend_item_id)
            .where(
                TrendObservationModel.run_id == latest_run.id,
                TrendObservationModel.status.in_(["fresh", "stale"]),
            )
            .order_by(TrendObservationModel.fetched_at.desc(), TrendObservationModel.rank.asc())
        )
        if platform and platform != "all":
            stmt = stmt.where(TrendObservationModel.platform == platform)
        if cutoff is not None:
            stmt = stmt.where(TrendObservationModel.fetched_at >= cutoff)

        rows = (await self.session.execute(stmt)).all()
        selected: list[tuple[TrendObservationModel, TrendSourceRunModel, TrendItemModel]] = []
        seen: set[tuple[str, str]] = set()
        for observation, source_run, item in rows:
            key = (item.id, observation.platform)
            if key in seen:
                continue
            seen.add(key)
            selected.append((observation, source_run, item))

        matches: dict[str, TrendProjectMatchModel] = {}
        if project_id and selected:
            item_ids = {item.id for _, _, item in selected}
            run_ids = {observation.run_id for observation, _, _ in selected}
            match_stmt = (
                select(TrendProjectMatchModel)
                .where(
                    TrendProjectMatchModel.project_id == project_id,
                    TrendProjectMatchModel.trend_item_id.in_(item_ids),
                    TrendProjectMatchModel.run_id.in_(run_ids),
                )
                .order_by(TrendProjectMatchModel.evaluated_at.desc())
            )
            for match in (await self.session.scalars(match_stmt)).all():
                matches.setdefault(match.trend_item_id, match)

        items = [
            TrendItemResponse(
                id=item.id,
                title=item.title,
                platform=observation.platform,
                platform_label=PLATFORM_LABELS.get(observation.platform, observation.platform),
                rank=observation.rank,
                raw_metric=observation.raw_metric,
                metric_unit=observation.metric_unit,
                fetched_at=as_utc(observation.fetched_at),
                source_url=observation.source_url,
                project_relevance=(
                    matches.get(item.id).relation if item.id in matches else "unknown"
                ),
                source_status=self._public_source_status(source_run.status),
                risk_note=self._risk_note(source_run.status),
                summary=self._source_summary(source_run),
            )
            for observation, source_run, item in selected
        ]

        source_runs = (
            await self.session.scalars(
                select(TrendSourceRunModel).where(TrendSourceRunModel.run_id == latest_run.id)
            )
        ).all()
        has_stale_source = any(
            source.status in {"stale", "failed", "unavailable"} for source in source_runs
        )
        if latest_run.status == "failed" or not source_runs:
            feed_status = "unavailable"
        elif latest_run.status == "partial" or has_stale_source:
            feed_status = "stale"
        else:
            feed_status = "ready"

        return TrendFeedResponse(
            status=feed_status,
            items=items,
            fetched_at=as_utc(latest_run.fetched_at),
            source_message=latest_run.error_summary,
        )

    async def list_runs(
        self, limit: int = 20, *, run_id: str | None = None
    ) -> list[TrendRunResponse]:
        stmt = select(TrendRunModel).order_by(TrendRunModel.started_at.desc())
        if run_id:
            stmt = stmt.where(TrendRunModel.id == run_id)
        runs = (await self.session.scalars(stmt.limit(max(1, min(limit, 100))))).all()
        if not runs:
            return []
        source_rows = (
            await self.session.scalars(
                select(TrendSourceRunModel)
                .where(TrendSourceRunModel.run_id.in_({run.id for run in runs}))
                .order_by(TrendSourceRunModel.created_at.asc())
            )
        ).all()
        source_map: dict[str, list[TrendSourceRunModel]] = {}
        for source in source_rows:
            source_map.setdefault(source.run_id, []).append(source)
        return [build_trend_run_response(run, source_map.get(run.id, [])) for run in runs]

    async def persist_results(
        self,
        results: Sequence[TrendSourceResult],
        *,
        subscription_id: str | None = None,
        trigger_key: str | None = None,
        run_id: str | None = None,
    ) -> TrendRunResponse:
        source_keys = [result.source_key for result in results]
        if len(source_keys) != len(set(source_keys)):
            raise ValidationException("一次采集运行中的 source_key 必须唯一。")

        now = datetime.now(UTC)
        run = await self.session.get(TrendRunModel, run_id) if run_id else None
        if run is None:
            run = TrendRunModel(
                id=run_id or f"trend_run_{uuid.uuid4().hex[:12]}",
                status="running",
                requested_platforms=sorted({result.platform for result in results}),
                source_count=len(results),
                started_at=now,
                created_at=now,
                subscription_id=subscription_id,
                trigger_key=trigger_key,
            )
            self.session.add(run)
            await self.session.flush()
        else:
            if run.subscription_id != subscription_id or run.trigger_key != trigger_key:
                raise ValidationException("趋势运行 provenance 与订阅触发槽不一致。")
            if run.status != "running":
                # Lease recovery may have fenced this attempt while an old
                # adapter request was still in flight.  Its late result must
                # never revive a stale/failed run or overwrite the next slot.
                raise ConflictException("趋势运行租约已失效，结果不会覆盖恢复运行。")
            # A scheduler creates this row before the external fetch.  Reset
            # counters when the normalized source results arrive, preserving
            # the original started_at for durable restart ordering.
            run.status = "running"
            run.requested_platforms = sorted({result.platform for result in results})
            run.source_count = len(results)
            run.success_count = 0
            run.stale_count = 0
            run.error_count = 0
            run.error_summary = None
            run.fetched_at = None
            run.completed_at = None

        projects = list((await self.session.scalars(select(ProjectModel))).all())
        canonical_keys = {
            normalize_trend_title(item.title)
            for result in results
            if result.status in {"fresh", "stale"}
            for item in self._dedupe_source_items(result.items)
        }
        existing_items = {}
        if canonical_keys:
            existing_items = {
                item.canonical_key: item
                for item in (
                    await self.session.scalars(
                        select(TrendItemModel).where(
                            TrendItemModel.canonical_key.in_(canonical_keys)
                        )
                    )
                ).all()
            }

        errors: list[str] = []
        fetched_times: list[datetime] = []
        match_cache: dict[tuple[str, str], TrendProjectMatchModel] = {}
        latest_project_observations: dict[
            str, tuple[TrendObservationModel, TrendSourceRunModel, TrendSourceResult]
        ] = {}
        for result in results:
            status = (
                result.status
                if result.status in {"fresh", "stale", "failed", "unavailable"}
                else "failed"
            )
            fetched_at = as_utc(result.fetched_at) or now
            fetched_times.append(fetched_at)
            source_items = (
                self._dedupe_source_items(result.items) if status in {"fresh", "stale"} else []
            )
            source_run = TrendSourceRunModel(
                id=f"trend_source_{uuid.uuid4().hex[:12]}",
                run_id=run.id,
                source_key=result.source_key,
                adapter_name=result.adapter_name,
                platform=result.platform,
                status=status,
                item_count=len(source_items),
                fetched_at=fetched_at,
                source_updated_at=as_utc(result.source_updated_at),
                error_message=result.error_message,
                metadata_json=result.metadata or {},
                created_at=now,
            )
            self.session.add(source_run)
            await self.session.flush()

            if status == "fresh":
                run.success_count += 1
            elif status == "stale":
                run.stale_count += 1
            else:
                run.error_count += 1
            if result.error_message:
                errors.append(f"{result.source_key}: {result.error_message}")

            for item_input in source_items:
                canonical_key = normalize_trend_title(item_input.title)
                item = existing_items.get(canonical_key)
                if item is None:
                    item = TrendItemModel(
                        id=f"trend_item_{uuid.uuid4().hex[:12]}",
                        canonical_key=canonical_key,
                        title=item_input.title.strip(),
                        created_at=now,
                        updated_at=now,
                    )
                    self.session.add(item)
                    existing_items[canonical_key] = item
                    await self.session.flush()
                elif item.title != item_input.title.strip():
                    item.title = item_input.title.strip()
                    item.updated_at = now

                observation = TrendObservationModel(
                    id=f"trend_observation_{uuid.uuid4().hex[:12]}",
                    run_id=run.id,
                    source_run_id=source_run.id,
                    trend_item_id=item.id,
                    platform=result.platform,
                    rank=item_input.rank,
                    raw_metric=self._metric_as_string(item_input.raw_metric),
                    metric_unit=item_input.metric_unit,
                    source_url=item_input.source_url,
                    status=status,
                    fetched_at=fetched_at,
                    source_updated_at=(
                        as_utc(item_input.source_updated_at) or as_utc(result.source_updated_at)
                    ),
                    published_at=as_utc(item_input.published_at),
                )
                self.session.add(observation)
                previous_observation = latest_project_observations.get(item.id)
                if previous_observation is None or (
                    observation.fetched_at,
                    -observation.rank,
                ) > (
                    previous_observation[0].fetched_at,
                    -previous_observation[0].rank,
                ):
                    latest_project_observations[item.id] = (
                        observation,
                        source_run,
                        result,
                    )
                for project in projects:
                    relation, reason, matched_keywords = self._match_project(
                        project, item_input.title, result.platform
                    )
                    cache_key = (project.id, item.id)
                    previous = match_cache.get(cache_key)
                    if previous is not None:
                        if relation_priority(relation) > relation_priority(previous.relation):
                            previous.relation = relation
                            previous.match_reason = reason
                            previous.matched_keywords = matched_keywords
                        continue
                    match = TrendProjectMatchModel(
                        id=f"trend_match_{uuid.uuid4().hex[:12]}",
                        run_id=run.id,
                        project_id=project.id,
                        trend_item_id=item.id,
                        relation=relation,
                        match_reason=reason,
                        matched_keywords=matched_keywords,
                        evaluated_at=now,
                    )
                    match_cache[cache_key] = match
                    self.session.add(match)

        run.fetched_at = max(fetched_times) if fetched_times else now
        run.error_summary = "; ".join(errors)[:2000] if errors else None
        if run.success_count == 0 and run.stale_count == 0:
            run.status = "failed"
        elif run.error_count or run.stale_count:
            run.status = "partial"
        else:
            run.status = "completed"
        run.completed_at = datetime.now(UTC)
        await self._refresh_open_proposals(
            run,
            latest_project_observations,
            match_cache,
        )
        await self.session.commit()
        # A scheduler-created run may have a synthetic clock in tests or a
        # restored timestamp older than another process's row.  Return the
        # exact run just finalized instead of whichever row happens to sort
        # first globally.
        return (await self.list_runs(limit=1, run_id=run.id))[0]

    async def _refresh_open_proposals(
        self,
        run: TrendRunModel,
        observations: dict[
            str, tuple[TrendObservationModel, TrendSourceRunModel, TrendSourceResult]
        ],
        match_cache: dict[tuple[str, str], TrendProjectMatchModel],
    ) -> None:
        """Move draft proposals to the newest snapshot without duplicating them."""

        if not observations:
            return
        item_ids = set(observations)
        proposals = (
            await self.session.scalars(
                select(TopicProposalModel).where(
                    TopicProposalModel.trend_item_id.in_(item_ids),
                    TopicProposalModel.task_id.is_(None),
                    TopicProposalModel.status == "draft",
                )
            )
        ).all()
        for proposal in proposals:
            observation, source_run, result = observations.get(
                proposal.trend_item_id, (None, None, None)
            )
            if observation is None or source_run is None or result is None:
                continue
            match = match_cache.get((proposal.project_id, proposal.trend_item_id))
            proposal.trend_run_id = run.id
            proposal.trend_observation_id = observation.id
            proposal.trend_snapshot = build_trend_snapshot(
                title=proposal.title,
                platform=result.platform,
                rank=observation.rank,
                raw_metric=observation.raw_metric,
                metric_unit=observation.metric_unit,
                source_url=observation.source_url,
                fetched_at=observation.fetched_at,
                source_status=self._public_source_status(source_run.status),
                source_key=source_run.source_key,
                adapter_name=source_run.adapter_name,
                run_id=run.id,
            )
            if match is not None:
                proposal.match_reason = match.match_reason
                proposal.matched_keywords = list(match.matched_keywords or [])
            proposal.updated_at = datetime.now(UTC)

    @staticmethod
    def _dedupe_source_items(items) -> list:
        by_key = {}
        for item in items:
            title = str(item.title).strip()
            if not title:
                continue
            key = normalize_trend_title(title)
            current = by_key.get(key)
            if current is None or item.rank < current.rank:
                by_key[key] = item
        return sorted(by_key.values(), key=lambda item: item.rank)

    @staticmethod
    def _metric_as_string(value) -> str | None:
        if value is None or value == "":
            return None
        return str(value)

    @staticmethod
    def _match_project(
        project: ProjectModel, title: str, platform: str
    ) -> tuple[str, str, list[str]]:
        preferences = _project_trend_preferences(project)
        if preferences["platforms"] and platform.casefold() not in {
            value.casefold() for value in preferences["platforms"]
        }:
            return "unknown", "该平台不在项目趋势偏好范围内。", []
        if not preferences["include_keywords"]:
            return "unknown", "项目尚未配置趋势偏好关键词。", []

        haystack = unicodedata.normalize("NFKC", title).casefold()
        excluded = [term for term in preferences["exclude_keywords"] if term.casefold() in haystack]
        if excluded:
            return "low", f"命中项目排除词：{', '.join(excluded)}。", []
        matched = [term for term in preferences["include_keywords"] if term.casefold() in haystack]
        if len(matched) >= 2:
            return "high", f"命中 {len(matched)} 个项目趋势关键词：{', '.join(matched)}。", matched
        if matched:
            return "medium", f"命中项目趋势关键词：{matched[0]}。", matched
        return "low", "未命中项目趋势关键词。", []

    @staticmethod
    def _public_source_status(status: str) -> str:
        return "fresh" if status == "fresh" else "stale" if status == "stale" else "unavailable"

    @staticmethod
    def _risk_note(status: str) -> str:
        if status == "stale":
            return "来源标记为可能过期，生成和发布前请核验原始页面。"
        return "平台指标保留来源原始单位，跨平台比较前请先确认口径。"

    @staticmethod
    def _source_summary(source_run: TrendSourceRunModel) -> str | None:
        metadata = source_run.metadata_json if isinstance(source_run.metadata_json, dict) else {}
        summary = metadata.get("summary")
        return str(summary)[:1000] if summary else None

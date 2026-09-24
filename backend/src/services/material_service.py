from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException, ValidationException
from src.domain.enums import AssetType
from src.models.asset import AssetModel
from src.models.project import ProjectAssetBindingModel, ProjectModel
from src.models.scene import SceneModel
from src.models.task import TaskModel
from src.providers.materials import MaterialCandidate, MaterialProvider
from src.providers.materials._http import safe_pexels_page_url
from src.services.asset_service import AssetService
from src.services.media_probe import media_probe_service
from src.services.provider_manager import ProviderManager
from src.services.workflow_execution import WorkflowLeaseLost
from src.storage.local_storage import LocalStorageService, local_storage


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(value) if value is not None else 0
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


_MATERIAL_QUERY_STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "video",
    "footage",
    "stock",
}


def _material_search_keywords(keyword: str, aspect_ratio: str) -> list[str]:
    """Build a short, deterministic fallback chain for stock-video search."""
    normalized = " ".join(str(keyword or "").split())
    keywords: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        value = " ".join(str(value or "").split()).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            keywords.append(value)

    add(normalized)
    english_words = re.findall(r"[A-Za-z0-9]+", normalized)
    if english_words:
        add(" ".join(english_words[:5]))
        focused_words = [
            word for word in english_words if word.casefold() not in _MATERIAL_QUERY_STOP_WORDS
        ]
        add(" ".join(focused_words[:5]))
    else:
        chinese_terms = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
        add(" ".join(chinese_terms[:4]))

    orientation_keyword = {
        "9:16": "vertical stock footage",
        "16:9": "landscape stock footage",
        "1:1": "square stock footage",
    }.get(aspect_ratio, "cinematic stock footage")
    fallback_keywords = (
        orientation_keyword,
        "cinematic stock footage",
        "lifestyle stock footage",
        "nature stock footage",
    )
    for fallback_keyword in fallback_keywords:
        add(fallback_keyword)

    selected = keywords[:3]
    selected_keys = {value.casefold() for value in selected}
    for fallback_keyword in fallback_keywords:
        if fallback_keyword.casefold() not in selected_keys:
            selected.append(fallback_keyword)
            break
    return selected[:4]


@dataclass(frozen=True)
class MaterialSearchRequest:
    keyword: str
    provider_id: str | None = None
    aspect_ratio: str = "9:16"
    min_duration_seconds: float = 0.0
    limit: int = 20
    target_width: int | None = None
    target_height: int | None = None

    def __post_init__(self) -> None:
        keyword = " ".join(str(self.keyword).split())
        if not keyword:
            raise ValidationException("在线素材搜索词不能为空。")
        if self.aspect_ratio not in {"9:16", "16:9", "1:1"}:
            raise ValidationException("不支持的在线素材画幅比例。")
        object.__setattr__(self, "keyword", keyword)
        object.__setattr__(self, "limit", max(1, min(80, int(self.limit))))
        object.__setattr__(self, "min_duration_seconds", max(0.0, float(self.min_duration_seconds)))
        object.__setattr__(self, "target_width", _positive_int(self.target_width))
        object.__setattr__(self, "target_height", _positive_int(self.target_height))


@dataclass(frozen=True)
class MaterialImportRequest:
    candidate_id: str
    provider_id: str | None = None
    task_id: str | None = None
    scene_id: str | None = None
    keyword: str | None = None
    aspect_ratio: str = "9:16"


@dataclass(frozen=True)
class MaterialCandidateResponse:
    candidate_id: str
    provider: str
    external_id: str
    title: str
    source_page_url: str | None = None
    author: str | None = None
    author_url: str | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class MaterialSourceResponse:
    asset_id: str
    provider: str
    external_id: str
    source_page_url: str | None = None
    author: str | None = None
    author_url: str | None = None
    search_keyword: str | None = None
    content_sha256: str | None = None


class MaterialService:
    """Search, import, and provenance-track online stock video assets."""

    CACHE_VERSION = 4
    CACHE_TTL = timedelta(hours=24)
    MAX_CANDIDATES = 80
    _cache_locks: dict[str, asyncio.Lock] = {}

    def __init__(
        self,
        session: AsyncSession,
        storage: LocalStorageService | None = None,
        providers: dict[str, MaterialProvider] | None = None,
        provider_manager: ProviderManager | None = None,
        execution_context=None,
    ) -> None:
        self.session = session
        self.storage = storage or local_storage
        self.asset_service = AssetService(session, storage=self.storage)
        self.providers = providers or {}
        self.provider_manager = provider_manager or ProviderManager(session)
        self.execution_context = execution_context
        self.asset_service.execution_context = execution_context

    @classmethod
    def cache_key(
        cls,
        request: MaterialSearchRequest,
        provider_id: str | None = None,
        provider: MaterialProvider | None = None,
    ) -> str:
        fingerprint = getattr(provider, "cache_fingerprint", {}) if provider else {}
        if not isinstance(fingerprint, dict):
            fingerprint = {}
        safe_fingerprint = {
            str(key): value
            for key, value in fingerprint.items()
            if not any(secret in str(key).lower() for secret in ("key", "secret", "token", "password"))
        }
        raw = json.dumps(
            {
                "cache_version": cls.CACHE_VERSION,
                "provider_id": str(provider_id or request.provider_id or "default"),
                "keyword": request.keyword.casefold(),
                "aspect_ratio": request.aspect_ratio,
                "min_duration_seconds": round(request.min_duration_seconds, 3),
                "limit": request.limit,
                "target_width": request.target_width,
                "target_height": request.target_height,
                "provider": safe_fingerprint,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def candidate_id(cache_key: str, external_id: str) -> str:
        return "mat_" + hashlib.sha256(f"{cache_key}\x1f{external_id}".encode()).hexdigest()[:24]

    @classmethod
    def _cache_item(cls, cache_key: str, candidate: MaterialCandidate) -> dict:
        return {
            "candidate_id": cls.candidate_id(cache_key, candidate.external_id),
            "provider": candidate.provider,
            "external_id": candidate.external_id,
            "title": candidate.title,
            "source_page_url": safe_pexels_page_url(candidate.source_page_url),
            "author": candidate.author,
            "author_url": safe_pexels_page_url(candidate.author_url, author=True),
            "duration_seconds": candidate.duration_seconds,
            "width": candidate.width,
            "height": candidate.height,
        }

    def _cache_path(self, cache_key: str) -> Path:
        return self.storage.get_path(f"cache/material_search/{cache_key}.json")

    @classmethod
    def _cache_is_fresh(cls, payload: object) -> bool:
        if not isinstance(payload, dict) or payload.get("version") != cls.CACHE_VERSION:
            return False
        now = datetime.now(UTC)
        created_at = payload.get("created_at")
        try:
            created = datetime.fromisoformat(str(created_at))
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            return False
        if created > now:
            return False
        expires_at = payload.get("expires_at")
        try:
            expires = datetime.fromisoformat(str(expires_at))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            return False
        return (
            created <= now < expires
            and expires <= created + cls.CACHE_TTL
            and bool(payload.get("candidates"))
        )

    @staticmethod
    async def _delete_cache_file(path: Path) -> None:
        try:
            await asyncio.to_thread(path.unlink, True)
        except (OSError, TypeError):
            return

    async def _read_cache(self, cache_key: str) -> list[MaterialCandidateResponse] | None:
        path = self._cache_path(cache_key)
        if not path.is_file():
            return None
        try:
            payload = await asyncio.to_thread(path.read_text, encoding="utf-8")
            data = json.loads(payload)
        except (OSError, ValueError, TypeError):
            await self._delete_cache_file(path)
            return None
        if not self._cache_is_fresh(data):
            await self._delete_cache_file(path)
            return None
        try:
            return [self._candidate_from_cache(item) for item in data.get("candidates", [])]
        except (TypeError, ValueError, KeyError):
            await self._delete_cache_file(path)
            return None

    @staticmethod
    def _candidate_from_cache(item: object) -> MaterialCandidateResponse:
        if not isinstance(item, dict):
            raise TypeError("invalid cached candidate")
        return MaterialCandidateResponse(
            candidate_id=str(item["candidate_id"]),
            provider=str(item["provider"]),
            external_id=str(item["external_id"]),
            title=str(item.get("title") or ""),
            source_page_url=safe_pexels_page_url(item.get("source_page_url")),
            author=str(item.get("author") or "").strip() or None,
            author_url=safe_pexels_page_url(item.get("author_url"), author=True),
            duration_seconds=item.get("duration_seconds"),
            width=item.get("width"),
            height=item.get("height"),
        )

    async def _write_cache(self, cache_key: str, candidates: list[dict]) -> None:
        if not candidates:
            return
        path = self._cache_path(cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now(UTC)
        payload = {
            "version": self.CACHE_VERSION,
            "created_at": created_at.isoformat(),
            "expires_at": (created_at + self.CACHE_TTL).isoformat(),
            "candidates": candidates,
        }
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            await asyncio.to_thread(temporary.write_text, json.dumps(payload, ensure_ascii=False), "utf-8")
            await asyncio.to_thread(temporary.replace, path)
        finally:
            temporary.unlink(missing_ok=True)

    async def _provider(self, provider_id: str | None = None) -> MaterialProvider:
        if provider_id and provider_id in self.providers:
            return self.providers[provider_id]
        if not provider_id and len(self.providers) == 1:
            return next(iter(self.providers.values()))
        provider = await self.provider_manager.get_material(provider_id)
        if not (hasattr(provider, "search_videos") or hasattr(provider, "search")) or not hasattr(provider, "download"):
            raise ValidationException("在线素材 Provider 不支持当前接口。")
        return provider

    async def search(
        self,
        project_id: str,
        request: MaterialSearchRequest,
    ) -> tuple[str, bool, list[MaterialCandidateResponse]]:
        if not await self.session.get(ProjectModel, project_id):
            raise NotFoundException("Project", project_id)
        provider = await self._provider(request.provider_id)
        bounded_request = replace(request, limit=min(self.MAX_CANDIDATES, request.limit))
        cache_key = self.cache_key(bounded_request, request.provider_id, provider)
        lock = self._cache_locks.setdefault(cache_key, asyncio.Lock())
        try:
            async with lock:
                cached = await self._read_cache(cache_key)
                if cached:
                    return cache_key, True, cached
                if hasattr(provider, "search_videos"):
                    candidates = await provider.search_videos(bounded_request)
                else:
                    candidates = await provider.search(
                        bounded_request.keyword,
                        bounded_request.aspect_ratio,
                        bounded_request.min_duration_seconds,
                        bounded_request.limit,
                    )
                items = [self._cache_item(cache_key, item) for item in candidates]
                await self._write_cache(cache_key, items)
                return cache_key, False, [self._candidate_from_cache(item) for item in items]
        finally:
            if not lock.locked() and not getattr(lock, "_waiters", None):
                self._cache_locks.pop(cache_key, None)

    async def _candidate_for_import(self, candidate_id: str) -> dict:
        if not candidate_id:
            raise ValidationException("缺少在线素材候选 ID，请先搜索素材。")
        directory = self.storage.get_path("cache/material_search")
        if directory.is_dir():
            for path in directory.glob("*.json"):
                try:
                    payload = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
                except (OSError, ValueError, TypeError):
                    await self._delete_cache_file(path)
                    continue
                if not self._cache_is_fresh(payload):
                    await self._delete_cache_file(path)
                    continue
                for item in payload.get("candidates", []):
                    if isinstance(item, dict) and item.get("candidate_id") == candidate_id:
                        return self._cache_item_from_import(item)
        raise ValidationException("在线素材候选已失效，请重新搜索后再导入。")

    @staticmethod
    def _cache_item_from_import(item: dict) -> dict:
        required = {"candidate_id", "provider", "external_id"}
        if not required.issubset(item):
            raise ValidationException("在线素材候选缓存格式无效，请重新搜索。")
        return {
            **item,
            "source_page_url": safe_pexels_page_url(item.get("source_page_url")),
            "author_url": safe_pexels_page_url(item.get("author_url"), author=True),
        }

    async def _validate_binding(self, project_id: str, request: MaterialImportRequest, asset_id: str) -> None:
        if request.task_id:
            task = await self.session.get(TaskModel, request.task_id)
            if not task or task.project_id != project_id:
                raise ValidationException("任务不存在或不属于当前项目。")
        if request.scene_id:
            scene = await self.session.get(SceneModel, request.scene_id)
            if not scene:
                raise ValidationException("分镜不存在。")
            task = await self.session.get(TaskModel, scene.task_id)
            if not task or task.project_id != project_id or (request.task_id and task.id != request.task_id):
                raise ValidationException("分镜不属于当前项目或指定任务。")
            scene.media_asset_id = asset_id
            scene.layout_params = {
                **(scene.layout_params or {}),
                "media_source": "online",
                "media_type": "video",
            }

    async def _deduplicated_asset(self, project_id: str, content_hash: str) -> AssetModel | None:
        rows = await self.session.scalars(
            select(AssetModel)
            .join(
                ProjectAssetBindingModel,
                ProjectAssetBindingModel.asset_id == AssetModel.id,
            )
            .where(ProjectAssetBindingModel.project_id == project_id)
        )
        for asset in rows:
            if (asset.metadata_json or {}).get("content_sha256") == content_hash:
                return asset
        return None

    async def _asset_bound_to_other_scene(
        self, task_id: str, scene_id: str | None, asset_id: str
    ) -> bool:
        query = select(SceneModel.id).where(
            SceneModel.task_id == task_id,
            SceneModel.media_asset_id == asset_id,
        )
        if scene_id:
            query = query.where(SceneModel.id != scene_id)
        return await self.session.scalar(query.limit(1)) is not None

    @staticmethod
    def _safe_extension(file_name: str) -> str:
        suffix = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "mp4"
        return suffix if re.fullmatch(r"[a-z0-9]{1,8}", suffix) else "mp4"

    async def import_candidate(
        self,
        project_id: str,
        request: MaterialImportRequest,
    ) -> tuple[AssetModel, MaterialSourceResponse, bool]:
        if not await self.session.get(ProjectModel, project_id):
            raise NotFoundException("Project", project_id)
        candidate = await self._candidate_for_import(request.candidate_id or "")
        provider = await self._provider(request.provider_id)
        if candidate.get("provider") != provider.name:
            raise ValidationException("素材候选与当前 Provider 不匹配。")
        temporary_rel = f"cache/material_download_{uuid.uuid4().hex}.mp4"
        temporary_path = self.storage.get_path(temporary_rel)
        created_asset: AssetModel | None = None
        try:
            preferred_rendition = getattr(provider, "set_preferred_rendition", None)
            if callable(preferred_rendition):
                preferred_rendition(
                    str(candidate["external_id"]),
                    candidate.get("width"),
                    candidate.get("height"),
                )
            if self.execution_context:
                await self.execution_context.fence(self.session)
                await self.session.commit()
            download = await provider.download(
                str(candidate["external_id"]),
                request.aspect_ratio,
                temporary_path,
            )
            if Path(download.file_path).resolve() != temporary_path.resolve():
                raise ValidationException("在线素材 Provider 返回了非法临时文件路径。")
            if self.execution_context:
                await self.execution_context.fence(self.session)
                await self.session.commit()
            probe = await media_probe_service.probe(temporary_path)
            if self.execution_context:
                await self.execution_context.fence(self.session)
                await self.session.commit()
            if not probe.has_video or not probe.video_duration or not probe.width or not probe.height:
                raise ValidationException("在线素材未通过 FFprobe 视频流校验。")
            digest = await asyncio.to_thread(self._sha256_path, temporary_path)

            if self.execution_context:
                await self.execution_context.fence(self.session)
            existing = await self._deduplicated_asset(project_id, digest)
            if existing and request.task_id and await self._asset_bound_to_other_scene(
                request.task_id, request.scene_id, existing.id
            ):
                raise ValidationException("任务内不能重复使用同一份在线素材，请重新获取。")
            source_page_url = safe_pexels_page_url(candidate.get("source_page_url"))
            author_url = safe_pexels_page_url(candidate.get("author_url"), author=True)
            metadata = {
                "source_kind": "online_asset",
                "provider": provider.name,
                "external_id": candidate["external_id"],
                "source_page_url": source_page_url,
                "author": candidate.get("author"),
                "author_url": author_url,
                "search_keyword": request.keyword,
                "rendition": {"width": probe.width, "height": probe.height},
                "content_sha256": digest,
                "duration_source": "ffprobe",
                "actual_duration_seconds": probe.video_duration,
                "ffprobe_width": probe.width,
                "ffprobe_height": probe.height,
                "attribution_url": source_page_url,
                "license_url": "https://www.pexels.com/license/",
            }
            reused = existing is not None
            if existing is not None:
                asset = existing
                merged_metadata = dict(asset.metadata_json or {})
                merged_metadata.update({key: value for key, value in metadata.items() if value is not None})
                asset.metadata_json = merged_metadata
            else:
                created_asset = await self.asset_service.save_asset_from_file(
                    file_path=temporary_path,
                    file_name=f"online_{candidate['external_id']}.{self._safe_extension(download.file_name)}",
                    mime_type="video/mp4",
                    asset_type=AssetType.VIDEO,
                    project_id=project_id,
                    duration_seconds=probe.video_duration,
                    width=probe.width,
                    height=probe.height,
                    metadata=metadata,
                )
                asset = created_asset
            await self._validate_binding(project_id, request, asset.id)
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            source = MaterialSourceResponse(
                asset_id=asset.id,
                provider=provider.name,
                external_id=str(candidate["external_id"]),
                source_page_url=source_page_url,
                author=candidate.get("author"),
                author_url=author_url,
                search_keyword=request.keyword,
                content_sha256=digest,
            )
            return asset, source, reused
        except WorkflowLeaseLost:
            if created_asset is not None:
                await self._cleanup_created_asset(created_asset)
            raise
        except asyncio.CancelledError:
            if created_asset is not None:
                await self._cleanup_created_asset(created_asset)
            raise
        except Exception:
            if created_asset is not None:
                await self._cleanup_created_asset(created_asset)
            raise
        finally:
            await self.storage.delete_file(temporary_rel)

    async def _cleanup_created_asset(self, asset: AssetModel) -> None:
        await self.session.rollback()
        await self.storage.delete_file(asset.file_path)

    @staticmethod
    def _sha256_path(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    async def acquire_for_scene(
        self,
        project_id: str,
        task_id: str,
        scene_id: str,
        keyword: str,
        aspect_ratio: str = "9:16",
        provider_id: str | None = None,
        *,
        min_duration_seconds: float = 0.0,
        excluded_external_ids: set[str] | None = None,
        target_size: tuple[int, int] | None = None,
        execution_context=None,
    ) -> tuple[AssetModel, MaterialSourceResponse, bool]:
        if execution_context and self.execution_context is None:
            self.execution_context = execution_context
            self.asset_service.execution_context = execution_context
        base_request = MaterialSearchRequest(
            provider_id=provider_id,
            keyword=keyword,
            aspect_ratio=aspect_ratio,
            min_duration_seconds=min_duration_seconds,
            limit=20,
            target_width=target_size[0] if target_size else None,
            target_height=target_size[1] if target_size else None,
        )
        excluded = {str(external_id) for external_id in (excluded_external_ids or set())}
        attempted_external_ids = set(excluded)
        failures: list[str] = []
        search_keywords = _material_search_keywords(base_request.keyword, base_request.aspect_ratio)
        for search_index, search_keyword in enumerate(search_keywords):
            request = replace(base_request, keyword=search_keyword)
            _, _, candidates = await self.search(project_id, request)
            if not candidates:
                failures.append(f"{search_keyword}: 没有可用候选")
                if search_index + 1 < len(search_keywords):
                    logger.warning(
                        "Online material search returned no candidates for scene {} with keyword '{}'; trying '{}'",
                        scene_id,
                        search_keyword,
                        search_keywords[search_index + 1],
                    )
                continue

            usable_candidate = False
            for candidate in candidates:
                external_id = str(candidate.external_id)
                if external_id in attempted_external_ids:
                    continue
                usable_candidate = True
                attempted_external_ids.add(external_id)
                try:
                    if execution_context:
                        await execution_context.fence(self.session)
                    asset, source, reused = await self.import_candidate(
                        project_id,
                        MaterialImportRequest(
                            candidate_id=candidate.candidate_id,
                            provider_id=provider_id,
                            task_id=task_id,
                            scene_id=scene_id,
                            keyword=search_keyword,
                            aspect_ratio=aspect_ratio,
                        ),
                    )
                    return asset, source, reused
                except WorkflowLeaseLost:
                    raise
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    failures.append(f"{external_id}: {type(exc).__name__} ({str(exc)[:120]})")
            if not usable_candidate:
                failures.append(f"{search_keyword}: 候选均已使用或排除")
            if search_index + 1 < len(search_keywords):
                logger.warning(
                    "Online material candidates were not usable for scene {} with keyword '{}'; trying '{}'",
                    scene_id,
                    search_keyword,
                    search_keywords[search_index + 1],
                )
        detail = "；".join(failures[:3])
        raise ValidationException(f"未找到可用的在线素材，请重新获取。{detail}")

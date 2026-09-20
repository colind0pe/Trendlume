import uuid
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException, ValidationException
from src.core.security import redact_sensitive_text, secret_cipher
from src.domain.enums import (
    AssetType,
    CredentialType,
    PlatformType,
    PublishJobStatus,
)
from src.models.asset import AssetModel
from src.models.provider_config import ProviderConfigModel
from src.models.publishing import CredentialModel, PublishingJobModel, SocialAccountModel
from src.models.task import TaskModel
from src.models.workflow import WorkflowArtifactModel
from src.providers.publishing.auth_service import auth_service
from src.providers.publishing.cookie_helper import normalize_storage_state
from src.providers.publishing.douyin import DouyinPublishingProvider
from src.providers.publishing.protocol import PublishingProvider
from src.repositories.asset_repository import AssetRepository
from src.repositories.project_repository import ProjectRepository
from src.repositories.publishing_repository import (
    CredentialRepository,
    PublishingJobRepository,
    SocialAccountRepository,
)
from src.repositories.task_repository import TaskRepository
from src.schemas.generation import PlatformMetadata
from src.schemas.publishing import (
    AccountCheckResponse,
    CredentialCreate,
    ManualCookieImportRequest,
    PublishingJobCreate,
    QRCompleteRequest,
    SocialAccountCreate,
)
from src.services.rendering_service import RenderingService
from src.storage.local_storage import LocalStorageService, local_storage
from src.tasks.broadcaster import event_broadcaster


class PublishingService:
    """Application service for Douyin video publishing, social accounts, QR login, and scheduling."""

    def __init__(
        self,
        session: AsyncSession,
        storage: LocalStorageService = local_storage,
        provider: PublishingProvider | None = None,
        rendering_service: RenderingService | None = None,
    ):
        self.session = session
        self.storage = storage
        self.provider = provider or DouyinPublishingProvider()
        self.cred_repo = CredentialRepository(session)
        self.acc_repo = SocialAccountRepository(session)
        self.job_repo = PublishingJobRepository(session)
        self.task_repo = TaskRepository(session)
        self.asset_repo = AssetRepository(session)
        self.project_repo = ProjectRepository(session)
        self.rendering_service = rendering_service or RenderingService(session, storage=storage)
        self.auth = auth_service

    async def _publishing_provider_config(self) -> ProviderConfigModel | None:
        provider = await self.session.get(ProviderConfigModel, "prov_pub_douyin")
        if provider:
            return provider
        stmt = select(ProviderConfigModel).where(
            ProviderConfigModel.provider_type == "publishing",
            ProviderConfigModel.enabled.is_(True),
        )
        return (await self.session.execute(stmt)).scalars().first()

    # ========================================================================
    # Credential methods
    # ========================================================================
    @staticmethod
    def _credential_payload(credential: CredentialModel | None) -> dict[str, Any]:
        if not credential or not credential.payload:
            return {}
        stored = credential.payload
        encrypted = stored.get("__encrypted__") if isinstance(stored, dict) else None
        if encrypted:
            return secret_cipher.decrypt_dict(encrypted)
        if isinstance(stored, dict) and "__encrypted__" in stored:
            return {}
        # Backwards compatibility for databases created before credential encryption.
        return dict(stored) if isinstance(stored, dict) else {}

    async def migrate_legacy_credentials(self) -> int:
        """Encrypt credentials stored as plaintext JSON by older releases."""
        result = await self.session.execute(select(CredentialModel))
        migrated = 0
        for credential in result.scalars().all():
            payload = credential.payload
            if isinstance(payload, dict) and payload and "__encrypted__" not in payload:
                credential.payload = {"__encrypted__": secret_cipher.encrypt_dict(payload)}
                migrated += 1
        if migrated:
            await self.session.commit()
            logger.info(f"Migrated {migrated} legacy publishing credentials to encrypted storage")
        return migrated

    async def create_credential(self, data: CredentialCreate) -> CredentialModel:
        cred_id = f"cred_{uuid.uuid4().hex[:12]}"
        encrypted_payload = secret_cipher.encrypt_dict(data.payload)
        cred = CredentialModel(
            id=cred_id,
            platform=data.platform.value,
            credential_type=data.credential_type.value,
            payload={"__encrypted__": encrypted_payload} if encrypted_payload else {},
            is_valid=True,
        )
        return await self.cred_repo.create(cred)

    # ========================================================================
    # Account methods
    # ========================================================================
    async def create_account(self, data: SocialAccountCreate) -> SocialAccountModel:
        account_id = f"acc_{uuid.uuid4().hex[:12]}"
        account = SocialAccountModel(
            id=account_id,
            platform=data.platform.value,
            account_name=data.account_name,
            username=data.username,
            avatar_url=data.avatar_url,
            credential_id=data.credential_id,
        )
        return await self.acc_repo.create(account)

    async def list_accounts(self, platform: str | None = None) -> list[SocialAccountModel]:
        res = await self.acc_repo.list_by_platform(platform)
        return list(res)

    async def _attach_task_links(self, jobs: list[PublishingJobModel]) -> None:
        if not jobs:
            return
        assets = (
            (
                await self.session.execute(
                    select(AssetModel).where(
                        AssetModel.id.in_([job.video_asset_id for job in jobs])
                    )
                )
            )
            .scalars()
            .all()
        )
        asset_tasks = {asset.id: (asset.metadata_json or {}).get("task_id") for asset in assets}
        tasks = (
            (
                await self.session.execute(
                    select(TaskModel).where(
                        TaskModel.project_id.in_({job.project_id for job in jobs})
                    )
                )
            )
            .scalars()
            .all()
        )
        tasks_by_id = {task.id: task for task in tasks}
        for job in jobs:
            task_id = (
                (job.custom_params or {}).get("task_id")
                or (job.custom_params or {}).get("source_task_id")
                or asset_tasks.get(job.video_asset_id)
            )
            task = tasks_by_id.get(task_id)
            job.task_id = task.id if task and task.project_id == job.project_id else None

    async def get_account(self, account_id: str) -> SocialAccountModel:
        acc = await self.acc_repo.get_by_id(account_id)
        if not acc:
            raise NotFoundException("SocialAccount", account_id)
        return acc

    async def delete_account(self, account_id: str) -> bool:
        acc = await self.acc_repo.get_by_id(account_id)
        if not acc:
            return False
        # Clean up associated credential if present
        if acc.credential_id:
            await self.cred_repo.delete_by_id(acc.credential_id)
        deleted = await self.acc_repo.delete_by_id(account_id)

        # Update publishing provider diagnostics if accounts state changed
        remaining = list(await self.acc_repo.list_by_platform(acc.platform))
        pub_provider = await self._publishing_provider_config()
        if pub_provider:
            if not remaining:
                pub_provider.last_test_connected = None
                pub_provider.last_tested_at = None
                pub_provider.last_test_message = None
            else:
                has_valid = any(r.status == "active" for r in remaining)
                pub_provider.last_test_connected = has_valid
                pub_provider.last_tested_at = datetime.now(UTC)
            await self.session.commit()

        return deleted

    async def check_account_status(self, account_id: str) -> AccountCheckResponse:
        """Inspect and test social account credentials validity."""
        acc = await self.get_account(account_id)
        if not acc.credential_id:
            return AccountCheckResponse(
                account_id=account_id,
                is_valid=False,
                username=acc.username,
                error_message="未绑定任何授权凭证或Cookie",
                checked_at=datetime.now(UTC).isoformat(),
            )

        cred = await self.cred_repo.get_by_id(acc.credential_id)
        credential_data = self._credential_payload(cred)
        if not credential_data:
            return AccountCheckResponse(
                account_id=account_id,
                is_valid=False,
                username=acc.username,
                error_message="凭证数据不存在或已清空",
                checked_at=datetime.now(UTC).isoformat(),
            )

        is_valid = await self.provider.validate_account(credential_data)

        if is_valid and hasattr(self.provider, "fetch_user_info"):
            try:
                u_info = await self.provider.fetch_user_info(credential_data)
                if u_info:
                    if u_info.get("display_name") and not acc.account_name:
                        acc.account_name = u_info["display_name"]
                    if u_info.get("username") and not acc.username:
                        acc.username = u_info["username"]
                    if u_info.get("avatar_url") and not acc.avatar_url:
                        acc.avatar_url = u_info["avatar_url"]
            except Exception as e:
                logger.debug(f"Could not fetch user info during check: {e}")

        # Update account and credential status in DB
        acc.status = "active" if is_valid else "error"
        acc.updated_at = datetime.now(UTC)
        await self.acc_repo.update(acc)

        cred.is_valid = is_valid
        cred.updated_at = datetime.now(UTC)
        await self.cred_repo.update(cred)

        # Update publishing provider last test diagnostic status
        pub_provider = await self._publishing_provider_config()

        if pub_provider:
            if is_valid:
                pub_provider.last_test_connected = True
                pub_provider.last_tested_at = datetime.now(UTC)
                display_label = acc.account_name or acc.username or "抖音账号"
                pub_provider.last_test_message = (
                    f"抖音账号【{display_label}】凭证检测有效，发布服务就绪。"
                )
            else:
                other_accounts = list(await self.acc_repo.list_by_platform(acc.platform))
                has_other_valid = any(
                    other.id != acc.id and other.status == "active" for other in other_accounts
                )
                pub_provider.last_test_connected = has_other_valid
                pub_provider.last_tested_at = datetime.now(UTC)
                if not has_other_valid:
                    pub_provider.last_test_message = "抖音账号凭证已失效，请重新扫码登录。"

        await self.session.commit()

        return AccountCheckResponse(
            account_id=account_id,
            is_valid=is_valid,
            username=acc.username,
            error_message=None if is_valid else "抖音登录凭据已过期或失效，请重新扫码登录",
            checked_at=datetime.now(UTC).isoformat(),
        )

    # ========================================================================
    # Interactive QR Code Login & Cookie Import
    # ========================================================================
    async def complete_qr_login(self, request: QRCompleteRequest) -> SocialAccountModel:
        """Finalize account creation from successful QR code login."""
        sess = self.auth.get_qr_session(request.session_id)
        if not sess:
            raise ValidationException(f"未找到扫码会话: {request.session_id}")

        if sess.status != "success" or not sess.storage_state:
            raise ValidationException(f"扫码会话尚未完成登录 (当前状态: {sess.status})")

        # 1. Create Credential
        user_info = sess.user_info or {}
        if hasattr(self.provider, "fetch_user_info") and not user_info.get("username"):
            try:
                fetched = await self.provider.fetch_user_info(sess.storage_state)
                if fetched:
                    user_info.update(fetched)
            except Exception:
                pass

        username = request.username or user_info.get("username", "")
        display_name = user_info.get("display_name", request.account_name)
        avatar_url = user_info.get("avatar_url")

        cred = await self.create_credential(
            CredentialCreate(
                platform=PlatformType(sess.platform)
                if sess.platform in [p.value for p in PlatformType]
                else PlatformType.DOUYIN,
                credential_type=CredentialType.COOKIE,
                payload=sess.storage_state,
            )
        )

        # 2. Create Social Account
        acc = await self.create_account(
            SocialAccountCreate(
                platform=PlatformType(sess.platform)
                if sess.platform in [p.value for p in PlatformType]
                else PlatformType.DOUYIN,
                account_name=request.account_name or display_name,
                username=username,
                avatar_url=avatar_url,
                credential_id=cred.id,
            )
        )

        pub_provider = await self._publishing_provider_config()

        if pub_provider:
            pub_provider.last_test_connected = True
            pub_provider.last_tested_at = datetime.now(UTC)
            pub_provider.last_test_message = (
                f"抖音账号【{acc.account_name}】扫码授权成功，发布服务就绪。"
            )
            await self.session.commit()

        return acc

    async def import_cookie(self, request: ManualCookieImportRequest) -> SocialAccountModel:
        """Normalize cookie string/json and create account with credentials."""
        normalized = normalize_storage_state(request.cookie_string, platform=request.platform)
        if not normalized or not normalized.get("cookies"):
            raise ValidationException("无法从输入的文本中解析出有效的 Cookie 数据，请检查格式。")

        plat_enum = (
            PlatformType(request.platform)
            if request.platform in [p.value for p in PlatformType]
            else PlatformType.DOUYIN
        )

        # 1. Create Credential
        cred = await self.create_credential(
            CredentialCreate(
                platform=plat_enum,
                credential_type=CredentialType.COOKIE,
                payload=normalized,
            )
        )

        # 2. Create Social Account
        username = request.username or ""
        avatar_url = None
        if hasattr(self.provider, "fetch_user_info") and not username:
            try:
                u_info = await self.provider.fetch_user_info(normalized)
                if u_info:
                    username = u_info.get("username", "")
                    avatar_url = u_info.get("avatar_url")
            except Exception:
                pass

        acc = await self.create_account(
            SocialAccountCreate(
                platform=plat_enum,
                account_name=request.account_name,
                username=username,
                avatar_url=avatar_url,
                credential_id=cred.id,
            )
        )
        return acc

    # ========================================================================
    # Publishing Job methods
    # ========================================================================
    async def _validate_publish_asset(
        self,
        asset_id: str,
        project_id: str,
        expected_type: AssetType,
        label: str,
    ) -> AssetModel:
        asset = await self.asset_repo.get_by_id(asset_id)
        if not asset:
            raise ValidationException(f"{label}素材不存在或已被删除。")
        if asset.project_id != project_id:
            raise ValidationException(f"{label}素材不属于当前项目。")
        if asset.asset_type != expected_type.value:
            raise ValidationException(f"{label}素材类型必须为 {expected_type.value}。")

        path = self.storage.get_path(asset.file_path)
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValidationException(f"{label}素材文件不存在或为空。")
        return asset

    @staticmethod
    def _normalize_publish_metadata(
        title: str,
        description: str,
        tags: list[str],
        custom_params: dict[str, Any] | None,
    ) -> tuple[PlatformMetadata, dict[str, Any]]:
        params = dict(custom_params or {})
        constrained_fields = {
            key: params[key]
            for key in (
                "platform",
                "declaration",
                "location",
                "collection_name",
                "visibility",
                "allow_download",
            )
            if key in params
        }
        try:
            metadata = PlatformMetadata(
                title=title,
                description=description,
                tags=tags,
                **constrained_fields,
            )
        except ValueError as exc:
            raise ValidationException(f"发布平台元数据无效: {exc}") from exc

        for key in constrained_fields:
            params[key] = getattr(metadata, key)
        return metadata, params

    async def create_publishing_job(self, data: PublishingJobCreate) -> PublishingJobModel:
        metadata, normalized_params = self._normalize_publish_metadata(
            data.title,
            data.description,
            data.tags,
            data.custom_params,
        )
        await self._validate_publish_asset(
            data.video_asset_id,
            data.project_id,
            AssetType.VIDEO,
            "视频",
        )
        if data.cover_asset_id:
            await self._validate_publish_asset(
                data.cover_asset_id,
                data.project_id,
                AssetType.IMAGE,
                "封面",
            )

        job_id = f"pub_{uuid.uuid4().hex[:12]}"
        job = PublishingJobModel(
            id=job_id,
            project_id=data.project_id,
            video_asset_id=data.video_asset_id,
            account_id=data.account_id,
            platform=data.platform.value,
            title=metadata.title,
            description=metadata.description,
            tags=metadata.tags,
            cover_asset_id=data.cover_asset_id or None,
            status=PublishJobStatus.QUEUED.value
            if not data.scheduled_at
            else PublishJobStatus.SCHEDULED.value,
            scheduled_at=data.scheduled_at,
            custom_params={
                **normalized_params,
                "publish_attempt_id": f"attempt_{uuid.uuid4().hex[:12]}",
            },
        )
        return await self.job_repo.create(job)

    async def list_jobs(
        self,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PublishingJobModel]:
        res = await self.job_repo.list_jobs(
            project_id=project_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        jobs = list(res)
        await self._attach_task_links(jobs)
        return jobs

    async def get_job(self, job_id: str) -> PublishingJobModel:
        job = await self.job_repo.get_by_id(job_id)
        if not job:
            raise NotFoundException("PublishingJob", job_id)
        await self._attach_task_links([job])
        return job

    # ========================================================================
    # Task Publishing Workflow
    # ========================================================================
    async def prepare_task_publishing(
        self,
        task_id: str,
        account_id: str | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        cover_asset_id: str | None = None,
        scheduled_at: datetime | None = None,
        custom_params: dict[str, Any] | None = None,
    ) -> PublishingJobModel:
        """Ensure final video exists, generate metadata if missing, and create PublishingJob"""
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            raise NotFoundException("Task", task_id)

        # 1. Resolve Account
        if not account_id:
            accounts = await self.list_accounts(PlatformType.DOUYIN.value)
            if not accounts:
                raise ValidationException(
                    "未检测到已绑定的抖音账号，请先在发布中心完成抖音创作者扫码登录。"
                )
            account_id = accounts[0].id

        # 2. Ensure Final Video Asset
        video_asset_id = await self.session.scalar(
            select(WorkflowArtifactModel.asset_id)
            .where(
                WorkflowArtifactModel.task_id == task_id,
                WorkflowArtifactModel.kind.in_(["final_video", "composition"]),
                WorkflowArtifactModel.asset_id.is_not(None),
            )
            .order_by(WorkflowArtifactModel.created_at.desc())
            .limit(1)
        )
        if not video_asset_id:
            composed_asset = await self.rendering_service.compose_task_video(task_id)
            video_asset_id = composed_asset.id

        # 3. Reuse the metadata generated with the storyboard.  Explicit
        # publish-form values still win, while old tasks fall back to the
        # historical defaults.
        generation_settings = task.generation_settings or {}
        generated_metadata = generation_settings.get("metadata")
        if not isinstance(generated_metadata, dict):
            generated_metadata = {}
        else:
            try:
                generated_metadata = PlatformMetadata.model_validate(
                    generated_metadata
                ).model_dump()
            except Exception:
                logger.warning(
                    "Ignoring malformed generated platform metadata for task %s", task_id
                )
                generated_metadata = {}

        pub_title = (
            title
            if title is not None and title.strip()
            else generated_metadata.get("title") or task.title or "精彩短视频"
        )
        pub_desc = (
            description
            if description is not None
            else generated_metadata.get("description")
            or task.description
            or getattr(task.commerce_detail, "hook", "")
        )
        pub_tags = (
            tags
            if tags is not None
            else generated_metadata.get("tags") or ["Trendlume", "科普", "热点视频", "AI创作"]
        )

        generated_custom_params = {
            key: generated_metadata[key]
            for key in (
                "platform",
                "declaration",
                "location",
                "collection_name",
                "visibility",
                "allow_download",
            )
            if generated_metadata.get(key) is not None
        }
        platform_custom_params = generated_metadata.get("platform_custom_params")
        if isinstance(platform_custom_params, dict):
            generated_custom_params.update(platform_custom_params)
        if custom_params:
            generated_custom_params.update(custom_params)
        generated_custom_params["task_id"] = task.id

        # 4. Create PublishingJob
        job = await self.create_publishing_job(
            PublishingJobCreate(
                project_id=task.project_id,
                video_asset_id=video_asset_id,
                account_id=account_id,
                platform=PlatformType.DOUYIN,
                title=pub_title,
                description=pub_desc,
                tags=pub_tags,
                cover_asset_id=cover_asset_id,
                custom_params=generated_custom_params,
                # Keep the timezone-aware value on the ORM instance for API callers.
                # The durable queue normalizes it to naive UTC for SQLite comparisons.
                scheduled_at=scheduled_at,
            )
        )
        return job

    async def execute_publish_job(self, publishing_job_id: str) -> PublishingJobModel:
        """Execute publishing job via Douyin provider and update status"""
        job = await self.get_job(publishing_job_id)
        account = await self.get_account(job.account_id)
        video_asset = await self.asset_repo.get_by_id(job.video_asset_id)

        if not video_asset:
            job.status = PublishJobStatus.FAILED.value
            job.error_message = "视频素材不存在"
            await self.job_repo.update(job)
            await self.session.commit()
            raise NotFoundException("Asset", job.video_asset_id)

        video_path = self.storage.get_path(video_asset.file_path)
        if not video_path.exists() or video_path.stat().st_size == 0:
            raise ValidationException("待发布视频文件不存在或为空。")
        if getattr(self.provider, "name", "") != "mock":
            await self.rendering_service._validate_media_file(video_path, require_audio=True)

        job.status = PublishJobStatus.PUBLISHING.value
        job.attempt_count += 1
        await self.job_repo.update(job)
        await self.session.commit()

        attempt_started = False
        try:
            credential_data = None
            if account and account.credential_id:
                cred = await self.cred_repo.get_by_id(account.credential_id)
                if cred:
                    credential_data = self._credential_payload(cred)

            params = dict(job.custom_params or {})
            params.update(
                {
                    "job_id": job.id,
                    "account_id": account.id if account else "",
                    "account_name": account.account_name if account else "",
                }
            )
            attempt_started = True
            res = await self.provider.publish_video(
                video_path=video_path,
                title=job.title,
                description=job.description,
                tags=job.tags,
                credential_data=credential_data,
                custom_params=params,
            )
            if res.success:
                job.status = PublishJobStatus.PUBLISHED.value
                job.published_at = datetime.now(UTC)
                job.platform_post_id = res.platform_post_id
                job.error_message = None
                # Persist a compact, redacted provider summary for diagnostics;
                # never retain cookies, tokens, headers, or the full response.
                raw_summary = res.raw_response if isinstance(res.raw_response, dict) else {}
                blocked = {
                    "token",
                    "access_token",
                    "refresh_token",
                    "cookie",
                    "cookies",
                    "headers",
                    "authorization",
                }
                summary = {
                    str(key): value
                    for key, value in raw_summary.items()
                    if str(key).lower() not in blocked
                    and isinstance(value, (str, int, float, bool, type(None)))
                }
                job.custom_params = {
                    **(job.custom_params or {}),
                    "provider_response_summary": summary,
                }
            else:
                job.status = PublishJobStatus.FAILED.value
                job.error_message = res.error or "发布失败"

            await self.job_repo.update(job)
            await self.session.commit()

            # Broadcast SSE Event
            await event_broadcaster.broadcast(
                "publish.completed" if res.success else "publish.failed",
                {
                    "job_id": job.id,
                    "status": job.status,
                    "platform": job.platform,
                    "post_id": job.platform_post_id,
                },
            )
            return job

        except Exception as e:
            safe_error = redact_sensitive_text(str(e))
            logger.error(f"Publish execution error for job {job.id}: {safe_error}")
            job.status = (
                PublishJobStatus.UNCERTAIN.value
                if attempt_started
                else PublishJobStatus.FAILED.value
            )
            job.error_message = safe_error
            await self.job_repo.update(job)
            await self.session.commit()
            raise

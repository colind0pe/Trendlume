from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db, get_publishing_service, request_session_factory
from src.domain.enums import JobType
from src.providers.publishing.auth_service import auth_service
from src.schemas.common import APIResponse
from src.schemas.publishing import (
    AccountCheckResponse,
    CredentialCreate,
    CredentialResponse,
    ManualCookieImportRequest,
    PublishingJobCreate,
    PublishingJobResponse,
    QRCompleteRequest,
    QRStartRequest,
    QRStartResponse,
    QRStatusResponse,
    SocialAccountCreate,
    SocialAccountResponse,
    UncertainPublishResolveRequest,
    VerificationCancelRequest,
    VerificationRequestResponse,
    VerificationSubmitRequest,
)
from src.services.publishing_service import PublishingService
from src.tasks.manager import task_manager

router = APIRouter(prefix="/publishing", tags=["Publishing"])


# ============================================================================
# Interactive QR Code Login & Cookie Import
# ============================================================================


@router.post("/auth/qr/start", response_model=APIResponse[QRStartResponse])
async def start_qr_auth(payload: QRStartRequest):
    """Start an interactive QR code login session for Douyin."""
    try:
        session = auth_service.start_qr_session(
            platform=payload.platform,
            headless=payload.headless,
        )
        return APIResponse(
            data=QRStartResponse(
                session_id=session.session_id,
                platform=session.platform,
                status=session.status,
                qrcode_data_url=session.qrcode_data_url,
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/qr/status/{session_id}", response_model=APIResponse[QRStatusResponse])
async def get_qr_auth_status(session_id: str):
    """Poll live scanning status of a QR login session."""
    session = auth_service.get_qr_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"未找到扫码登录会话: {session_id}")

    return APIResponse(
        data=QRStatusResponse(
            session_id=session.session_id,
            platform=session.platform,
            status=session.status,
            qrcode_data_url=session.qrcode_data_url,
            is_logged_in=(session.status == "success"),
            error_message=session.error_message,
        )
    )


@router.post("/auth/qr/cancel/{session_id}", response_model=APIResponse[bool])
async def cancel_qr_auth(session_id: str):
    """Cancel an active QR login session."""
    success = auth_service.cancel_qr_session(session_id)
    return APIResponse(data=success)


@router.post(
    "/auth/qr/complete",
    response_model=APIResponse[SocialAccountResponse],
    status_code=status.HTTP_201_CREATED,
)
async def complete_qr_auth(
    payload: QRCompleteRequest,
    service: PublishingService = Depends(get_publishing_service),
):
    """Finalize QR code login by creating a social account and storing session credentials."""
    account = await service.complete_qr_login(payload)
    return APIResponse(data=SocialAccountResponse.model_validate(account))


@router.post(
    "/auth/cookie/import",
    response_model=APIResponse[SocialAccountResponse],
    status_code=status.HTTP_201_CREATED,
)
async def import_manual_cookie(
    payload: ManualCookieImportRequest,
    service: PublishingService = Depends(get_publishing_service),
):
    """Import raw cookie string or storage_state JSON, normalize it, and register account."""
    account = await service.import_cookie(payload)
    return APIResponse(data=SocialAccountResponse.model_validate(account))


# ============================================================================
# Credentials
# ============================================================================


@router.post(
    "/credentials",
    response_model=APIResponse[CredentialResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_credential(
    payload: CredentialCreate,
    service: PublishingService = Depends(get_publishing_service),
):
    cred = await service.create_credential(payload)
    return APIResponse(data=CredentialResponse.model_validate(cred))


# ============================================================================
# Accounts
# ============================================================================


@router.post(
    "/accounts",
    response_model=APIResponse[SocialAccountResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_account(
    payload: SocialAccountCreate,
    service: PublishingService = Depends(get_publishing_service),
):
    account = await service.create_account(payload)
    return APIResponse(data=SocialAccountResponse.model_validate(account))


@router.get("/accounts", response_model=APIResponse[list[SocialAccountResponse]])
async def list_accounts(
    platform: str | None = Query(None),
    service: PublishingService = Depends(get_publishing_service),
):
    accounts = await service.list_accounts(platform)
    return APIResponse(data=[SocialAccountResponse.model_validate(a) for a in accounts])


@router.get("/accounts/{account_id}", response_model=APIResponse[SocialAccountResponse])
async def get_account(
    account_id: str,
    service: PublishingService = Depends(get_publishing_service),
):
    account = await service.get_account(account_id)
    return APIResponse(data=SocialAccountResponse.model_validate(account))


@router.delete("/accounts/{account_id}", response_model=APIResponse[bool])
async def delete_account(
    account_id: str,
    service: PublishingService = Depends(get_publishing_service),
):
    res = await service.delete_account(account_id)
    return APIResponse(data=res)


@router.post("/accounts/{account_id}/check", response_model=APIResponse[AccountCheckResponse])
async def check_account(
    account_id: str,
    service: PublishingService = Depends(get_publishing_service),
):
    """Test and inspect account cookie validity and login status."""
    res = await service.check_account_status(account_id)
    return APIResponse(data=res)


# ============================================================================
# Publishing Jobs
# ============================================================================


@router.post(
    "/jobs", response_model=APIResponse[PublishingJobResponse], status_code=status.HTTP_201_CREATED
)
async def create_publishing_job(
    payload: PublishingJobCreate,
    service: PublishingService = Depends(get_publishing_service),
    db: AsyncSession = Depends(get_db),
):
    job = await service.create_publishing_job(payload)
    if job.scheduled_at is not None:
        task_id = str((job.custom_params or {}).get("task_id") or "")
        try:
            await task_manager.submit_task(
                task_id=task_id,
                job_type=JobType.PUBLISH.value,
                params={"publishing_job_id": job.id, "task_id": task_id},
                available_at=job.scheduled_at,
                scheduled_at=job.scheduled_at,
                session_factory=request_session_factory(db),
            )
        except Exception as exc:
            job.status = "failed"
            job.error_message = f"定时发布排队失败：{exc}"
            await db.commit()
            raise
    return APIResponse(data=PublishingJobResponse.model_validate(job))


@router.get("/jobs", response_model=APIResponse[list[PublishingJobResponse]])
async def list_publishing_jobs(
    project_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: PublishingService = Depends(get_publishing_service),
):
    jobs = await service.list_jobs(
        project_id=project_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return APIResponse(data=[PublishingJobResponse.model_validate(j) for j in jobs])


@router.get("/jobs/{job_id}", response_model=APIResponse[PublishingJobResponse])
async def get_publishing_job(
    job_id: str,
    service: PublishingService = Depends(get_publishing_service),
):
    job = await service.get_job(job_id)
    return APIResponse(data=PublishingJobResponse.model_validate(job))


@router.post("/jobs/{job_id}/publish", response_model=APIResponse[PublishingJobResponse])
async def execute_publishing_job(
    job_id: str,
    service: PublishingService = Depends(get_publishing_service),
):
    job = await service.execute_publish_job(job_id)
    return APIResponse(data=PublishingJobResponse.model_validate(job))


@router.post("/jobs/{job_id}/retry", response_model=APIResponse[PublishingJobResponse])
async def retry_publishing_job(
    job_id: str,
    service: PublishingService = Depends(get_publishing_service),
):
    job = await service.execute_publish_job(job_id)
    return APIResponse(data=PublishingJobResponse.model_validate(job))


@router.post("/jobs/{job_id}/confirm-missed", response_model=APIResponse[PublishingJobResponse])
async def confirm_missed_publishing_job(
    job_id: str,
    service: PublishingService = Depends(get_publishing_service),
    db: AsyncSession = Depends(get_db),
):
    try:
        await task_manager.confirm_missed_publish(job_id, session_factory=request_session_factory(db))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    job = await service.get_job(job_id)
    return APIResponse(data=PublishingJobResponse.model_validate(job))


@router.post("/jobs/{job_id}/cancel", response_model=APIResponse[PublishingJobResponse])
async def cancel_publishing_job(
    job_id: str,
    service: PublishingService = Depends(get_publishing_service),
    db: AsyncSession = Depends(get_db),
):
    cancelled = await task_manager.cancel_publishing_workflow(job_id, session_factory=request_session_factory(db))
    if not cancelled:
        raise HTTPException(status_code=404, detail=f"未找到发布任务: {job_id}")
    job = await service.get_job(job_id)
    return APIResponse(data=PublishingJobResponse.model_validate(job))


@router.post("/jobs/{job_id}/resolve-uncertain", response_model=APIResponse[PublishingJobResponse])
async def resolve_uncertain_publishing_job(
    job_id: str,
    payload: UncertainPublishResolveRequest,
    service: PublishingService = Depends(get_publishing_service),
    db: AsyncSession = Depends(get_db),
):
    try:
        await task_manager.resolve_uncertain_publish(job_id, payload.action, session_factory=request_session_factory(db))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    job = await service.get_job(job_id)
    return APIResponse(data=PublishingJobResponse.model_validate(job))


@router.delete("/jobs/{job_id}", response_model=APIResponse[bool])
async def delete_publishing_job(
    job_id: str,
    service: PublishingService = Depends(get_publishing_service),
    db: AsyncSession = Depends(get_db),
):
    job = await service.get_job(job_id)
    if job.status in {"publishing", "published", "uncertain"}:
        raise HTTPException(status_code=409, detail="请先取消正在执行的发布；已发布或结果不确定的记录不能删除。")
    await task_manager.cancel_publishing_workflow(job_id, session_factory=request_session_factory(db))
    await db.delete(job)
    await db.commit()
    return APIResponse(data=True)


# ============================================================================
# Interactive Verification Requests (SMS / 2FA)
# ============================================================================


@router.get(
    "/verification/pending", response_model=APIResponse[list[VerificationRequestResponse]]
)
async def list_pending_verifications():
    """List all currently pending interactive verification requests awaiting user code."""
    from src.providers.publishing.verification import verification_manager

    pending = verification_manager.list_pending_requests()
    return APIResponse(
        data=[
            VerificationRequestResponse(
                request_id=req.request_id,
                job_id=req.job_id,
                account_id=req.account_id,
                account_name=req.account_name,
                title=req.title,
                platform=req.platform,
                prompt=req.prompt,
                status=req.status,
                remaining_seconds=req.remaining_seconds,
                timeout_seconds=req.timeout_seconds,
                created_at=req.created_at,
                error_message=req.error_message,
            )
            for req in pending
        ]
    )


@router.post("/verification/submit", response_model=APIResponse[bool])
async def submit_verification_code(payload: VerificationSubmitRequest):
    """Submit a verification code (e.g. SMS code) entered by user for an active job."""
    from src.providers.publishing.verification import verification_manager

    success = verification_manager.submit_code(
        request_id=payload.request_id,
        code=payload.code,
    )
    if not success:
        raise HTTPException(
            status_code=400,
            detail="验证请求不存在、已超时或已完成提交",
        )
    return APIResponse(data=True, message=f"已成功提交验证码: {payload.request_id}")


@router.post("/verification/cancel", response_model=APIResponse[bool])
async def cancel_verification(payload: VerificationCancelRequest):
    """Cancel an active verification request."""
    from src.providers.publishing.verification import verification_manager

    success = verification_manager.cancel_request(payload.request_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"未找到待处理的验证请求: {payload.request_id}",
        )
    return APIResponse(data=True, message="已取消验证请求")

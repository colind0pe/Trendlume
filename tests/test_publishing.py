import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from tests.mocks import MockPublishingProvider

from src.domain.enums import (
    AssetType,
    JobType,
    PlatformType,
    PublishJobStatus,
    TaskStatus,
)
from src.models.project import ProjectModel
from src.models.scene import SceneModel
from src.models.task import TaskModel
from src.providers.publishing.auth_service import PlatformAuthService
from src.providers.publishing.cookie_helper import (
    normalize_storage_state,
    parse_cookie_string,
)
from src.providers.publishing.douyin import (
    DouyinPublishingProvider,
    _build_douyin_caption,
    _build_douyin_publish_text,
    _normalize_douyin_tags,
)
from src.repositories.project_repository import ProjectRepository
from src.repositories.scene_repository import SceneRepository
from src.repositories.task_repository import TaskRepository
from src.schemas.publishing import (
    ManualCookieImportRequest,
    QRCompleteRequest,
    SocialAccountCreate,
)
from src.services.asset_service import AssetService
from src.services.publishing_service import PublishingService
from src.storage.local_storage import LocalStorageService


@pytest.mark.asyncio
async def test_cookie_helper_normalization():
    # 1. Parse raw cookie string
    raw_str = "sessionid=mock_session_abc; sid_guard=xyz789;"
    parsed = parse_cookie_string(raw_str, default_domain=".douyin.com")
    assert len(parsed) == 2
    assert parsed[0]["name"] == "sessionid"
    assert parsed[0]["value"] == "mock_session_abc"
    assert parsed[0]["domain"] == ".douyin.com"

    # 2. Normalize storage state dict with sameSite and domain handling
    norm_dict = normalize_storage_state(
        {
            "cookies": [
                {"name": "s_v_web_id", "value": "verify_123", "sameSite": "none"},
                {"name": "sessionid", "value": "sess_456", "sameSite": "lax"},
            ]
        },
        platform="douyin",
    )
    assert len(norm_dict["cookies"]) == 2
    assert norm_dict["cookies"][0]["domain"] == ".douyin.com"
    assert norm_dict["cookies"][0]["sameSite"] == "None"
    assert norm_dict["cookies"][0]["secure"] is True
    assert norm_dict["cookies"][1]["sameSite"] == "Lax"


def test_douyin_tags_are_normalized_and_capped():
    tags = _normalize_douyin_tags(
        ["#古墓", " 古墓 ", "科技, AI 创作", "，", "#科技", *[f"tag-{i}" for i in range(12)]]
    )

    assert tags[:4] == ["古墓", "科技", "AI", "创作"]
    assert len(tags) == 5
    assert _normalize_douyin_tags([" ", "#"]) == ["Trendlume", "AI短视频", "科普"]


def test_douyin_caption_uses_space_and_compacts_newlines():
    assert _build_douyin_caption("说明文案  ", ["#古墓", "科技"]) == "说明文案 #古墓 #科技"
    assert _build_douyin_caption("第一行\n第二行\r\n第三行", ["科技"]) == "第一行 第二行 第三行 #科技"
    assert _build_douyin_publish_text("视频标题", "说明文案", ["#古墓", "科技"]) == (
        "视频标题\n说明文案\n#古墓 #科技"
    )


def test_sanitize_douyin_payload_text():
    from src.providers.publishing.douyin import _sanitize_douyin_payload_text

    # Leading asterisk before topic
    assert _sanitize_douyin_payload_text("*#宋朝 #熟水") == "#宋朝 #熟水"
    assert _sanitize_douyin_payload_text("文案\n*#宋朝 #熟水") == "文案\n#宋朝 #熟水"
    assert _sanitize_douyin_payload_text("文案\r\n*#宋朝 #熟水") == "文案\r\n#宋朝 #熟水"

    # Multiple leading asterisks
    assert _sanitize_douyin_payload_text("**#宋朝") == "#宋朝"

    # EditorKit newline asterisk on regular text
    assert _sanitize_douyin_payload_text("第一行\n*第二行") == "第一行\n第二行"

    # Preserve markdown emphasis in body text
    assert _sanitize_douyin_payload_text("正文 *强调* #话题") == "正文 *强调* #话题"
    assert _sanitize_douyin_payload_text("家庭👨‍👩‍👧 #生活") == "家庭👨‍👩‍👧 #生活"
    assert _sanitize_douyin_payload_text("") == ""
    assert _sanitize_douyin_payload_text(None) is None


class _FakeCaptionEditor:
    def __init__(self, retained_text: str | None = None):
        self.retained_text = retained_text
        self.fill_values: list[str] = []
        self.current_text = ""

    async def fill(self, value: str):
        self.fill_values.append(value)
        self.current_text = self.retained_text if self.retained_text is not None else value

    async def inner_text(self) -> str:
        return self.current_text


class _FakeBrowserLocator:
    def __init__(self, count: int = 0, editor: _FakeCaptionEditor | None = None):
        self.count_value = count
        self.editor = editor

    @property
    def first(self):
        return self

    async def count(self) -> int:
        return self.count_value

    async def is_visible(self) -> bool:
        return self.count_value > 0

    async def wait_for(self, **kwargs):
        return None

    async def set_input_files(self, path: str):
        return None

    async def click(self, **kwargs):
        return None

    async def scroll_into_view_if_needed(self, **kwargs):
        return None

    async def fill(self, value: str):
        if self.editor is not None:
            await self.editor.fill(value)

    async def inner_text(self) -> str:
        return await self.editor.inner_text() if self.editor is not None else ""


class _FakeBrowserPage:
    url = "https://creator.douyin.com/creator-micro/content/upload"

    def __init__(self, editor: _FakeCaptionEditor):
        self.editor = editor
        self.publish_lookup = False

    async def goto(self, *args, **kwargs):
        return None

    async def wait_for_timeout(self, timeout: int):
        return None

    def locator(self, selector: str):
        if "zone-container" in selector:
            return _FakeBrowserLocator(1, self.editor)
        if "填写作品标题" in selector:
            return _FakeBrowserLocator(1)
        if 'input[type="file"]' in selector:
            return _FakeBrowserLocator(1)
        return _FakeBrowserLocator()

    def get_by_role(self, *args, **kwargs):
        self.publish_lookup = True
        return _FakeBrowserLocator()


class _FakeBrowserSession:
    def __init__(self, page: _FakeBrowserPage):
        self.page = page

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.mark.asyncio
async def test_douyin_browser_stops_before_publish_when_caption_verification_fails(
    monkeypatch, tmp_path
):
    monkeypatch.setattr("src.providers.publishing.douyin.asyncio.sleep", AsyncMock())
    editor = _FakeCaptionEditor(retained_text="错位文案")
    page = _FakeBrowserPage(editor)
    monkeypatch.setattr(
        "src.providers.publishing.douyin.BrowserManager.get_session",
        lambda *args, **kwargs: _FakeBrowserSession(page),
    )
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")

    result = await DouyinPublishingProvider()._publish_via_browser(
        video_path=video_path,
        title="视频标题",
        description="说明文案",
        tags=["古墓", "科技"],
        cover_path=None,
        credential_data={"cookies": [{"name": "sessionid", "value": "session"}]},
        custom_params={},
    )

    assert result.success is False
    assert result.raw_response["error"] == "DOUYIN_CAPTION_INVALID"
    assert page.publish_lookup is False


@pytest.mark.asyncio
async def test_douyin_open_api_uses_normalized_caption_payload(monkeypatch, tmp_path):
    calls = []

    class FakeResponse:
        status_code = 200
        text = ""

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, **kwargs):
            calls.append({"url": url, **kwargs})
            if "upload_video" in url:
                return FakeResponse({"data": {"error_code": 0, "video": {"video_id": "video-1"}}})
            return FakeResponse({"data": {"error_code": 0, "item_id": "item-1"}})

    monkeypatch.setattr("src.providers.publishing.douyin.httpx.AsyncClient", FakeClient)
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")

    result = await DouyinPublishingProvider()._publish_via_open_api(
        video_path=video_path,
        title="视频标题",
        description="说明文案",
        tags=["#古墓", "古墓", "科技"],
        credential_data={"access_token": "token", "open_id": "open"},
    )

    assert result.success is True
    assert calls[1]["json"]["text"] == "视频标题\n说明文案\n#古墓 #科技"


@pytest.mark.asyncio
async def test_mock_qr_login_flow(test_session, tmp_path):
    storage = LocalStorageService(base_storage_dir=tmp_path / "storage")
    pub_service = PublishingService(
        test_session,
        storage=storage,
        provider=MockPublishingProvider(),
    )

    # 1. Start mock QR session
    auth_srv = PlatformAuthService()
    session = auth_srv.start_qr_session(platform="mock")
    assert session.session_id.startswith("qr_mock_")

    for _ in range(10):
        if session.status == "success":
            break
        await asyncio.sleep(0.1)

    assert session.status == "success"
    assert session.storage_state is not None
    assert session.qrcode_data_url is not None
    assert auth_srv.cancel_qr_session(session.session_id) is False
    assert session.status == "success"

    # Replace pub_service auth service with our instance for complete test
    pub_service.auth = auth_srv

    # 2. Complete QR Auth
    account = await pub_service.complete_qr_login(
        QRCompleteRequest(
            session_id=session.session_id,
            account_name="抖音创作号A",
        )
    )
    assert account.id is not None
    assert account.account_name == "抖音创作号A"
    assert account.credential_id is not None

    # 3. Check account validity
    check_res = await pub_service.check_account_status(account.id)
    assert check_res.account_id == account.id


@pytest.mark.asyncio
async def test_qr_cancel_stops_mock_login_before_credentials_are_written():
    auth_srv = PlatformAuthService()
    session = auth_srv.start_qr_session(platform="mock")

    import asyncio

    for _ in range(10):
        if session.status == "pending":
            break
        await asyncio.sleep(0.05)

    assert session.status == "pending"
    assert auth_srv.cancel_qr_session(session.session_id) is True
    assert auth_srv.cancel_qr_session(session.session_id) is False

    for _ in range(20):
        if session.status == "error":
            break
        await asyncio.sleep(0.05)

    assert session.status == "error"
    assert "取消" in (session.error_message or "")
    assert session.storage_state is None


@pytest.mark.asyncio
async def test_manual_cookie_import(test_session, tmp_path):
    storage = LocalStorageService(base_storage_dir=tmp_path / "storage")
    pub_service = PublishingService(
        test_session,
        storage=storage,
        provider=MockPublishingProvider(),
    )

    account = await pub_service.import_cookie(
        ManualCookieImportRequest(
            platform="douyin",
            account_name="Cookie导入号",
            cookie_string="sessionid=my_mock_sess_999; passport_csrf_token=tok_888",
            username="douyin_user_888",
        )
    )
    assert account.id is not None
    assert account.username == "douyin_user_888"
    assert account.credential_id is not None


@pytest.mark.asyncio
async def test_douyin_provider_authentication_boundaries(tmp_path):
    provider = DouyinPublishingProvider()
    video_file = tmp_path / "test_dy_video.mp4"
    video_file.write_bytes(b"\x00" * 1024)

    # 1. Missing credentials should cleanly fail
    result_missing = await provider.publish_video(
        video_path=video_file,
        title="测试抖音爆款视频",
        description="这是一个自动化发布的抖音视频测试",
        tags=["抖音", "AI创作", "Trendlume"],
    )
    assert result_missing.success is False
    assert "缺少有效抖音授权凭证" in (result_missing.error or "")

    # 2. Account validation contract
    assert await provider.validate_account({}) is False
    assert await provider.validate_account({"cookies": [{"name": "random_cookie", "value": "123"}]}) is False
    assert (
        await provider.validate_account(
            {"cookies": [{"name": "sessionid", "value": "mock_session_test_999"}]}
        )
        is True
    )
    assert (
        await provider.validate_account({"access_token": "token_123", "open_id": "open_123"})
        is True
    )


@pytest.mark.asyncio
async def test_publishing_service_flow_with_mock_provider(test_session, tmp_path):
    storage = LocalStorageService(base_storage_dir=tmp_path / "storage")
    asset_service = AssetService(test_session, storage=storage)

    async def mock_ffmpeg_runner(cmd: list[str], output_path: Path) -> bool:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free")
        return True

    from src.services.rendering_service import RenderingService

    rendering_service = RenderingService(
        test_session, storage=storage, ffmpeg_runner=mock_ffmpeg_runner
    )
    pub_service = PublishingService(
        test_session,
        storage=storage,
        provider=MockPublishingProvider(),
        rendering_service=rendering_service,
    )

    proj_repo = ProjectRepository(test_session)
    task_repo = TaskRepository(test_session)
    scene_repo = SceneRepository(test_session)

    # 1. Create project, task and scene
    proj = ProjectModel(id="proj_pub_test", name="Pub Test", aspect_ratio="9:16")
    await proj_repo.create(proj)

    task = TaskModel(
        id="task_pub_test",
        project_id=proj.id,
        title="Quantum Teleportation Explained",
        description="Here is why quantum is awesome",
        job_type=JobType.FULL_PIPELINE.value,
        status=TaskStatus.COMPLETED.value,
    )
    await task_repo.create(task)

    img_asset = await asset_service.save_asset(
        content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
        file_name="scene.png",
        mime_type="image/png",
        asset_type=AssetType.IMAGE,
        project_id=proj.id,
    )

    scene = SceneModel(
        id="scene_pub_test_1",
        task_id=task.id,
        sequence_index=0,
        narration_text="Quantum mechanics is fascinating",
        visual_prompt="Quantum particles glowing",
        duration_seconds=3.0,
        media_asset_id=img_asset.id,
    )
    await scene_repo.create(scene)
    await test_session.commit()

    # 2. Account creation
    account = await pub_service.create_account(
        SocialAccountCreate(
            platform=PlatformType.DOUYIN,
            account_name="抖音官方号",
            username="trendlume_douyin",
        )
    )
    assert account.id is not None

    # 3. Prepare publishing job
    job = await pub_service.prepare_task_publishing(
        task_id=task.id,
        account_id=account.id,
        title="重磅！量子隐形传态的秘密",
        tags=["量子力学", "科技科普"],
        cover_asset_id=img_asset.id,
    )
    assert job.id is not None
    assert job.status == PublishJobStatus.QUEUED.value
    assert job.cover_asset_id == img_asset.id

    # 4. Execute publishing job
    executed_job = await pub_service.execute_publish_job(job.id)
    assert executed_job.status == PublishJobStatus.PUBLISHED.value
    assert executed_job.platform_post_id is not None
    assert executed_job.published_at is not None

    # 5. Schedule publishing test
    task.input_payload = {
        "metadata": {
            "title": "自动生成的抖音标题",
            "description": "自动生成的发布说明，欢迎评论区交流。",
            "tags": ["量子科普", "前沿科技"],
            "declaration": "内容由AI生成",
            "visibility": "public",
        }
    }
    await task_repo.update(task)
    await test_session.commit()
    future_time = datetime.now(UTC) + timedelta(days=2)
    sched_job = await pub_service.prepare_task_publishing(
        task_id=task.id,
        account_id=account.id,
        scheduled_at=future_time,
    )
    assert sched_job.status == PublishJobStatus.SCHEDULED.value
    assert sched_job.scheduled_at == future_time
    assert sched_job.title == "自动生成的抖音标题"
    assert sched_job.description == "自动生成的发布说明，欢迎评论区交流。"
    assert sched_job.tags == ["量子科普", "前沿科技"]
    assert sched_job.custom_params["declaration"] == "内容由AI生成"

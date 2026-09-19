"""Browser smoke coverage for the single-task creator workspace.

Run this opt-in test against a running frontend with:

    $env:TRENDLUME_FRONTEND_URL = "http://127.0.0.1:3000"
    .\\backend\\.venv\\Scripts\\python.exe -m pytest -c backend/pyproject.toml tests/e2e/test_task_storyboard_smoke.py -q

The backend API is mocked in the browser, so no external Provider or account is
required for this regression check.
"""

from __future__ import annotations

import base64
import json
import os
import re
from urllib.parse import urlparse

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

FRONTEND_URL = os.environ.get("TRENDLUME_FRONTEND_URL", "").strip()
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not FRONTEND_URL,
        reason="Set TRENDLUME_FRONTEND_URL to run the browser smoke test",
    ),
]

ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            test_page = browser.new_page()
            test_page.set_default_timeout(10_000)
            test_page.set_default_navigation_timeout(20_000)
            yield test_page
        finally:
            browser.close()


def _fulfill_api(route, data, *, status: int = 200) -> None:
    route.fulfill(
        status=status,
        content_type="application/json",
        body=json.dumps(
            {"data": data} if status < 400 else data,
            ensure_ascii=False,
        ),
    )


def _task_payload() -> dict:
    return {
        "id": "task-1",
        "project_id": "project-1",
        "title": "量子通信一分钟科普",
        "description": "前 3 秒先抛出反直觉问题。",
        "job_type": "video_composition",
        "production_mode": "knowledge",
        "status": "completed",
        "progress_percentage": 100,
        "input_payload": {
            "topic": "量子通信",
            "content_mode": "generated_image",
            "template_id": "image_default",
            "template_params": {},
            "genre": "auto",
            "target_scene_count": 8,
            "bgm_enabled": True,
            "bgm_asset_id": "bgm-1",
            "bgm_volume": 0.2,
        },
        "result_payload": {
            "final_video_url": "/api/v1/assets/files/video/final.mp4",
            "final_video_asset_id": "video-1",
        },
        "error_message": None,
        "scenes_count": 1,
        "query": "量子通信",
        "started_at": None,
        "completed_at": "2026-09-02T00:00:00Z",
        "created_at": "2026-09-02T00:00:00Z",
        "updated_at": "2026-09-02T00:00:00Z",
        "active_job": None,
        "current_stage": "ready",
        "resume_count": 0,
        "last_heartbeat_at": None,
        "can_resume": False,
        "scenes": [
            {
                "id": "scene-1",
                "task_id": "task-1",
                "sequence_index": 0,
                "narration_text": "量子通信为什么难以被窃听？",
                "visual_prompt": "发光的量子通信网络，蓝色粒子流动，主体清晰，背景简洁",
                "duration_seconds": 4,
                "layout_params": {"media_type": "image", "image_status": "completed"},
                "audio_asset_id": "audio-1",
                "media_asset_id": "image-1",
                "rendered_segment_asset_id": None,
                "created_at": "2026-09-02T00:00:00Z",
                "updated_at": "2026-09-02T00:00:00Z",
            }
        ],
    }


def _template_payload() -> dict:
    return {
        "id": "image_default",
        "name": "Image Default",
        "version": "1",
        "width": 1080,
        "height": 1920,
        "media_width": 1024,
        "media_height": 1024,
        "aspect_ratio": "9:16",
        "template_type": "image",
        "html_path": "1080x1920/image_gallery_matted.html",
        "preview_path": "previews/1080x1920/image_gallery_matted.png",
        "parameter_schema": [],
        "default_params": {},
        "supported_content_modes": ["generated_image", "uploaded_asset"],
    }


def _research_payload() -> dict:
    return {
        "topic": "量子通信",
        "status": "completed",
        "provider": "mock-search",
        "queries": ["量子通信 原理"],
        "query_records": [],
        "summary": "研究资料概要",
        "sources": [
            {"title": "量子通信资料", "url": "https://example.com/quantum", "snippet": "来源摘要"}
        ],
        "from_cache": False,
        "query_source": "heuristic",
        "warnings": [],
        "error_message": None,
        "duration_seconds": 0.1,
        "started_at": None,
        "completed_at": "2026-09-02T00:00:02Z",
    }


def _project_payload() -> dict:
    return {
        "id": "project-1",
        "name": "量子通信项目",
        "description": "用清晰的短视频解释量子通信。",
        "aspect_ratio": "9:16",
        "status": "configured",
        "primary_production_mode": "knowledge",
        "cover_asset_id": None,
        "default_voice_id": None,
        "bgm_asset_id": None,
        "settings": {},
        "template": None,
        "tasks": [],
        "created_at": "2026-09-02T00:00:00Z",
        "updated_at": "2026-09-02T00:00:00Z",
    }


def test_create_task_uses_new_scene_presets_and_auto_genre(page):
    created_payload: dict = {}
    project = _project_payload()
    template = _template_payload()

    def handle_api(route):
        request = route.request
        path = urlparse(request.url).path
        if path.endswith(("/events/stream", "/events")):
            route.fulfill(status=200, content_type="text/event-stream", body=": connected\n\n")
            return
        if path == "/api/v1/projects/project-1":
            data = project
        elif path == "/api/v1/projects/project-1/tasks":
            if request.method == "POST":
                created_payload.update(json.loads(request.post_data or "{}"))
                data = {"id": "task-new"}
            else:
                data = []
        elif path == "/api/v1/templates":
            data = [template]
        elif path.startswith("/api/v1/templates/previews/"):
            route.fulfill(status=200, content_type="image/png", body=ONE_PIXEL_PNG)
            return
        elif path in {
            "/api/v1/assets",
            "/api/v1/projects/project-1/bgm",
            "/api/v1/providers",
            "/api/v1/providers/voices",
            "/api/v1/providers/comfyui/workflows",
            "/api/v1/publishing/accounts",
        }:
            data = []
        elif path == "/api/v1/providers/summary":
            data = {}
        elif path == "/api/v1/projects/project-1/template":
            data = None
        else:
            _fulfill_api(route, {"detail": "not mocked"}, status=404)
            return
        _fulfill_api(route, data)

    page.route("**/api/v1/**", handle_api)
    page.goto(f"{FRONTEND_URL}/projects/project-1", wait_until="domcontentloaded")
    page.get_by_role("button", name="新建 Production Task").click()

    genre = page.get_by_label("知识方向")
    genre.wait_for()
    assert genre.input_value() == "auto"
    page.get_by_role("button", name="高级配置与自动化").click()
    preset_text = " ".join(page.locator('button[aria-pressed="false"], button[aria-pressed="true"]').all_text_contents())
    assert all(f"{count} 镜" in preset_text for count in (8, 12, 14, 18, 20))
    assert all(
        page.get_by_role("button", name=re.compile(rf"^{count} 镜")).count() == 0
        for count in (4, 6, 10)
    )

    page.get_by_role("button", name=re.compile(r"20 镜")).click()
    page.get_by_label("主题 / 要回答的问题").fill("量子通信为什么难以窃听")
    with page.expect_request(
        lambda request: request.method == "POST"
        and request.url.endswith("/api/v1/projects/project-1/tasks")
    ):
        page.get_by_role("button", name="创建并进入工作台").click()

    assert created_payload["title"] == "量子通信为什么难以窃听"
    assert created_payload["job_type"] == "video_composition"
    assert created_payload["target_scene_count"] == 20
    assert created_payload["input_payload"]["target_scene_count"] == 20
    assert created_payload["input_payload"]["genre"] == "auto"


def test_task_storyboard_core_flow(page):
    task = _task_payload()
    task_state = {"value": task}
    project = _project_payload()
    research_requests = {"count": 0}

    def handle_api(route):
        request = route.request
        path = urlparse(request.url).path

        if path.endswith(("/events/stream", "/events")):
            route.fulfill(status=200, content_type="text/event-stream", body=": connected\n\n")
            return
        if path == "/api/v1/projects/project-1":
            data = project
        elif path == "/api/v1/providers":
            data = []
        elif path == "/api/v1/providers/summary":
            data = {"categories": []}
        elif path == "/api/v1/tasks/task-1":
            data = task_state["value"]
        elif path == "/api/v1/tasks/task-1/workflow":
            data = {"task_id": "task-1", "stages": []}
        elif path in {
            "/api/v1/assets",
            "/api/v1/projects/project-1/bgm",
            "/api/v1/publishing/accounts",
        }:
            data = []
        elif path == "/api/v1/tasks/task-1/research":
            data = _research_payload()
        elif path in {
            "/api/v1/generation/tasks/task-1/research",
            "/api/v1/generation/research",
        }:
            research_requests["count"] += 1
            data = _research_payload()
        elif path == "/api/v1/templates":
            data = [_template_payload()]
        elif path.startswith("/api/v1/templates/previews/"):
            route.fulfill(status=200, content_type="image/png", body=ONE_PIXEL_PNG)
            return
        elif request.method in {"PATCH", "PUT"}:
            if path == "/api/v1/tasks/task-1":
                payload = json.loads(request.post_data or "{}")
                task_state["value"] = {**task_state["value"], **payload}
                data = task_state["value"]
            elif path == "/api/v1/tasks/task-1/scenes":
                data = task_state["value"]["scenes"]
            else:
                _fulfill_api(route, {"detail": "not mocked"}, status=404)
                return
        else:
            _fulfill_api(route, {"detail": "not mocked"}, status=404)
            return

        _fulfill_api(route, data)

    page.route("**/api/v1/**", handle_api)
    page.goto(f"{FRONTEND_URL}/projects/project-1/tasks/task-1", wait_until="domcontentloaded")
    page.get_by_text("量子通信一分钟科普").first.wait_for()

    title_input = page.get_by_label("视频标题")
    title_input.fill("量子通信：一分钟看懂")
    page.get_by_role("button", name="保存故事板").click()
    page.get_by_role("status").filter(has_text="故事板与成片配置已保存").wait_for()

    page.get_by_role("button", name="AI 生成脚本").click()
    assert page.get_by_label("知识方向").input_value() == "auto"
    scene_count_input = page.get_by_label("期望分镜数量")
    assert scene_count_input.get_attribute("min") == "8"
    assert scene_count_input.get_attribute("max") == "20"
    page.get_by_role("button", name="全网调研").click()
    page.get_by_text("研究资料概要").wait_for()
    assert research_requests["count"] == 1
    page.get_by_role("button", name="取消").last.click()

import shutil
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_asset_service
from src.core.exceptions import ValidationException
from src.domain.enums import AssetType
from src.models.asset import AssetModel
from src.models.project import ProjectModel
from src.models.scene import SceneModel
from src.schemas.project import ProjectCreate
from src.schemas.task import TaskCreate
from src.services.asset_service import AssetService
from src.services.project_service import ProjectService
from src.services.rendering_service import RenderingService
from src.services.system_asset_service import sync_bgm_directory_assets
from src.services.task_service import TaskService
from src.storage.local_storage import LocalStorageService, local_storage

REAL_BGM = Path(__file__).resolve().parent.parent / "backend" / "resources" / "bgm" / "default.mp3"


def _seed_bgm_directory(storage: LocalStorageService) -> Path:
    bgm_dir = storage.get_path("audio/bgm")
    bgm_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REAL_BGM, bgm_dir / "andriih-piano.mp3")
    return bgm_dir


@pytest.mark.asyncio
async def test_bgm_directory_sync_registers_real_audio_once_and_skips_invalid_files(
    test_session: AsyncSession, tmp_path: Path
):
    storage = LocalStorageService(base_storage_dir=tmp_path)
    bgm_dir = _seed_bgm_directory(storage)
    (bgm_dir / "broken.mp3").write_bytes(b"not an audio file")
    (bgm_dir / "upload.mp3.tmp").write_bytes(REAL_BGM.read_bytes())

    first_count = await sync_bgm_directory_assets(test_session, storage)
    second_count = await sync_bgm_directory_assets(test_session, storage)

    assert first_count == 1
    assert second_count == 0
    result = await test_session.execute(
        select(AssetModel).where(AssetModel.file_name == "andriih-piano.mp3")
    )
    asset = result.scalar_one()
    assert asset.asset_type == AssetType.BGM.value
    assert asset.file_path == "audio/bgm/andriih-piano.mp3"
    assert asset.project_id is None
    assert asset.duration_seconds and asset.duration_seconds > 0
    assert asset.metadata_json["duration_source"] == "ffprobe"
    assert not (
        await test_session.execute(
            select(AssetModel).where(AssetModel.file_name == "broken.mp3")
        )
    ).scalar_one_or_none()


@pytest.mark.asyncio
async def test_project_bgm_query_excludes_tts_and_noncanonical_paths(
    test_session: AsyncSession, tmp_path: Path
):
    project_id = "proj_bgm_filter"
    test_session.add(ProjectModel(id=project_id, name="BGM filter"))
    await test_session.flush()
    storage = LocalStorageService(base_storage_dir=tmp_path)
    service = AssetService(test_session, storage=storage)

    tts = await service.save_asset(
        b"tts",
        "voice.mp3",
        "audio/mpeg",
        AssetType.AUDIO,
        project_id=project_id,
    )
    project_bgm = await service.save_asset(
        REAL_BGM.read_bytes(),
        "project-bgm.mp3",
        "audio/mpeg",
        AssetType.BGM,
        project_id=project_id,
    )
    system_bgm = AssetModel(
        id="asset_bgm_system_test",
        project_id=None,
        asset_type=AssetType.BGM.value,
        file_name="system.mp3",
        file_path="audio/bgm/system.mp3",
        mime_type="audio/mpeg",
        file_size_bytes=1,
        metadata_json={"scope": "system"},
    )
    legacy_audio_in_bgm_dir = AssetModel(
        id="asset_legacy_audio",
        project_id=project_id,
        asset_type=AssetType.AUDIO.value,
        file_name="legacy.mp3",
        file_path="audio/bgm/legacy.mp3",
        mime_type="audio/mpeg",
        file_size_bytes=1,
        metadata_json={},
    )
    noncanonical_bgm = AssetModel(
        id="asset_bgm_wrong_path",
        project_id=project_id,
        asset_type=AssetType.BGM.value,
        file_name="wrong.mp3",
        file_path=f"projects/{project_id}/wrong.mp3",
        mime_type="audio/mpeg",
        file_size_bytes=1,
        metadata_json={},
    )
    test_session.add_all([system_bgm, legacy_audio_in_bgm_dir, noncanonical_bgm])
    await test_session.commit()

    assets = await service.list_project_bgm(project_id)
    asset_ids = {asset.id for asset in assets}

    assert asset_ids == {project_bgm.id, system_bgm.id}
    assert tts.id not in asset_ids
    assert legacy_audio_in_bgm_dir.id not in asset_ids
    assert noncanonical_bgm.id not in asset_ids


@pytest.mark.asyncio
async def test_bgm_upload_uses_bgm_path_ffprobe_and_project_query(
    client: AsyncClient, test_session: AsyncSession, tmp_path: Path
):
    storage = LocalStorageService(base_storage_dir=tmp_path)
    _seed_bgm_directory(storage)
    app = client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_asset_service] = lambda: AssetService(
        test_session, storage=storage
    )
    try:
        project_response = await client.post(
            "/api/v1/projects", json={"name": "BGM upload project"}
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["data"]["id"]

        upload_response = await client.post(
            "/api/v1/assets/upload",
            data={"asset_type": "bgm", "project_id": project_id},
            files={"file": ("uploaded-bgm.mp3", REAL_BGM.read_bytes(), "audio/mpeg")},
        )
        assert upload_response.status_code == 201
        asset = upload_response.json()["data"]
        assert asset["asset_type"] == "bgm"
        assert asset["file_path"].startswith("audio/bgm/")
        assert asset["duration_seconds"] > 0
        assert asset["metadata_json"]["duration_source"] == "ffprobe"

        bgm_response = await client.get(f"/api/v1/projects/{project_id}/bgm")
        assert bgm_response.status_code == 200
        assert any(item["id"] == asset["id"] for item in bgm_response.json()["data"])
        assert any(
            item["file_name"] == "andriih-piano.mp3"
            for item in bgm_response.json()["data"]
        )
    finally:
        app.dependency_overrides.pop(get_asset_service, None)


@pytest.mark.asyncio
async def test_asset_file_endpoints_reject_unsafe_or_unreadable_paths_and_serve_media(
    client: AsyncClient, test_session: AsyncSession, tmp_path: Path, monkeypatch
):
    storage = LocalStorageService(base_storage_dir=tmp_path)
    app = client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_asset_service] = lambda: AssetService(
        test_session, storage=storage
    )
    monkeypatch.setattr(local_storage, "base_dir", storage.base_dir)
    try:
        media = await AssetService(test_session, storage=storage).save_asset(
            b"media",
            "clip.mp4",
            "video/mp4",
            AssetType.VIDEO,
        )
        bgm = await AssetService(test_session, storage=storage).save_asset(
            b"bgm",
            "track.mp3",
            "audio/mpeg",
            AssetType.BGM,
        )
        unsafe = AssetModel(
            id="asset_unsafe_path",
            project_id=None,
            asset_type=AssetType.VIDEO.value,
            file_name="outside.mp4",
            file_path="../outside.mp4",
            mime_type="video/mp4",
            file_size_bytes=1,
            metadata_json={},
        )
        directory = AssetModel(
            id="asset_directory_path",
            project_id=None,
            asset_type=AssetType.VIDEO.value,
            file_name="projects",
            file_path="projects",
            mime_type="video/mp4",
            file_size_bytes=0,
            metadata_json={},
        )
        test_session.add_all([unsafe, directory])
        await test_session.commit()

        raw_traversal = await client.get(
            "/api/v1/assets/files/%2E%2E/%2E%2E/secret.mp4"
        )
        assert raw_traversal.status_code == 404
        assert "Illegal path access" not in raw_traversal.text

        missing_asset = await client.get("/api/v1/assets/missing-asset/file")
        assert missing_asset.status_code == 404

        unsafe_asset = await client.get(f"/api/v1/assets/{unsafe.id}/file")
        assert unsafe_asset.status_code == 404
        directory_asset = await client.get(f"/api/v1/assets/{directory.id}/file")
        assert directory_asset.status_code == 404

        media_response = await client.get(f"/api/v1/assets/{media.id}/file")
        assert media_response.status_code == 200
        assert media_response.content == b"media"

        bgm_response = await client.get(f"/api/v1/assets/{bgm.id}/file")
        assert bgm_response.status_code == 200
        assert bgm_response.content == b"bgm"
    finally:
        app.dependency_overrides.pop(get_asset_service, None)


@pytest.mark.asyncio
async def test_rendering_rejects_tts_asset_as_bgm(test_session: AsyncSession, tmp_path: Path):
    project = await ProjectService(test_session).create_project(
        ProjectCreate(name="BGM render validation project")
    )
    storage = LocalStorageService(base_storage_dir=tmp_path)
    asset_service = AssetService(test_session, storage=storage)
    tts = await asset_service.save_asset(
        b"tts",
        "voice.mp3",
        "audio/mpeg",
        AssetType.AUDIO,
        project_id=project.id,
    )
    clip_fixture = Path(__file__).resolve().parent / "fixtures" / "mock.mp4"
    clip = await asset_service.save_asset(
        clip_fixture.read_bytes(),
        "scene.mp4",
        "video/mp4",
        AssetType.VIDEO,
        project_id=project.id,
        duration_seconds=0.5,
        metadata={"type": "scene_clip"},
    )
    task = await TaskService(test_session).create_task(
        project.id,
        TaskCreate(
            title="render BGM validation",
            input_payload={"topic": "test"},
            bgm_enabled=False,
        ),
    )
    task.input_payload = {
        **task.input_payload,
        "bgm_enabled": True,
        "bgm_asset_id": tts.id,
    }
    test_session.add(
        SceneModel(
            id="scene_bgm_validation",
            task_id=task.id,
            sequence_index=0,
            narration_text="validation",
            visual_prompt="",
            duration_seconds=0.5,
            rendered_segment_asset_id=clip.id,
        )
    )
    await test_session.commit()

    with pytest.raises(ValidationException, match="audio/bgm"):
        await RenderingService(test_session, storage=storage).compose_task_video(task.id)

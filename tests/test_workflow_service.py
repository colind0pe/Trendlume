import pytest
from httpx import AsyncClient
from src.services.workflow_service import workflow_service


def test_scan_workflows_subfolders():
    items = workflow_service.scan_workflows()
    assert {item["type"] for item in items} >= {"image", "video", "audio", "analysis"}
    assert {item["subfolder"] for item in items} >= {"image", "video", "audio", "analysis"}

    by_id = {item["id"]: item for item in items}
    assert by_id["image/image_flux.json"]["file_name"] == "image_flux.json"
    assert by_id["video/video_wan2.1_fusionx.json"]["file_name"] == "video_wan2.1_fusionx.json"
    assert all(item["name"] for item in by_id.values())


def test_resolve_workflow_file_various_formats():
    # 1. Exact subfolder relative path
    p1 = workflow_service.resolve_workflow_file("image/image_flux.json")
    assert p1 is not None
    assert p1.exists()
    assert p1.name == "image_flux.json"

    # 2. Filename only match
    p2 = workflow_service.resolve_workflow_file("image_flux.json")
    assert p2 is not None
    assert p2.exists()
    assert p2.name == "image_flux.json"

    # Filename lookup remains deterministic when only a workflow filename is stored.
    p3 = workflow_service.resolve_workflow_file("selfhost/video_wan2.1_fusionx.json")
    assert p3 is not None
    assert p3.exists()
    assert p3.name == "video_wan2.1_fusionx.json"

    # 4. Non-existent workflow target
    p4 = workflow_service.resolve_workflow_file("non_existent_workflow_xyz.json")
    assert p4 is None

    # 5. Empty / None target
    assert workflow_service.resolve_workflow_file("") is None
    assert workflow_service.resolve_workflow_file(None) is None


@pytest.mark.asyncio
async def test_api_list_comfyui_workflows(client: AsyncClient):
    res = await client.get("/api/v1/providers/comfyui/workflows", params={"type": "image"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data
    assert {item["type"] for item in data} == {"image"}

    for item in data:
        assert "id" in item
        assert "name" in item
        assert "type" in item
        assert "subfolder" in item
        assert "file_name" in item

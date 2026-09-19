from pathlib import Path

import pytest
from httpx import AsyncClient

from src.services.product_service import ProductService
from src.storage.local_storage import LocalStorageService


@pytest.mark.asyncio
async def test_product_api_crud_truth_sheet_and_asset_upload(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    storage = LocalStorageService(tmp_path / "storage")
    monkeypatch.setattr(
        "src.api.dependencies.ProductService",
        lambda session: ProductService(session, storage=storage),
    )

    created = await client.post(
        "/api/v1/products",
        json={
            "name": "API 商品",
            "brand": "Demo",
            "price": "129",
            "currency": "CNY",
            "specifications": {"容量": "500ml"},
            "selling_points": [{"text": "用户确认卖点"}],
        },
    )
    assert created.status_code == 201
    product = created.json()["data"]
    product_id = product["id"]
    assert product["title"] == "API 商品"
    assert product["truth_sheet"]["selling_points"][0]["evidence_refs"]

    listed = await client.get("/api/v1/products")
    assert listed.status_code == 200
    assert listed.json()["data"][0]["id"] == product_id

    updated = await client.patch(
        f"/api/v1/products/{product_id}",
        json={"description": "人工核对后的描述", "price": "139"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["description"] == "人工核对后的描述"
    assert updated.json()["data"]["truth_sheet"]["facts"]

    truth = updated.json()["data"]["truth_sheet"]
    truth["unresolved_fields"] = []
    truth_updated = await client.put(
        f"/api/v1/products/{product_id}/truth-sheet",
        json={"truth_sheet": truth},
    )
    assert truth_updated.status_code == 200
    assert truth_updated.json()["data"]["truth_sheet"]["unresolved_fields"] == []

    uploaded = await client.post(
        f"/api/v1/products/{product_id}/assets",
        files={"file": ("hero.png", b"fake-png", "image/png")},
        data={"asset_type": "image", "role": "hero", "alt_text": "商品主图"},
    )
    assert uploaded.status_code == 201
    asset = uploaded.json()["data"]["assets"][0]
    assert asset["role"] == "hero"
    assert asset["asset_id"]

    updated_asset = await client.patch(
        f"/api/v1/products/{product_id}/assets/{asset['id']}",
        json={"role": "proof", "alt_text": "核对后的商品主图"},
    )
    assert updated_asset.status_code == 200
    assert updated_asset.json()["data"]["assets"][0]["role"] == "proof"

    deleted_asset = await client.delete(
        f"/api/v1/products/{product_id}/assets/{asset['id']}"
    )
    assert deleted_asset.status_code == 200
    assert deleted_asset.json()["data"] is True

    deleted = await client.delete(f"/api/v1/products/{product_id}")
    assert deleted.status_code == 200
    assert deleted.json()["data"] is True


@pytest.mark.asyncio
async def test_commerce_task_api_persists_product_reference(client: AsyncClient):
    product_response = await client.post(
        "/api/v1/products",
        json={"title": "Commerce API 商品", "brand": "Demo"},
    )
    product_id = product_response.json()["data"]["id"]
    project_response = await client.post(
        "/api/v1/projects",
        json={"name": "Commerce API 项目", "primary_production_mode": "commerce"},
    )
    project_id = project_response.json()["data"]["id"]
    task_response = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={
            "title": "API 商品视频",
            "production_mode": "commerce",
            "product_id": product_id,
            "creative_angle": "demo",
            "content_mode": "static",
            "template_id": "static_editorial_quote",
            "enable_research": False,
            "bgm_enabled": False,
        },
    )
    assert task_response.status_code == 201
    assert task_response.json()["data"]["product_id"] == product_id
    assert task_response.json()["data"]["creative_angle"] == "demo"

    blocked = await client.delete(f"/api/v1/products/{product_id}")
    assert blocked.status_code == 409
    assert "Commerce" in blocked.json()["error"]["message"]

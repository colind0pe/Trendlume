from datetime import datetime

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"status", "app_name", "version", "timestamp", "storage"}
    assert data["status"] == "healthy"
    assert data["app_name"] == "Trendlume"
    assert isinstance(data["version"], str) and data["version"]
    assert datetime.fromisoformat(data["timestamp"]).tzinfo is not None

    storage = data["storage"]
    assert isinstance(storage, dict)
    assert set(storage) == {"data_dir", "storage_dir"}
    assert all(isinstance(value, str) and value for value in storage.values())

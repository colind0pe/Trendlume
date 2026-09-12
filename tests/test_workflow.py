import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_task_api_generate_and_cancel(client: AsyncClient):
    # 1. Create Project and Task
    p_res = await client.post("/api/v1/projects", json={"name": "Cancel Test Project", "aspect_ratio": "9:16"})
    proj_id = p_res.json()["data"]["id"]

    t_res = await client.post(
        f"/api/v1/projects/{proj_id}/tasks",
        json={
            "title": "To be cancelled task",
            "material_provider_id": "material-provider-contract",
        },
    )
    task_id = t_res.json()["data"]["id"]
    assert t_res.json()["data"]["input_payload"]["material_provider_id"] == "material-provider-contract"

    # 2. Trigger generate
    gen_res = await client.post(f"/api/v1/tasks/{task_id}/generate")
    assert gen_res.status_code == 200
    generated_job = gen_res.json()["data"]
    assert generated_job["task_id"] == task_id
    assert generated_job["type"] == generated_job["job_type"] == "full_pipeline"
    assert generated_job["current_step"] == generated_job["current_stage"] == "queued"
    assert generated_job["error"] is None and generated_job["error_message"] is None
    assert generated_job["checkpoint"] == {}
    assert generated_job["available_at"] and generated_job["updated_at"]
    assert generated_job["scheduled_at"] is None

    # 3. Cancel task
    cancel_res = await client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["data"] is True

    # 4. Retry task
    retry_res = await client.post(f"/api/v1/tasks/{task_id}/retry")
    assert retry_res.status_code == 200
    retried_job = retry_res.json()["data"]
    assert retried_job["retry_count"] >= 1
    assert retried_job["checkpoint"] == {}
    assert retried_job["available_at"] and retried_job["updated_at"]
    assert retried_job["scheduled_at"] is None

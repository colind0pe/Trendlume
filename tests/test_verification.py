import asyncio

import pytest

from src.providers.publishing.verification import VerificationManager


@pytest.mark.asyncio
async def test_verification_manager_lifecycle():
    vm = VerificationManager()

    # 1. Create verification request
    req = vm.request_code(
        job_id="job_test_123",
        account_id="acc_test_456",
        platform="douyin",
        prompt="测试短信验证码输入",
        account_name="测试创作者",
        title="测试短视频",
        timeout_seconds=5.0,
    )
    assert req.request_id == "ver_douyin_job_test_123"
    assert req.status == "pending"
    assert not req.is_expired
    assert req.remaining_seconds > 0

    # 2. List pending requests
    pending = vm.list_pending_requests()
    assert len(pending) == 1
    assert pending[0].request_id == req.request_id

    # 3. Test async wait and submit
    async def _waiter():
        return await vm.wait_for_code(req.request_id)

    wait_task = asyncio.create_task(_waiter())
    await asyncio.sleep(0.2)

    # Submit code
    ok = vm.submit_code(req.request_id, "889922")
    assert ok is True

    code = await wait_task
    assert code == "889922"

    # Complete request
    vm.complete_request(req.request_id)
    assert len(vm.list_pending_requests()) == 0

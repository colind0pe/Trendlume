from __future__ import annotations

import asyncio
import mimetypes
import time
from pathlib import Path

import httpx

from src.core.exceptions import ProviderException
from src.core.security import redact_sensitive_text


class RunningHubWorkflowClient:
    """Small client for RunningHub's configurable ComfyUI workflow API."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float,
        generation_timeout: float,
        poll_interval: float,
    ):
        self.api_key = str(api_key or "").strip()
        self.base_url = (base_url or "https://www.runninghub.ai").rstrip("/")
        self.timeout = float(timeout)
        self.generation_timeout = float(generation_timeout)
        self.poll_interval = max(1.0, float(poll_interval))

    async def upload(self, client: httpx.AsyncClient, path_value: str) -> str:
        path = Path(path_value)
        if not path.is_file():
            raise ProviderException("runninghub", f"工作流输入文件不存在: {path_value}")
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as source:
            response = await client.post(
                f"{self.base_url}/task/openapi/upload",
                data={"apiKey": self.api_key, "fileType": "input"},
                files={"file": (path.name, source, mime_type)},
            )
        body = self._body(response, "上传输入文件")
        file_name = (
            (body.get("data") or {}).get("fileName") if isinstance(body.get("data"), dict) else None
        )
        if not file_name:
            raise ProviderException("runninghub", "RunningHub 上传成功响应中没有 fileName。")
        return str(file_name)

    async def run(self, workflow_id: str, node_info_list: list[dict]) -> tuple[bytes, str]:
        if not self.api_key:
            raise ProviderException("runninghub", "RunningHub 未配置 API Key。")
        if not str(workflow_id or "").strip():
            raise ProviderException("runninghub", "RunningHub 未配置 Workflow ID。")
        payload = {
            "apiKey": self.api_key,
            "workflowId": str(workflow_id),
            "nodeInfoList": node_info_list,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, trust_env=False, follow_redirects=True
            ) as client:
                create = await client.post(f"{self.base_url}/task/openapi/create", json=payload)
                body = self._body(create, "创建工作流任务")
                data = body.get("data")
                task_id = data.get("taskId") if isinstance(data, dict) else data
                if not task_id:
                    raise ProviderException("runninghub", "RunningHub 创建响应中没有 taskId。")
                output_url, output_type = await self._poll_output(client, str(task_id))
                download = await client.get(output_url)
                if not download.is_success or not download.content:
                    raise ProviderException(
                        "runninghub", f"下载工作流输出失败 HTTP {download.status_code}。"
                    )
                mime_type = download.headers.get("content-type", "application/octet-stream").split(
                    ";", 1
                )[0]
                if mime_type == "application/octet-stream":
                    suffix = str(output_type or "").lower().lstrip(".")
                    mime_type = mimetypes.types_map.get(f".{suffix}", mime_type)
                return download.content, mime_type
        except ProviderException:
            raise
        except httpx.RequestError as exc:
            raise ProviderException("runninghub", f"连接 RunningHub 失败: {exc}") from exc

    async def _poll_output(self, client: httpx.AsyncClient, task_id: str) -> tuple[str, str]:
        deadline = time.monotonic() + self.generation_timeout
        while True:
            response = await client.post(
                f"{self.base_url}/task/openapi/outputs",
                json={"apiKey": self.api_key, "taskId": task_id},
            )
            body = self._body(response, "查询工作流输出", allow_codes={0, 805})
            data = body.get("data")
            if body.get("code") == 805:
                reason = data.get("failedReason") if isinstance(data, dict) else data
                raise ProviderException(
                    "runninghub",
                    f"RunningHub 工作流执行失败: {reason or body.get('msg') or '未知错误'}",
                )
            if isinstance(data, list) and data:
                output = next(
                    (item for item in data if isinstance(item, dict) and item.get("fileUrl")), None
                )
                if output:
                    return str(output["fileUrl"]), str(output.get("fileType") or "")
            if time.monotonic() >= deadline:
                raise ProviderException(
                    "runninghub",
                    f"RunningHub 工作流等待超时 ({self.generation_timeout}s，task_id={task_id})。",
                )
            await asyncio.sleep(self.poll_interval)

    @staticmethod
    def _body(response: httpx.Response, action: str, allow_codes: set[int] | None = None) -> dict:
        if not response.is_success:
            raise ProviderException(
                "runninghub",
                f"RunningHub {action}失败 HTTP {response.status_code}: {redact_sensitive_text(response.text[:500])}",
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderException("runninghub", f"RunningHub {action}返回了无效 JSON。") from exc
        allowed = allow_codes or {0}
        if not isinstance(body, dict) or body.get("code") not in allowed:
            message = body.get("msg") if isinstance(body, dict) else body
            raise ProviderException(
                "runninghub", f"RunningHub {action}失败: {redact_sensitive_text(str(message))}"
            )
        return body


def node_value(node_id: str | None, field_name: str | None, value: object) -> dict | None:
    if not str(node_id or "").strip() or value is None:
        return None
    return {
        "nodeId": str(node_id).strip(),
        "fieldName": str(field_name or "text").strip(),
        "fieldValue": str(value),
    }


def node_ids(value: str | list | None) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]

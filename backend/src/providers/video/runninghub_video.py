from __future__ import annotations

import httpx

from src.core.exceptions import ProviderException
from src.providers.media_utils import output_dimensions
from src.providers.runninghub import RunningHubWorkflowClient, node_ids, node_value
from src.providers.video.protocol import VideoResult


class RunningHubVideoProvider:
    name = "runninghub"
    DEFAULT_BASE_URL = "https://www.runninghub.ai"

    def __init__(
        self,
        api_key: str,
        workflow_id: str,
        base_url: str = DEFAULT_BASE_URL,
        *,
        prompt_node_id: str,
        prompt_field_name: str = "text",
        width_node_id: str | None = None,
        width_field_name: str = "width",
        height_node_id: str | None = None,
        height_field_name: str = "height",
        duration_node_id: str | None = None,
        duration_field_name: str = "duration",
        first_frame_node_id: str | None = None,
        first_frame_field_name: str = "image",
        last_frame_node_id: str | None = None,
        last_frame_field_name: str = "image",
        reference_node_ids: str | list | None = None,
        reference_field_name: str = "image",
        timeout: float = 60.0,
        generation_timeout: float = 1800.0,
        poll_interval: float = 5.0,
    ):
        self.workflow_id = str(workflow_id or "").strip()
        self.prompt_node_id, self.prompt_field_name = (
            str(prompt_node_id or "").strip(),
            prompt_field_name,
        )
        self.width_node_id, self.width_field_name = width_node_id, width_field_name
        self.height_node_id, self.height_field_name = height_node_id, height_field_name
        self.duration_node_id, self.duration_field_name = duration_node_id, duration_field_name
        self.first_frame_node_id, self.first_frame_field_name = (
            first_frame_node_id,
            first_frame_field_name,
        )
        self.last_frame_node_id, self.last_frame_field_name = (
            last_frame_node_id,
            last_frame_field_name,
        )
        self.reference_node_ids, self.reference_field_name = (
            node_ids(reference_node_ids),
            reference_field_name,
        )
        self.client = RunningHubWorkflowClient(
            api_key, base_url, timeout, generation_timeout, poll_interval
        )

    async def generate_video(
        self,
        prompt: str,
        image_url: str | None = None,
        aspect_ratio: str = "9:16",
        duration_seconds: float = 4.0,
        workflow: str | None = None,
        width: int | None = None,
        height: int | None = None,
        last_frame_url: str | None = None,
        reference_image_urls: list[str] | None = None,
    ) -> VideoResult:
        if not self.prompt_node_id:
            raise ProviderException(self.name, "RunningHub 未配置提示词节点 ID。")
        if image_url and not self.first_frame_node_id:
            raise ProviderException(self.name, "RunningHub 工作流未配置首帧节点 ID。")
        if last_frame_url and not self.last_frame_node_id:
            raise ProviderException(self.name, "RunningHub 工作流未配置尾帧节点 ID。")
        references = list(reference_image_urls or [])
        if references and len(self.reference_node_ids) < len(references):
            raise ProviderException(
                self.name, "RunningHub 参考图节点数量少于短剧参考资产数量，请补充节点映射。"
            )
        paths = [item for item in [image_url, last_frame_url, *references] if item]
        async with httpx.AsyncClient(timeout=self.client.timeout, trust_env=False) as upload_client:
            uploaded = [await self.client.upload(upload_client, item) for item in paths]
        cursor = iter(uploaded)
        first_value = next(cursor) if image_url else None
        last_value = next(cursor) if last_frame_url else None
        ref_values = list(cursor)
        target_width, target_height = output_dimensions(aspect_ratio, width, height)
        values = [
            node_value(self.prompt_node_id, self.prompt_field_name, prompt),
            node_value(self.width_node_id, self.width_field_name, target_width),
            node_value(self.height_node_id, self.height_field_name, target_height),
            node_value(
                self.duration_node_id,
                self.duration_field_name,
                max(1, int(round(duration_seconds))),
            ),
            node_value(self.first_frame_node_id, self.first_frame_field_name, first_value),
            node_value(self.last_frame_node_id, self.last_frame_field_name, last_value),
        ]
        values.extend(
            node_value(node_id, self.reference_field_name, value)
            for node_id, value in zip(self.reference_node_ids, ref_values)
        )
        content, mime_type = await self.client.run(
            workflow or self.workflow_id, [item for item in values if item]
        )
        if not mime_type.startswith("video/"):
            raise ProviderException(self.name, f"RunningHub 工作流返回的不是视频: {mime_type}")
        return VideoResult(
            content,
            float(max(1, int(round(duration_seconds)))),
            target_width,
            target_height,
            "mp4",
            mime_type,
        )

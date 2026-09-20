from __future__ import annotations

import httpx

from src.core.exceptions import ProviderException
from src.providers.image.protocol import ImageResult
from src.providers.image.style_presets import apply_image_style_preset
from src.providers.media_utils import output_dimensions
from src.providers.runninghub import RunningHubWorkflowClient, node_ids, node_value


class RunningHubImageProvider:
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
        reference_node_ids: str | list | None = None,
        reference_field_name: str = "image",
        timeout: float = 60.0,
        generation_timeout: float = 1800.0,
        poll_interval: float = 5.0,
    ):
        self.workflow_id = str(workflow_id or "").strip()
        self.prompt_node_id = str(prompt_node_id or "").strip()
        self.prompt_field_name = prompt_field_name
        self.width_node_id, self.width_field_name = width_node_id, width_field_name
        self.height_node_id, self.height_field_name = height_node_id, height_field_name
        self.reference_node_ids, self.reference_field_name = (
            node_ids(reference_node_ids),
            reference_field_name,
        )
        self.client = RunningHubWorkflowClient(
            api_key, base_url, timeout, generation_timeout, poll_interval
        )

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "9:16",
        style_preset: str = "cinematic",
        workflow: str | None = None,
        width: int | None = None,
        height: int | None = None,
        reference_image_path: str | None = None,
        reference_image_paths: list[str] | None = None,
        continuity_input: dict | None = None,
    ) -> ImageResult:
        del continuity_input
        if not self.prompt_node_id:
            raise ProviderException(self.name, "RunningHub 未配置提示词节点 ID。")
        references = list(reference_image_paths or [])
        if reference_image_path and reference_image_path not in references:
            references.insert(0, reference_image_path)
        if references and len(self.reference_node_ids) < len(references):
            raise ProviderException(
                self.name, "RunningHub 参考图节点数量少于短剧参考资产数量，请补充节点映射。"
            )
        target_width, target_height = output_dimensions(aspect_ratio, width, height)
        async with httpx.AsyncClient(timeout=self.client.timeout, trust_env=False) as upload_client:
            uploaded = [await self.client.upload(upload_client, item) for item in references]
        values = [
            node_value(
                self.prompt_node_id,
                self.prompt_field_name,
                apply_image_style_preset(prompt, style_preset),
            ),
            node_value(self.width_node_id, self.width_field_name, target_width),
            node_value(self.height_node_id, self.height_field_name, target_height),
        ]
        values.extend(
            node_value(node_id, self.reference_field_name, value)
            for node_id, value in zip(self.reference_node_ids, uploaded)
        )
        content, mime_type = await self.client.run(
            workflow or self.workflow_id, [item for item in values if item]
        )
        if not mime_type.startswith("image/"):
            raise ProviderException(self.name, f"RunningHub 工作流返回的不是图片: {mime_type}")
        return ImageResult(
            content, mime_type, target_width, target_height, mime_type.split("/", 1)[1]
        )

import asyncio
import json
import mimetypes
import uuid
from pathlib import Path

import httpx
from loguru import logger

from src.core.exceptions import ProviderException
from src.providers.image.protocol import ImageResult
from src.providers.image.style_presets import apply_image_style_preset
from src.services.workflow_service import workflow_service

DEFAULT_COMFYUI_IMAGE_WORKFLOW = "image/image_flux.json"
COMFYUI_IMAGE_COMPATIBILITY_WORKFLOW = "image/image_z_image_turbo.json"


class ComfyUIImageProvider:
    """ComfyUI Image Generation Provider via REST API with Workflow & API Key support"""

    name = "comfyui"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8188",
        api_key: str | None = None,
        default_workflow: str = DEFAULT_COMFYUI_IMAGE_WORKFLOW,
        timeout: float = 120.0,
        generation_timeout: float = 1800.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_workflow = default_workflow or DEFAULT_COMFYUI_IMAGE_WORKFLOW
        self.timeout = timeout
        self.generation_timeout = generation_timeout

    def _get_headers(self) -> dict[str, str]:
        headers = {}
        if self.api_key and self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"
        return headers

    @staticmethod
    def _is_prompt_validation_error(response: httpx.Response) -> bool:
        if response.status_code != 400:
            return False
        try:
            payload = response.json()
        except ValueError:
            return False
        error = payload.get("error") if isinstance(payload, dict) else None
        return isinstance(error, dict) and error.get("type") == "prompt_outputs_failed_validation"

    @staticmethod
    def _format_queue_error(response: httpx.Response) -> str:
        raw_text = response.text.strip()
        try:
            payload = response.json()
        except ValueError:
            return raw_text[:1000]

        error = payload.get("error") if isinstance(payload, dict) else None
        summary = ""
        if isinstance(error, dict):
            summary = str(error.get("message") or error.get("type") or "").strip()
        node_errors = payload.get("node_errors") if isinstance(payload, dict) else None
        details: list[str] = []
        if isinstance(node_errors, dict):
            for node_id, node_error in node_errors.items():
                errors = node_error.get("errors", []) if isinstance(node_error, dict) else []
                for item in errors:
                    if not isinstance(item, dict):
                        continue
                    detail = str(item.get("details") or item.get("message") or "").strip()
                    if detail:
                        details.append(f"节点 {node_id}: {detail}")
        if summary and details:
            return f"{summary}；{'；'.join(details)}"
        return summary or raw_text[:1000]

    def _load_workflow_graph(
        self,
        workflow_name: str | None,
        prompt: str,
        width: int,
        height: int,
        reference_image_name: str | None = None,
    ) -> dict:
        """Load and parameterize one canonical workflow catalog entry."""
        wf_target = workflow_name or self.default_workflow
        workflows_dir = Path(__file__).resolve().parent.parent.parent.parent / "workflows"
        wf_path = workflow_service.resolve_workflow_file(wf_target, workflows_dir)
        if wf_path is None:
            raise ProviderException("ComfyUI", f"工作流不存在或不是 canonical catalog id: {wf_target}")
        try:
            with open(wf_path, encoding="utf-8") as f:
                graph = json.load(f)
        except (OSError, TypeError, ValueError) as exc:
            raise ProviderException("ComfyUI", f"读取工作流失败 ({wf_target}): {exc}") from exc
        if not isinstance(graph, dict):
            raise ProviderException("ComfyUI", f"工作流必须是节点对象 ({wf_target})")

        reference_bound = False
        # Inject prompt, dimensions, and an optional uploaded reference into
        # the canonical graph. Reference images are never silently ignored.
        for node_id, node in graph.items():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs", {})
            class_type = node.get("class_type", "")
            title = node.get("_meta", {}).get("title", "")

            if "$prompt" in title or class_type == "CLIPTextEncode" or "prompt" in str(title).lower():
                if "text" in inputs and isinstance(inputs["text"], str):
                    inputs["text"] = prompt
                elif "value" in inputs and isinstance(inputs["value"], str):
                    inputs["value"] = prompt

            if class_type in {"EmptyLatentImage", "EmptySD3LatentImage"}:
                if "width" in inputs and isinstance(inputs["width"], (int, float)):
                    inputs["width"] = width
                if "height" in inputs and isinstance(inputs["height"], (int, float)):
                    inputs["height"] = height

            if reference_image_name and class_type in {"LoadImage", "LoadImageOutput"}:
                if "image" in inputs:
                    inputs["image"] = reference_image_name
                    reference_bound = True

        if reference_image_name and not reference_bound:
            raise ProviderException(
                "ComfyUI",
                f"工作流 {wf_target} 不包含可绑定参考图的 LoadImage 节点；"
                "请改用 img2img 工作流，不能静默退化为文生图。",
            )

        logger.info(f"Loaded ComfyUI workflow graph from {wf_path}")
        return graph

    async def _upload_reference_image(self, client: httpx.AsyncClient, path: str) -> str:
        reference_path = Path(path)
        if not reference_path.is_file():
            raise ProviderException("ComfyUI", f"参考图不存在: {path}")
        mime_type = mimetypes.guess_type(reference_path.name)[0] or "application/octet-stream"
        try:
            with reference_path.open("rb") as stream:
                response = await client.post(
                    f"{self.base_url}/upload/image",
                    files={"image": (reference_path.name, stream, mime_type)},
                    data={"type": "input", "overwrite": "true"},
                )
        except OSError as exc:
            raise ProviderException("ComfyUI", f"读取参考图失败: {path}") from exc
        if response.status_code != 200:
            raise ProviderException(
                "ComfyUI",
                f"上传参考图失败 (Status {response.status_code}): {response.text[:500]}",
            )
        try:
            name = response.json().get("name")
        except ValueError as exc:
            raise ProviderException("ComfyUI", "上传参考图响应不是有效 JSON。") from exc
        if not isinstance(name, str) or not name:
            raise ProviderException("ComfyUI", "上传参考图响应缺少文件名。")
        return name

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "9:16",
        style_preset: str = "cinematic",
        workflow: str | None = None,
        width: int | None = None,
        height: int | None = None,
        reference_image_path: str | None = None,
        continuity_input: dict | None = None,
    ) -> ImageResult:
        prompt = apply_image_style_preset(prompt, style_preset)
        if width is None or height is None or width <= 0 or height <= 0:
            width, height = (
                (720, 1280)
                if aspect_ratio == "9:16"
                else (1280, 720)
                if aspect_ratio == "16:9"
                else (1024, 1024)
            )
        else:
            width, height = int(width), int(height)
        client_id = f"trendlume_{uuid.uuid4().hex[:8]}"
        uses_default_workflow = workflow is None
        headers = self._get_headers()

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
                reference_image_name = (
                    await self._upload_reference_image(client, reference_image_path)
                    if reference_image_path
                    else None
                )
                prompt_graph = self._load_workflow_graph(
                    workflow,
                    prompt,
                    width,
                    height,
                    reference_image_name=reference_image_name,
                )
                # 1. Queue prompt
                queue_res = await client.post(
                    f"{self.base_url}/prompt",
                    json={"prompt": prompt_graph, "client_id": client_id},
                )
                if (
                    self._is_prompt_validation_error(queue_res)
                    and uses_default_workflow
                    and self.default_workflow == DEFAULT_COMFYUI_IMAGE_WORKFLOW
                ):
                    # Only the built-in default gets a compatibility retry.
                    # A saved custom default or an explicit per-call workflow
                    # must fail visibly so the configured workflow is actually
                    # tested instead of being silently replaced.
                    fallback_graph = self._load_workflow_graph(
                        COMFYUI_IMAGE_COMPATIBILITY_WORKFLOW,
                        prompt,
                        width,
                        height,
                        reference_image_name=reference_image_name,
                    )
                    fallback_res = await client.post(
                        f"{self.base_url}/prompt",
                        json={"prompt": fallback_graph, "client_id": client_id},
                    )
                    if fallback_res.status_code == 200:
                        logger.warning(
                            "ComfyUI default workflow {} failed validation; using compatible fallback {}",
                            self.default_workflow,
                            COMFYUI_IMAGE_COMPATIBILITY_WORKFLOW,
                        )
                    queue_res = fallback_res
                if queue_res.status_code != 200:
                    raise ProviderException(
                        "ComfyUI",
                        f"提交 ComfyUI 工作流失败 (Status {queue_res.status_code}): "
                        f"{self._format_queue_error(queue_res)}",
                    )

                prompt_id = queue_res.json().get("prompt_id")
                if not prompt_id:
                    raise ProviderException("ComfyUI", "ComfyUI 返回未包含有效 prompt_id")

                logger.info(f"ComfyUI image job queued: {prompt_id} on {self.base_url}")

                # 2. Poll history until execution complete
                start_time = asyncio.get_event_loop().time()
                image_output = None

                while (asyncio.get_event_loop().time() - start_time) < self.generation_timeout:
                    await asyncio.sleep(1.0)
                    history_res = await client.get(f"{self.base_url}/history/{prompt_id}")
                    if history_res.status_code == 200:
                        history_data = history_res.json()
                        if prompt_id in history_data:
                            history = history_data[prompt_id]
                            status = history.get("status", {})
                            if status.get("status_str") == "error":
                                raise ProviderException(
                                    "ComfyUI", f"ComfyUI 工作流执行失败 (prompt_id={prompt_id})，请检查 ComfyUI 日志。"
                                )
                            outputs = history.get("outputs", {})
                            for node_id, node_out in outputs.items():
                                if "images" in node_out and len(node_out["images"]) > 0:
                                    image_output = node_out["images"][0]
                                    break
                            if image_output:
                                break
                            if status.get("completed"):
                                raise ProviderException("ComfyUI", "ComfyUI 工作流已完成，但未返回输出图像。")

                if not image_output:
                    raise ProviderException(
                        "ComfyUI",
                        f"ComfyUI 生图等待超时 ({self.generation_timeout}s，prompt_id={prompt_id})。"
                        "任务可能仍在 ComfyUI 中排队或运行，可调大 generation_timeout 配置。",
                    )

                # 3. Download generated image
                view_params = {
                    "filename": image_output.get("filename"),
                    "subfolder": image_output.get("subfolder", ""),
                    "type": image_output.get("type", "output"),
                }
                img_res = await client.get(f"{self.base_url}/view", params=view_params)
                if img_res.status_code != 200:
                    raise ProviderException(
                        "ComfyUI",
                        f"获取 ComfyUI 图像输出失败 (Status {img_res.status_code})",
                    )

                logger.info(f"ComfyUI image generated successfully: {image_output.get('filename')}")
                return ImageResult(
                    image_bytes=img_res.content,
                    mime_type="image/png",
                    width=width,
                    height=height,
                    format="png",
                )

        except httpx.RequestError as e:
            logger.error(f"Failed to connect to ComfyUI at {self.base_url}: {e}")
            raise ProviderException(
                "ComfyUI",
                f"连接 ComfyUI 服务失败 ({self.base_url})。请确认已启动 ComfyUI 或检查设置。",
            ) from e

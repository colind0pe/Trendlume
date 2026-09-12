import asyncio
import json
import random
import uuid
from pathlib import Path

import httpx
from loguru import logger

from src.core.exceptions import ProviderException
from src.providers.image.protocol import ImageResult
from src.providers.image.style_presets import apply_image_style_preset
from src.services.workflow_service import workflow_service


class ComfyUIImageProvider:
    """ComfyUI Image Generation Provider via REST API with Workflow & API Key support"""

    name = "comfyui"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8188",
        api_key: str | None = None,
        default_workflow: str = "image/image_flux.json",
        timeout: float = 120.0,
        generation_timeout: float = 1800.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_workflow = default_workflow
        self.timeout = timeout
        self.generation_timeout = generation_timeout

    def _get_headers(self) -> dict[str, str]:
        headers = {}
        if self.api_key and self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"
        return headers

    def _load_workflow_graph(self, workflow_name: str | None, prompt: str, width: int, height: int) -> dict:
        """Load workflow JSON from workflows directory or build default standard graph"""
        wf_target = workflow_name or self.default_workflow
        workflows_dir = Path(__file__).resolve().parent.parent.parent.parent / "workflows"
        wf_path = workflow_service.resolve_workflow_file(wf_target, workflows_dir)

        if wf_path and wf_path.exists():
            try:
                with open(wf_path, encoding="utf-8") as f:
                    graph = json.load(f)

                # Inject prompt into prompt node if found
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

                    if "EmptyLatentImage" in class_type:
                        if "width" in inputs and isinstance(inputs["width"], (int, float)):
                            inputs["width"] = width
                        if "height" in inputs and isinstance(inputs["height"], (int, float)):
                            inputs["height"] = height

                logger.info(f"Loaded ComfyUI workflow graph from {wf_path}")
                return graph
            except Exception as e:
                logger.warning(f"Failed to parse custom workflow {wf_path}, fallback to default: {e}")

        # Standard Fallback Prompt Graph
        return {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "cfg": 8,
                    "denoise": 1,
                    "latent_image": ["5", 0],
                    "model": ["4", 0],
                    "negative": ["7", 0],
                    "positive": ["6", 0],
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "seed": random.randint(1, 10**15),
                    "steps": 20,
                },
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "batch_size": 1,
                    "height": height,
                    "width": width,
                },
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["4", 1], "text": prompt},
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["4", 1],
                    "text": "low quality, blurry, distorted, watermark, text",
                },
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": "Trendlume", "images": ["8", 0]},
            },
        }

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "9:16",
        style_preset: str = "cinematic",
        workflow: str | None = None,
        width: int | None = None,
        height: int | None = None,
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
        prompt_graph = self._load_workflow_graph(workflow, prompt, width, height)
        headers = self._get_headers()

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
                # 1. Queue prompt
                queue_res = await client.post(
                    f"{self.base_url}/prompt",
                    json={"prompt": prompt_graph, "client_id": client_id},
                )
                if queue_res.status_code != 200:
                    raise ProviderException(
                        "ComfyUI",
                        f"提交 ComfyUI 工作流失败 (Status {queue_res.status_code}): {queue_res.text[:200]}",
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

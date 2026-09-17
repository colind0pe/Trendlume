import asyncio
import json
import mimetypes
import random
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from src.core.exceptions import ProviderException
from src.providers.image.protocol import ImageResult
from src.providers.image.reference_frame import (
    normalize_reference_frame_options,
    prepare_reference_image,
    reference_frame_signature,
)
from src.providers.image.style_presets import apply_image_style_preset
from src.services.workflow_service import workflow_service

DEFAULT_COMFYUI_IMAGE_WORKFLOW = "image/image_flux.json"
DEFAULT_COMFYUI_REFERENCE_IMAGE_WORKFLOW = "image/image_flux2_img2img.json"
COMFYUI_IMAGE_COMPATIBILITY_WORKFLOW = "image/image_z_image_turbo.json"
COMFYUI_CAPABILITY_CACHE_SECONDS = 30.0


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
        self._reference_upload_cache: tuple[tuple[str, int, int, str], str] | None = None
        self._available_unet_names_cache: frozenset[str] | None = None
        self._available_unet_names_checked_at = 0.0

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

    @staticmethod
    def _workflow_unet_names(graph: dict) -> frozenset[str]:
        names: set[str] = set()
        for node in graph.values():
            if not isinstance(node, dict) or node.get("class_type") != "UNETLoader":
                continue
            inputs = node.get("inputs")
            name = inputs.get("unet_name") if isinstance(inputs, dict) else None
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
        return frozenset(names)

    @staticmethod
    def _available_unet_names(payload: Any) -> frozenset[str] | None:
        if not isinstance(payload, dict):
            return None
        node_info = payload.get("UNETLoader")
        if not isinstance(node_info, dict):
            return None
        required = ((node_info.get("input") or {}).get("required") or {})
        raw_choices = required.get("unet_name") if isinstance(required, dict) else None
        if not isinstance(raw_choices, list) or not raw_choices:
            return None
        choices = raw_choices[0]
        if not isinstance(choices, list):
            return None
        names = frozenset(
            item.strip() for item in choices if isinstance(item, str) and item.strip()
        )
        return names or None

    async def _get_available_unet_names(self, client: httpx.AsyncClient) -> frozenset[str] | None:
        now = time.monotonic()
        if (
            self._available_unet_names_cache is not None
            and now - self._available_unet_names_checked_at < COMFYUI_CAPABILITY_CACHE_SECONDS
        ):
            return self._available_unet_names_cache
        try:
            response = await client.get(f"{self.base_url}/object_info/UNETLoader")
        except httpx.RequestError:
            logger.debug("ComfyUI capability preflight unavailable; keeping configured workflow")
            return None
        if response.status_code != 200:
            return None
        try:
            available = self._available_unet_names(response.json())
        except ValueError:
            return None
        if available is not None:
            self._available_unet_names_cache = available
            self._available_unet_names_checked_at = now
        return available

    async def _prepare_implicit_default_workflow(
        self,
        client: httpx.AsyncClient,
        prompt_graph: dict,
        prompt: str,
        width: int,
        height: int,
    ) -> tuple[dict, bool]:
        """Avoid submitting a known-incompatible built-in default graph."""
        requested = self._workflow_unet_names(prompt_graph)
        if not requested:
            return prompt_graph, False
        available = await self._get_available_unet_names(client)
        if available is None or requested.issubset(available):
            return prompt_graph, False

        fallback_graph = self._load_workflow_graph(
            COMFYUI_IMAGE_COMPATIBILITY_WORKFLOW, prompt, width, height
        )
        fallback_models = self._workflow_unet_names(fallback_graph)
        if not fallback_models or not fallback_models.issubset(available):
            return prompt_graph, False

        logger.info(
            "ComfyUI default workflow {} is incompatible with the available UNET models; "
            "using {} before queueing",
            self.default_workflow,
            COMFYUI_IMAGE_COMPATIBILITY_WORKFLOW,
        )
        return fallback_graph, True

    @staticmethod
    def _reference_image_node(graph: dict) -> tuple[str, dict]:
        candidates = [
            (node_id, node)
            for node_id, node in graph.items()
            if isinstance(node, dict) and node.get("class_type") == "LoadImage"
        ]
        if not candidates:
            raise ProviderException(
                "ComfyUI",
                "参考图输入需要所选工作流包含 LoadImage 节点；请改用支持图生图的 workflow。",
            )

        for node_id, node in candidates:
            title = str((node.get("_meta") or {}).get("title") or "").lower()
            if "$image.image" in title or "reference" in title or "参考" in title:
                return node_id, node
        return candidates[0]

    @classmethod
    def _inject_reference_image(cls, graph: dict, image_name: str) -> None:
        _node_id, node = cls._reference_image_node(graph)
        inputs = node.setdefault("inputs", {})
        if not isinstance(inputs, dict):
            raise ProviderException("ComfyUI", "参考图 LoadImage 节点的 inputs 无效。")
        inputs["image"] = image_name

    async def _upload_reference_image(
        self,
        client: httpx.AsyncClient,
        image_path: Path,
        *,
        reference_image_options: dict[str, Any] | None = None,
        default_width: int,
        default_height: int,
    ) -> str:
        try:
            stat = image_path.stat()
        except OSError as exc:
            raise ProviderException("ComfyUI", f"读取参考图失败: {image_path.name}") from exc

        normalized_options = normalize_reference_frame_options(
            reference_image_options,
            default_width=default_width,
            default_height=default_height,
        )
        cache_key = (
            str(image_path.resolve()),
            int(stat.st_size),
            int(stat.st_mtime_ns),
            reference_frame_signature(normalized_options),
        )
        if self._reference_upload_cache:
            cached_key, cached_name = self._reference_upload_cache
            if cache_key == cached_key:
                return cached_name

        prepared = await prepare_reference_image(image_path, normalized_options)
        try:
            upload_path = prepared.path
            suffix = upload_path.suffix or ".png"
            upload_name = f"trendlume_reference_{uuid.uuid4().hex[:12]}{suffix}"
            mime_type = mimetypes.guess_type(upload_path.name)[0] or "application/octet-stream"
            try:
                with upload_path.open("rb") as image_file:
                    response = await client.post(
                        f"{self.base_url}/upload/image",
                        files={"image": (upload_name, image_file, mime_type)},
                        data={"type": "input", "overwrite": "false"},
                    )
            except OSError as exc:
                raise ProviderException("ComfyUI", f"读取参考图失败: {image_path.name}") from exc

            if response.status_code < 200 or response.status_code >= 300:
                raise ProviderException(
                    "ComfyUI",
                    f"上传 ComfyUI 参考图失败 (Status {response.status_code}): "
                    f"{response.text[:500]}",
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise ProviderException("ComfyUI", "上传参考图后返回了无效 JSON。") from exc
            if not isinstance(payload, dict) or not str(payload.get("name") or "").strip():
                raise ProviderException("ComfyUI", "上传参考图后未返回有效文件名。")

            name = str(payload["name"]).strip().lstrip("/\\")
            subfolder = str(payload.get("subfolder") or "").strip().strip("/\\")
            remote_name = f"{subfolder}/{name}" if subfolder else name
            self._reference_upload_cache = (cache_key, remote_name)
            return remote_name
        finally:
            prepared.cleanup()

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
                    metadata = node.get("_meta") or {}
                    title = metadata.get("title", "") if isinstance(metadata, dict) else ""
                    title_lower = str(title).lower()
                    is_negative_prompt = any(
                        marker in title_lower
                        for marker in ("negative", "负面", "负向", "反向")
                    )

                    if (
                        not is_negative_prompt
                        and (
                            "$prompt" in title_lower
                            or class_type == "CLIPTextEncode"
                            or "prompt" in title_lower
                        )
                    ):
                        if "text" in inputs and isinstance(inputs["text"], str):
                            inputs["text"] = prompt
                        elif "value" in inputs and isinstance(inputs["value"], str):
                            inputs["value"] = prompt

                    if class_type in {"EmptyLatentImage", "EmptySD3LatentImage"}:
                        if "width" in inputs and isinstance(inputs["width"], (int, float)):
                            inputs["width"] = width
                        if "height" in inputs and isinstance(inputs["height"], (int, float)):
                            inputs["height"] = height

                    if class_type == "easy int":
                        title_lower = str(title).lower()
                        if "width" in title_lower and "value" in inputs:
                            inputs["value"] = width
                        elif "height" in title_lower and "value" in inputs:
                            inputs["value"] = height

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
        reference_image_path: str | None = None,
        reference_image_options: dict[str, Any] | None = None,
    ) -> ImageResult:
        prompt = apply_image_style_preset(prompt, style_preset)
        reference_path = Path(reference_image_path) if reference_image_path else None
        if reference_path is not None and (
            not reference_path.is_file() or reference_path.stat().st_size <= 0
        ):
            raise ProviderException(
                "ComfyUI",
                f"参考图不存在或为空: {reference_path.name}",
            )
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
        workflow_target = workflow
        if (
            reference_path is not None
            and workflow is None
            and self.default_workflow == DEFAULT_COMFYUI_IMAGE_WORKFLOW
        ):
            workflow_target = DEFAULT_COMFYUI_REFERENCE_IMAGE_WORKFLOW
        prompt_graph = self._load_workflow_graph(workflow_target, prompt, width, height)
        uses_default_workflow = workflow is None and reference_path is None
        preflight_compatibility_selected = False
        headers = self._get_headers()

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
                if (
                    uses_default_workflow
                    and self.default_workflow == DEFAULT_COMFYUI_IMAGE_WORKFLOW
                ):
                    prompt_graph, preflight_compatibility_selected = (
                        await self._prepare_implicit_default_workflow(
                            client,
                            prompt_graph,
                            prompt,
                            width,
                            height,
                        )
                    )
                if reference_path is not None:
                    # Validate the selected graph before uploading so a plain
                    # text-to-image workflow fails clearly instead of silently
                    # ignoring the requested reference image.
                    self._reference_image_node(prompt_graph)
                    uploaded_name = await self._upload_reference_image(
                        client,
                        reference_path,
                        reference_image_options=reference_image_options,
                        default_width=width,
                        default_height=height,
                    )
                    self._inject_reference_image(prompt_graph, uploaded_name)

                # 1. Queue prompt
                queue_res = await client.post(
                    f"{self.base_url}/prompt",
                    json={"prompt": prompt_graph, "client_id": client_id},
                )
                if (
                    self._is_prompt_validation_error(queue_res)
                    and uses_default_workflow
                    and self.default_workflow == DEFAULT_COMFYUI_IMAGE_WORKFLOW
                    and not preflight_compatibility_selected
                ):
                    # Only the built-in default gets a compatibility retry.
                    # A saved custom default or an explicit per-call workflow
                    # must fail visibly so the configured workflow is actually
                    # tested instead of being silently replaced.
                    fallback_graph = self._load_workflow_graph(
                        COMFYUI_IMAGE_COMPATIBILITY_WORKFLOW, prompt, width, height
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
                    try:
                        history_res = await client.get(f"{self.base_url}/history/{prompt_id}")
                    except httpx.ReadTimeout:
                        # Large Flux2 jobs can leave ComfyUI's history endpoint
                        # unreadable for a poll interval. The prompt continues
                        # running, so keep polling until generation_timeout.
                        logger.warning(
                            "ComfyUI history poll timed out; continuing prompt_id={}",
                            prompt_id,
                        )
                        continue
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

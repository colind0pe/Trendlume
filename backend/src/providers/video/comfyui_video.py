import asyncio
import json
import uuid
from pathlib import Path

import httpx
from loguru import logger

from src.core.exceptions import ProviderException
from src.providers.video.protocol import VideoResult
from src.services.workflow_service import workflow_service


class ComfyUIVideoProvider:
    """ComfyUI Video Generation Provider via REST API with Workflow & API Key support"""

    name = "comfyui"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8188",
        api_key: str | None = None,
        default_workflow: str = "video/video_wan2.1_fusionx.json",
        timeout: float = 240.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_workflow = default_workflow
        self.timeout = timeout

    def _get_headers(self) -> dict[str, str]:
        headers = {}
        if self.api_key and self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"
        return headers

    def _load_workflow_graph(
        self,
        workflow_name: str | None,
        prompt: str,
        width: int,
        height: int,
        duration_seconds: float,
    ) -> dict:
        """Load video workflow JSON from workflows directory or build default video graph"""
        wf_target = workflow_name or self.default_workflow
        workflows_dir = Path(__file__).resolve().parent.parent.parent.parent / "workflows"
        wf_path = workflow_service.resolve_workflow_file(wf_target, workflows_dir)

        if wf_path and wf_path.exists():
            try:
                with open(wf_path, encoding="utf-8") as f:
                    graph = json.load(f)

                # Inject prompt and dimensions into graph nodes if matching
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

                    if "EmptyLatentImage" in class_type or "Wan" in class_type:
                        if "width" in inputs and isinstance(inputs["width"], (int, float)):
                            inputs["width"] = width
                        if "height" in inputs and isinstance(inputs["height"], (int, float)):
                            inputs["height"] = height

                logger.info(f"Loaded ComfyUI video workflow graph from {wf_path}")
                return graph
            except Exception as e:
                logger.warning(f"Failed to parse custom video workflow {wf_path}, fallback to default: {e}")

        # Fallback standard video generation prompt graph
        return {
            "10": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "filenames": ["11", 0],
                    "format": "video/h264-mp4",
                    "frame_rate": 24,
                    "loop_count": 0,
                    "save_output": True,
                },
            },
            "11": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "batch_size": int(duration_seconds * 12),
                    "height": height,
                    "width": width,
                },
            },
        }

    async def generate_video(
        self,
        prompt: str,
        image_url: str | None = None,
        aspect_ratio: str = "9:16",
        duration_seconds: float = 4.0,
        workflow: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> VideoResult:
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
        client_id = f"trendlume_vid_{uuid.uuid4().hex[:8]}"
        prompt_graph = self._load_workflow_graph(workflow, prompt, width, height, duration_seconds)
        headers = self._get_headers()

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
                queue_res = await client.post(
                    f"{self.base_url}/prompt",
                    json={"prompt": prompt_graph, "client_id": client_id},
                )
                if queue_res.status_code != 200:
                    raise ProviderException(
                        "ComfyUI",
                        f"提交 ComfyUI 视频工作流失败 (Status {queue_res.status_code}): {queue_res.text[:200]}",
                    )

                prompt_id = queue_res.json().get("prompt_id")
                if not prompt_id:
                    raise ProviderException("ComfyUI", "ComfyUI 返回未包含有效 prompt_id")

                logger.info(f"ComfyUI video job queued: {prompt_id} on {self.base_url}")

                start_time = asyncio.get_event_loop().time()
                video_output = None

                while (asyncio.get_event_loop().time() - start_time) < self.timeout:
                    await asyncio.sleep(1.5)
                    history_res = await client.get(f"{self.base_url}/history/{prompt_id}")
                    if history_res.status_code == 200:
                        history_data = history_res.json()
                        if prompt_id in history_data:
                            outputs = history_data[prompt_id].get("outputs", {})
                            for node_id, node_out in outputs.items():
                                if "gifs" in node_out and len(node_out["gifs"]) > 0:
                                    video_output = node_out["gifs"][0]
                                    break
                                if "videos" in node_out and len(node_out["videos"]) > 0:
                                    video_output = node_out["videos"][0]
                                    break
                            if video_output:
                                break

                if not video_output:
                    raise ProviderException(
                        "ComfyUI",
                        f"ComfyUI 视频生成超时 ({self.timeout}s)，未能在指定时间内获取输出视频。",
                    )

                view_params = {
                    "filename": video_output.get("filename"),
                    "subfolder": video_output.get("subfolder", ""),
                    "type": video_output.get("type", "output"),
                }
                vid_res = await client.get(f"{self.base_url}/view", params=view_params)
                if vid_res.status_code != 200:
                    raise ProviderException(
                        "ComfyUI",
                        f"获取 ComfyUI 视频输出失败 (Status {vid_res.status_code})",
                    )

                logger.info(f"ComfyUI video generated successfully: {video_output.get('filename')}")
                return VideoResult(
                    video_bytes=vid_res.content,
                    duration_seconds=duration_seconds,
                    width=width,
                    height=height,
                    format="mp4",
                    mime_type="video/mp4",
                )

        except httpx.RequestError as e:
            logger.error(f"Failed to connect to ComfyUI at {self.base_url}: {e}")
            raise ProviderException(
                "ComfyUI",
                f"连接 ComfyUI 服务失败 ({self.base_url})。请确认已启动 ComfyUI 或检查设置。",
            ) from e

import io
import re
import uuid
import wave
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel
from src.domain.enums import PlatformType
from src.providers.image.protocol import ImageResult
from src.providers.publishing.protocol import PublishResult
from src.providers.search.protocol import SearchResult
from src.providers.tts.protocol import TTSResult, VoiceInfo
from src.providers.video.protocol import VideoResult

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider:
    name = "mock"

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        return f"【Mock LLM 生成】针对主题 '{prompt}' 的优质短视频文案：在科学与生活的交汇处，存在着许多令人惊叹的未知真相。"

    async def generate_structured(
        self,
        prompt: str,
        schema_class: type[T],
        system_prompt: str | None = None,
        temperature: float = 0.5,
        **kwargs,
    ) -> T:
        match = re.search(r"(?:期望分镜数量|target_scene_count)\s*[:=]\s*(\d+)", prompt)
        scene_count = int(match.group(1)) if match else 8
        scene_templates = [
            (
                f"首先，当我们首次观察到 {prompt} 时，整个科学界都震惊了。",
                f"发光粒子特写，表现与 {prompt} 相关的微观结构，主体清晰，电影感光影，细节丰富",
                "核心发现",
            ),
            (
                "在随后的关键实验中，科学家证实了这一惊人猜想。",
                f"未来感实验室，激光与全息图表展示 {prompt} 的工作原理，构图清晰，冷色光线",
                "实验求证",
            ),
            (
                "这意味着未来我们甚至可以借此实现前所未有的技术突破。",
                f"赛博城市夜景，超高速数据流与科技装置呈现 {prompt} 的应用场景，层次分明，光影鲜明",
                "未来展望",
            ),
        ]
        scenes = [
            {
                "sequence_index": index,
                "narration_text": scene_templates[index % len(scene_templates)][0],
                "visual_prompt": scene_templates[index % len(scene_templates)][1],
                "badge_text": scene_templates[index % len(scene_templates)][2],
            }
            for index in range(scene_count)
        ]
        mock_data = {
            "title": f"揭秘：{prompt} 背后震撼的科学真相",
            "hook": "你知道吗？90% 的人都不知道这个颠覆认知的秘密！",
            "narration": f"今天我们来深度聊聊 {prompt}。从微观量子到宏观宇宙，每一个细节都藏着大自然的终极规律。",
            "metadata": {
                "title": f"揭秘：{prompt}",
                "description": f"用通俗方式讲清 {prompt} 的关键原理，欢迎在评论区分享你的看法。",
                "tags": ["科普", "科技", "AI创作"],
                "declaration": "内容由AI生成",
            },
            "scenes": scenes,
        }
        return schema_class.model_validate(mock_data)


class MockSearchProvider:
    name = "mock"

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title=f"关于 {query} 的权威科学综述",
                url="https://encyclopedia.mock.com/science",
                snippet=f"本文深度总结了 {query} 的历史演进与前沿理论突破，是当今短视频创作的重要素材来源。",
                score=0.95,
            ),
            SearchResult(
                title=f"{query} 最新实验成果与应用展望",
                url="https://discovery.mock.com/quantum",
                snippet=f"研究团队最新发布了关于 {query} 的关键应用实验数据，展示了巨大的商业化潜力。",
                score=0.91,
            ),
            SearchResult(
                title=f"从零开始读懂 {query}：通俗科普指南",
                url="https://futuretech.mock.com/applications",
                snippet=f"一文讲清 {query} 的核心机制与未来发展，适合大众普及。",
                score=0.88,
            ),
        ][:max_results]


class MockImageProvider:
    name = "mock"

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "9:16",
        workflow: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> ImageResult:
        # Minimal 1x1 PNG header + bytes
        png_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        return ImageResult(
            image_bytes=png_data,
            width=int(width) if width and width > 0 else 720,
            height=int(height) if height and height > 0 else 1280,
            format="png",
            mime_type="image/png",
        )


class MockTTSProvider:
    name = "mock"

    async def synthesize(
        self, text: str, voice_id: str = "mock-voice-1", speed: float = 1.0
    ) -> TTSResult:
        sample_rate = 16_000
        frames = b"\x00\x00" * int(sample_rate * 3.5)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(frames)
        return TTSResult(
            audio_bytes=wav_buffer.getvalue(),
            duration_seconds=3.5,
            # Keep the historical mock contract while using a valid RIFF
            # payload so the new ffprobe validation can inspect it.
            format="mp3",
            mime_type="audio/mpeg",
        )

    async def list_voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo("mock-voice-1", "Mock 解说男声", "Male", "Chinese", "zh-CN"),
            VoiceInfo("mock-voice-2", "Mock 故事女声", "Female", "Chinese", "zh-CN"),
        ]


class MockVideoProvider:
    name = "mock"

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
        fixture = Path(__file__).resolve().parent.parent / "fixtures" / "mock.mp4"
        return VideoResult(
            video_bytes=fixture.read_bytes(),
            duration_seconds=duration_seconds,
            format="mp4",
            mime_type="video/mp4",
            width=int(width) if width and width > 0 else 720,
            height=int(height) if height and height > 0 else 1280,
        )


class MockPublishingProvider:
    name = "mock"
    platform = PlatformType.MOCK

    async def publish_video(
        self,
        video_path: Any,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        cover_path: Any | None = None,
        credential_data: dict[str, Any] | None = None,
        custom_params: dict[str, Any] | None = None,
    ) -> PublishResult:
        mock_id = f"mock_post_{uuid.uuid4().hex[:8]}"
        return PublishResult(
            success=True,
            platform_post_id=mock_id,
            post_url=f"https://platform.mock/video/{mock_id}",
            raw_response={"status": "mock_success", "title": title},
        )

    async def validate_account(self, credential_data: dict[str, Any]) -> bool:
        return True


__all__ = [
    "MockImageProvider",
    "MockLLMProvider",
    "MockPublishingProvider",
    "MockSearchProvider",
    "MockTTSProvider",
    "MockVideoProvider",
]

import asyncio

import edge_tts
from loguru import logger

from src.core.exceptions import ProviderException
from src.providers.base import retry_async
from src.providers.tts.protocol import TTSResult, VoiceInfo

CURATED_VOICES = [
    # 1. 汉语普通话 (Mandarin / zh-CN)
    VoiceInfo("zh-CN-YunxiNeural", "云希 (活力/短视频解说/男声)", "Male", "Chinese", "zh-CN"),
    VoiceInfo("zh-CN-XiaoxiaoNeural", "晓晓 (亲切/日常播报/女声)", "Female", "Chinese", "zh-CN"),
    VoiceInfo("zh-CN-YunjianNeural", "云健 (沉稳/影视纪录片/男声)", "Male", "Chinese", "zh-CN"),
    VoiceInfo("zh-CN-XiaoyiNeural", "晓伊 (年轻/生活抒情/女声)", "Female", "Chinese", "zh-CN"),
    VoiceInfo("zh-CN-YunyangNeural", "云扬 (专业/新闻播报/男声)", "Male", "Chinese", "zh-CN"),
    VoiceInfo("zh-CN-YunxiaNeural", "云夏 (元气/少年动漫/男声)", "Male", "Chinese", "zh-CN"),

    # 2. 粤语 (Cantonese / zh-HK)
    VoiceInfo("zh-HK-HiuMaanNeural", "晓曼 (粤语香港/生活资讯/女声)", "Female", "Cantonese", "zh-HK"),
    VoiceInfo("zh-HK-WanLungNeural", "云龙 (粤语香港/影视解说/男声)", "Male", "Cantonese", "zh-HK"),
    VoiceInfo("zh-HK-HiuGaaiNeural", "晓佳 (粤语香港/自然广播/女声)", "Female", "Cantonese", "zh-HK"),

    # 3. 地方方言与台湾国语 (Dialects & Taiwanese / zh-TW)
    VoiceInfo("zh-CN-liaoning-XiaobeiNeural", "晓北 (东北方言/幽默搞笑/女声)", "Female", "Chinese", "zh-CN"),
    VoiceInfo("zh-CN-shaanxi-XiaoniNeural", "晓妮 (陕西方言/特色风情/女声)", "Female", "Chinese", "zh-CN"),
    VoiceInfo("zh-TW-HsiaoChenNeural", "晓臻 (台湾国语/温柔有声/女声)", "Female", "Chinese", "zh-TW"),
    VoiceInfo("zh-TW-YunJheNeural", "云哲 (台湾国语/亲和自然/男声)", "Male", "Chinese", "zh-TW"),
    VoiceInfo("zh-TW-HsiaoYuNeural", "晓雨 (台湾国语/生动播报/女声)", "Female", "Chinese", "zh-TW"),

    # 4. 英语音色 (English / en-US, en-GB)
    VoiceInfo("en-US-GuyNeural", "Guy (美式英语/新闻解说/男声)", "Male", "English", "en-US"),
    VoiceInfo("en-US-JennyNeural", "Jenny (美式英语/故事助手/女声)", "Female", "English", "en-US"),
    VoiceInfo("en-US-AriaNeural", "Aria (美式英语/专业自信/女声)", "Female", "English", "en-US"),
    VoiceInfo("en-US-ChristopherNeural", "Christopher (美式英语/磁性沉稳/男声)", "Male", "English", "en-US"),
    VoiceInfo("en-GB-SoniaNeural", "Sonia (英式英语/正式播报/女声)", "Female", "English", "en-GB"),
    VoiceInfo("en-GB-RyanNeural", "Ryan (英式英语/叙事旁白/男声)", "Male", "English", "en-GB"),

    # 5. 日语音色 (Japanese / ja-JP)
    VoiceInfo("ja-JP-NanamiNeural", "Nanami (七海/甜美动漫/女声)", "Female", "Japanese", "ja-JP"),
    VoiceInfo("ja-JP-KeitaNeural", "Keita (圭太/阳光活力/男声)", "Male", "Japanese", "ja-JP"),
    VoiceInfo("ja-JP-AoiNeural", "Aoi (葵/自然对话/女声)", "Female", "Japanese", "ja-JP"),
    VoiceInfo("ja-JP-DaichiNeural", "Daichi (大地/沉稳解说/男声)", "Male", "Japanese", "ja-JP"),

    # 6. 韩语音色 (Korean / ko-KR)
    VoiceInfo("ko-KR-SunHiNeural", "Sun-Hi (善熙/影视解说/女声)", "Female", "Korean", "ko-KR"),
    VoiceInfo("ko-KR-InJoonNeural", "In-Joon (仁俊/温柔青年/男声)", "Male", "Korean", "ko-KR"),
    VoiceInfo("ko-KR-BongJinNeural", "Bong-Jin (奉镇/沉稳播报/男声)", "Male", "Korean", "ko-KR"),
    VoiceInfo("ko-KR-JiMinNeural", "Ji-Min (智敏/元气少女/女声)", "Female", "Korean", "ko-KR"),
]


class EdgeTTSProvider:
    """Zero-cost Edge-TTS neural speech synthesis supporting Chinese, Cantonese, English, Japanese, and Korean"""

    name = "edge_tts"

    def __init__(self, default_voice: str = "zh-CN-YunxiNeural"):
        self.default_voice = default_voice or "zh-CN-YunxiNeural"

    async def _stream_edge_tts(self, text: str, voice_id: str, speed: float) -> tuple[bytes, float]:
        normalized_speed = max(0.5, min(2.0, float(speed or 1.0)))
        rate_percent = round((normalized_speed - 1.0) * 100)
        communicate = edge_tts.Communicate(text, voice_id, rate=f"{rate_percent:+d}%")
        audio_chunks = []
        duration_offset = 0.0

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                end_offset = (chunk["offset"] + chunk["duration"]) / 10_000_000
                if end_offset > duration_offset:
                    duration_offset = end_offset

        return b"".join(audio_chunks), duration_offset

    @retry_async(max_retries=2, delay_seconds=1.5, exceptions=(Exception,))
    async def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        speed: float = 1.0,
    ) -> TTSResult:
        voice_id = voice_id or self.default_voice
        if not text or not text.strip():
            text = "欢迎观看短视频。"

        logger.info(f"EdgeTTS synthesizing text ({len(text)} chars) with voice '{voice_id}'")
        try:
            # 15s timeout for EdgeTTS live stream
            audio_data, duration_offset = await asyncio.wait_for(
                self._stream_edge_tts(text, voice_id, speed),
                timeout=15.0,
            )

            if not audio_data:
                raise ValueError("EdgeTTS 返回了空音频数据")

            if duration_offset <= 0.1:
                duration_offset = max(2.0, len(text) / 3.5)

            return TTSResult(
                audio_bytes=audio_data,
                duration_seconds=round(duration_offset, 2),
                format="mp3",
                mime_type="audio/mpeg",
            )
        except Exception as e:
            raise ProviderException(self.name, f"EdgeTTS 语音合成失败: {e}") from e

    async def list_voices(self) -> list[VoiceInfo]:
        """Return curated high-quality voices with official usage descriptions"""
        return CURATED_VOICES

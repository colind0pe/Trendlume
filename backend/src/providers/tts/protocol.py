from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class VoiceInfo:
    id: str
    name: str
    gender: str
    language: str
    locale: str


@dataclass
class TTSResult:
    audio_bytes: bytes
    duration_seconds: float
    format: str = "mp3"
    mime_type: str = "audio/mpeg"


@runtime_checkable
class TTSProvider(Protocol):
    name: str

    async def synthesize(
        self,
        text: str,
        voice_id: str = "zh-CN-YunxiNeural",
        speed: float = 1.0,
    ) -> TTSResult:
        """Synthesize text into speech audio bytes and duration"""
        ...

    async def list_voices(self) -> list[VoiceInfo]:
        """List supported neural voice options"""
        ...

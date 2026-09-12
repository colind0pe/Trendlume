"""Shared ffprobe-based media inspection for generated and uploaded assets."""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.core.exceptions import ValidationException


@dataclass(frozen=True)
class MediaProbeResult:
    """The media facts used by generation and rendering decisions."""

    audio_duration: float | None
    video_duration: float | None
    width: int | None
    height: int | None
    has_audio: bool
    has_video: bool

    @property
    def duration_seconds(self) -> float | None:
        """Return the primary duration for this media file."""
        if self.has_video:
            return self.video_duration
        return self.audio_duration


class MediaProbeService:
    """Run ffprobe once and normalize its stream/format output."""

    async def probe(self, path: Path) -> MediaProbeResult:
        if not path.exists() or not path.is_file() or path.stat().st_size == 0:
            raise ValidationException(f"媒体文件不存在或为空: {path}")

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type,duration,width,height:format=duration",
                    "-of",
                    "json",
                    str(path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ValidationException("服务器未检测到 ffprobe，请安装 FFmpeg。") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValidationException(f"媒体探测超时: {path.name}") from exc

        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="ignore").strip()
            suffix = f" ({detail[:160]})" if detail else ""
            raise ValidationException(f"媒体文件无法通过 ffprobe 探测: {path.name}{suffix}")

        try:
            payload = json.loads(result.stdout.decode("utf-8", errors="ignore") or "{}")
        except json.JSONDecodeError as exc:
            raise ValidationException(f"媒体文件探测结果无效: {path.name}") from exc

        streams = payload.get("streams") or []
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
        format_duration = self._positive_float((payload.get("format") or {}).get("duration"))

        audio_duration = self._stream_duration(audio_streams) or (
            format_duration if audio_streams else None
        )
        video_duration = self._stream_duration(video_streams) or (
            format_duration if video_streams else None
        )
        video_stream = video_streams[0] if video_streams else {}

        return MediaProbeResult(
            audio_duration=audio_duration,
            video_duration=video_duration,
            width=self._positive_int(video_stream.get("width")),
            height=self._positive_int(video_stream.get("height")),
            has_audio=bool(audio_streams),
            has_video=bool(video_streams),
        )

    @classmethod
    def _stream_duration(cls, streams: list[dict]) -> float | None:
        durations = [
            duration
            for stream in streams
            if (duration := cls._positive_float(stream.get("duration"))) is not None
        ]
        return max(durations) if durations else None

    @staticmethod
    def _positive_float(value: object) -> float | None:
        try:
            parsed = float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _positive_int(value: object) -> int | None:
        try:
            parsed = int(value) if value is not None else 0
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None


media_probe_service = MediaProbeService()

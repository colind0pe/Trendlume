from __future__ import annotations

import base64
import binascii
import json
import math
import uuid

import httpx
from loguru import logger

from src.core.exceptions import ProviderException
from src.core.security import redact_sensitive_text
from src.providers.tts.protocol import TTSResult, VoiceInfo


class VolcengineTTSProvider:
    """Doubao TTS V3 HTTP Chunked provider."""

    name = "volcengine"
    DEFAULT_BASE_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    DEFAULT_VOICE = "zh_female_vv_uranus_bigtts"
    DEFAULT_RESOURCE_ID = "seed-tts-2.0"
    DEFAULT_SPEED_RATIO = 1.0
    MIN_SPEED_RATIO = 0.5
    MAX_SPEED_RATIO = 2.0

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        resource_id: str = DEFAULT_RESOURCE_ID,
        model: str | None = None,
        default_voice: str = DEFAULT_VOICE,
        timeout: float = 60.0,
        default_speed_ratio: float = DEFAULT_SPEED_RATIO,
    ):
        self.api_key = str(api_key or "").strip()
        self.base_url = (base_url or self.DEFAULT_BASE_URL).strip()
        self.resource_id = str(resource_id or self.DEFAULT_RESOURCE_ID).strip()
        self.model = str(model or "").strip()
        self.default_voice = str(default_voice or self.DEFAULT_VOICE).strip()
        self.timeout = float(timeout)
        self.default_speed_ratio = self.normalize_speed_ratio(default_speed_ratio)

    @classmethod
    def normalize_speed_ratio(cls, value: object) -> float:
        try:
            speed_ratio = float(value)
        except (TypeError, ValueError):
            speed_ratio = cls.DEFAULT_SPEED_RATIO
        if not math.isfinite(speed_ratio):
            speed_ratio = cls.DEFAULT_SPEED_RATIO
        return max(cls.MIN_SPEED_RATIO, min(cls.MAX_SPEED_RATIO, speed_ratio))

    def _headers(self, request_id: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Api-Key": self.api_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": request_id,
        }

    @staticmethod
    async def _error_message(response: httpx.Response) -> str:
        try:
            body = await response.aread()
        except Exception as exc:
            return f"无法读取错误响应: {exc}"
        if not body:
            return ""
        try:
            payload = json.loads(body)
        except (TypeError, ValueError, UnicodeDecodeError):
            payload = body.decode(response.encoding or "utf-8", errors="replace")[:500]
        if isinstance(payload, dict):
            header = payload.get("header")
            if isinstance(header, dict):
                code = header.get("code")
                message = str(header.get("message") or header.get("detail") or "")
                if code in (45000030, "45000030") or "resource not granted" in message.lower():
                    return (
                        f"Resource ID 未授权（{message or code}）。请在火山控制台开通该资源，或改用账号已授权的 "
                        "V3 Resource ID；豆包语音 2.0 通常使用 seed-tts-2.0，且音色必须匹配。"
                    )
                if message:
                    return f"{code}: {message}" if code else message
            return str(payload.get("message") or payload.get("detail") or payload)
        return str(payload)

    def _payload(self, text: str, voice_id: str, speed: float | None) -> dict:
        speed_ratio = self.normalize_speed_ratio(
            self.default_speed_ratio if speed is None else speed
        )
        req_params = {
            "text": text,
            "speaker": voice_id,
            "audio_params": {
                "format": "mp3",
                "sample_rate": 24000,
                # V3 big-model TTS maps normal speed to 0, 0.5x to -50,
                # and 2.0x to 100.
                "speech_rate": round((speed_ratio - 1.0) * 100),
            },
        }
        if self.model:
            req_params["model"] = self.model
        return {
            "user": {"uid": "trendlume"},
            "req_params": req_params,
        }

    @staticmethod
    def _decode_frame(frame: dict) -> tuple[bytes, float, bool]:
        code = frame.get("code")
        header = frame.get("header")
        if code is None and isinstance(header, dict):
            code = header.get("code")
        try:
            numeric_code = int(code) if code is not None else None
        except (TypeError, ValueError):
            numeric_code = None
        if code is not None and numeric_code not in (0, 3000, 20000000):
            message = frame.get("message")
            if not message and isinstance(header, dict):
                message = header.get("message")
            raise ProviderException(
                "volcengine",
                f"豆包语音返回错误 {code}: {message or '未知错误'}",
            )
        audio = b""
        encoded = frame.get("data")
        if isinstance(encoded, str) and encoded:
            try:
                audio = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ProviderException("volcengine", "豆包语音返回的音频 Base64 无效。") from exc
        addition = frame.get("addition")
        if isinstance(addition, str):
            try:
                addition = json.loads(addition)
            except (TypeError, ValueError):
                addition = None
        duration_ms = 0.0
        if isinstance(addition, dict):
            raw_duration = addition.get("duration")
            if raw_duration is None and isinstance(addition.get("audio_info"), dict):
                raw_duration = addition["audio_info"].get("duration")
            try:
                duration_ms = float(raw_duration or 0.0)
            except (TypeError, ValueError):
                duration_ms = 0.0
        sequence = frame.get("sequence")
        try:
            finished = numeric_code == 20000000 or float(sequence) < 0
        except (TypeError, ValueError):
            finished = numeric_code == 20000000
        return audio, duration_ms / 1000.0, finished

    @staticmethod
    def _decode_json_frames(buffered: str) -> tuple[list[dict], str]:
        """Decode newline-delimited or concatenated JSON response frames."""
        decoder = json.JSONDecoder()
        frames: list[dict] = []
        while buffered:
            buffered = buffered.lstrip()
            if not buffered:
                break
            try:
                frame, end = decoder.raw_decode(buffered)
            except json.JSONDecodeError:
                break
            buffered = buffered[end:]
            if isinstance(frame, dict):
                frames.append(frame)
        return frames, buffered

    async def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        speed: float | None = None,
    ) -> TTSResult:
        if not self.api_key:
            raise ProviderException(self.name, "豆包语音未配置 X-Api-Key。")
        if not text or not text.strip():
            raise ProviderException(self.name, "语音合成文本不能为空。")

        request_id = str(uuid.uuid4())
        payload = self._payload(text, voice_id or self.default_voice, speed)
        audio_chunks: list[bytes] = []
        duration_seconds = 0.0
        finished = False

        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                async with client.stream(
                    "POST",
                    self.base_url,
                    json=payload,
                    headers=self._headers(request_id),
                ) as response:
                    if response.status_code < 200 or response.status_code >= 300:
                        raise ProviderException(
                            self.name,
                            f"豆包语音请求失败 HTTP {response.status_code}: "
                            f"{redact_sensitive_text(await self._error_message(response))}",
                        )

                    content_type = response.headers.get("content-type", "").lower()
                    if content_type.startswith("audio/"):
                        async for chunk in response.aiter_bytes():
                            if chunk:
                                audio_chunks.append(chunk)
                    else:
                        buffered = ""
                        async for line in response.aiter_lines():
                            line = line.strip()
                            if not line or line.startswith(":"):
                                continue
                            if line.startswith("data:"):
                                line = line[5:].strip()
                            buffered += line
                            frames, buffered = self._decode_json_frames(buffered)
                            for frame in frames:
                                audio, frame_duration, frame_finished = self._decode_frame(frame)
                                if audio:
                                    audio_chunks.append(audio)
                                duration_seconds = max(duration_seconds, frame_duration)
                                finished = finished or frame_finished
                                if finished:
                                    break
                            if finished:
                                break

            audio_bytes = b"".join(audio_chunks)
            if not audio_bytes:
                raise ProviderException(self.name, "豆包语音返回空音频。")
            logger.info(
                "Volcengine TTS synthesized text with voice '{}' ({} bytes)",
                voice_id or self.default_voice,
                len(audio_bytes),
            )
            return TTSResult(
                audio_bytes=audio_bytes,
                duration_seconds=duration_seconds,
                format="mp3",
                mime_type="audio/mpeg",
            )
        except ProviderException:
            raise
        except httpx.RequestError as exc:
            raise ProviderException(self.name, f"连接豆包语音服务失败: {exc}") from exc
        except Exception as exc:
            raise ProviderException(self.name, f"豆包语音合成失败: {exc}") from exc

    async def list_voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo(
                id=self.default_voice,
                name=f"火山引擎 · {self.default_voice}",
                gender="Unknown",
                language="Chinese",
                locale="zh-CN",
            )
        ]

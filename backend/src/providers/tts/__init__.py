from src.providers.tts.edge_tts import EdgeTTSProvider
from src.providers.tts.protocol import TTSProvider, TTSResult, VoiceInfo
from src.providers.tts.volcengine_tts import VolcengineTTSProvider

__all__ = [
    "TTSProvider",
    "TTSResult",
    "VoiceInfo",
    "EdgeTTSProvider",
    "VolcengineTTSProvider",
]

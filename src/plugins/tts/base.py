"""可插拔 TTS 语音合成驱动抽象基类 (BaseTTSDriver)。
支持任意语音引擎驱动（GPT-SoVITS, Edge-TTS, CosyVoice, Fish-Speech, ElevenLabs, VITS 等）。
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple


class BaseTTSDriver(ABC):
    """TTS 语音驱动抽象基类。"""

    def __init__(self, driver_id: str, display_name: str, description: str = ""):
        self.driver_id = driver_id
        self.display_name = display_name
        self.description = description

    @abstractmethod
    async def generate_speech(
        self, text: str, lang: str = "ja", **kwargs
    ) -> Optional[str]:
        """
        合成语音并返回音频可发送标识（Base64 Data URI 或本地音频绝对路径）。
        合成失败时返回 None。
        """
        pass

    @abstractmethod
    async def ping(self) -> Tuple[bool, str]:
        """服务存活心跳健康检测。返回 (是否正常, 状态信息/延迟)。"""
        pass

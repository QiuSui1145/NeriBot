"""默认 GPT-SoVITS 语音合成驱动实现。
无缝桥接现有的本地 GPT-SoVITS 同传与双轨推理服务。
"""

from typing import Optional, Tuple
from src.plugins.tts.base import BaseTTSDriver
from src.tts_client import tts_client


class GPTSoVITSTTSDriver(BaseTTSDriver):
    """基于本地 GPT-SoVITS 服务的默认语音驱动。"""

    def __init__(self):
        super().__init__(
            driver_id="gpt_sovits_default",
            display_name="GPT-SoVITS 本地克隆同传引擎 (默认内置)",
            description="基于本地 GPT-SoVITS 深度微调的高保真动漫女声拟人化配音引擎",
        )

    async def generate_speech(
        self, text: str, lang: str = "ja", **kwargs
    ) -> Optional[str]:
        return await tts_client.generate_speech(text, lang=lang)

    async def ping(self) -> Tuple[bool, str]:
        return await tts_client.ping()


gpt_sovits_default_tts_driver = GPTSoVITSTTSDriver()

"""本地 GPT-SoVITS TTS 客户端与同声传译双轨解析器。
负责将台词交由本地声学模型推理合成，并生成适用于 OneBot11 的语音消息文件。
"""

import base64
import hashlib
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Optional, Tuple

import httpx

from src.config import config_manager

AUDIO_CACHE_DIR = Path("cache/audio")


class TTSClient:
    """本地 GPT-SoVITS 语音合成客户端。"""

    def __init__(self, cache_dir: Path = AUDIO_CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.is_synthesizing: bool = False
        self.last_synthesized_time: float = 0.0

    async def ping(self) -> Tuple[bool, str]:
        """探测本地 TTS 服务连通性。智能规避推理时的单线程假死误报。"""
        if self.is_synthesizing:
            return True, "在线 (正在推理语音...)"
        if time.time() - self.last_synthesized_time < 15.0:
            return True, "在线 (已就绪)"

        cfg = config_manager.config.tts
        base_api = cfg.api_url.split("?")[0]
        try:
            # 请求根路径或 /openapi.json 查看服务存活状态
            url = base_api.rsplit("/tts", 1)[0] + "/docs"
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url)
                if resp.status_code in [200, 307, 404]:
                    return True, "在线 (已就绪)"
                return False, f"异常状态码: {resp.status_code}"
        except Exception as e:
            # 若最近刚刚合成过，说明服务一定存活，仅是被推理计算短暂占用
            if time.time() - self.last_synthesized_time < 30.0:
                return True, "在线 (运算忙碌)"
            return False, f"未连接: {str(e)}"

    def parse_dual_track(self, raw_content: str) -> Tuple[str, str]:
        """解析同声传译输出格式 [TEXT]中文文本[/TEXT][VOICE]日文配音[/VOICE]。
        如果模型未封装标签或标签因 max_tokens 未完全闭合，则进行智能容错解析。
        """
        raw_str = raw_content.strip()
        display_text = ""
        voice_text = ""

        # 1. 尝试标准闭合标签匹配
        text_match = re.search(r"\[TEXT\](.*?)\[/TEXT\]", raw_str, flags=re.DOTALL | re.IGNORECASE)
        voice_match = re.search(r"\[VOICE\](.*?)\[/VOICE\]", raw_str, flags=re.DOTALL | re.IGNORECASE)

        if text_match:
            display_text = text_match.group(1).strip()
        if voice_match:
            voice_text = voice_match.group(1).strip()

        # 2. 若未闭合，按标签位置切分（应对 token 截断情况）
        if not display_text and re.search(r"\[TEXT\]", raw_str, flags=re.IGNORECASE):
            parts = re.split(r"\[TEXT\]", raw_str, maxsplit=1, flags=re.IGNORECASE)
            after_text = parts[1]
            if re.search(r"\[/?VOICE\]|\[/TEXT\]", after_text, flags=re.IGNORECASE):
                display_text = re.split(r"\[/?VOICE\]|\[/TEXT\]", after_text, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            else:
                display_text = after_text.strip()

        if not voice_text and re.search(r"\[VOICE\]", raw_str, flags=re.IGNORECASE):
            parts = re.split(r"\[VOICE\]", raw_str, maxsplit=1, flags=re.IGNORECASE)
            after_voice = parts[1]
            voice_text = re.sub(r"\[/?(TEXT|VOICE)\]", "", after_voice, flags=re.IGNORECASE).strip()

        # 3. 若仍无任何标签，整体降级
        if not display_text and not voice_text:
            cleaned_all = re.sub(r"\[/?(TEXT|VOICE)\]", "", raw_str, flags=re.IGNORECASE).strip()
            display_text = cleaned_all
            voice_text = cleaned_all
        elif not display_text:
            display_text = voice_text
        elif not voice_text:
            voice_text = display_text

        # 4. 分别清洗（严禁将文本清空）
        cleaned_display = self._clean_text(display_text, is_voice=False)
        cleaned_voice = self._clean_text(voice_text, is_voice=True)

        return (cleaned_display or display_text or raw_str), (cleaned_voice or voice_text or raw_str)

    def _clean_text(self, text: str, is_voice: bool = False) -> str:
        """剔除表情符号与不适合发音的动作括号，保护中日文字符绝不丢失。"""
        if not text:
            return ""

        # 标准 Emoji 字符范围（绝不侵犯 0x4E00-0x9FFF 汉字和 0x3040-0x30FF 假名）
        emoji_pattern = re.compile(
            "["
            "\U0001F300-\U0001F9FF"
            "\U0001FA70-\U0001FAFF"
            "\U00002600-\U000026FF"
            "\U00002700-\U000027BF"
            "]+",
            flags=re.UNICODE,
        )
        cleaned = emoji_pattern.sub("", text)

        if is_voice:
            # 语音清洗：去除括号及动作说明，波浪号转为长音符
            cleaned = re.sub(r"（.*?）|\(.*?\)|\[.*?\]|【.*?】", "", cleaned)
            cleaned = cleaned.replace("〜", "ー").replace("～", "ー")
        else:
            # 展示文本清洗：若全句被括号包围，保留句内文字；仅移除局部动作描写括号
            stripped = cleaned.strip()
            wrap_match = re.match(r"^[（(【](.*?)[）)】]$", stripped)
            if wrap_match:
                cleaned = wrap_match.group(1)
            else:
                cleaned = re.sub(r"（.*?）|\(.*?\)|\[.*?\]|【.*?】", "", cleaned)

        cleaned = cleaned.strip()
        # 若清洗后变为空字符串，退回原始文本，避免吞消息
        return cleaned if cleaned else text.strip()

    async def generate_speech(self, text: str, lang: Optional[str] = None) -> Optional[str]:
        """调用本地 GPT-SoVITS 合成音频，返回 Base64 编码数据流或绝对路径。"""
        cfg = config_manager.config.tts
        if not cfg.enabled or not text.strip():
            return None

        self.is_synthesizing = True
        try:
            target_lang = lang or cfg.text_lang
            ref_file = Path(cfg.ref_audio_path)
            if not ref_file.is_absolute():
                ref_file = (Path(__file__).parent.parent / ref_file).resolve()
            if not ref_file.exists():
                local_fallback = (Path(__file__).parent.parent / "patches" / "gpt_sovits" / "ref_audio" / "ner0092.wav").resolve()
                if local_fallback.exists():
                    ref_file = local_fallback

            params = {
                "ref_audio_path": str(ref_file),
                "prompt_text": cfg.prompt_text,
                "prompt_lang": cfg.prompt_lang,
                "text": text.strip(),
                "text_lang": target_lang,
                "text_split_method": "cut0",
                "streaming_mode": "false",
                "media_type": "wav",
                "speed_factor": cfg.speed_factor,
            }

            # 计算内容哈希，若缓存存在则复用
            text_hash = hashlib.md5(f"{text}_{target_lang}_{cfg.speed_factor}".encode("utf-8")).hexdigest()
            cache_file = self.cache_dir / f"voice_{text_hash}.wav"

            if not cache_file.exists():
                api_url = cfg.api_url.split("?")[0]
                full_url = f"{api_url}?{urllib.parse.urlencode(params)}"
                async with httpx.AsyncClient(timeout=45.0) as client:
                    resp = await client.get(full_url)
                    if resp.status_code != 200:
                        print(f"[TTS] 合成失败 [HTTP {resp.status_code}]: {resp.text[:200]}")
                        return None
                    cache_file.write_bytes(resp.content)

            # 默认返回 base64 数据流（全平台兼容，完美解决 Docker 容器无法访问宿主机绝对路径导致转 Silk 失败的问题）
            if cfg.audio_send_format == "base64" or cfg.send_as_record or cfg.audio_send_format != "file":
                data = cache_file.read_bytes()
                b64_str = base64.b64encode(data).decode("utf-8")
                return f"base64://{b64_str}"
            else:
                abs_path = os.path.abspath(str(cache_file)).replace("\\", "/")
                return f"file:///{abs_path}"
        except Exception as e:
            print(f"[TTS] 请求本地语音合成服务出错: {e}")
            return None
        finally:
            self.is_synthesizing = False
            self.last_synthesized_time = time.time()


tts_client = TTSClient()

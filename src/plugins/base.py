"""插件基类 (BasePlugin) 与宿主上下文 (PluginContext) 核心定义。
为插件开发者提供清晰、安全、功能完备的微内核扩展接入点。
"""

from abc import ABC
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter

from src.plugins.adapters.base import BaseAdapter, UnifiedMessageEvent
from src.plugins.manifest import PluginManifest
from src.plugins.memory.base import BaseMemoryDriver
from src.plugins.skills.base import BaseSkill
from src.plugins.tts.base import BaseTTSDriver


class PluginContext:
    """提供给插件调用的核心宿主环境能力上下文。"""

    def __init__(self, plugin_id: str, plugin_dir: Path):
        self.plugin_id = plugin_id
        self.plugin_dir = plugin_dir
        self.logger = logging.getLogger(f"Plugin.{plugin_id}")
        self._data_dir = plugin_dir / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._config_file = plugin_dir / "config.json"
        self._default_config_file = plugin_dir / "default_config.json"

    @property
    def data_dir(self) -> Path:
        """插件私有数据持久化目录。"""
        return self._data_dir

    def get_config(self) -> Dict[str, Any]:
        """获取插件私有配置。若尚未配置则优先回退到 default_config.json。"""
        if self._config_file.exists():
            try:
                with open(self._config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"读取插件配置异常: {e}")
        if self._default_config_file.exists():
            try:
                with open(self._default_config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_config(self, cfg: Dict[str, Any]) -> bool:
        """持久化保存插件私有配置。"""
        try:
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"保存插件配置异常: {e}")
            return False

    async def send_text_message(
        self, session_type: str, target_id: str, user_id: str, text: str, platform: str = "onebot"
    ) -> bool:
        """向指定平台和会话发送文本消息。"""
        from src.plugins.manager import plugin_manager
        adapter = plugin_manager.get_adapter(platform)
        if adapter:
            return await adapter.send_text_message(session_type, str(target_id), str(user_id), text)
        return False

    async def generate_speech(self, text: str, lang: str = "ja") -> Optional[str]:
        """使用当前激活的 TTS 驱动生成语音。"""
        from src.plugins.manager import plugin_manager
        driver = plugin_manager.get_active_tts_driver()
        if driver:
            return await driver.generate_speech(text, lang=lang)
        from src.tts_client import tts_client
        return await tts_client.generate_speech(text, lang=lang)

    async def call_llm(
        self,
        prompt: str,
        system_prompt: str = "",
        model_id: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """直接调用大模型推理。"""
        from src.llm_client import llm_client
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        reply, _ = await llm_client.chat_completion(
            messages=messages,
            session_type="plugin",
            target_id=0,
            user_id=0,
            model_tag=model_id,
            tools=tools,
        )
        return reply


class BasePlugin(ABC):
    """音理插件统一抽象基类。"""

    def __init__(self, context: PluginContext, manifest: PluginManifest):
        self.context = context
        self.manifest = manifest
        self.enabled: bool = False
        self.router: Optional[APIRouter] = None

        # 插件注册的各种驱动与能力容器
        self._adapters: List[BaseAdapter] = []
        self._memory_drivers: List[BaseMemoryDriver] = []
        self._skills: List[BaseSkill] = []
        self._tts_drivers: List[BaseTTSDriver] = []
        self._commands: Dict[str, Tuple[Callable, str]] = {}  # cmd -> (handler, desc)

    # ====== 驱动与功能注册接口 ======
    def register_adapter(self, adapter: BaseAdapter):
        """向内核注册通信协议适配器。"""
        self._adapters.append(adapter)

    def register_memory_driver(self, driver: BaseMemoryDriver):
        """向内核注册异构记忆系统驱动。"""
        self._memory_drivers.append(driver)

    def register_skill(self, skill: BaseSkill):
        """向内核注册 Agentic 技能工具供大模型自主调用。"""
        self._skills.append(skill)

    def register_tts_driver(self, driver: BaseTTSDriver):
        """向内核注册语音合成驱动。"""
        self._tts_drivers.append(driver)

    def register_command(self, cmd: str, handler: Callable, description: str = ""):
        """向内核注册前缀聊天指令。"""
        self._commands[cmd.strip().lower()] = (handler, description)

    # ====== 插件生命周期 ======
    async def on_load(self) -> bool:
        """插件被发现并载入内存时调用。返回 False 则放弃加载。"""
        return True

    async def on_enable(self) -> None:
        """插件启用时调用（启动适配器、后台任务、连接外部数据库等）。"""
        pass

    async def on_disable(self) -> None:
        """插件停用时调用（停止适配器、断开连接等）。"""
        pass

    async def on_unload(self) -> None:
        """插件被卸载或热重载前调用。"""
        pass

    # ====== 管道拦截 Hook (按需重写) ======
    async def on_message_received(self, event: UnifiedMessageEvent) -> Optional[bool]:
        """
        消息进入系统时第一时间拦截。
        返回 True 表示此消息已被插件消费阻断，不再向下游流动。
        """
        return None

    async def on_command(
        self, cmd: str, args: List[str], event: UnifiedMessageEvent
    ) -> Optional[str]:
        """指令处理拦截。返回字符串将直接作为文本回复发送给用户并终止命令链路。"""
        return None

    async def before_chat_completion(
        self, session_key: str, system_prompt: str, messages: list
    ) -> Tuple[str, list]:
        """
        大模型推理前置 Hook。
        可向 system_prompt 追加外部搜索知识、微调提示词或增删上下文 messages。
        """
        return system_prompt, messages

    async def after_chat_completion(self, session_key: str, raw_reply: str) -> str:
        """大模型推理后置 Hook。可对模型生成的回复进行敏感词替换、表情追加、格式清洗等。"""
        return raw_reply

    async def before_output_dispatch(
        self, event: UnifiedMessageEvent, display_text: str, voice_text: str
    ) -> Tuple[str, str]:
        """消息向最终平台发送前 Hook。可对展示文本与语音文本做最终干预。"""
        return display_text, voice_text

    async def on_tick(self, timestamp: float) -> None:
        """后台时钟心跳 tick。"""
        pass

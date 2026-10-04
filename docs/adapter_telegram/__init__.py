"""Telegram 机器人通信适配器插件实现。
展示如何将音理微内核接入全新第三方聊天平台，收发标准化 UnifiedMessageEvent。
"""

import asyncio
from typing import Any, Dict, Optional

import httpx

from src.plugins.adapters.base import BaseAdapter, UnifiedMessageEvent
from src.plugins.base import BasePlugin


class TelegramAdapter(BaseAdapter):
    """Telegram Bot API 通信适配器。"""

    def __init__(self, plugin_context):
        super().__init__(adapter_id="telegram_bot", platform_name="Telegram Bot")
        self.context = plugin_context
        self._connected = False
        self._task: Optional[asyncio.Task] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _get_api_url(self) -> str:
        cfg = self.context.get_config()
        token = cfg.get("bot_token", "").strip()
        return f"https://api.telegram.org/bot{token}" if token else ""

    async def start(self) -> None:
        cfg = self.context.get_config()
        token = cfg.get("bot_token", "").strip()
        if not token:
            self.context.logger.info("未配置 Telegram bot_token，适配器处于待命状态。可在 WebUI 插件配置中填入 Token。")
            return

        self._connected = True
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._connected = False
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None

    async def _poll_loop(self):
        """Telegram Long Polling 消息接收协程。"""
        offset = 0
        cfg = self.context.get_config()
        proxy = cfg.get("proxy_url", "").strip() or None

        self.context.logger.info("Telegram 轮询监听已启动...")
        while self._connected:
            api_url = self._get_api_url()
            if not api_url:
                await asyncio.sleep(10)
                continue

            try:
                url = f"{api_url}/getUpdates"
                params = {"offset": offset, "timeout": 20}
                async with httpx.AsyncClient(timeout=30.0, proxy=proxy) as client:
                    resp = await client.get(url, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        for update in data.get("result", []):
                            offset = max(offset, update["update_id"] + 1)
                            msg = update.get("message")
                            if not msg:
                                continue

                            chat = msg.get("chat", {})
                            from_user = msg.get("from", {})
                            chat_id = str(chat.get("id"))
                            user_id = str(from_user.get("id"))
                            username = from_user.get("username") or from_user.get("first_name") or user_id
                            text = msg.get("text", "")

                            is_group = chat.get("type") in ["group", "supergroup", "channel"]
                            session_type = "group" if is_group else "private"

                            unified_event = UnifiedMessageEvent(
                                platform="telegram",
                                message_id=str(msg.get("message_id", "")),
                                session_type=session_type,
                                target_id=chat_id,
                                user_id=user_id,
                                user_name=username,
                                text=text,
                                is_at_bot=True if not is_group else ("@" in text),
                                raw_event=update,
                            )

                            # 投递至内核调度总线
                            await self.emit_message(unified_event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                # 遇到网络错误时避让重试
                await asyncio.sleep(5)

    async def send_text_message(
        self, session_type: str, target_id: str, user_id: str, text: str
    ) -> bool:
        api_url = self._get_api_url()
        if not api_url:
            return False

        cfg = self.context.get_config()
        proxy = cfg.get("proxy_url", "").strip() or None
        url = f"{api_url}/sendMessage"
        payload = {"chat_id": target_id, "text": text}

        try:
            async with httpx.AsyncClient(timeout=10.0, proxy=proxy) as client:
                resp = await client.post(url, json=payload)
                return resp.status_code == 200
        except Exception as e:
            self.context.logger.error(f"Telegram 发送文本失败: {e}")
            return False

    async def send_voice_message(
        self, session_type: str, target_id: str, user_id: str, voice_uri: str
    ) -> bool:
        api_url = self._get_api_url()
        if not api_url:
            return False

        cfg = self.context.get_config()
        proxy = cfg.get("proxy_url", "").strip() or None
        url = f"{api_url}/sendVoice"
        # 支持发送本地文件路径
        try:
            import os
            if os.path.exists(voice_uri):
                with open(voice_uri, "rb") as f:
                    files = {"voice": f}
                    data = {"chat_id": target_id}
                    async with httpx.AsyncClient(timeout=20.0, proxy=proxy) as client:
                        resp = await client.post(url, data=data, files=files)
                        return resp.status_code == 200
            else:
                return await self.send_text_message(session_type, target_id, user_id, f"[语音消息: {voice_uri[:30]}]")
        except Exception as e:
            self.context.logger.error(f"Telegram 发送语音失败: {e}")
            return False


class AdapterTelegramPlugin(BasePlugin):
    """Telegram 适配器插件主类。"""

    async def on_load(self) -> bool:
        adapter = TelegramAdapter(self.context)
        self.register_adapter(adapter)
        return True

    async def on_enable(self) -> None:
        self.context.logger.info("Telegram 适配器插件已启用！可在快捷设置中配置 bot_token 开始跨平台收发。")

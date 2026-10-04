"""默认 OneBot11 通信协议适配器实现。
无缝桥接现有的 NapCat / Go-CQHttp 反向与正向 WebSocket 客户端。
"""

import asyncio
from typing import Any, Dict, List, Optional

from src.onebot import onebot_client
from src.plugins.adapters.base import BaseAdapter, UnifiedMessageEvent


class OneBotV11Adapter(BaseAdapter):
    """OneBot11 标准协议默认通信适配器。"""

    def __init__(self):
        super().__init__(adapter_id="onebot_default", platform_name="OneBot11 (NapCat / QQ)")
        self._raw_handler_installed = False

    @property
    def is_connected(self) -> bool:
        return onebot_client.is_connected

    async def start(self) -> None:
        """注册 OneBot 原始事件转换监听。"""
        if not self._raw_handler_installed:
            onebot_client.add_message_handler(self._on_onebot_raw_message)
            self._raw_handler_installed = True

    async def stop(self) -> None:
        """停用适配器。"""
        if self._raw_handler_installed:
            onebot_client.remove_message_handler(self._on_onebot_raw_message)
            self._raw_handler_installed = False

    async def _on_onebot_raw_message(self, raw_event: dict):
        """将 OneBot 原始 dict 转换为微内核标准的 UnifiedMessageEvent 并投递。"""
        if not self._message_handler:
            return
        message_type = raw_event.get("message_type")  # "group" or "private"
        user_id = str(raw_event.get("user_id", 0))
        group_id = str(raw_event.get("group_id", 0)) if message_type == "group" else ""
        raw_message = raw_event.get("raw_message", "")
        message_obj = raw_event.get("message", raw_message)
        sender = raw_event.get("sender", {})
        nickname = sender.get("card") or sender.get("nickname") or str(user_id)

        clean_text, is_at_bot, _, image_urls = onebot_client.extract_message_elements(message_obj)

        target_id = group_id if message_type == "group" else user_id

        unified_event = UnifiedMessageEvent(
            platform="onebot",
            message_id=str(raw_event.get("message_id", "")),
            session_type="group" if message_type == "group" else "private",
            target_id=target_id,
            user_id=user_id,
            user_name=nickname,
            text=clean_text,
            image_urls=image_urls,
            is_at_bot=is_at_bot,
            raw_event=raw_event,
        )

        await self.emit_message(unified_event)

    async def send_text_message(
        self, session_type: str, target_id: str, user_id: str, text: str
    ) -> bool:
        try:
            if session_type == "group":
                res = await onebot_client.send_group_msg(int(target_id), text)
            else:
                res = await onebot_client.send_private_msg(int(user_id), text)
            return bool(res and res.get("status") != "failed")
        except Exception as e:
            print(f"[OneBotAdapter] 发送文本消息失败: {e}")
            return False

    async def send_voice_message(
        self, session_type: str, target_id: str, user_id: str, voice_uri: str
    ) -> bool:
        try:
            msg_payload = [{"type": "record", "data": {"file": voice_uri}}]
            if session_type == "group":
                res = await onebot_client.send_group_msg(int(target_id), msg_payload)
            else:
                res = await onebot_client.send_private_msg(int(user_id), msg_payload)
            return bool(res and res.get("status") != "failed")
        except Exception as e:
            print(f"[OneBotAdapter] 发送语音消息失败: {e}")
            return False


onebot_default_adapter = OneBotV11Adapter()

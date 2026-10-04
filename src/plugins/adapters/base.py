"""全平台统一通信适配器抽象基类 (BaseAdapter) 与标准化事件定义。
使音理微内核与特定通信协议解耦，支持 QQ(NapCat)、Telegram、Discord、微信等多平台共存与即插即用。
"""

from abc import ABC, abstractmethod
import time
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class UnifiedMessageEvent(BaseModel):
    """跨平台标准化接收消息事件。"""
    model_config = ConfigDict(extra="ignore")
    platform: str = Field(default="onebot", description="平台标识: onebot, telegram, discord, wechat, web 等")
    message_id: str = Field(default="", description="平台侧消息唯一ID")
    session_type: str = Field(default="group", description="会话类型: group, private, channel")
    target_id: str = Field(..., description="目标ID（群号、频道ID、或私聊用户ID）")
    user_id: str = Field(..., description="发言用户唯一ID")
    user_name: str = Field(default="", description="发言用户昵称/群名片")
    text: str = Field(default="", description="纯文本内容（已剔除平台特异性CQ码或特殊控制符）")
    image_urls: List[str] = Field(default_factory=list, description="消息携带的图片直链或本地缓存路径列表")
    is_at_bot: bool = Field(default=False, description="是否@了机器人，或为私聊直发")
    raw_event: Dict[str, Any] = Field(default_factory=dict, description="平台原始事件对象")
    timestamp: float = Field(default_factory=time.time, description="接收时间戳")

    @property
    def session_key(self) -> str:
        """全局唯一会话路由键，例如 onebot_group_10001 或 tg_channel_-1001234567"""
        return f"{self.platform}_{self.session_type}_{self.target_id}"


class BaseAdapter(ABC):
    """通信协议适配器抽象基类。"""

    def __init__(self, adapter_id: str, platform_name: str):
        self.adapter_id = adapter_id
        self.platform_name = platform_name
        self._message_handler: Optional[Callable[[UnifiedMessageEvent], Any]] = None

    def set_message_handler(self, handler: Callable[[UnifiedMessageEvent], Any]):
        """注册内核统一消息派发回调。"""
        self._message_handler = handler

    async def emit_message(self, event: UnifiedMessageEvent):
        """适配器接收到底层平台消息后，封装为统一事件投递至内核。"""
        if self._message_handler:
            await self._message_handler(event)

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """当前适配器是否保持活跃连接。"""
        pass

    @abstractmethod
    async def start(self) -> None:
        """启动适配器客户端/服务端监听。"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """安全停止适配器连接并释放资源。"""
        pass

    @abstractmethod
    async def send_text_message(
        self, session_type: str, target_id: str, user_id: str, text: str
    ) -> bool:
        """向下游平台发送纯文本消息。"""
        pass

    @abstractmethod
    async def send_voice_message(
        self, session_type: str, target_id: str, user_id: str, voice_uri: str
    ) -> bool:
        """向下游平台发送语音/音频消息。"""
        pass

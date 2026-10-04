"""系统全局配置管理模块。
支持环境变量、JSON持久化、Pydantic强类型校验与热重载。
"""

import json
import os
from pathlib import Path
import secrets
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

CONFIG_FILE_PATH = Path("config/config.json")


class LLMConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    base_url: str = Field(default="https://api.openai.com/v1", description="OpenAI 兼容接口 Base URL")
    api_key: str = Field(default="", description="API 密钥")
    model: str = Field(default="gpt-4o-mini", description="主聊天模型名称")
    temperature: float = Field(default=0.7, description="采样温度")
    max_tokens: int = Field(default=1200, description="单次最大输出Token数")
    top_p: float = Field(default=1.0, description="Top-P 采样阈值")
    max_retries: int = Field(default=3, description="LLM 错误重试次数")


class DecisionLLMConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    use_separate_model: bool = Field(default=False, description="是否启用独立的决策模型")
    base_url: str = Field(default="", description="决策模型 Base URL（留空则沿用主模型）")
    api_key: str = Field(default="", description="决策模型 API 密钥（留空则沿用主模型）")
    model: str = Field(default="gpt-4o-mini", description="决策模型名称")
    temperature: float = Field(default=0.2, description="决策模型温度（越低越稳定理性）")
    max_retries: int = Field(default=3, description="决策模型错误重试次数")


class IdentityBinding(BaseModel):
    qq: int = Field(..., description="绑定 QQ 号")
    nickname: str = Field(default="", description="称呼备注昵称")
    identity_tag: str = Field(default="普通群友", description="身份标签 (如 哥哥/钟城晓, 好朋友, 画师同行, 群主)")
    custom_notes: str = Field(default="", description="自定义专属备忘，模型可见")
    is_master: bool = Field(default=False, description="是否为主人/哥哥")


class OneBotConfig(BaseModel):
    mode: str = Field(default="both", description="连接模式: reverse_ws(反向WebSocket) / forward_ws(正向WebSocket) / both(双向同时支持)")
    reverse_ws_path: str = Field(default="/onebot/v11/ws", description="反向 WebSocket 监听路径")
    forward_ws_url: str = Field(default="ws://127.0.0.1:3001", description="正向 WebSocket 目标URL（Docker 或本地 NapCat 暴露的 ws 端口）")
    access_token: str = Field(default="", description="OneBot11 连接密钥（若 NapCat 设置了 token）")
    bot_qq: int = Field(default=0, description="机器人的QQ号（自动获取或手动指定）")
    nickname: str = Field(default="风又音理", description="机器人昵称")


class SecurityConfig(BaseModel):
    admin_password: str = Field(default="admin123", description="WebUI 管理员密码")
    jwt_secret: str = Field(default_factory=lambda: secrets.token_hex(32), description="Session/JWT 签名密钥")
    private_whitelist_enabled: bool = Field(default=False, description="是否开启私聊白名单")
    private_whitelist: List[int] = Field(default_factory=list, description="私聊白名单 QQ 列表")
    group_whitelist_enabled: bool = Field(default=False, description="是否开启群聊白名单")
    group_whitelist: List[int] = Field(default_factory=list, description="群聊白名单 群号列表")
    admin_list: List[int] = Field(default_factory=list, description="超级管理员 QQ 列表")
    master_qq: int = Field(default=0, description="指定的核心主人/哥哥 QQ 号（为0时默认将所有管理员视为主人/哥哥）")
    identity_bindings: List[IdentityBinding] = Field(default_factory=list, description="身份绑定列表 (指定QQ备注昵称与身份标签)")


class CommandsConfig(BaseModel):
    prefix: str = Field(default="/", description="指令前缀 (如 / 或 #)")
    wake_words: List[str] = Field(default_factory=lambda: ["音理", "ねり", "音理酱"], description="群聊唤醒词")
    require_wake_in_group: bool = Field(default=True, description="群聊中是否要求@或唤醒词才触发普通对话")
    enable_reset: bool = Field(default=True, description="启用重置上下文指令 (如 /reset 或 /清空记忆)")
    enable_help: bool = Field(default=True, description="启用帮助指令 (如 /help)")
    enable_status: bool = Field(default=True, description="启用状态查询指令 (如 /status)")
    enable_new: bool = Field(default=True, description="启用 /new 指令")
    enable_chatlist: bool = Field(default=True, description="启用 /chatlist 指令")
    enable_model: bool = Field(default=True, description="启用 /model 指令")
    enable_chat_onoff: bool = Field(default=True, description="启用 /chat on/off 指令")


class TTSConfig(BaseModel):
    enabled: bool = Field(default=True, description="是否开启 TTS 语音合成")
    api_url: str = Field(default="http://127.0.0.1:9880/tts", description="本地 GPT-SoVITS TTS API 地址")
    gpt_sovits_dir: str = Field(default=r"D:\GPT-SoVITS\GPT-SoVITS-v2pro-20250604", description="GPT-SoVITS 根目录路径")
    mode: str = Field(default="simultaneous", description="模式: simultaneous(同声传译: 中文文本+日语配音) / text_and_voice(同文同音) / voice_only(仅语音) / text_only(仅文本)")
    ref_audio_path: str = Field(default=r"patches\gpt_sovits\ref_audio\ner0092.wav", description="参考音频绝对路径或相对路径")
    prompt_text: str = Field(default="犬もいいけどね。今日は猫ちゃん見たから猫派。", description="参考音频对应台词")
    prompt_lang: str = Field(default="ja", description="参考音频语言代码")
    text_lang: str = Field(default="ja", description="目标合成语音语言代码")
    speed_factor: float = Field(default=1.0, description="语速因子 (0.5~2.0)")
    send_as_record: bool = Field(default=True, description="以语音消息(record)形式发送至QQ")
    audio_send_format: str = Field(default="base64", description="语音发送格式: base64(默认推荐，全平台兼容Docker) 或 file")
    gpt_weights_path: str = Field(default=r"D:\GPT-SoVITS\GPT-SoVITS-v2pro-20250604\GPT_weights_v4\inori_v4-e15.ckpt", description="GPT 模型权重路径 (.ckpt)")
    sovits_weights_path: str = Field(default=r"D:\GPT-SoVITS\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v4\inori_v4_e15_s1740_l32.pth", description="SoVITS 模型权重路径 (.pth)")



class ActiveReplyConfig(BaseModel):
    enabled: bool = Field(default=True, description="是否启用群聊主动回复")
    strategy: str = Field(default="decision_model", description="主动回复方案: decision_model(决策模型) 或 probability(自定义概率)")
    probability: float = Field(default=0.05, description="自定义概率触发率 (0.0~1.0)")
    whitelist: List[int] = Field(default_factory=list, description="主动回复群聊白名单")
    frequency: int = Field(default=5, description="检查频率（群内每收到 N 条未@消息触发一次判定）")
    min_confidence: float = Field(default=0.7, description="决策模型最低置信度阈值 (0.0~1.0)")
    idle_timeout_seconds: int = Field(default=0, description="静默超时唤醒秒数（0表示不按静默时间触发）")
    max_history_context: int = Field(default=8, description="提交给决策模型评估的最近群聊上下文条数")


class WebConfig(BaseModel):
    host: str = Field(default="0.0.0.0", description="WebUI 监听地址")
    port: int = Field(default=8088, description="WebUI 监听端口")


class ProviderConfig(BaseModel):
    id: str = Field(..., description="供应商唯一标识")
    name: str = Field(..., description="供应商名称，例如 SiliconFlow、OpenAI、本地Ollama")
    base_url: str = Field(default="", description="Base URL")
    api_key: str = Field(default="", description="API Key")
    max_retries: int = Field(default=3, description="LLM 错误重试次数")
    enabled: bool = Field(default=True, description="是否启用")


class ModelHubItem(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    id: str = Field(..., description="专属Tag，格式: 提供商/模型名称，例如 SiliconFlow/deepseek-ai/DeepSeek-V3")
    provider_id: str = Field(..., description="所属供应商ID")
    model_name: str = Field(..., description="上游模型真实ID")
    display_name: str = Field(default="", description="显示名称")
    temperature: float = Field(default=0.7, description="采样温度")
    max_tokens: int = Field(default=200, description="单次最大输出Token数")
    context_limit: int = Field(default=12, description="上下文轮数限制")
    supports_vision: bool = Field(default=False, description="是否开启图传/识图功能")
    supports_audio: bool = Field(default=False, description="是否开启音频传输功能")
    supports_video: bool = Field(default=False, description="是否开启视频传输功能")
    prompt_price_per_1m: float = Field(default=0.0, description="输入(Prompt)价格(元/百万Tokens, ¥/1M)")
    completion_price_per_1m: float = Field(default=0.0, description="输出(Completion)价格(元/百万Tokens, ¥/1M)")
    prompt_price_per_1k: float = Field(default=0.0, description="输入(Prompt)价格(元/千Tokens, 兼容字段)")
    completion_price_per_1k: float = Field(default=0.0, description="输出(Completion)价格(元/千Tokens, 兼容字段)")


class SessionConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    session_id: str = Field(..., description="会话唯一键，例如 group_10001 或 private_10001")
    session_type: str = Field(default="group", description="会话类型: group 或 private")
    target_id: int = Field(..., description="群号或QQ号")
    display_name: str = Field(default="", description="显示名称（备注昵称或群名）")
    is_pinned: bool = Field(default=False, description="是否置顶")
    is_favorite: bool = Field(default=False, description="是否收藏")
    chat_enabled: bool = Field(default=True, description="此会话的LLM自动聊天功能开关")
    tts_enabled: Optional[bool] = Field(default=None, description="独立TTS开关 (None继承全局)")
    tts_mode: Optional[str] = Field(default=None, description="独立TTS模式 (None继承全局)")
    tts_text_lang: Optional[str] = Field(default=None, description="独立TTS输出语种 (None继承全局)")
    model_id: Optional[str] = Field(default=None, description="指定LLM模型Tag (None使用全局主模型)")
    decision_model_id: Optional[str] = Field(default=None, description="指定决策模型Tag (None使用全局决策模型)")
    rate_limit_per_min: int = Field(default=0, description="每分钟限流条数 (0不限制)")
    cooldown_seconds: int = Field(default=0, description="单次回复后冷却秒数 (0无冷却)")


class AppConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    llm: LLMConfig = Field(default_factory=LLMConfig)
    decision_llm: DecisionLLMConfig = Field(default_factory=DecisionLLMConfig)
    providers: List[ProviderConfig] = Field(default_factory=list, description="多供应商配置列表")
    model_hub: List[ModelHubItem] = Field(default_factory=list, description="系统模型库")
    active_model_id: str = Field(default="", description="当前主聊天模型Tag")
    active_decision_model_id: str = Field(default="", description="当前决策模型Tag")
    session_overrides: dict[str, SessionConfig] = Field(default_factory=dict, description="特定会话独立配置覆盖表")
    onebot: OneBotConfig = Field(default_factory=OneBotConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    commands: CommandsConfig = Field(default_factory=CommandsConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    active_reply: ActiveReplyConfig = Field(default_factory=ActiveReplyConfig)
    web: WebConfig = Field(default_factory=WebConfig)

    def get_session_config(self, session_type: str, target_id: int) -> SessionConfig:
        """获取指定会话的独立配置，未单独配置时返回默认实例。"""
        session_id = f"{session_type}_{target_id}"
        if session_id in self.session_overrides:
            return self.session_overrides[session_id]
        return SessionConfig(
            session_id=session_id,
            session_type=session_type,
            target_id=target_id,
            display_name=str(target_id),
        )

    def get_provider(self, provider_id: str) -> Optional[ProviderConfig]:
        """根据供应商ID检索配置。"""
        for p in self.providers:
            if p.id == provider_id:
                return p
        return None

    def get_model_hub_item(self, model_id_or_tag: str) -> Optional[ModelHubItem]:
        """根据Tag或模型名从模型库检索配置。"""
        if not model_id_or_tag:
            return None
        for item in self.model_hub:
            if item.id == model_id_or_tag or item.model_name == model_id_or_tag:
                return item
        return None


class ConfigManager:
    """配置加载与持久化管理器。"""

    def __init__(self, config_path: Path = CONFIG_FILE_PATH):
        self.config_path = config_path
        self._config: AppConfig = self._load()

    def _load(self) -> AppConfig:
        cfg = None
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cfg = AppConfig.model_validate(data)
            except Exception as e:
                print(f"[Config] 加载现有配置失败，使用默认配置: {e}")
                cfg = AppConfig()
        else:
            cfg = AppConfig()

        # 自动迁移旧版单一模型配置到多供应商系统模型库
        self._ensure_migrated(cfg)
        self.save(cfg)
        return cfg

    def _ensure_migrated(self, cfg: AppConfig):
        """平滑迁移：保证 providers 与 model_hub 至少存在默认主模型。"""
        if not cfg.providers:
            default_p = ProviderConfig(
                id="default",
                name="默认提供商",
                base_url=cfg.llm.base_url,
                api_key=cfg.llm.api_key,
                enabled=True,
            )
            cfg.providers.append(default_p)

        if not cfg.model_hub:
            default_tag = f"默认提供商/{cfg.llm.model}"
            m_item = ModelHubItem(
                id=default_tag,
                provider_id="default",
                model_name=cfg.llm.model,
                display_name=f"{cfg.llm.model} (默认主模型)",
                temperature=cfg.llm.temperature,
                max_tokens=cfg.llm.max_tokens,
                context_limit=12,
                supports_vision=False,
                supports_audio=False,
                supports_video=False,
            )
            cfg.model_hub.append(m_item)
            if not cfg.active_model_id:
                cfg.active_model_id = default_tag

        if not cfg.active_model_id and cfg.model_hub:
            cfg.active_model_id = cfg.model_hub[0].id

    @property
    def config(self) -> AppConfig:
        return self._config

    def save(self, config: Optional[AppConfig] = None) -> None:
        if config is not None:
            self._config = config
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._config.model_dump(), f, ensure_ascii=False, indent=2)

    def update(self, partial_data: dict) -> AppConfig:
        current_data = self._config.model_dump()
        for k, v in partial_data.items():
            if isinstance(v, dict) and k in current_data and isinstance(current_data[k], dict):
                current_data[k].update(v)
            else:
                current_data[k] = v
        self._config = AppConfig.model_validate(current_data)
        self.save()
        return self._config

    def get_session_config(self, session_type: str, target_id: int) -> SessionConfig:
        """获取或创建指定会话的独立配置。"""
        session_id = f"{session_type}_{target_id}"
        if session_id in self._config.session_overrides:
            return self._config.session_overrides[session_id]
        new_sess = SessionConfig(
            session_id=session_id,
            session_type=session_type,
            target_id=target_id,
            display_name=str(target_id),
        )
        self._config.session_overrides[session_id] = new_sess
        self.save()
        return new_sess

    def update_session_config(
        self,
        session_type_or_id: str,
        target_id_or_updates: Any = None,
        **kwargs,
    ) -> SessionConfig:
        """更新并保存会话特定配置。支持两种传参方式：
        1. update_session_config('group_123', {'chat_enabled': False})
        2. update_session_config('group', 123, chat_enabled=False)
        """
        updates = {}
        if isinstance(target_id_or_updates, int):
            session_id = f"{session_type_or_id}_{target_id_or_updates}"
            updates.update(kwargs)
        elif isinstance(target_id_or_updates, dict):
            session_id = session_type_or_id
            updates.update(target_id_or_updates)
            updates.update(kwargs)
        else:
            session_id = session_type_or_id
            updates.update(kwargs)

        if session_id not in self._config.session_overrides:
            parts = session_id.split("_", 1)
            stype = parts[0] if len(parts) > 1 else "group"
            tid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            self._config.session_overrides[session_id] = SessionConfig(
                session_id=session_id, session_type=stype, target_id=tid
            )
        current = self._config.session_overrides[session_id].model_dump()
        current.update(updates)
        updated_obj = SessionConfig.model_validate(current)
        self._config.session_overrides[session_id] = updated_obj
        self.save()
        return updated_obj

    def get_model_hub_item(self, model_id_or_tag: str) -> Optional[ModelHubItem]:
        """根据Tag或模型名从模型库检索配置。"""
        if not model_id_or_tag:
            return None
        for item in self._config.model_hub:
            if item.id == model_id_or_tag or item.model_name == model_id_or_tag:
                return item
        return None

    def get_provider(self, provider_id: str) -> Optional[ProviderConfig]:
        """根据供应商ID检索配置。"""
        for p in self._config.providers:
            if p.id == provider_id:
                return p
        return None


config_manager = ConfigManager()

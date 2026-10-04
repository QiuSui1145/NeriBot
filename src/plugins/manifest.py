"""插件元数据清单模型与校验定义。
遵循标准 Neri Plugin v1 规范，提供 JSON 强类型解析与合法性校验。
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class PluginUISettingItem(BaseModel):
    """插件设置项 Schema 定义，用于前端自动化渲染磨砂玻璃表单。"""
    model_config = ConfigDict(extra="ignore")
    key: str = Field(..., description="设置字段名")
    label: str = Field(..., description="显示标签")
    type: str = Field(default="text", description="字段类型: text, number, boolean, password, select, time, list")
    default: Any = Field(default=None, description="默认值")
    description: str = Field(default="", description="详细说明")
    options: List[Dict[str, str]] = Field(default_factory=list, description="当类型为 select 时的候选项 [{label: 'A', value: 'a'}]")


class PluginUIConfig(BaseModel):
    """插件前端扩展声明。"""
    model_config = ConfigDict(extra="ignore")
    has_tab: bool = Field(default=False, description="是否在侧边栏注入独立 Tab 页面")
    tab_title: str = Field(default="", description="侧边栏 Tab 按钮显示标题")
    tab_icon: str = Field(default="puzzle-piece", description="Tab 图标名称或 Emoji")
    has_overview_card: bool = Field(default=False, description="是否在状态总览页注入监控卡片")
    settings_schema: List[PluginUISettingItem] = Field(default_factory=list, description="自动生成配置表单的字段列表")


class PluginDependencies(BaseModel):
    """插件依赖声明。"""
    model_config = ConfigDict(extra="ignore")
    python: List[str] = Field(default_factory=list, description="Python 依赖列表，如 ['httpx>=0.24.0']")
    plugins: List[str] = Field(default_factory=list, description="前置依赖的其他插件 ID 列表")


class PluginManifest(BaseModel):
    """插件规范清单模型 (plugin.json)。"""
    model_config = ConfigDict(extra="ignore")
    schema_version: str = Field(default="neri_plugin_v1", alias="$schema")
    id: str = Field(..., description="插件唯一标识符 (英文字母、数字、下划线)")
    name: str = Field(..., description="插件友好显示名称")
    version: str = Field(default="1.0.0", description="语义化版本号")
    author: str = Field(default="Unknown", description="插件作者")
    description: str = Field(default="", description="插件功能概述")
    icon: str = Field(default="🧩", description="插件图标 Emoji 或图片相对路径")
    homepage: str = Field(default="", description="插件主页或代码仓库地址")
    min_bot_version: str = Field(default="1.0.0", description="要求的宿主最低版本")
    permissions: List[str] = Field(default_factory=list, description="申请的权限列表")
    dependencies: PluginDependencies = Field(default_factory=PluginDependencies)
    ui: PluginUIConfig = Field(default_factory=PluginUIConfig)
    
    # 扩展驱动能力声明列表
    adapters: List[str] = Field(default_factory=list, description="提供的通信适配器列表")
    memory_drivers: List[str] = Field(default_factory=list, description="提供的记忆系统驱动列表")
    skills: List[str] = Field(default_factory=list, description="提供的 Agentic 技能工具列表")
    tts_drivers: List[str] = Field(default_factory=list, description="提供的 TTS 语音驱动列表")

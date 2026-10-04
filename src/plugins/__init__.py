"""音理 (Kazamata Neri) 插件系统核心导出模块。
供第三方插件开发者统一导入使用。
"""

from src.plugins.adapters.base import BaseAdapter, UnifiedMessageEvent
from src.plugins.base import BasePlugin, PluginContext
from src.plugins.manifest import PluginManifest, PluginUIConfig, PluginUISettingItem
from src.plugins.memory.base import BaseMemoryDriver, MemoryFragment
from src.plugins.skills.base import BaseSkill, skill
from src.plugins.tts.base import BaseTTSDriver
from src.plugins.manager import plugin_manager

__all__ = [
    "BasePlugin",
    "PluginContext",
    "PluginManifest",
    "PluginUIConfig",
    "PluginUISettingItem",
    "BaseAdapter",
    "UnifiedMessageEvent",
    "BaseMemoryDriver",
    "MemoryFragment",
    "BaseSkill",
    "skill",
    "BaseTTSDriver",
    "plugin_manager",
]

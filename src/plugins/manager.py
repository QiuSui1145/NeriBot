"""插件总控中心 (PluginManager)。
负责插件动态扫描、生命周期管理、驱动挂载、事件拦截管道与技能调用沙箱调度。
"""

import asyncio
import importlib
import importlib.util
import json
import logging
from pathlib import Path
import sys
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.plugins.adapters.base import BaseAdapter, UnifiedMessageEvent
from src.plugins.base import BasePlugin, PluginContext
from src.plugins.manifest import PluginManifest
from src.plugins.memory.base import BaseMemoryDriver
from src.plugins.skills.base import BaseSkill
from src.plugins.tts.base import BaseTTSDriver


class PluginManager:
    """音理插件中枢单例。"""

    def __init__(self, plugins_dir: Path = Path("plugins"), config_file: Path = Path("config/plugins.json")):
        self.plugins_dir = plugins_dir
        self.config_file = config_file
        self.logger = logging.getLogger("PluginManager")
        
        # 插件实例字典 plugin_id -> BasePlugin
        self.plugins: Dict[str, BasePlugin] = {}
        # 插件清单字典 plugin_id -> PluginManifest
        self.manifests: Dict[str, PluginManifest] = {}
        # 插件加载错误信息 plugin_id -> str
        self.load_errors: Dict[str, str] = {}

        # 核心多驱动注册表
        self.adapters: Dict[str, BaseAdapter] = {}
        self.memory_drivers: Dict[str, BaseMemoryDriver] = {}
        self.skills: Dict[str, BaseSkill] = {}
        self.tts_drivers: Dict[str, BaseTTSDriver] = {}
        self.commands: Dict[str, Tuple[Callable, str, str]] = {}  # cmd -> (handler, desc, plugin_id)

        # 激活的默认驱动指针
        self.active_memory_driver_id: str = "chroma_default"
        self.active_tts_driver_id: str = "gpt_sovits_default"

        # 插件启用配置持久化状态
        self.state_config: Dict[str, Any] = {
            "enabled_plugins": [],
            "active_memory_driver": "chroma_default",
            "active_tts_driver": "gpt_sovits_default",
        }
        self._load_state()

    def _load_state(self):
        """加载插件开关与激活驱动持久化配置。"""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.state_config.update(data)
                    self.active_memory_driver_id = self.state_config.get("active_memory_driver", "chroma_default")
                    self.active_tts_driver_id = self.state_config.get("active_tts_driver", "gpt_sovits_default")
            except Exception as e:
                self.logger.error(f"读取 plugins.json 失败: {e}")

    def save_state(self):
        """保存插件状态配置。"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_config["active_memory_driver"] = self.active_memory_driver_id
            self.state_config["active_tts_driver"] = self.active_tts_driver_id
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.state_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存 plugins.json 失败: {e}")

    # ====== 核心驱动注册与获取 ======
    def register_adapter(self, adapter: BaseAdapter):
        """注册通信协议适配器。"""
        self.adapters[adapter.adapter_id] = adapter
        self.logger.info(f"注册通信适配器: [{adapter.adapter_id}] ({adapter.platform_name})")

    def get_adapter(self, adapter_id: str) -> Optional[BaseAdapter]:
        return self.adapters.get(adapter_id)

    def register_memory_driver(self, driver: BaseMemoryDriver):
        """注册可插拔记忆系统驱动。"""
        self.memory_drivers[driver.driver_id] = driver
        self.logger.info(f"注册记忆系统驱动: [{driver.driver_id}] ({driver.display_name})")

    def get_active_memory_driver(self) -> BaseMemoryDriver:
        """获取当前激活的记忆系统驱动，如无则自动回退到默认驱动。"""
        if self.active_memory_driver_id in self.memory_drivers:
            return self.memory_drivers[self.active_memory_driver_id]
        if "chroma_default" in self.memory_drivers:
            return self.memory_drivers["chroma_default"]
        # 若尚未载入任何驱动，返回首个可用驱动或报错
        if self.memory_drivers:
            return next(iter(self.memory_drivers.values()))
        raise RuntimeError("系统尚未加载任何记忆系统驱动！")

    def set_active_memory_driver(self, driver_id: str) -> bool:
        if driver_id in self.memory_drivers:
            self.active_memory_driver_id = driver_id
            self.save_state()
            self.logger.info(f"已切换当前记忆系统驱动为: {driver_id}")
            return True
        return False

    def register_skill(self, skill: BaseSkill):
        """注册 Agentic 技能工具。"""
        self.skills[skill.name] = skill
        self.logger.info(f"注册 Agentic 技能: [{skill.name}] - {skill.description[:30]}")

    def get_active_tools_schema(self, is_admin: bool = False) -> List[Dict[str, Any]]:
        """获取所有可用技能并转化为 OpenAI Function Calling tools 结构。"""
        tools = []
        for s in self.skills.values():
            if s.admin_only and not is_admin:
                continue
            tools.append(s.to_openai_tool())
        return tools

    async def execute_skill(
        self, skill_name: str, params: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        """执行特定技能，带超时与容错熔断保护。"""
        skill = self.skills.get(skill_name)
        if not skill:
            return f"错误: 未找到名为「{skill_name}」的可用技能工具"
        try:
            res = await asyncio.wait_for(skill.execute(params, context=context), timeout=15.0)
            return str(res)
        except asyncio.TimeoutError:
            self.logger.warning(f"技能 {skill_name} 执行超时 (15s)")
            return f"执行失败: 技能 {skill_name} 执行超时"
        except Exception as e:
            self.logger.error(f"技能 {skill_name} 执行异常: {e}\n{traceback.format_exc()}")
            return f"执行错误: {str(e)}"

    def register_tts_driver(self, driver: BaseTTSDriver):
        """注册 TTS 语音驱动。"""
        self.tts_drivers[driver.driver_id] = driver
        self.logger.info(f"注册 TTS 语音驱动: [{driver.driver_id}] ({driver.display_name})")

    def get_active_tts_driver(self) -> Optional[BaseTTSDriver]:
        if self.active_tts_driver_id in self.tts_drivers:
            return self.tts_drivers[self.active_tts_driver_id]
        if "gpt_sovits_default" in self.tts_drivers:
            return self.tts_drivers["gpt_sovits_default"]
        return next(iter(self.tts_drivers.values())) if self.tts_drivers else None

    def set_active_tts_driver(self, driver_id: str) -> bool:
        if driver_id in self.tts_drivers:
            self.active_tts_driver_id = driver_id
            self.save_state()
            self.logger.info(f"已切换当前 TTS 语音驱动为: {driver_id}")
            return True
        return False

    # ====== 插件生命周期调度 ======
    def discover_plugins(self):
        """扫描 plugins 目录发现所有合法插件。"""
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        if str(self.plugins_dir.resolve()) not in sys.path:
            sys.path.insert(0, str(self.plugins_dir.resolve()))

        for item in self.plugins_dir.iterdir():
            if not item.is_dir() or item.name.startswith((".", "_")):
                continue
            manifest_file = item / "plugin.json"
            if not manifest_file.exists():
                continue

            plugin_id = item.name
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
                manifest = PluginManifest(**manifest_data)
                self.manifests[plugin_id] = manifest
                self.load_errors.pop(plugin_id, None)
            except Exception as e:
                err = f"解析插件清单失败: {e}"
                self.logger.error(f"[{plugin_id}] {err}")
                self.load_errors[plugin_id] = err

    async def load_and_enable_all(self):
        """发现并根据配置启动启用的插件。"""
        self.discover_plugins()
        enabled_list = self.state_config.get("enabled_plugins", [])
        for pid in list(self.manifests.keys()):
            if pid in enabled_list:
                await self.load_plugin(pid)
                await self.enable_plugin(pid)

    async def load_plugin(self, plugin_id: str) -> bool:
        """加载插件代码到内存。"""
        if plugin_id in self.plugins:
            return True
        manifest = self.manifests.get(plugin_id)
        if not manifest:
            return False

        plugin_dir = self.plugins_dir / plugin_id
        entry_file = plugin_dir / "__init__.py"
        if not entry_file.exists():
            entry_file = plugin_dir / "main.py"
        if not entry_file.exists():
            self.load_errors[plugin_id] = "缺少代码入口文件 __init__.py 或 main.py"
            return False

        try:
            # 动态加载模块（支持任意 plugins_dir 路径）
            module_name = f"neri_plugin_{plugin_id}"
            spec = importlib.util.spec_from_file_location(module_name, entry_file)
            if not spec or not spec.loader:
                self.load_errors[plugin_id] = f"无法为入口文件构建模块规范: {entry_file}"
                return False
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 寻找继承自 BasePlugin 的类
            plugin_cls = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin:
                    plugin_cls = attr
                    break

            if not plugin_cls:
                self.load_errors[plugin_id] = "未找到继承自 BasePlugin 的插件主类"
                return False

            context = PluginContext(plugin_id=plugin_id, plugin_dir=plugin_dir)
            instance: BasePlugin = plugin_cls(context=context, manifest=manifest)
            
            ok = await instance.on_load()
            if ok is False:
                self.load_errors[plugin_id] = "on_load() 返回 False，加载中止"
                return False

            self.plugins[plugin_id] = instance
            self.load_errors.pop(plugin_id, None)
            self.logger.info(f"插件 [{manifest.name}] (v{manifest.version}) 加载成功")
            return True
        except Exception as e:
            err = f"加载插件异常: {e}"
            self.logger.error(f"[{plugin_id}] {err}\n{traceback.format_exc()}")
            self.load_errors[plugin_id] = err
            return False

    async def enable_plugin(self, plugin_id: str) -> bool:
        """启用插件并挂载其驱动与功能。"""
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            loaded = await self.load_plugin(plugin_id)
            if not loaded:
                return False
            plugin = self.plugins.get(plugin_id)

        if plugin.enabled:
            return True

        try:
            await plugin.on_enable()
            plugin.enabled = True

            # 挂载驱动
            for a in plugin._adapters:
                self.register_adapter(a)
                asyncio.create_task(a.start())
            for m in plugin._memory_drivers:
                self.register_memory_driver(m)
            for s in plugin._skills:
                self.register_skill(s)
            for t in plugin._tts_drivers:
                self.register_tts_driver(t)
            for cmd, (handler, desc) in plugin._commands.items():
                self.commands[cmd] = (handler, desc, plugin_id)

            # 更新持久化列表
            enabled_list = self.state_config.setdefault("enabled_plugins", [])
            if plugin_id not in enabled_list:
                enabled_list.append(plugin_id)
                self.save_state()

            self.logger.info(f"插件 [{plugin.manifest.name}] 已成功启用")
            return True
        except Exception as e:
            self.logger.error(f"启用插件 {plugin_id} 失败: {e}\n{traceback.format_exc()}")
            plugin.enabled = False
            return False

    async def disable_plugin(self, plugin_id: str) -> bool:
        """停用插件并注销其挂载的所有驱动与技能。"""
        plugin = self.plugins.get(plugin_id)
        if not plugin or not plugin.enabled:
            return True

        try:
            await plugin.on_disable()
            plugin.enabled = False

            # 卸载驱动与指令
            for a in plugin._adapters:
                await a.stop()
                self.adapters.pop(a.adapter_id, None)
            for m in plugin._memory_drivers:
                self.memory_drivers.pop(m.driver_id, None)
            for s in plugin._skills:
                self.skills.pop(s.name, None)
            for t in plugin._tts_drivers:
                self.tts_drivers.pop(t.driver_id, None)
            
            # 清理指令
            to_remove_cmds = [cmd for cmd, val in self.commands.items() if val[2] == plugin_id]
            for cmd in to_remove_cmds:
                self.commands.pop(cmd, None)

            # 更新持久化状态
            enabled_list = self.state_config.get("enabled_plugins", [])
            if plugin_id in enabled_list:
                enabled_list.remove(plugin_id)
                self.save_state()

            self.logger.info(f"插件 [{plugin.manifest.name}] 已成功停用")
            return True
        except Exception as e:
            self.logger.error(f"停用插件 {plugin_id} 异常: {e}\n{traceback.format_exc()}")
            return False

    async def reload_plugin(self, plugin_id: str) -> bool:
        """热重载单个插件。"""
        self.logger.info(f"正在热重载插件: {plugin_id}...")
        was_enabled = plugin_id in self.state_config.get("enabled_plugins", [])
        if plugin_id in self.plugins:
            await self.disable_plugin(plugin_id)
            plugin = self.plugins.pop(plugin_id)
            await plugin.on_unload()

        self.discover_plugins()
        if was_enabled:
            loaded = await self.load_plugin(plugin_id)
            if loaded:
                return await self.enable_plugin(plugin_id)
            return False
        return True

    # ====== 核心洋葱模型事件拦截管道 (Pipeline Hooks) ======
    async def hook_message_received(self, event: UnifiedMessageEvent) -> bool:
        """接收消息前置拦截。任意插件返回 True 则阻断后续链路。"""
        for plugin in self.plugins.values():
            if not plugin.enabled:
                continue
            try:
                res = await asyncio.wait_for(plugin.on_message_received(event), timeout=3.0)
                if res is True:
                    self.logger.info(f"消息已被插件 [{plugin.manifest.name}] 拦截阻断")
                    return True
            except asyncio.TimeoutError:
                self.logger.warning(f"插件 {plugin.manifest.name} on_message_received 超时已跳过")
            except Exception as e:
                self.logger.error(f"插件 {plugin.manifest.name} on_message_received 报错: {e}")
        return False

    async def hook_command(
        self, cmd: str, args: List[str], event: UnifiedMessageEvent
    ) -> Optional[str]:
        """优先调度插件注册的指令与 on_command Hook。"""
        # 1. 检查插件注册的独立指令表
        cmd_lower = cmd.lower()
        if cmd_lower in self.commands:
            handler, _, plugin_id = self.commands[cmd_lower]
            try:
                if asyncio.iscoroutinefunction(handler):
                    res = await asyncio.wait_for(handler(args, event), timeout=5.0)
                else:
                    res = handler(args, event)
                if res:
                    return str(res)
            except Exception as e:
                self.logger.error(f"插件指令 {cmd} 执行异常: {e}")
                return f"指令执行出错: {e}"

        # 2. 调用插件 on_command Hook
        for plugin in self.plugins.values():
            if not plugin.enabled:
                continue
            try:
                res = await asyncio.wait_for(plugin.on_command(cmd, args, event), timeout=3.0)
                if res is not None:
                    return str(res)
            except Exception as e:
                self.logger.error(f"插件 {plugin.manifest.name} on_command 报错: {e}")
        return None

    async def hook_before_chat(
        self, session_key: str, system_prompt: str, messages: list
    ) -> Tuple[str, list]:
        """大模型生成前置拦截（知识注入/Prompt修改）。"""
        cur_prompt, cur_messages = system_prompt, messages
        for plugin in self.plugins.values():
            if not plugin.enabled:
                continue
            try:
                cur_prompt, cur_messages = await asyncio.wait_for(
                    plugin.before_chat_completion(session_key, cur_prompt, cur_messages), timeout=3.0
                )
            except Exception as e:
                self.logger.error(f"插件 {plugin.manifest.name} before_chat_completion 报错: {e}")
        return cur_prompt, cur_messages

    async def hook_after_chat(self, session_key: str, raw_reply: str) -> str:
        """大模型回复后置拦截（回复修饰/敏感词过滤）。"""
        cur_reply = raw_reply
        for plugin in self.plugins.values():
            if not plugin.enabled:
                continue
            try:
                cur_reply = await asyncio.wait_for(
                    plugin.after_chat_completion(session_key, cur_reply), timeout=3.0
                )
            except Exception as e:
                self.logger.error(f"插件 {plugin.manifest.name} after_chat_completion 报错: {e}")
        return cur_reply

    async def hook_before_output(
        self, event: UnifiedMessageEvent, display_text: str, voice_text: str
    ) -> Tuple[str, str]:
        """向具体通信平台分发前拦截。"""
        cur_disp, cur_voice = display_text, voice_text
        for plugin in self.plugins.values():
            if not plugin.enabled:
                continue
            try:
                cur_disp, cur_voice = await asyncio.wait_for(
                    plugin.before_output_dispatch(event, cur_disp, cur_voice), timeout=3.0
                )
            except Exception as e:
                self.logger.error(f"插件 {plugin.manifest.name} before_output_dispatch 报错: {e}")
        return cur_disp, cur_voice

    async def hook_tick(self, timestamp: float):
        """心跳 Tick 调度。"""
        for plugin in self.plugins.values():
            if not plugin.enabled:
                continue
            try:
                await plugin.on_tick(timestamp)
            except Exception as e:
                self.logger.error(f"插件 {plugin.manifest.name} on_tick 报错: {e}")


plugin_manager = PluginManager()

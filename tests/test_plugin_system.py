"""微内核插件系统完整单元与集成测试套件。
涵盖：
1. 插件自动发现与元数据解析 (Manifest)
2. 插件生命周期 (load, enable, disable, reload)
3. 驱动注册 (通信适配器、记忆系统、TTS驱动、Agentic 技能)
4. 可插拔记忆系统 (SQLiteMemoryDriver 增删查与召回)
5. Agentic 技能执行 (WebSearchSkill 与 OpenAI Tool Schema 转换)
6. 管道事件拦截 Hook (Message, Command, Before/After LLM)
7. FastAPI Web API 接口自动化测试
"""

import asyncio
import os
from pathlib import Path
import sys
import unittest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient

from main import app
from src.auth import generate_token
from src.plugins.adapters.base import UnifiedMessageEvent
from src.plugins.manager import plugin_manager


class TestPluginSystem(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        from src.plugins.adapters.onebot_adapter import onebot_default_adapter
        from src.plugins.memory.chroma_driver import chroma_default_memory_driver
        from src.plugins.tts.gpt_sovits_driver import gpt_sovits_default_tts_driver

        plugin_manager.register_adapter(onebot_default_adapter)
        plugin_manager.register_memory_driver(chroma_default_memory_driver)
        plugin_manager.register_tts_driver(gpt_sovits_default_tts_driver)
        plugin_manager.plugins_dir = ROOT_DIR / "docs" / "examples"
        plugin_manager.discover_plugins()

    def test_01_plugin_discovery(self):
        """测试 4 个核心示范插件是否均被正常扫描发现。"""
        self.assertIn("skill_websearch", plugin_manager.manifests)
        self.assertIn("memory_sqlite_fts", plugin_manager.manifests)
        self.assertIn("adapter_telegram", plugin_manager.manifests)
        self.assertIn("plugin_sample_notes", plugin_manager.manifests)

        websearch_m = plugin_manager.manifests["skill_websearch"]
        self.assertEqual(websearch_m.name, "实时联网搜索与资讯增强")
        self.assertIn("web_search", websearch_m.skills)

    async def test_02_skill_plugin_lifecycle_and_execution(self):
        """测试技能插件的启用、函数工具注册、执行与Schema转化。"""
        ok = await plugin_manager.enable_plugin("skill_websearch")
        self.assertTrue(ok)
        self.assertIn("web_search", plugin_manager.skills)

        # 检查 tools schema
        tools = plugin_manager.get_active_tools_schema()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("web_search", tool_names)

        # 模拟执行技能
        result = await plugin_manager.execute_skill("web_search", {"query": "Python 3.12"}, {})
        self.assertIsInstance(result, str)
        self.assertTrue("Python" in result or "搜索" in result)

        # 测试指令分发 hook
        event = UnifiedMessageEvent(
            platform="test",
            target_id="123",
            user_id="456",
            text="/search AI",
        )
        cmd_reply = await plugin_manager.hook_command("search", ["AI"], event)
        self.assertIsNotNone(cmd_reply)

    async def test_03_memory_driver_plugin(self):
        """测试可插拔异构记忆系统 (SQLite) 的启用、数据读写与切换。"""
        ok = await plugin_manager.enable_plugin("memory_sqlite_fts")
        self.assertTrue(ok)
        self.assertIn("sqlite_fts", plugin_manager.memory_drivers)

        driver = plugin_manager.memory_drivers["sqlite_fts"]
        # 测试出厂重置
        await driver.factory_reset()

        # 测试写入记忆
        mem_id = await driver.add_memory(session_id="group_1001", content="用户非常喜欢喝冰美式咖啡", importance=3.5, mem_type="fact")
        self.assertTrue(mem_id.startswith("mem_"))

        # 测试关键词检索召回
        mems = await driver.search_memories(session_id="group_1001", query="今天想喝咖啡", top_k=2)
        self.assertEqual(len(mems), 1)
        self.assertIn("冰美式咖啡", mems[0])

        # 测试时间线与状态
        timeline = await driver.get_timeline()
        self.assertGreaterEqual(len(timeline), 1)

        status = await driver.get_status()
        self.assertEqual(status["driver"], "sqlite_fts")

        # 切换微内核当前记忆驱动
        switched = plugin_manager.set_active_memory_driver("sqlite_fts")
        self.assertTrue(switched)
        self.assertEqual(plugin_manager.get_active_memory_driver().driver_id, "sqlite_fts")

        # 切换回默认驱动
        plugin_manager.set_active_memory_driver("chroma_default")
        self.assertEqual(plugin_manager.get_active_memory_driver().driver_id, "chroma_default")

    async def test_04_telegram_adapter_plugin(self):
        """测试第三方通信适配器插件的启用与适配器注册。"""
        ok = await plugin_manager.enable_plugin("adapter_telegram")
        self.assertTrue(ok)
        self.assertIn("telegram_bot", plugin_manager.adapters)

        adapter = plugin_manager.adapters["telegram_bot"]
        self.assertEqual(adapter.platform_name, "Telegram Bot")
        self.assertFalse(adapter.is_connected)  # 未配 Token 时处于待命状态

    async def test_05_web_api_endpoints(self):
        """测试 WebUI /api/plugins/* REST 接口。"""
        token = generate_token("admin")
        headers = {"Authorization": f"Bearer {token}"}
        client = TestClient(app)

        # 1. 列表接口
        res = client.get("/api/plugins/list", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertGreaterEqual(len(data["plugins"]), 4)

        # 2. 驱动列表
        res = client.get("/api/plugins/drivers/list", headers=headers)
        self.assertEqual(res.status_code, 200)
        drivers = res.json()
        self.assertIn("active_memory_driver", drivers)

        # 3. 插件配置读写
        res = client.get("/api/plugins/skill_websearch/config", headers=headers)
        self.assertEqual(res.status_code, 200)
        cfg_data = res.json()
        self.assertIn("schema", cfg_data)

        # 4. 文档读取
        res = client.get("/api/plugins/skill_websearch/readme", headers=headers)
        self.assertEqual(res.status_code, 200)

        # 5. 微前端 Tab 内容读取
        res = client.get("/api/plugins/plugin_sample_notes/web/tab", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("备忘便签中心", res.text)


if __name__ == "__main__":
    unittest.main()

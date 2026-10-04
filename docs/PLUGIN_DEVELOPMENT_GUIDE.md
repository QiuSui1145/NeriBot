# 音理 (Kazamata Neri) 微内核插件开发全景指南 (Plugin Development Specification)

> **版本**：v2.0 (Microkernel & Driver Architecture)  
> **面向对象**：音理机器人核心贡献者、第三方社区扩展开发者、平台适配器作者与 Agent 技能构建者。

---

## 1. 架构概览与微内核设计理念

音理 (Kazamata Neri) 采用**微内核 + 驱动提供者 (Microkernel & Pluggable Driver Provider)** 架构设计：
- **微内核中枢**：专注于会话上下文维护 (`ContextManager`)、多供应商 LLM 调度 (`LLMClient`)、安全鉴权与洋葱模型事件总线 (`EventBus`)。
- **驱动与扩展能力完全开放**：通信协议适配器 (Adapter)、异构记忆存储架构 (Memory)、Agentic 技能工具 (Skill) 与语音合成引擎 (TTS) 均被抽象为标准驱动接口，完全向插件开放。
- **全栈微前端**：插件不仅能拓展后端业务逻辑，还可通过 WebUI 动态微前端机制向前端控制台注入独立侧边栏 Tab 页面、仪表盘监控卡片及自适应磨砂玻璃设置面板。

```
plugins/
└── your_plugin_id/                  # 插件唯一标识目录 (小写字母、数字、下划线)
    ├── plugin.json                  # [必须] 插件元数据清单 (Manifest)
    ├── __init__.py                  # [必须] 插件入口主类 (继承 BasePlugin)
    ├── config.json                  # [自动生成] 插件私有持久化配置 (用户修改后自动保存)
    ├── default_config.json          # [可选] 插件私有配置默认模板
    ├── README.md                    # [可选] 插件详细说明与 Markdown 帮助文档
    ├── icon.png                     # [可选] 插件图标
    ├── requirements.txt             # [可选] 插件依赖的第三方 Python 库声明
    └── web/                         # [可选] 前端微前端资源目录
        ├── tab.html                 # 动态注入侧边栏的独立页面 HTML 片段
        ├── card.html                # 动态注入状态总览看板的监控卡片 HTML 片段
        └── style.css                # 插件专属样式表
```

---

## 2. 插件清单规范 (`plugin.json`)

每个插件根目录下**必须**包含合法的 `plugin.json`。微内核在扫描时将对该文件执行强类型校验：

```json
{
  "$schema": "neri_plugin_v1",
  "id": "my_awesome_plugin",
  "name": "趣味小游戏与技能扩展",
  "version": "1.0.0",
  "author": "YourName",
  "description": "提供猜拳小游戏、整点报时以及大模型自主调用的联网搜索工具",
  "icon": "🎮",
  "homepage": "https://github.com/your-repo/my_awesome_plugin",
  "min_bot_version": "1.0.0",
  "permissions": [
    "network",
    "call_skill",
    "schedule_task",
    "web_route"
  ],
  "dependencies": {
    "python": ["httpx>=0.24.0"],
    "plugins": []
  },
  "adapters": [],
  "memory_drivers": [],
  "skills": ["my_search_skill"],
  "tts_drivers": [],
  "ui": {
    "has_tab": true,
    "tab_title": "🎮 游戏中心",
    "tab_icon": "gamepad",
    "has_overview_card": true,
    "settings_schema": [
      {
        "key": "enable_auto_push",
        "label": "是否开启每日早报推送",
        "type": "boolean",
        "default": true,
        "description": "开启后每天早晨8点在主群自动播报"
      },
      {
        "key": "push_time",
        "label": "推送时间",
        "type": "time",
        "default": "08:00",
        "description": "24小时制具体时间"
      },
      {
        "key": "api_secret",
        "label": "第三方 API 密钥",
        "type": "password",
        "default": "",
        "description": "连接私有服务所需的口令密钥"
      },
      {
        "key": "game_difficulty",
        "label": "游戏默认难度",
        "type": "select",
        "default": "normal",
        "description": "选择机器人人机的博弈策略等级",
        "options": [
          {"label": "简单 (呆萌)", "value": "easy"},
          {"label": "普通 (标准)", "value": "normal"},
          {"label": "困难 (腹黑)", "value": "hard"}
        ]
      }
    ]
  }
}
```

### `settings_schema` 支持的字段类型
| 类型 (`type`) | 前端渲染表现 | 说明 |
| :--- | :--- | :--- |
| `text` | 文本输入框 | 常规字符串配置 |
| `number` | 数字输入框 | 整数或浮点数 |
| `boolean` | 磨砂玻璃 Toggle 开关 | 布尔真假值 (`true`/`false`) |
| `password` | 密文密码框 | 密钥/Token，自动屏蔽明文 |
| `select` | 下拉选择器 | 需提供 `options: [{label, value}]` |
| `time` | 时间选择器 | 格式 `HH:MM` |

---

## 3. 插件核心生命周期与宿主上下文

插件主类必须继承自 `src.plugins.BasePlugin`：

```python
from src.plugins import BasePlugin, PluginContext, PluginManifest

class MyPlugin(BasePlugin):
    async def on_load(self) -> bool:
        """
        插件被内核扫描发现并载入内存时调用。
        可在此时注册驱动、技能、指令、初始化本地数据库。
        返回 False 将终止该插件的载入。
        """
        self.context.logger.info("插件载入中...")
        return True

    async def on_enable(self) -> None:
        """插件启用时调用（启动网络监听、定时任务等）。"""
        self.context.logger.info("插件已启用")

    async def on_disable(self) -> None:
        """插件停用时调用（停止网络监听、释放内存句柄等）。"""
        self.context.logger.info("插件已停用")

    async def on_unload(self) -> None:
        """插件被卸载或热重载前调用。"""
        pass
```

### 宿主上下文 `self.context` 提供的能力
- `self.context.data_dir`: 专属数据持久化目录路径 (`Path`)，位于 `plugins/<id>/data/`。
- `self.context.get_config()`: 获取当前插件的私有配置字典（用户在 WebUI 保存的内容）。
- `self.context.save_config(dict)`: 持久化保存插件的私有配置。
- `self.context.logger`: 专属日志对象 (`logging.Logger`)。
- `await self.context.send_text_message(session_type, target_id, user_id, text, platform="onebot")`: 发送纯文本消息。
- `await self.context.generate_speech(text, lang="ja")`: 调用当前激活的 TTS 语音驱动生成音频。
- `await self.context.call_llm(prompt, system_prompt="", model_id=None, tools=None)`: 独立调用大模型推理。

---

## 4. 洋葱模型事件拦截管道 (Pipeline Hooks)

插件可通过重写下列 Hook 方法，在消息生命周期的不同关键节点介入并修改数据流：

```python
from typing import Optional, List, Tuple
from src.plugins import BasePlugin, UnifiedMessageEvent

class MyHookPlugin(BasePlugin):

    # 1. 消息到达第一时间拦截
    async def on_message_received(self, event: UnifiedMessageEvent) -> Optional[bool]:
        """
        返回 True 表示彻底消费并阻断该消息，内核不再执行后续逻辑与大模型推理。
        返回 None 或 False 则放行给下游。
        """
        if "测试拦截" in event.text:
            await self.context.send_text_message(event.session_type, event.target_id, event.user_id, "消息已被拦截！")
            return True
        return None

    # 2. 聊天指令拦截
    async def on_command(self, cmd: str, args: List[str], event: UnifiedMessageEvent) -> Optional[str]:
        """
        当收到 /xxx 指令时触发。返回非空字符串将直接作为文本回复发送，并终止命令链路。
        """
        if cmd == "ping":
            return "pong! 插件响应正常！"
        return None

    # 3. 大模型推理前置介入
    async def before_chat_completion(self, session_key: str, system_prompt: str, messages: list) -> Tuple[str, list]:
        """
        可动态追加外部知识库检索结果或调整提示词风格。
        """
        enhanced_prompt = system_prompt + "\n【额外提示】对方是个喜欢猫咪的朋友。"
        return enhanced_prompt, messages

    # 4. 大模型回复后置介入
    async def after_chat_completion(self, session_key: str, raw_reply: str) -> str:
        """
        对大模型生成的内容进行敏感词替换、表情追加、格式清洗。
        """
        return raw_reply.replace("笨蛋", "小可爱")

    # 5. 消息向目标平台分发前最终干预
    async def before_output_dispatch(self, event: UnifiedMessageEvent, display_text: str, voice_text: str) -> Tuple[str, str]:
        """
        可调整最终送往屏幕展示的文字以及送往 TTS 语音合成引擎的日文台词。
        """
        return display_text, voice_text

    # 6. 后台心跳 Tick
    async def on_tick(self, timestamp: float) -> None:
        """系统时钟心跳，供定时器与计划任务使用。"""
        pass
```

---

## 5. 开发第三方通信协议适配器 (`BaseAdapter`)

若要将音理接入 **Telegram、Discord、微信、KOOK、飞书** 或私有 Web 聊天客户端，仅需继承 `BaseAdapter`：

```python
from src.plugins import BaseAdapter, UnifiedMessageEvent, BasePlugin

class DiscordAdapter(BaseAdapter):
    def __init__(self, plugin_context):
        super().__init__(adapter_id="discord_bot", platform_name="Discord 官方机器人")
        self.context = plugin_context
        self._running = False

    @property
    def is_connected(self) -> bool:
        return self._running

    async def start(self) -> None:
        self._running = True
        # 启动与 Discord 网关的 WebSocket 或 HTTP 连接...

    async def stop(self) -> None:
        self._running = False

    # 当底层收到 Discord 消息时，组装并投递至微内核：
    async def on_discord_raw_message(self, discord_msg):
        event = UnifiedMessageEvent(
            platform="discord",
            message_id=str(discord_msg.id),
            session_type="channel",
            target_id=str(discord_msg.channel_id),
            user_id=str(discord_msg.author.id),
            user_name=discord_msg.author.name,
            text=discord_msg.content,
            is_at_bot=True,
            raw_event=discord_msg.to_dict(),
        )
        # 核心：投递至内核总线！
        await self.emit_message(event)

    async def send_text_message(self, session_type: str, target_id: str, user_id: str, text: str) -> bool:
        # 调用 Discord API 发送文字消息
        return True

    async def send_voice_message(self, session_type: str, target_id: str, user_id: str, voice_uri: str) -> bool:
        # 调用 Discord API 发送语音音频附件
        return True

class DiscordPlugin(BasePlugin):
    async def on_load(self) -> bool:
        self.register_adapter(DiscordAdapter(self.context))
        return True
```

---

## 6. 开发异构记忆系统驱动 (`BaseMemoryDriver`)

若不想使用默认的 ChromaDB 向量库，或期望引入 **Mem0、GraphRAG、Neo4j 知识图谱、SQLite 本地轻量存储**，可实现 `BaseMemoryDriver`：

```python
from typing import List, Dict, Any, Optional
from src.plugins import BaseMemoryDriver, BasePlugin

class MyMemoryDriver(BaseMemoryDriver):
    def __init__(self):
        super().__init__(
            driver_id="my_mem0_driver",
            display_name="Mem0 智能实体关联记忆引擎",
            description="基于实体关系图谱与自适应重要度衰减的高级记忆架构",
        )

    async def search_memories(self, session_id: str, query: str, top_k: int = 2) -> List[str]:
        # 根据 query 检索相关事实与事件，返回格式化字符串列表
        return ["用户养了一只叫小橘的橘猫", "用户对花生过敏"]

    async def add_memory(self, session_id: str, content: str, importance: float = 1.0, mem_type: str = "episode", metadata: Optional[Dict[str, Any]] = None) -> str:
        # 存储新记忆片段，返回生成的记忆 ID
        return "mem_12345"

    async def forget_memory(self, memory_id: str) -> bool: ...
    async def list_memories(self, session_id=None, mem_type=None, query=None, page=1, page_size=50) -> Dict[str, Any]: ...
    async def get_timeline(self, session_id=None) -> List[Dict[str, Any]]: ...
    async def get_graph(self, session_id=None) -> Dict[str, Any]: ...
    async def factory_reset(self) -> bool: ...
    async def export_data(self) -> bytes: ...
    async def get_status(self) -> Dict[str, Any]: ...

class MyMemoryPlugin(BasePlugin):
    async def on_load(self) -> bool:
        self.register_memory_driver(MyMemoryDriver())
        return True
```
> 用户可在 WebUI 控制台的「🧩 插件生态与驱动」页面中，一键将当前激活的记忆驱动切换至您开发的引擎！

---

## 7. 开发 Agentic 技能工具 (`BaseSkill` / `@skill`)

通过向内核注册技能工具，大模型在推理过程中能够**自主感知何时需要调用工具**（Function Calling），自动提取参数并获取执行结果。

### 方式 A：使用 `@skill` 快捷装饰器
```python
from src.plugins import BasePlugin, skill

class MySkillPlugin(BasePlugin):
    async def on_load(self) -> bool:
        
        @skill(
            name="calculate_math",
            description="当用户询问复杂的数学运算、方程求解或几何计算时调用此工具。",
            parameters_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "要计算的数学算式，例如 '(128 + 256) * 0.15'",
                    }
                },
                "required": ["expression"],
            },
            admin_only=False,
        )
        async def calculate_math(params, context):
            expr = params.get("expression", "")
            try:
                # 提示：实际生产请使用安全受限的计算解析器
                return f"计算结果: {eval(expr)}"
            except Exception as e:
                return f"计算错误: {e}"

        self.register_skill(calculate_math)
        return True
```

### 方式 B：继承 `BaseSkill`
参考官方示范插件 `docs/skill_websearch/`（或 `docs/examples/skill_websearch/`），实现 `execute(self, params, context) -> str`。
内核在收到大模型触发 `tool_calls` 后，会自动调用该方法，将结果打包注入消息历史，驱动模型完成下一轮综合回答，并在 WebUI 实时渲染 Planner 状态卡片。

---

## 8. 开发全栈微前端动态 Tab 页面 (`web/tab.html`)

插件如需在 WebUI 中呈现独立的业务管理页面（例如备忘便签、TRPG 跑团卡、RSS 订阅列表等）：

1. 在 `plugin.json` 中配置：
   ```json
   "ui": {
     "has_tab": true,
     "tab_title": "📝 备忘便签",
     "tab_icon": "clipboard-list"
   }
   ```
2. 在 `plugins/<id>/web/tab.html` 编写 HTML 片段：
   ```html
   <div class="glass-card p-6">
       <h2 class="text-xl font-bold flex items-center gap-2">
           <span>📝</span> 便签管理面板
       </h2>
       <p class="text-sm text-gray-400 mt-1">这是由插件动态注入的前端独立视口。</p>

       <button id="btn-demo" class="btn-primary px-4 py-2 mt-4 text-xs">点击测试</button>
   </div>

   <script>
   (function() {
       document.getElementById('btn-demo').onclick = () => {
           // 使用音理标准微前端 SDK 弹出磨砂玻璃弹窗与 Toast
           window.NeriPluginAPI.toast("插件前端微代码运行正常！", "success");
       };
   })();
   </script>
   ```

### 客户端微前端 SDK `window.NeriPluginAPI` 接口
- `window.NeriPluginAPI.fetch(url, options)`: 封装标准请求。
- `window.NeriPluginAPI.toast(message, "success"|"info"|"warning"|"error")`: 触发宿主毛玻璃 Toast。
- `window.NeriPluginAPI.confirm(title, message)`: 触发宿主中央居中磨砂玻璃二选一弹窗（返回 Promise<bool>）。
- `window.NeriPluginAPI.alert(title, message)`: 触发宿主中央警告弹窗。
- `window.NeriPluginAPI.db.get(key)` / `set(key, val)`: 读写本地持久化 IndexedDB。

---

## 9. 插件打包与二次分发标准

1. **零绝对路径**：插件内部一律使用 `self.context.data_dir` 或相对路径操作文件，严禁硬编码宿主机盘符路径（如 `D:\...`）。
2. **打包导出**：
   在 WebUI 控制台的「插件生态」卡片底部直接点击 **📥 导出** 按钮，系统会自动将插件目录完整打包为标准 `neri_plugin_<id>.zip`。
3. **分发安装**：
   接收方在 WebUI 控制台点击「安装插件 (.zip)」，选择文件即可无感一键安装并自动完成语法自检。

"""主程序启动入口。
整合 FastAPI Web 服务、NapCat 反向 WebSocket 端点、静态文件及后台事件调度。
"""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# 将当前目录加入模块搜索路径
BOT_ROOT = Path(__file__).resolve().parent
if str(BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_ROOT))

# Windows 控制台标准输出 UTF-8 兼容性修复
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.bot_service import bot_service
from src.config import config_manager
from src.onebot import onebot_client
from src.web_routes import router as web_router
from src.plugins.web_routes import router as plugin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    cfg = config_manager.config
    print("=" * 60)
    print("✨ 音理 (Kazamata Neri) QQ机器人 & 控制中心正在启动...")
    print(f"🌐 WebUI 控制面板: http://127.0.0.1:{cfg.web.port}")
    print(f"🔌 NapCat 反向 WebSocket: ws://127.0.0.1:{cfg.web.port}{cfg.onebot.reverse_ws_path}")
    print(f"🔗 NapCat 正向 WebSocket 目标: {cfg.onebot.forward_ws_url} (模式: {cfg.onebot.mode})")
    print(f"🎙️ 本地 TTS API 目标: {cfg.tts.api_url}")
    print(f"🧠 当前 LLM 聊天模型: {cfg.llm.model}")
    print("=" * 60)

    # 注册微内核默认系统驱动 (OneBot11, ChromaDB, GPT-SoVITS)
    try:
        from src.plugins.adapters.onebot_adapter import onebot_default_adapter
        from src.plugins.memory.chroma_driver import chroma_default_memory_driver
        from src.plugins.tts.gpt_sovits_driver import gpt_sovits_default_tts_driver
        from src.plugins.manager import plugin_manager

        plugin_manager.register_adapter(onebot_default_adapter)
        plugin_manager.register_memory_driver(chroma_default_memory_driver)
        plugin_manager.register_tts_driver(gpt_sovits_default_tts_driver)

        # 启动适配器监听
        await onebot_default_adapter.start()
        # 扫描并加载所有启用的插件
        await plugin_manager.load_and_enable_all()
    except Exception as e:
        print(f"[PluginManager] 初始化驱动与插件异常: {e}")

    # 确保核心业务消息处理器始终挂载在 OneBot 客户端
    onebot_client.add_message_handler(bot_service.on_message)

    # 启动正向 WebSocket 客户端自动连接协程
    onebot_client.start_forward_client()
    yield
    print("✨ 音理机器人服务已安全停止。")


app = FastAPI(
    title="音理 QQ 机器人控制面板",
    description="OneBot11 NapCat QQ 机器人与本地 TTS 同声传译一体化系统",
    version="1.0.0",
    lifespan=lifespan,
)

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    """防止浏览器对静态前端脚本及接口进行强制缓存导致界面卡死。"""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static") or path == "/" or path.startswith("/api") or path.startswith("/plugins"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# 挂载静态文件
static_dir = BOT_ROOT / "web" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 挂载插件静态资源目录供动态前端加载
plugins_dir = BOT_ROOT / "plugins"
if not plugins_dir.exists():
    plugins_dir.mkdir(parents=True, exist_ok=True)
app.mount("/plugins", StaticFiles(directory=str(plugins_dir)), name="plugins")

# 注册 Web 接口路由
app.include_router(web_router)
app.include_router(plugin_router)


# ---------------- OneBot11 反向 WebSocket 端点 ----------------
@app.websocket("/")
@app.websocket("/onebot/v11/ws")
@app.websocket("/ws")
async def onebot_ws_endpoint(websocket: WebSocket):
    """供 NapCat / Go-CQHttp 反向连接的 WebSocket 端点。"""
    await onebot_client.handle_reverse_ws(websocket)


# ---------------- 首页路由 ----------------
@app.get("/")
async def index():
    """提供 WebUI 首页。"""
    index_file = BOT_ROOT / "web" / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "WebUI 文件缺失"}


def run():
    cfg = config_manager.config
    uvicorn.run(
        "main:app",
        host=cfg.web.host,
        port=cfg.web.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run()

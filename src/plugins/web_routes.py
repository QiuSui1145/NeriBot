"""插件生态 Web 路由集 (Plugin Ecosystem API Routes)。
提供插件列表查看、一键启停、热重载、在线配置表单、ZIP 上传安装、打包导出与驱动切换功能。
"""

import io
import json
import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional
import zipfile

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from src.auth import require_auth
from src.plugins.manager import plugin_manager

router = APIRouter(prefix="/api/plugins", tags=["Plugins"])


class TogglePluginRequest(BaseModel):
    enabled: bool


class SaveConfigRequest(BaseModel):
    config: Dict[str, Any]


class SetActiveDriverRequest(BaseModel):
    driver_id: str


@router.get("/list", dependencies=[Depends(require_auth)])
async def list_plugins():
    """获取所有发现的插件清单、当前启用状态、驱动声明与加载报错信息。"""
    plugin_manager.discover_plugins()
    enabled_set = set(plugin_manager.state_config.get("enabled_plugins", []))
    
    result = []
    for pid, manifest in plugin_manager.manifests.items():
        is_enabled = pid in enabled_set and pid in plugin_manager.plugins and plugin_manager.plugins[pid].enabled
        
        # 收集该插件注册的各种能力实例
        plugin_inst = plugin_manager.plugins.get(pid)
        registered_adapters = [a.adapter_id for a in plugin_inst._adapters] if plugin_inst else []
        registered_memory = [m.driver_id for m in plugin_inst._memory_drivers] if plugin_inst else []
        registered_skills = [s.name for s in plugin_inst._skills] if plugin_inst else []
        registered_tts = [t.driver_id for t in plugin_inst._tts_drivers] if plugin_inst else []
        registered_commands = [c for c, val in plugin_manager.commands.items() if val[2] == pid]

        # 检查是否有专属 tab.html
        plugin_dir = plugin_manager.plugins_dir / pid
        has_tab_html = (plugin_dir / "web" / "tab.html").exists()

        result.append({
            "id": pid,
            "manifest": manifest.model_dump(),
            "enabled": is_enabled,
            "error": plugin_manager.load_errors.get(pid),
            "capabilities": {
                "adapters": registered_adapters,
                "memory_drivers": registered_memory,
                "skills": registered_skills,
                "tts_drivers": registered_tts,
                "commands": registered_commands,
            },
            "has_tab_html": has_tab_html,
        })

    return {"status": "ok", "plugins": result}


@router.get("/docs/guide", dependencies=[Depends(require_auth)])
async def get_plugin_dev_guide():
    """获取完整的插件开发与规范文档 Markdown 内容。"""
    docs_path = Path(__file__).resolve().parent.parent.parent / "docs" / "PLUGIN_DEVELOPMENT_GUIDE.md"
    if not docs_path.exists():
        raise HTTPException(status_code=404, detail="插件开发规范文档未找到")
    content = docs_path.read_text(encoding="utf-8")
    return {"status": "ok", "filename": "PLUGIN_DEVELOPMENT_GUIDE.md", "content": content}


@router.get("/docs/guide/raw")
async def get_plugin_dev_guide_raw():
    """直接查看插件开发规范文档原始文件。"""
    docs_path = Path(__file__).resolve().parent.parent.parent / "docs" / "PLUGIN_DEVELOPMENT_GUIDE.md"
    if not docs_path.exists():
        raise HTTPException(status_code=404, detail="插件开发规范文档未找到")
    return FileResponse(docs_path, media_type="text/markdown", filename="PLUGIN_DEVELOPMENT_GUIDE.md")


@router.post("/{plugin_id}/toggle", dependencies=[Depends(require_auth)])
async def toggle_plugin(plugin_id: str, req: TogglePluginRequest):
    """一键启用或停用指定插件。"""
    if plugin_id not in plugin_manager.manifests:
        raise HTTPException(status_code=404, detail="插件不存在")

    if req.enabled:
        ok = await plugin_manager.enable_plugin(plugin_id)
        if not ok:
            err = plugin_manager.load_errors.get(plugin_id, "未知启用失败")
            raise HTTPException(status_code=400, detail=f"启用插件失败: {err}")
    else:
        ok = await plugin_manager.disable_plugin(plugin_id)
        if not ok:
            raise HTTPException(status_code=400, detail="停用插件失败")

    return {"status": "ok", "plugin_id": plugin_id, "enabled": req.enabled}


@router.post("/{plugin_id}/reload", dependencies=[Depends(require_auth)])
async def reload_plugin(plugin_id: str):
    """热重载指定插件。"""
    if plugin_id not in plugin_manager.manifests:
        raise HTTPException(status_code=404, detail="插件不存在")

    ok = await plugin_manager.reload_plugin(plugin_id)
    if not ok:
        err = plugin_manager.load_errors.get(plugin_id, "未知重载失败")
        raise HTTPException(status_code=400, detail=f"热重载失败: {err}")

    return {"status": "ok", "plugin_id": plugin_id, "message": "插件热重载成功"}


@router.get("/{plugin_id}/config", dependencies=[Depends(require_auth)])
async def get_plugin_config(plugin_id: str):
    """获取指定插件的私有配置及其 UI 设置 Schema。"""
    manifest = plugin_manager.manifests.get(plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="插件不存在")

    plugin_dir = plugin_manager.plugins_dir / plugin_id
    from src.plugins.base import PluginContext
    ctx = PluginContext(plugin_id=plugin_id, plugin_dir=plugin_dir)
    current_cfg = ctx.get_config()

    return {
        "status": "ok",
        "plugin_id": plugin_id,
        "config": current_cfg,
        "schema": [item.model_dump() for item in manifest.ui.settings_schema],
    }


@router.post("/{plugin_id}/config", dependencies=[Depends(require_auth)])
async def save_plugin_config(plugin_id: str, req: SaveConfigRequest):
    """保存指定插件的私有配置并通知插件更新。"""
    manifest = plugin_manager.manifests.get(plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="插件不存在")

    plugin_dir = plugin_manager.plugins_dir / plugin_id
    from src.plugins.base import PluginContext
    ctx = PluginContext(plugin_id=plugin_id, plugin_dir=plugin_dir)
    ok = ctx.save_config(req.config)
    if not ok:
        raise HTTPException(status_code=500, detail="保存插件配置失败")

    return {"status": "ok", "message": "配置保存成功"}


@router.get("/{plugin_id}/readme", dependencies=[Depends(require_auth)])
async def get_plugin_readme(plugin_id: str):
    """读取插件目录下的 README.md 说明文档。"""
    plugin_dir = plugin_manager.plugins_dir / plugin_id
    for name in ["README.md", "readme.md", "README.txt", "readme.txt"]:
        readme_file = plugin_dir / name
        if readme_file.exists():
            try:
                with open(readme_file, "r", encoding="utf-8") as f:
                    return {"status": "ok", "content": f.read()}
            except Exception as e:
                return {"status": "error", "message": str(e)}
    return {"status": "ok", "content": "暂无详细说明文档。"}


@router.get("/{plugin_id}/web/tab", dependencies=[Depends(require_auth)])
async def get_plugin_tab_html(plugin_id: str):
    """获取插件自定义独立 Tab 页面的 HTML 内容供动态注入。"""
    tab_file = plugin_manager.plugins_dir / plugin_id / "web" / "tab.html"
    if not tab_file.exists():
        raise HTTPException(status_code=404, detail="该插件未提供 web/tab.html")
    with open(tab_file, "r", encoding="utf-8") as f:
        return Response(content=f.read(), media_type="text/html")


@router.get("/{plugin_id}/web/card", dependencies=[Depends(require_auth)])
async def get_plugin_card_html(plugin_id: str):
    """获取插件仪表盘卡片 HTML 内容。"""
    card_file = plugin_manager.plugins_dir / plugin_id / "web" / "card.html"
    if not card_file.exists():
        raise HTTPException(status_code=404, detail="该插件未提供 web/card.html")
    with open(card_file, "r", encoding="utf-8") as f:
        return Response(content=f.read(), media_type="text/html")


@router.post("/install", dependencies=[Depends(require_auth)])
async def install_plugin_zip(file: UploadFile = File(...)):
    """上传并解压安装 .zip 插件包。"""
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="仅支持上传 .zip 格式的插件包")

    content = await file.read()
    try:
        z = zipfile.ZipFile(io.BytesIO(content))
        # 寻找 plugin.json 所在目录
        manifest_path = None
        for n in z.namelist():
            if n.endswith("plugin.json") and not n.startswith("__MACOSX"):
                manifest_path = n
                break

        if not manifest_path:
            raise HTTPException(status_code=400, detail="ZIP 包内未发现 plugin.json 规范清单")

        # 读取 manifest 确认 plugin_id
        manifest_raw = z.read(manifest_path).decode("utf-8")
        manifest_dict = json.loads(manifest_raw)
        plugin_id = manifest_dict.get("id")
        if not plugin_id:
            raise HTTPException(status_code=400, detail="plugin.json 中缺少有效的 id 字段")

        # 确定解压目标目录
        target_dir = plugin_manager.plugins_dir / plugin_id
        target_dir.mkdir(parents=True, exist_ok=True)

        # 解压对应文件
        prefix = manifest_path[:-len("plugin.json")]
        for member in z.infolist():
            if member.filename.startswith("__MACOSX"):
                continue
            if member.filename.startswith(prefix):
                rel_name = member.filename[len(prefix):]
                if not rel_name or rel_name.endswith("/"):
                    continue
                dest_file = target_dir / rel_name
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                with open(dest_file, "wb") as f_out:
                    f_out.write(z.read(member.filename))

        # 触发插件发现
        plugin_manager.discover_plugins()
        return {"status": "ok", "plugin_id": plugin_id, "message": f"插件 [{manifest_dict.get('name', plugin_id)}] 安装成功！"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解压安装插件失败: {e}")


@router.get("/{plugin_id}/export", dependencies=[Depends(require_auth)])
async def export_plugin_zip(plugin_id: str):
    """将指定插件完整目录打包为 .zip 文件导出，便于二次分发。"""
    plugin_dir = plugin_manager.plugins_dir / plugin_id
    if not plugin_dir.exists():
        raise HTTPException(status_code=404, detail="插件目录不存在")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(plugin_dir):
            for file in files:
                full_path = Path(root) / file
                rel_path = full_path.relative_to(plugin_dir)
                z.write(full_path, arcname=f"{plugin_id}/{rel_path}")

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="neri_plugin_{plugin_id}.zip"'},
    )


@router.get("/drivers/list", dependencies=[Depends(require_auth)])
async def list_registered_drivers():
    """获取所有已注册的适配器、记忆系统、TTS驱动及 Agentic 技能列表。"""
    adapters_list = [
        {"id": a.adapter_id, "name": a.platform_name, "is_connected": a.is_connected}
        for a in plugin_manager.adapters.values()
    ]
    memory_list = [
        {"id": m.driver_id, "name": m.display_name, "description": m.description, "is_active": (m.driver_id == plugin_manager.active_memory_driver_id)}
        for m in plugin_manager.memory_drivers.values()
    ]
    tts_list = [
        {"id": t.driver_id, "name": t.display_name, "description": t.description, "is_active": (t.driver_id == plugin_manager.active_tts_driver_id)}
        for t in plugin_manager.tts_drivers.values()
    ]
    skills_list = [
        {"name": s.name, "description": s.description, "admin_only": s.admin_only}
        for s in plugin_manager.skills.values()
    ]

    return {
        "status": "ok",
        "active_memory_driver": plugin_manager.active_memory_driver_id,
        "active_tts_driver": plugin_manager.active_tts_driver_id,
        "adapters": adapters_list,
        "memory_drivers": memory_list,
        "tts_drivers": tts_list,
        "skills": skills_list,
    }


@router.post("/drivers/set_active_memory", dependencies=[Depends(require_auth)])
async def set_active_memory_driver(req: SetActiveDriverRequest):
    """切换当前系统使用的记忆驱动。"""
    ok = plugin_manager.set_active_memory_driver(req.driver_id)
    if not ok:
        raise HTTPException(status_code=400, detail="未找到该记忆系统驱动")
    return {"status": "ok", "active_memory_driver": req.driver_id}


@router.post("/drivers/set_active_tts", dependencies=[Depends(require_auth)])
async def set_active_tts_driver(req: SetActiveDriverRequest):
    """切换当前系统使用的 TTS 语音驱动。"""
    ok = plugin_manager.set_active_tts_driver(req.driver_id)
    if not ok:
        raise HTTPException(status_code=400, detail="未找到该 TTS 语音驱动")
    return {"status": "ok", "active_tts_driver": req.driver_id}

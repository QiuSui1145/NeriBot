"""WebUI 后端 API 路由集。
涵盖鉴权、实时看板、Token可视化、LLM与模型列表、TTS测试、白名单配置及在线沙盒对话。
"""

from datetime import datetime
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

from src.auth import generate_token, require_auth, verify_token
from src.bot_service import bot_service
from src.config import AppConfig, ModelHubItem, ProviderConfig, SessionConfig, config_manager
from src.context_manager import context_manager
from src.llm_client import llm_client
from src.onebot import onebot_client
from src.prompting import load_chat_system, load_manifest
from src.statistics import stats_tracker
from src.tts_client import tts_client
from src.image_cache import image_cache_manager

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ModelsFetchRequest(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class TTSTestRequest(BaseModel):
    text: str
    lang: str = "ja"


class PromptSaveRequest(BaseModel):
    filepath: str
    content: str


class SandboxChatRequest(BaseModel):
    message: str
    messages: Optional[List[Dict[str, Any]]] = None
    model_tag: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class QuickMsgRequest(BaseModel):
    message_type: str = "private"
    target_id: int
    message: Any


class ProviderSaveRequest(BaseModel):
    id: Optional[str] = None
    name: str
    base_url: str
    api_key: str = ""
    max_retries: int = 3
    enabled: bool = True


class ModelHubItemRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    id: Optional[str] = None
    provider_id: str
    model_name: str
    display_name: str = ""
    temperature: float = 0.7
    max_tokens: int = 200
    context_limit: int = 12
    supports_vision: bool = False
    supports_audio: bool = False
    supports_video: bool = False
    prompt_price_per_1m: Optional[float] = None
    completion_price_per_1m: Optional[float] = None
    prompt_price_per_1k: Optional[float] = None
    completion_price_per_1k: Optional[float] = None


class SetActiveModelRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    active_model_id: Optional[str] = None
    active_decision_model_id: Optional[str] = None


class FlowSendRequest(BaseModel):
    text: str
    as_bot: bool = True
    send_to_qq: bool = True


class BranchCreateRequest(BaseModel):
    name: str = ""


class BranchSwitchRequest(BaseModel):
    branch_id: int


# ---------------- 鉴权接口 ----------------
@router.post("/api/auth/login")
async def login(req: LoginRequest, response: Response):
    admin_pw = config_manager.config.security.admin_password
    if req.username != "admin" or req.password != admin_pw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    token = generate_token(req.username)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=86400 * 7,
        samesite="lax",
    )
    return {"token": token, "username": req.username}


@router.get("/api/auth/me")
async def me(username: str = Depends(require_auth)):
    return {"username": username}


@router.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token")
    return {"message": "已成功退出登录"}


@router.post("/api/auth/change_password")
async def change_password(req: ChangePasswordRequest, username: str = Depends(require_auth)):
    cfg = config_manager.config
    if req.old_password != cfg.security.admin_password:
        raise HTTPException(status_code=400, detail="原密码不正确")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度不能少于6位")

    config_manager.update({"security": {"admin_password": req.new_password}})
    return {"message": "密码修改成功，请妥善保管"}


# ---------------- 状态与统计接口 ----------------
@router.get("/api/status")
async def get_status(_: str = Depends(require_auth)):
    cfg = config_manager.config
    tts_online, tts_desc = await tts_client.ping()

    return {
        "onebot": {
            "connected": onebot_client.is_connected,
            "reverse_connected": onebot_client.reverse_connected,
            "forward_connected": onebot_client.forward_connected,
            "mode": cfg.onebot.mode,
            "bot_qq": onebot_client.bot_qq or cfg.onebot.bot_qq,
            "nickname": onebot_client.bot_nickname or cfg.onebot.nickname,
            "last_heartbeat": onebot_client.last_heartbeat_time,
            "ws_endpoint": f"ws://{cfg.web.host if cfg.web.host != '0.0.0.0' else '127.0.0.1'}:{cfg.web.port}{cfg.onebot.reverse_ws_path}",
            "forward_ws_url": cfg.onebot.forward_ws_url,
        },
        "tts": {
            "enabled": cfg.tts.enabled,
            "online": tts_online,
            "status_text": tts_desc,
            "mode": cfg.tts.mode,
            "api_url": cfg.tts.api_url,
        },
        "llm": {
            "model": cfg.active_model_id or cfg.llm.model,
            "active_model_id": cfg.active_model_id or cfg.llm.model,
            "display_name": (cfg.get_model_hub_item(cfg.active_model_id).display_name if cfg.get_model_hub_item(cfg.active_model_id) else "") or (cfg.active_model_id or cfg.llm.model),
            "base_url": cfg.llm.base_url,
        },
    }


@router.get("/api/stats/summary")
async def get_stats_summary(_: str = Depends(require_auth)):
    return stats_tracker.get_summary()


def format_uptime(secs: int) -> str:
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}天")
    if hours > 0 or days > 0:
        parts.append(f"{hours}小时")
    if minutes > 0 or hours > 0 or days > 0:
        parts.append(f"{minutes}分")
    parts.append(f"{seconds}秒")
    return "".join(parts)


@router.get("/api/stats/chart")
async def get_stats_chart(range: str = "7d", days: int = 7, _: str = Depends(require_auth)):
    return stats_tracker.get_chart_data(range_type=range, days=days)


@router.get("/api/stats/cost")
async def get_stats_cost(_: str = Depends(require_auth)):
    model_prices = {}
    for it in config_manager.config.model_hub:
        p_1m = getattr(it, "prompt_price_per_1m", 0.0) or (it.prompt_price_per_1k * 1000.0 if getattr(it, "prompt_price_per_1k", 0.0) else 0.0)
        c_1m = getattr(it, "completion_price_per_1m", 0.0) or (it.completion_price_per_1k * 1000.0 if getattr(it, "completion_price_per_1k", 0.0) else 0.0)
        price_dict = {
            "prompt_price_per_1m": p_1m,
            "completion_price_per_1m": c_1m,
            "prompt_price_per_1k": round(p_1m / 1000.0, 6),
            "completion_price_per_1k": round(c_1m / 1000.0, 6),
        }
        model_prices[it.id] = price_dict
        if it.model_name:
            model_prices[it.model_name] = price_dict
    return stats_tracker.get_cost_summary(model_prices)


@router.get("/api/stats/models_distribution")
async def get_models_distribution(_: str = Depends(require_auth)):
    return stats_tracker.get_models_distribution()


@router.get("/api/system/status")
async def get_system_status(_: str = Depends(require_auth)):
    import psutil
    import time
    import platform

    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_count = psutil.cpu_count(logical=True) or 1

    vmem = psutil.virtual_memory()
    ram_used_gb = round(vmem.used / (1024**3), 2)
    ram_total_gb = round(vmem.total / (1024**3), 2)
    ram_percent = vmem.percent

    try:
        disk = psutil.disk_usage(".")
        disk_used_gb = round(disk.used / (1024**3), 1)
        disk_total_gb = round(disk.total / (1024**3), 1)
        disk_percent = disk.percent
    except Exception:
        disk_used_gb, disk_total_gb, disk_percent = 0, 0, 0

    gpu_info = {
        "has_gpu": False,
        "name": "无独立 GPU",
        "vram_used_mb": 0,
        "vram_total_mb": 0,
        "percent": 0,
    }
    try:
        import torch
        if torch.cuda.is_available():
            dev = 0
            dev_name = torch.cuda.get_device_name(dev)
            vram_used = round(torch.cuda.memory_allocated(dev) / (1024**2), 1)
            vram_reserved = round(torch.cuda.memory_reserved(dev) / (1024**2), 1)
            vram_total = round(torch.cuda.get_device_properties(dev).total_memory / (1024**2), 1)
            active_vram = max(vram_used, vram_reserved)
            pct = round((active_vram / vram_total * 100), 1) if vram_total > 0 else 0
            gpu_info = {
                "has_gpu": True,
                "name": dev_name,
                "vram_used_mb": active_vram,
                "vram_total_mb": vram_total,
                "percent": pct,
            }
    except Exception:
        pass

    now_ts = time.time()
    st_ts = getattr(bot_service, "start_time", None) or psutil.Process().create_time()
    uptime_secs = max(0, int(now_ts - st_ts))

    return {
        "cpu": {
            "percent": cpu_percent,
            "cores": cpu_count,
        },
        "ram": {
            "used_gb": ram_used_gb,
            "total_gb": ram_total_gb,
            "percent": ram_percent,
        },
        "disk": {
            "used_gb": disk_used_gb,
            "total_gb": disk_total_gb,
            "percent": disk_percent,
        },
        "gpu": gpu_info,
        "uptime": {
            "seconds": uptime_secs,
            "formatted": format_uptime(uptime_secs),
            "start_time": getattr(bot_service, "start_time_str", "已运行"),
            "pid": os.getpid(),
            "python_version": platform.python_version(),
            "platform": platform.platform(terse=True),
        },
        "health": {
            "onebot_connected": onebot_client.is_connected,
            "tts_enabled": config_manager.config.tts.enabled,
        }
    }


@router.get("/api/stats/logs")
async def get_stats_logs(limit: int = 50, _: str = Depends(require_auth)):
    return stats_tracker.get_recent_logs(limit=limit)


@router.post("/api/stats/clear")
async def clear_stats(_: str = Depends(require_auth)):
    stats_tracker.clear_records()
    return {"message": "统计与调用记录已清空"}


# ---------------- 群聊历史消息日志 ----------------
@router.get("/api/logs/group")
async def get_group_logs(
    group_id: Optional[int] = None,
    keyword: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    _: str = Depends(require_auth),
):
    logs = stats_tracker.get_group_messages(
        group_id=group_id, keyword=keyword, limit=limit, offset=offset
    )
    return {"logs": logs}


@router.post("/api/logs/group/clear")
async def clear_group_logs(group_id: Optional[int] = None, _: str = Depends(require_auth)):
    stats_tracker.clear_group_messages(group_id=group_id)
    return {"message": "群聊历史消息记录已清空"}


# ---------------- 身份绑定管理 ----------------
@router.get("/api/identities")
async def get_identities(_: str = Depends(require_auth)):
    bindings = [b.model_dump() for b in config_manager.config.security.identity_bindings]
    return {
        "master_qq": config_manager.config.security.master_qq,
        "admin_list": config_manager.config.security.admin_list,
        "bindings": bindings,
    }


@router.post("/api/identities/save")
async def save_identities(data: dict, _: str = Depends(require_auth)):
    sec_update = {}
    if "bindings" in data:
        sec_update["identity_bindings"] = data["bindings"]
    if "master_qq" in data:
        sec_update["master_qq"] = int(data["master_qq"] or 0)

    config_manager.update({"security": sec_update})
    return {"message": "身份绑定已更新生效！"}


# ---------------- 配置存取接口 ----------------
@router.get("/api/config")
async def get_config(_: str = Depends(require_auth)):
    return config_manager.config.model_dump()


@router.post("/api/config")
async def update_config(data: dict, _: str = Depends(require_auth)):
    # 保护密码不被空数据覆盖
    if "security" in data and not data["security"].get("admin_password"):
        data["security"]["admin_password"] = config_manager.config.security.admin_password
    updated = config_manager.update(data)
    return {"message": "配置更新成功", "config": updated.model_dump()}


# ---------------- 多供应商与系统模型库 ----------------
@router.post("/api/llm/models")
async def fetch_models(req: ModelsFetchRequest, _: str = Depends(require_auth)):
    try:
        models = await llm_client.fetch_models_list(base_url=req.base_url, api_key=req.api_key)
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/llm/providers")
async def get_providers(_: str = Depends(require_auth)):
    return [p.model_dump() for p in config_manager.config.providers]


@router.post("/api/llm/providers")
async def save_provider(req: ProviderSaveRequest, _: str = Depends(require_auth)):
    cfg = config_manager.config
    p_id = (req.id or req.name).strip().lower().replace(" ", "_")
    matched = next((p for p in cfg.providers if p.id == p_id), None)
    if matched:
        matched.name = req.name
        matched.base_url = req.base_url.rstrip("/")
        matched.api_key = req.api_key
        matched.max_retries = req.max_retries
        matched.enabled = req.enabled
    else:
        new_p = ProviderConfig(
            id=p_id,
            name=req.name,
            base_url=req.base_url.rstrip("/"),
            api_key=req.api_key,
            max_retries=req.max_retries,
            enabled=req.enabled,
        )
        cfg.providers.append(new_p)
    config_manager.save()
    return {"message": "供应商配置已保存", "provider_id": p_id}


@router.delete("/api/llm/providers/{provider_id}")
async def delete_provider(provider_id: str, _: str = Depends(require_auth)):
    cfg = config_manager.config
    cfg.providers = [p for p in cfg.providers if p.id != provider_id]
    config_manager.save()
    return {"message": f"供应商 {provider_id} 已删除"}


@router.post("/api/llm/providers/{provider_id}/fetch_models")
async def fetch_provider_models(provider_id: str, _: str = Depends(require_auth)):
    models = await llm_client.fetch_models_for_provider(provider_id)
    return {"models": models}


@router.get("/api/llm/hub")
async def get_model_hub(_: str = Depends(require_auth)):
    cfg = config_manager.config
    return {
        "items": [item.model_dump() for item in cfg.model_hub],
        "active_model_id": cfg.active_model_id or cfg.llm.model,
        "active_decision_model_id": cfg.active_decision_model_id or cfg.decision_llm.model,
    }


@router.post("/api/llm/hub/item")
async def save_hub_item(req: ModelHubItemRequest, _: str = Depends(require_auth)):
    cfg = config_manager.config
    provider_obj = cfg.get_provider(req.provider_id)
    provider_name = provider_obj.name if provider_obj else req.provider_id

    tag = req.id
    if not tag or "/" not in tag:
        tag = f"{provider_name}/{req.model_name}".strip()

    item_data = ModelHubItem(
        id=tag,
        provider_id=req.provider_id,
        model_name=req.model_name,
        display_name=req.display_name or req.model_name,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        context_limit=req.context_limit,
        supports_vision=req.supports_vision,
        supports_audio=req.supports_audio,
        prompt_price_per_1m=(req.prompt_price_per_1m if req.prompt_price_per_1m is not None else ((req.prompt_price_per_1k * 1000.0) if req.prompt_price_per_1k is not None else 0.0)),
        completion_price_per_1m=(req.completion_price_per_1m if req.completion_price_per_1m is not None else ((req.completion_price_per_1k * 1000.0) if req.completion_price_per_1k is not None else 0.0)),
        prompt_price_per_1k=(req.prompt_price_per_1k if req.prompt_price_per_1k is not None else ((req.prompt_price_per_1m / 1000.0) if req.prompt_price_per_1m is not None else 0.0)),
        completion_price_per_1k=(req.completion_price_per_1k if req.completion_price_per_1k is not None else ((req.completion_price_per_1m / 1000.0) if req.completion_price_per_1m is not None else 0.0)),
    )

    existing_idx = next((i for i, it in enumerate(cfg.model_hub) if it.id == tag), None)
    if existing_idx is not None:
        cfg.model_hub[existing_idx] = item_data
    else:
        cfg.model_hub.append(item_data)

    config_manager.save()
    return {"message": f"模型「{tag}」已加入系统模型库", "item": item_data.model_dump()}


@router.delete("/api/llm/hub/item/{item_tag:path}")
async def delete_hub_item(item_tag: str, _: str = Depends(require_auth)):
    cfg = config_manager.config
    cfg.model_hub = [it for it in cfg.model_hub if it.id != item_tag]
    config_manager.save()
    return {"message": f"模型「{item_tag}」已从模型库移除"}


@router.post("/api/llm/hub/set_active")
async def set_active_hub_models(req: SetActiveModelRequest, _: str = Depends(require_auth)):
    cfg = config_manager.config
    if req.active_model_id is not None:
        cfg.active_model_id = req.active_model_id
    if req.active_decision_model_id is not None:
        cfg.active_decision_model_id = req.active_decision_model_id
    config_manager.save()
    return {"message": "当前主聊天/决策模型已更新"}


# ---------------- 本地 TTS 测试 ----------------
@router.post("/api/tts/test")
async def test_tts(req: TTSTestRequest, _: str = Depends(require_auth)):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="合成文本不能为空")

    uri = await tts_client.generate_speech(req.text, lang=req.lang)
    if not uri:
        raise HTTPException(status_code=500, detail="TTS 语音合成失败，请检查本地 9880 端口服务状态")

    if uri.startswith("base64://"):
        return {"format": "base64", "data": uri[len("base64://") :]}
    else:
        # file:///D:/gal/Bot/cache/audio/voice_xxx.wav -> /api/tts/audio/voice_xxx.wav
        filename = os.path.basename(uri.replace("file:///", "").replace("file://", ""))
        return {"format": "url", "url": f"/api/tts/audio/{filename}"}


@router.get("/api/tts/audio/{filename}")
async def get_tts_audio(filename: str):
    file_path = Path("cache/audio") / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="音频文件不存在")
    return FileResponse(file_path, media_type="audio/wav")


@router.get("/api/cache/image/{filename}")
async def get_cached_image(filename: str, remote: Optional[str] = None):
    cache_dir = Path("cache/images").resolve()
    file_path = (cache_dir / filename).resolve()
    
    # 若本地尚未缓存且携带 remote 远程直链，实时按需拉取并落地
    if (not file_path.exists() or file_path.stat().st_size == 0) and remote:
        await image_cache_manager.cache_image_async(remote, expected_filename=filename)
        
    # 如果指定文件名不存在，尝试同名哈希的其他格式 (例如 .png / .jpg / .gif / .webp)
    if not file_path.exists() or file_path.stat().st_size == 0:
        base_hash = Path(filename).stem
        for candidate in cache_dir.glob(f"{base_hash}.*"):
            if candidate.is_file() and candidate.stat().st_size > 0:
                file_path = candidate.resolve()
                break

    if not file_path.is_relative_to(cache_dir) or not file_path.exists() or file_path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="图片文件不存在或已清除")
    
    fn = file_path.name.lower()
    media_type = "image/jpeg"
    if fn.endswith(".gif"):
        media_type = "image/gif"
    elif fn.endswith(".png"):
        media_type = "image/png"
    elif fn.endswith(".webp"):
        media_type = "image/webp"

    return FileResponse(file_path, media_type=media_type)


# ---------------- 提示词与人设管理 ----------------
@router.get("/api/prompts")
async def get_prompts(_: str = Depends(require_auth)):
    prompts_dir = Path("prompts")
    result = {}
    for p in prompts_dir.rglob("*"):
        if p.is_file() and p.suffix in [".md", ".yaml"]:
            rel_path = str(p.relative_to(prompts_dir)).replace("\\", "/")
            try:
                result[rel_path] = p.read_text(encoding="utf-8")
            except Exception:
                pass
    return result


@router.post("/api/prompts/save")
async def save_prompt(req: PromptSaveRequest, _: str = Depends(require_auth)):
    target_path = Path("prompts") / req.filepath
    if not target_path.resolve().is_relative_to(Path("prompts").resolve()):
        raise HTTPException(status_code=403, detail="非法路径越权访问")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(req.content, encoding="utf-8")
    return {"message": f"文件 {req.filepath} 保存成功"}


# ---------------- 在线沙盒测试聊天 ----------------
@router.post("/api/chat/test")
async def test_chat(req: SandboxChatRequest, _: str = Depends(require_auth)):
    cfg = config_manager.config
    tts_mode = cfg.tts.mode
    is_simultaneous = cfg.tts.enabled and (tts_mode == "simultaneous")

    sys_prompt = load_chat_system(
        root=Path("prompts"), language="zh", enable_simultaneous=is_simultaneous
    )

    # 注入哥哥专属档案，使沙盒测试与私聊体验完全一致
    speaker_profile, _ = bot_service.build_speaker_profile(cfg.security.master_qq or 10001, "哥哥")
    sys_prompt += speaker_profile

    # 语义检索召回核心记忆
    try:
        from src.plugins.manager import plugin_manager
        active_mem_driver = plugin_manager.get_active_memory_driver()
        retrieved_mems = await active_mem_driver.search_memories(str(cfg.security.master_qq or 10001), query=req.message, top_k=2)
        if retrieved_mems:
            mem_str = "\n".join([f"- {m}" for m in retrieved_mems])
            sys_prompt += f"\n\n【脑海中闪回的深层记忆片段】\n{mem_str}"
    except Exception:
        pass

    messages = [{"role": "system", "content": sys_prompt}]
    if req.messages and isinstance(req.messages, list):
        for m in req.messages:
            r = m.get("role")
            c = m.get("content")
            if r in ("user", "assistant") and c:
                messages.append({"role": r, "content": str(c)})
        if not messages or messages[-1].get("role") != "user" or messages[-1].get("content") != req.message:
            messages.append({"role": "user", "content": req.message})
    else:
        messages.append({"role": "user", "content": req.message})

    from src.prompting import get_tts_anchor_rules
    messages.append({"role": "system", "content": get_tts_anchor_rules()})

    try:
        reply_raw, usage = await llm_client.chat_completion(
            messages=messages,
            session_type="sandbox",
            target_id=0,
            user_id=cfg.security.master_qq or 10001,
            model_tag=req.model_tag,
            temperature_override=req.temperature,
            max_tokens_override=req.max_tokens,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 请求失败: {e}")

    if is_simultaneous:
        display_text, voice_text = tts_client.parse_dual_track(reply_raw)
    else:
        display_text = tts_client._clean_text(reply_raw)
        voice_text = display_text

    voice_url = None
    if cfg.tts.enabled:
        target_lang = "ja" if is_simultaneous else cfg.tts.text_lang
        voice_uri = await tts_client.generate_speech(voice_text, lang=target_lang)
        if voice_uri:
            if voice_uri.startswith("base64://"):
                voice_url = f"data:audio/wav;base64,{voice_uri[len('base64://'):]}"
            else:
                fn = os.path.basename(voice_uri.replace("file:///", "").replace("file://", ""))
                voice_url = f"/api/tts/audio/{fn}"

    return {
        "raw_reply": reply_raw,
        "display_text": display_text,
        "voice_text": voice_text,
        "voice_url": voice_url,
        "usage": usage,
    }


# ---------------- OneBot 调试消息发送 ----------------
@router.post("/api/onebot/send_test")
async def send_test_onebot(req: QuickMsgRequest, _: str = Depends(require_auth)):
    try:
        if req.message_type == "group":
            res = await onebot_client.send_group_msg(req.target_id, req.message)
        else:
            res = await onebot_client.send_private_msg(req.target_id, req.message)
        return {"status": "ok", "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/test/simulate_msg")
async def simulate_msg(text: str = "音理，你在做什么呢？", _: str = Depends(require_auth)):
    test_uid = config_manager.config.security.master_qq or 10001
    fake_event = {
        "post_type": "message",
        "message_type": "private",
        "user_id": test_uid,
        "raw_message": text,
        "message": text,
        "sender": {"user_id": test_uid, "nickname": "Master"},
    }
    await onebot_client._on_raw_event(fake_event)
    return {"status": "dispatched"}


# ---------------- 上下信息流总管理接口 ----------------
@router.get("/api/flow/sessions")
async def get_flow_sessions(_: str = Depends(require_auth)):
    cfg = config_manager.config
    sec = cfg.security
    sessions_dict: Dict[str, dict] = {}

    # 1. 扫描白名单群
    for gid in sec.group_whitelist:
        sid = f"group_{gid}"
        sess_cfg = cfg.get_session_config("group", gid)
        ctx = context_manager.get_session("group", gid)
        b = ctx.get_active_branch()
        sessions_dict[sid] = {
            "session_id": sid,
            "session_type": "group",
            "target_id": gid,
            "display_name": sess_cfg.display_name or f"群 {gid}",
            "is_pinned": sess_cfg.is_pinned,
            "is_favorite": sess_cfg.is_favorite,
            "chat_enabled": sess_cfg.chat_enabled,
            "tts_enabled": sess_cfg.tts_enabled,
            "tts_mode": sess_cfg.tts_mode,
            "tts_text_lang": sess_cfg.tts_text_lang,
            "model_id": sess_cfg.model_id,
            "decision_model_id": sess_cfg.decision_model_id,
            "rate_limit_per_min": sess_cfg.rate_limit_per_min,
            "cooldown_seconds": sess_cfg.cooldown_seconds,
            "active_branch_id": b.branch_id,
            "active_branch_name": b.name,
            "message_count": len(b.history),
            "last_active_time": ctx.last_active_time,
        }

    # 2. 扫描白名单私聊与管理员
    privates = set(sec.private_whitelist) | set(sec.admin_list)
    if sec.master_qq:
        privates.add(sec.master_qq)
    for qid in privates:
        sid = f"private_{qid}"
        sess_cfg = cfg.get_session_config("private", qid)
        ctx = context_manager.get_session("private", qid)
        b = ctx.get_active_branch()
        sessions_dict[sid] = {
            "session_id": sid,
            "session_type": "private",
            "target_id": qid,
            "display_name": sess_cfg.display_name or f"私聊 {qid}",
            "is_pinned": sess_cfg.is_pinned,
            "is_favorite": sess_cfg.is_favorite,
            "chat_enabled": sess_cfg.chat_enabled,
            "tts_enabled": sess_cfg.tts_enabled,
            "tts_mode": sess_cfg.tts_mode,
            "tts_text_lang": sess_cfg.tts_text_lang,
            "model_id": sess_cfg.model_id,
            "decision_model_id": sess_cfg.decision_model_id,
            "rate_limit_per_min": sess_cfg.rate_limit_per_min,
            "cooldown_seconds": sess_cfg.cooldown_seconds,
            "active_branch_id": b.branch_id,
            "active_branch_name": b.name,
            "message_count": len(b.history),
            "last_active_time": ctx.last_active_time,
        }

    # 3. 补充 session_overrides 中定义的其他会话
    for sid, sc in cfg.session_overrides.items():
        if sid not in sessions_dict:
            ctx = context_manager.get_session(sc.session_type, sc.target_id)
            b = ctx.get_active_branch()
            sessions_dict[sid] = {
                "session_id": sid,
                "session_type": sc.session_type,
                "target_id": sc.target_id,
                "display_name": sc.display_name or sid,
                "is_pinned": sc.is_pinned,
                "is_favorite": sc.is_favorite,
                "chat_enabled": sc.chat_enabled,
                "tts_enabled": sc.tts_enabled,
                "tts_mode": sc.tts_mode,
                "tts_text_lang": sc.tts_text_lang,
                "model_id": sc.model_id,
                "decision_model_id": sc.decision_model_id,
                "rate_limit_per_min": sc.rate_limit_per_min,
                "cooldown_seconds": sc.cooldown_seconds,
                "active_branch_id": b.branch_id,
                "active_branch_name": b.name,
                "message_count": len(b.history),
                "last_active_time": ctx.last_active_time,
            }

    # 排序：置顶优先，其次按最后活跃时间倒序
    res_list = list(sessions_dict.values())
    res_list.sort(key=lambda x: (not x["is_pinned"], -x["last_active_time"]))
    return {"sessions": res_list}


@router.get("/api/flow/session/{session_id}/settings")
async def get_session_settings(session_id: str, _: str = Depends(require_auth)):
    parts = session_id.split("_", 1)
    stype = parts[0] if len(parts) > 1 else "group"
    tid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    sc = config_manager.get_session_config(stype, tid)
    return sc.model_dump()


@router.post("/api/flow/session/{session_id}/settings")
async def update_session_settings(session_id: str, updates: dict, _: str = Depends(require_auth)):
    updated = config_manager.update_session_config(session_id, updates)
    return {"message": "会话设置已保存", "settings": updated.model_dump()}


@router.get("/api/flow/session/{session_id}/messages")
async def get_session_messages(session_id: str, _: str = Depends(require_auth)):
    parts = session_id.split("_", 1)
    stype = parts[0] if len(parts) > 1 else "group"
    tid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    ctx = context_manager.get_session(stype, tid)
    active_b = ctx.get_active_branch()
    msgs = []
    for m in active_b.history:
        sd = m.serialize()
        if sd.get("images"):
            sd["images"] = [image_cache_manager.get_local_url(u) for u in sd["images"]]
        msgs.append(sd)
    return {
        "session_id": session_id,
        "branch_id": active_b.branch_id,
        "branch_name": active_b.name,
        "messages": msgs,
    }


@router.post("/api/flow/session/{session_id}/send")
async def send_session_manual_message(session_id: str, req: FlowSendRequest, _: str = Depends(require_auth)):
    parts = session_id.split("_", 1)
    stype = parts[0] if len(parts) > 1 else "group"
    tid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="发送内容不能为空")

    ok = await bot_service.send_manual_message(
        session_type=stype,
        target_id=tid,
        text=req.text.strip(),
        as_bot=req.as_bot,
        send_to_qq=req.send_to_qq,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="发送消息至QQ失败，请检查连接状态")
    return {"status": "sent", "text": req.text}


@router.get("/api/flow/session/{session_id}/branches")
async def get_session_branches(session_id: str, _: str = Depends(require_auth)):
    parts = session_id.split("_", 1)
    stype = parts[0] if len(parts) > 1 else "group"
    tid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    ctx = context_manager.get_session(stype, tid)
    return {"branches": ctx.list_branches(), "active_branch_id": ctx.active_branch_id}


@router.post("/api/flow/session/{session_id}/branch/create")
async def create_session_branch(session_id: str, req: BranchCreateRequest, _: str = Depends(require_auth)):
    parts = session_id.split("_", 1)
    stype = parts[0] if len(parts) > 1 else "group"
    tid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    ctx = context_manager.get_session(stype, tid)
    b = ctx.create_branch(name=req.name)
    context_manager.save()
    return {"message": f"新上下文「{b.name}」已创建", "branch": b.serialize()}


@router.post("/api/flow/session/{session_id}/branch/switch")
async def switch_session_branch(session_id: str, req: BranchSwitchRequest, _: str = Depends(require_auth)):
    parts = session_id.split("_", 1)
    stype = parts[0] if len(parts) > 1 else "group"
    tid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    ctx = context_manager.get_session(stype, tid)
    b = ctx.switch_branch(req.branch_id)
    if not b:
        raise HTTPException(status_code=404, detail="未找到目标上下文分支")
    context_manager.save()
    return {"message": f"已切换至上下文「{b.name}」", "branch": b.serialize()}


@router.delete("/api/flow/session/{session_id}/branch/{branch_id}")
async def delete_session_branch(session_id: str, branch_id: int, _: str = Depends(require_auth)):
    parts = session_id.split("_", 1)
    stype = parts[0] if len(parts) > 1 else "group"
    tid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    ctx = context_manager.get_session(stype, tid)
    ctx.delete_branch(branch_id)
    context_manager.save()
    return {"message": "上下文分支已删除/清空"}


@router.post("/api/flow/session/{session_id}/branch/clear")
async def clear_session_context(session_id: str, _: str = Depends(require_auth)):
    parts = session_id.split("_", 1)
    stype = parts[0] if len(parts) > 1 else "group"
    tid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    ctx = context_manager.get_session(stype, tid)
    ctx.clear()
    context_manager.save()
    return {"message": "当前上下文记忆已清空"}


# ---------------- 现实世界时间感知接口 ----------------
@router.get("/api/system/time")
async def get_system_time():
    now = datetime.now()
    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
    hour = now.hour
    if 5 <= hour < 8:
        period = "清晨 / 早晨"
    elif 8 <= hour < 12:
        period = "上午"
    elif 12 <= hour < 14:
        period = "中午 / 午休"
    elif 14 <= hour < 18:
        period = "下午"
    elif 18 <= hour < 21:
        period = "傍晚 / 晚上"
    elif 21 <= hour < 24:
        period = "深夜"
    else:
        period = "凌晨 / 后半夜"
    return {
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": weekday_cn,
        "period": period,
    }



# ---------------- UI 资产上传接口 ----------------
import uuid
import time

@router.post("/api/ui/upload")
async def upload_ui_asset(file: UploadFile = File(...), _: str = Depends(require_auth)):
    """上传自定义壁纸图片或背景音乐"""
    uploads_dir = Path(__file__).resolve().parent.parent / "web" / "static" / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename).suffix.lower() if file.filename else ".bin"
    safe_name = f"{int(time.time())}_{uuid.uuid4().hex[:8]}{suffix}"
    dest = uploads_dir / safe_name
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)
    return {"status": "ok", "url": f"/static/uploads/{safe_name}", "filename": safe_name}


@router.get("/api/ui/config")
async def get_ui_config(_: str = Depends(require_auth)):
    """获取服务端持久化 UI 配置"""
    import json
    cfg_file = Path(__file__).resolve().parent.parent / "data" / "ui_config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

@router.post("/api/ui/config")
async def save_ui_config(req: Request, _: str = Depends(require_auth)):
    """持久化保存 UI 配置至服务端"""
    import json
    cfg_file = Path(__file__).resolve().parent.parent / "data" / "ui_config.json"
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    body = await req.json()
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)
    return {"status": "ok"}


# ---------------- GPT-SoVITS 补丁与服务管理接口 ----------------
from src.tts_service_manager import tts_service_manager

@router.get("/api/tts/service/status")
async def get_tts_service_status(_: str = Depends(require_auth)):
    """获取 GPT-SoVITS 服务健康与运行状态"""
    return tts_service_manager.get_status()

@router.post("/api/tts/service/install_patch")
async def install_tts_patch(req: Request, _: str = Depends(require_auth)):
    """向指定 GPT-SoVITS 目录自动打补丁并配置启动脚本"""
    body = await req.json()
    dir_path = body.get("gpt_sovits_dir", "")
    try:
        res = tts_service_manager.install_patch(dir_path)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/tts/service/start")
async def start_tts_service(_: str = Depends(require_auth)):
    """一键在后台拉起 GPT-SoVITS 服务"""
    try:
        return tts_service_manager.start_service()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/tts/service/stop")
async def stop_tts_service(_: str = Depends(require_auth)):
    """一键停止 GPT-SoVITS 服务"""
    try:
        return tts_service_manager.stop_service()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/api/tts/service/logs")
async def get_tts_service_logs(_: str = Depends(require_auth)):
    """获取 GPT-SoVITS 最近运行日志"""
    return {"logs": tts_service_manager.get_logs()}

class TTSWeightsSwitchRequest(BaseModel):
    gpt_weights_path: Optional[str] = None
    sovits_weights_path: Optional[str] = None

@router.post("/api/tts/service/switch_weights")
async def switch_tts_weights(req: TTSWeightsSwitchRequest, _: str = Depends(require_auth)):
    """热切换或保存 GPT 与 SoVITS 模型权重路径"""
    try:
        return tts_service_manager.switch_weights(
            gpt_weights_path=req.gpt_weights_path,
            sovits_weights_path=req.sovits_weights_path
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



# ---------------- 记忆管理与知识图谱接口 ----------------
from src.memory.vector_store import vector_store

class MemoryAddRequest(BaseModel):
    user_id: Any = 0
    content: str
    importance: float = 3.0
    mem_type: str = "fact"

class MemoryUpdateRequest(BaseModel):
    id: str
    content: Optional[str] = None
    importance: Optional[float] = None
    mem_type: Optional[str] = None
    is_forgotten: Optional[bool] = None
    user_id: Optional[Any] = None

class MemoryDeleteRequest(BaseModel):
    id: str
    hard: bool = False

class MemorySimulateRequest(BaseModel):
    user_id: Any = 0
    query: str
    top_k: int = 5
    lambda_decay: float = 0.1
    decay_rate: Optional[float] = None
    weight_sim: float = 0.7
    alpha: Optional[float] = None

class MemoryForgetRunRequest(BaseModel):
    threshold: float = 0.5


@router.get("/api/memory/stats")
async def get_memory_stats(_: str = Depends(require_auth)):
    try:
        stats = vector_store.get_stats()
        res = dict(stats)
        res["status"] = "ok"
        res["stats"] = stats
        return res
    except Exception as e:
        print(f"[WebAPI] 获取记忆统计异常: {e}")
        raise HTTPException(status_code=500, detail=f"获取记忆统计失败: {str(e)}")

@router.get("/api/memory/selftest")
async def get_memory_selftest(_: str = Depends(require_auth)):
    try:
        report = vector_store.self_test()
        res = dict(report)
        res["status"] = "ok"
        res["report"] = report
        return res
    except Exception as e:
        print(f"[WebAPI] 记忆自检异常: {e}")
        raise HTTPException(status_code=500, detail=f"记忆自检失败: {str(e)}")

@router.get("/api/memory/list")
async def get_memory_list(
    user_id: Optional[int] = None,
    mem_type: Optional[str] = None,
    is_forgotten: Optional[bool] = None,
    keyword: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    _: str = Depends(require_auth),
):
    try:
        items = vector_store.list_memories(
            user_id=user_id,
            mem_type=mem_type,
            is_forgotten=is_forgotten,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )
        return {"status": "ok", "memories": items, "count": len(items)}
    except Exception as e:
        print(f"[WebAPI] 获取记忆列表异常: {e}")
        raise HTTPException(status_code=500, detail=f"获取记忆列表失败: {str(e)}")

@router.post("/api/memory/add")
async def add_memory_item(req: MemoryAddRequest, _: str = Depends(require_auth)):
    if not req.content or not req.content.strip():
        raise HTTPException(status_code=400, detail="记忆内容不能为空")
    try:
        uid = int(req.user_id) if str(req.user_id).isdigit() else 0
        mem_id = vector_store.add_memory(
            user_id=uid,
            content=req.content.strip(),
            importance=req.importance,
            mem_type=req.mem_type,
        )
        return {"status": "ok", "id": mem_id, "message": "记忆碎片录入成功"}
    except Exception as e:
        print(f"[WebAPI] 录入记忆碎片异常: {e}")
        raise HTTPException(status_code=500, detail=f"录入记忆失败: {str(e)}")

@router.post("/api/memory/update")
async def update_memory_item(req: MemoryUpdateRequest, _: str = Depends(require_auth)):
    try:
        uid = None
        if req.user_id is not None:
            uid = int(req.user_id) if str(req.user_id).isdigit() else 0
        ok = vector_store.update_memory(
            mem_id=req.id,
            content=req.content,
            importance=req.importance,
            mem_type=req.mem_type,
            is_forgotten=req.is_forgotten,
            user_id=uid,
        )
        if not ok:
            raise HTTPException(status_code=404, detail="未找到目标记忆")
        return {"status": "ok", "message": "记忆修正更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[WebAPI] 更新记忆异常: {e}")
        raise HTTPException(status_code=500, detail=f"更新记忆失败: {str(e)}")

@router.post("/api/memory/delete")
async def delete_memory_item(req: MemoryDeleteRequest, _: str = Depends(require_auth)):
    try:
        ok = vector_store.delete_memory(mem_id=req.id, hard=req.hard)
        if not ok:
            raise HTTPException(status_code=404, detail="未找到目标记忆")
        return {"status": "ok", "message": "记忆已粉碎删除" if req.hard else "记忆已归档至遗忘库"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[WebAPI] 删除记忆异常: {e}")
        raise HTTPException(status_code=500, detail=f"删除记忆失败: {str(e)}")

@router.post("/api/memory/restore/{mem_id}")
async def restore_memory_item(mem_id: str, _: str = Depends(require_auth)):
    try:
        ok = vector_store.restore_memory(mem_id=mem_id)
        if not ok:
            raise HTTPException(status_code=404, detail="未找到目标记忆")
        return {"status": "ok", "message": "记忆已重新唤醒激活"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[WebAPI] 恢复记忆异常: {e}")
        raise HTTPException(status_code=500, detail=f"恢复记忆失败: {str(e)}")

@router.post("/api/memory/maintenance/forget")
async def run_forgetting_maintenance(req: Optional[MemoryForgetRunRequest] = None, _: str = Depends(require_auth)):
    try:
        th = req.threshold if req else 0.5
        cnt = vector_store.apply_forgetting_curve(threshold=th)
        return {"status": "ok", "result": {"scanned": 12, "newly_forgotten": cnt}, "message": f"遗忘扫描完成，共归档 {cnt} 条记忆碎片"}
    except Exception as e:
        print(f"[WebAPI] 遗忘扫描异常: {e}")
        raise HTTPException(status_code=500, detail=f"遗忘扫描失败: {str(e)}")

@router.post("/api/memory/maintenance/clear_test")
async def clear_test_data(_: str = Depends(require_auth)):
    try:
        cnt = vector_store.clear_test_memories()
        return {"status": "ok", "result": {"deleted": cnt}, "message": f"清理完成，共移除 {cnt} 条测试记忆"}
    except Exception as e:
        print(f"[WebAPI] 清理测试数据异常: {e}")
        raise HTTPException(status_code=500, detail=f"清理测试数据失败: {str(e)}")

@router.post("/api/memory/simulate")
async def simulate_retrieval(req: MemorySimulateRequest, _: str = Depends(require_auth)):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="查询内容不能为空")
    try:
        w_sim = req.alpha if req.alpha is not None else req.weight_sim
        l_decay = req.decay_rate if req.decay_rate is not None else req.lambda_decay
        uid = int(req.user_id) if str(req.user_id).isdigit() else 0
        results = vector_store.simulate_retrieval(
            user_id=uid,
            query=req.query.strip(),
            top_k=req.top_k,
            lambda_decay=l_decay,
            weight_sim=w_sim,
        )
        return {"status": "ok", "results": results, "count": len(results)}
    except Exception as e:
        print(f"[WebAPI] 模拟检索异常: {e}")
        raise HTTPException(status_code=500, detail=f"模拟检索失败: {str(e)}")

@router.get("/api/memory/graph")
async def get_memory_graph(limit: int = 120, _: str = Depends(require_auth)):
    try:
        return vector_store.get_graph_data(limit=limit)
    except Exception as e:
        print(f"[WebAPI] 获取图谱异常: {e}")
        return {"nodes": [], "links": []}

@router.post("/api/memory/reset_factory")
async def reset_memory_factory(_: str = Depends(require_auth)):
    """擦除全部记忆并恢复至出厂预置核心人设与情景记忆"""
    try:
        res = vector_store.reset_to_factory_defaults()
        return res
    except Exception as e:
        print(f"[WebAPI] 出厂初始化异常: {e}")
        raise HTTPException(status_code=500, detail=f"出厂初始化失败: {str(e)}")

@router.get("/api/memory/export")
async def export_memories_zip(_: str = Depends(require_auth)):
    """打包导出全部记忆库文件为 ZIP (包含 JSON、CSV 表格与系统元数据)"""
    import io
    import urllib.parse
    try:
        zip_bytes, filename = vector_store.export_memories_archive()
        ascii_filename = "neri_memories_export.zip"
        quoted_filename = urllib.parse.quote(filename)
        return StreamingResponse(
            io.BytesIO(zip_bytes),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{quoted_filename}',
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出记忆库失败: {e}")




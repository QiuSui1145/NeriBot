"""OneBot11 标准协议通信层（全面兼容 NapCat、Go-CQHttp、Lagrange）。
同时支持反向 WebSocket 服务端及正向 WebSocket 客户端模式，专为 Docker 容器与宿主机互联设计。
"""

import asyncio
import json
import time
from typing import Any, Callable, Dict, List, Optional

import httpx
import websockets
from fastapi import WebSocket, WebSocketDisconnect

from src.config import config_manager


class OneBotClient:
    """OneBot11 通信协议封装。"""

    def __init__(self):
        self.active_reverse_ws: Optional[WebSocket] = None
        self.active_forward_ws: Optional[Any] = None
        self.reverse_connected: bool = False
        self.forward_connected: bool = False
        self.last_heartbeat_time: float = 0.0
        self.bot_qq: int = 0
        self.bot_nickname: str = "风又音理"
        self._message_handlers: List[Callable[[dict], Any]] = []
        self._message_handler: Optional[Callable[[dict], Any]] = None
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._forward_task: Optional[asyncio.Task] = None
        self._is_fetching_login: bool = False
        self._req_counter: int = 0

    @property
    def is_connected(self) -> bool:
        return self.reverse_connected or self.forward_connected

    def set_message_handler(self, handler: Callable[[dict], Any]):
        """设置消息处理器（向上兼容保留，支持多处理器并存）。"""
        self._message_handler = handler
        if handler not in self._message_handlers:
            self._message_handlers.append(handler)

    def add_message_handler(self, handler: Callable[[dict], Any]):
        """添加消息处理器，支持多个模块共同消费消息事件。"""
        if handler not in self._message_handlers:
            self._message_handlers.append(handler)

    def remove_message_handler(self, handler: Callable[[dict], Any]):
        """移除指定消息处理器。"""
        if handler in self._message_handlers:
            self._message_handlers.remove(handler)
        if self._message_handler == handler:
            self._message_handler = self._message_handlers[0] if self._message_handlers else None

    # ---------------- 1. 反向 WebSocket 处理 (NapCat -> Bot) ----------------
    async def handle_reverse_ws(self, websocket: WebSocket):
        """处理 NapCat 反向 WebSocket 连接。"""
        await websocket.accept()
        self.active_reverse_ws = websocket
        self.reverse_connected = True
        self.last_heartbeat_time = time.time()
        print("[OneBot11] NapCat 反向 WebSocket 连接已建立！")

        asyncio.create_task(self._fetch_login_info())

        try:
            while True:
                data = await websocket.receive_text()
                try:
                    payload = json.loads(data)
                    await self._on_raw_event(payload)
                except Exception as e:
                    print(f"[OneBot11] 反向WS处理事件出错: {e}")
        except WebSocketDisconnect:
            print("[OneBot11] NapCat 反向 WebSocket 断开连接")
        finally:
            self.active_reverse_ws = None
            self.reverse_connected = False

    # ---------------- 2. 正向 WebSocket 处理 (Bot -> NapCat Docker) ----------------
    def start_forward_client(self):
        """启动正向 WebSocket 客户端常驻重连协程。"""
        if self._forward_task is None or self._forward_task.done():
            self._forward_task = asyncio.create_task(self._forward_ws_loop())

    async def _forward_ws_loop(self):
        """正向 WebSocket 客户端循环（断线自动重连）。"""
        while True:
            cfg = config_manager.config.onebot
            if cfg.mode not in ["forward_ws", "both"]:
                await asyncio.sleep(5)
                continue

            target_url = cfg.forward_ws_url.strip()
            if not target_url:
                await asyncio.sleep(5)
                continue

            headers = {}
            if cfg.access_token:
                headers["Authorization"] = f"Bearer {cfg.access_token}"

            try:
                # print(f"[OneBot11] 正在尝试正向连接至 NapCat: {target_url}")
                async with websockets.connect(target_url, extra_headers=headers, ping_interval=20, ping_timeout=10) as ws:
                    self.active_forward_ws = ws
                    self.forward_connected = True
                    self.last_heartbeat_time = time.time()
                    print(f"[OneBot11] 正向 WebSocket 连接已成功建立！目标: {target_url}")

                    asyncio.create_task(self._fetch_login_info())

                    while True:
                        msg = await ws.recv()
                        try:
                            payload = json.loads(msg)
                            await self._on_raw_event(payload)
                        except Exception as e:
                            print(f"[OneBot11] 正向WS解析消息出错: {e}")
            except Exception as e:
                self.active_forward_ws = None
                self.forward_connected = False
                # 保持静默重试，避免刷屏
                await asyncio.sleep(5)

    # ---------------- 3. 登录信息与事件总线 ----------------
    async def _fetch_login_info(self):
        """向 NapCat 请求当前登录账号的 QQ 与昵称。"""
        if self._is_fetching_login:
            return
        self._is_fetching_login = True
        await asyncio.sleep(0.5)
        try:
            info = await self.call_api("get_login_info", {})
            if info and "data" in info:
                self.bot_qq = info["data"].get("user_id", self.bot_qq)
                self.bot_nickname = info["data"].get("nickname", self.bot_nickname)
                config_manager.update({"onebot": {"bot_qq": self.bot_qq, "nickname": self.bot_nickname}})
                print(f"[OneBot11] 登录信息就绪: QQ={self.bot_qq}, 昵称={self.bot_nickname}")
        except Exception as e:
            print(f"[OneBot11] 获取登录信息失败: {e}")
        finally:
            self._is_fetching_login = False

    async def _safe_handle_message(self, event: dict):
        """异步并发处理消息事件，不阻塞 WebSocket 帧接收总线。"""
        handlers = list(self._message_handlers)
        if not handlers and self._message_handler:
            handlers = [self._message_handler]
        for h in handlers:
            try:
                await h(event)
            except Exception as e:
                print(f"[OneBot11] 异步消息处理异常: {e}")

    async def _on_raw_event(self, event: dict):
        """事件分发中心。"""
        # 1. 响应 API Echo 调用
        echo = event.get("echo")
        if echo:
            print(f"[OneBot11 Raw] 收到包含 echo 的消息: echo={echo}, status={event.get('status')}, retcode={event.get('retcode')}, msg={event.get('message') or event.get('wording') or ''}")
            if echo in self._pending_requests:
                future = self._pending_requests.pop(echo)
                if not future.done():
                    future.set_result(event)
                return
            else:
                print(f"[OneBot11 Raw 警告] echo={echo} 未在待命中 (当前等待: {list(self._pending_requests.keys())})")

        # 2. 心跳与元事件
        post_type = event.get("post_type")
        if post_type == "meta_event":
            self.last_heartbeat_time = time.time()
            if event.get("meta_event_type") == "lifecycle":
                sub_type = event.get("sub_type")
                if sub_type == "connect":
                    asyncio.create_task(self._fetch_login_info())
            return

        # 3. 消息事件处理 (异步协程调度，严禁阻塞 WebSocket 帧读取与 Echo 握手)
        if post_type == "message" and (self._message_handlers or self._message_handler):
            asyncio.create_task(self._safe_handle_message(event))

    # ---------------- 4. API 调用接口 ----------------
    async def call_api(self, action: str, params: dict, timeout: float = 30.0) -> dict:
        """通过可用的 WebSocket 或 HTTP 兜底调用 OneBot11 API，严禁重复发送。"""
        send_socket = self.active_reverse_ws or self.active_forward_ws
        ws_sent_ok = False

        # 1. 尝试通过 WebSocket 调用
        if send_socket and self.is_connected:
            self._req_counter += 1
            echo = f"req_{int(time.time() * 1000)}_{self._req_counter}_{action}"
            future = asyncio.get_event_loop().create_future()
            self._pending_requests[echo] = future

            payload = {"action": action, "params": params, "echo": echo}
            raw_str = json.dumps(payload)

            log_params = dict(params)
            if "message" in log_params and isinstance(log_params["message"], list):
                log_params["message"] = str(log_params["message"])[:80] + "..."
            print(f"[OneBot11 API] WS 发送请求: action={action}, params={log_params}, echo={echo}")

            try:
                if self.active_reverse_ws:
                    await self.active_reverse_ws.send_text(raw_str)
                elif self.active_forward_ws:
                    await self.active_forward_ws.send(raw_str)
                ws_sent_ok = True
            except Exception as e:
                self._pending_requests.pop(echo, None)
                print(f"[OneBot11 API 警告] WS 发送底层网络异常: {e}，将通过 HTTP 兜底...")

            if ws_sent_ok:
                try:
                    res = await asyncio.wait_for(future, timeout=timeout)
                    status = res.get("status")
                    retcode = res.get("retcode")
                    msg = res.get("message") or res.get("wording") or ""
                    print(f"[OneBot11 API] WS 收到响应: action={action}, status={status}, retcode={retcode}, msg={msg}")
                    return res
                except asyncio.TimeoutError:
                    self._pending_requests.pop(echo, None)
                    print(f"[OneBot11 API 警告] WS API {action} 等待响应超时 ({timeout}秒, echo={echo})，但请求帧已送达 NapCat，严防复读，跳过二次重发。")
                    return {"status": "ok", "retcode": 0, "message": "ws_assumed_sent"}
                except Exception as e:
                    self._pending_requests.pop(echo, None)
                    print(f"[OneBot11 API 异常] WS 等待结果异常: {e}")

        # 2. 仅当 WS 未连接或发送数据帧失败时，才调用 HTTP API 兜底 (NapCat 容器 3000 端口)
        try:
            http_url = f"http://127.0.0.1:3000/{action}"
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(http_url, json=params)
                if resp.status_code == 200:
                    res = resp.json()
                    print(f"[OneBot11 API] HTTP 兜底调用成功: action={action}, retcode={res.get('retcode')}")
                    return res
                else:
                    print(f"[OneBot11 API 错误] HTTP 兜底返回错误码 {resp.status_code}: {resp.text[:200]}")
        except Exception as http_err:
            print(f"[OneBot11 API 错误] HTTP 兜底请求失败: {http_err}")

        raise ConnectionError(f"OneBot11 调用 API {action} 失败 (WS 与 HTTP 均无法完成)")

    async def send_private_msg(self, user_id: int, message: Any):
        """发送私聊消息（支持字符串文本或 segment 列表）。"""
        return await self.call_api("send_private_msg", {"user_id": user_id, "message": message})

    async def send_group_msg(self, group_id: int, message: Any):
        """发送群聊消息（支持字符串文本或 segment 列表）。"""
        return await self.call_api("send_group_msg", {"group_id": group_id, "message": message})

    def extract_text_and_at(self, message: Any) -> tuple[str, bool, List[int]]:
        """从 OneBot11 消息结构解析出纯文本、是否@了机器人以及被@的所有QQ号列表。"""
        bot_qq = self.bot_qq or config_manager.config.onebot.bot_qq
        text_parts = []
        is_at_bot = False
        at_list = []

        if isinstance(message, str):
            import re
            for match in re.finditer(r"\[CQ:at,qq=([0-9a-zA-Z_]+)", message):
                raw_qq = match.group(1)
                if raw_qq.isdigit():
                    target_qq = int(raw_qq)
                    at_list.append(target_qq)
                    if bot_qq and target_qq == bot_qq:
                        is_at_bot = True
            cleaned = re.sub(r"\[CQ:.*?\]", "", message).strip()
            return cleaned, is_at_bot, at_list

        elif isinstance(message, list):
            for seg in message:
                if not isinstance(seg, dict):
                    continue
                seg_type = seg.get("type")
                seg_data = seg.get("data", {})
                if seg_type == "text":
                    text_parts.append(seg_data.get("text", ""))
                elif seg_type == "at":
                    raw_qq = str(seg_data.get("qq", "0")).strip()
                    if raw_qq.isdigit():
                        target_qq = int(raw_qq)
                        at_list.append(target_qq)
                        if bot_qq and target_qq == bot_qq:
                            is_at_bot = True
            full_text = "".join(text_parts).strip()
            return full_text, is_at_bot, at_list

        return str(message).strip(), False, []

    def extract_message_elements(self, message: Any) -> tuple[str, bool, List[int], List[str]]:
        """从 OneBot11 消息解析纯文本、@、以及图片 URL 列表（多模态图传）。"""
        import re
        bot_qq = self.bot_qq or config_manager.config.onebot.bot_qq
        text_parts = []
        is_at_bot = False
        at_list = []
        image_urls = []

        if isinstance(message, str):
            for match in re.finditer(r"\[CQ:at,qq=([0-9a-zA-Z_]+)", message):
                raw_qq = match.group(1)
                if raw_qq.isdigit():
                    t_qq = int(raw_qq)
                    at_list.append(t_qq)
                    if bot_qq and t_qq == bot_qq:
                        is_at_bot = True

            for match in re.finditer(r"\[CQ:image,([^\]]+)\]", message):
                params_str = match.group(1)
                url_m = re.search(r"url=([^,\]]+)", params_str)
                file_m = re.search(r"file=([^,\]]+)", params_str)
                path_m = re.search(r"path=([^,\]]+)", params_str)
                candidate = ""
                if url_m and url_m.group(1).startswith("http"):
                    candidate = url_m.group(1).replace("&amp;", "&")
                elif file_m and (file_m.group(1).startswith("http") or file_m.group(1).startswith("file://") or (len(file_m.group(1)) > 3 and file_m.group(1)[1:3] in (":\\", ":/"))):
                    candidate = file_m.group(1)
                elif path_m:
                    candidate = path_m.group(1)
                elif url_m:
                    candidate = url_m.group(1).replace("&amp;", "&")
                elif file_m:
                    candidate = file_m.group(1)
                if candidate:
                    image_urls.append(candidate)

            cleaned = re.sub(r"\[CQ:.*?\]", "", message).strip()
            return cleaned, is_at_bot, at_list, image_urls

        elif isinstance(message, list):
            for seg in message:
                if not isinstance(seg, dict):
                    continue
                seg_type = seg.get("type")
                seg_data = seg.get("data", {})
                if seg_type == "text":
                    text_parts.append(seg_data.get("text", ""))
                elif seg_type == "at":
                    raw_qq = str(seg_data.get("qq", "0")).strip()
                    if raw_qq.isdigit():
                        t_qq = int(raw_qq)
                        at_list.append(t_qq)
                        if bot_qq and t_qq == bot_qq:
                            is_at_bot = True
                elif seg_type == "image":
                    url = seg_data.get("url") or seg_data.get("file") or seg_data.get("path", "")
                    local_path = seg_data.get("path")
                    if local_path and (local_path.startswith("file://") or (len(local_path) > 3 and local_path[1:3] in (":\\", ":/"))):
                        url = local_path
                    elif seg_data.get("url"):
                        url = seg_data.get("url")
                    elif seg_data.get("file"):
                        url = seg_data.get("file")
                    if url:
                        image_urls.append(url)

            full_text = "".join(text_parts).strip()
            return full_text, is_at_bot, at_list, image_urls

        return str(message).strip(), False, [], []


onebot_client = OneBotClient()

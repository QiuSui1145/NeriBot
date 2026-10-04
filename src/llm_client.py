"""标准 OpenAI 兼容接口客户端与多供应商模型调度模块。
支持按会话路由至不同供应商、自动解析多模态能力（识图/音频/视频）、Token核算与低延迟异步通信。
"""

import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from src.config import config_manager
from src.statistics import stats_tracker


class LLMClient:
    """OpenAI 兼容多供应商接口客户端。"""

    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout

    def _normalize_base_url(self, base_url: str) -> str:
        url = base_url.strip().rstrip("/")
        if not url.endswith("/v1") and "/v1" not in url:
            url += "/v1"
        return url

    @staticmethod
    def _parse_sse_response(raw_text: str) -> Tuple[str, dict]:
        """解析 SSE (Server-Sent Events) 流式文本为完整的回复内容和用量统计。"""
        import json
        chunks = []
        reasoning_chunks = []
        usage = {}

        for line in raw_text.splitlines():
            line = line.strip()
            if not line or not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                if "usage" in chunk and chunk["usage"]:
                    usage = chunk["usage"]
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        chunks.append(content)
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                    if reasoning:
                        reasoning_chunks.append(reasoning)
            except Exception:
                continue

        reply_text = "".join(chunks)
        if not reply_text and reasoning_chunks:
            reply_text = "".join(reasoning_chunks)
        return reply_text, usage

    async def fetch_models_list(
        self, base_url: Optional[str] = None, api_key: Optional[str] = None
    ) -> List[str]:
        """获取目标 Base URL 提供的模型列表。"""
        cfg = config_manager.config.llm
        target_base = self._normalize_base_url(base_url or cfg.base_url)
        target_key = (api_key if api_key is not None else cfg.api_key).strip()

        headers = {"Content-Type": "application/json"}
        if target_key:
            headers["Authorization"] = f"Bearer {target_key}"

        models_endpoint = f"{target_base}/models"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(models_endpoint, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"获取模型列表失败 [HTTP {resp.status_code}]: {resp.text[:200]}"
                )
            data = resp.json()

        models = []
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            for item in data["data"]:
                if isinstance(item, dict) and "id" in item:
                    models.append(item["id"])
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "id" in item:
                    models.append(item["id"])
                elif isinstance(item, str):
                    models.append(item)

        models.sort()
        return models

    async def fetch_models_for_provider(self, provider_id: str) -> List[str]:
        """根据供应商ID获取其可用的模型列表。"""
        p = config_manager.get_provider(provider_id)
        if not p:
            raise ValueError(f"供应商 [{provider_id}] 不存在")
        return await self.fetch_models_list(base_url=p.base_url, api_key=p.api_key)

    def resolve_model_and_provider(
        self, model_tag_or_id: Optional[str] = None, is_decision: bool = False
    ) -> Tuple[str, str, str, float, int, bool]:
        """解析模型及其所属供应商的 base_url, api_key, model_name, temp, max_tokens, supports_vision。"""
        app_cfg = config_manager.config

        # 1. 决策模型特化分支
        if is_decision:
            decision_tag = app_cfg.active_decision_model_id
            if decision_tag and decision_tag != "same_as_active":
                model_tag_or_id = decision_tag
            elif app_cfg.decision_llm.use_separate_model and app_cfg.decision_llm.model:
                b_url = app_cfg.decision_llm.base_url or app_cfg.llm.base_url
                a_key = app_cfg.decision_llm.api_key or app_cfg.llm.api_key
                return (
                    b_url,
                    a_key,
                    app_cfg.decision_llm.model,
                    app_cfg.decision_llm.temperature,
                    200,
                    False,
                )

        # 2. 普通会话模型解析（优先传入的 tag，其次全局 active_model_id，再次回退）
        target_tag = model_tag_or_id or app_cfg.active_model_id
        model_item = config_manager.get_model_hub_item(target_tag)

        if model_item:
            provider = config_manager.get_provider(model_item.provider_id)
            base_url = (provider.base_url if provider and provider.base_url else app_cfg.llm.base_url)
            api_key = (provider.api_key if provider and provider.api_key else app_cfg.llm.api_key)
            return (
                base_url,
                api_key,
                model_item.model_name,
                model_item.temperature,
                model_item.max_tokens,
                model_item.supports_vision,
            )

        # 3. 回退默认单模型配置
        return (
            app_cfg.llm.base_url,
            app_cfg.llm.api_key,
            app_cfg.llm.model,
            app_cfg.llm.temperature,
            app_cfg.llm.max_tokens,
            False,
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        session_type: str = "sandbox",
        target_id: int = 0,
        user_id: int = 0,
        is_decision: bool = False,
        model_tag: Optional[str] = None,
        temperature_override: Optional[float] = None,
        max_tokens_override: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """调用聊天补全接口，返回回复文本及消耗的 Token (若触发技能调用则附带在 usage['tool_calls'] 中)。"""
        (
            base_url,
            api_key,
            model_name,
            default_temp,
            default_max_tokens,
            supports_vision,
        ) = self.resolve_model_and_provider(model_tag_or_id=model_tag, is_decision=is_decision)

        temp = temperature_override if temperature_override is not None else default_temp
        max_tokens = max_tokens_override if max_tokens_override is not None else default_max_tokens

        # 如果模型不支持识图，安全扁平化多模态结构为纯字符串，防止上游 400 报错
        cleaned_messages = []
        for m in messages:
            content = m.get("content")
            if isinstance(content, list) and not supports_vision:
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif isinstance(part, dict) and part.get("type") == "image_url":
                        text_parts.append("[图片]")
                cleaned_messages.append({"role": m["role"], "content": "\n".join(text_parts).strip()})
            else:
                cleaned_messages.append(m)

        target_base = self._normalize_base_url(base_url)
        headers = {"Content-Type": "application/json"}
        if api_key.strip():
            headers["Authorization"] = f"Bearer {api_key.strip()}"

        payload = {
            "model": model_name,
            "messages": cleaned_messages,
            "temperature": temp,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if is_decision:
            payload["response_format"] = {"type": "json_object"}
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        endpoint = f"{target_base}/chat/completions"
        
        keys = [k.strip() for k in api_key.replace(";", ",").split(",") if k.strip()]
        if not keys:
            keys = [""]
            
        from src.config import config_manager
        app_cfg = config_manager.config
        
        # 错误重试次数解析：决策模型从 decision_llm 读取；聊天模型优先从所属 provider 读取，回退全局 llm 配置，安全兜底3次
        if is_decision:
            max_retries = getattr(app_cfg.decision_llm, "max_retries", getattr(app_cfg.llm, "max_retries", 3))
        else:
            target_tag = model_tag or app_cfg.active_model_id
            model_item = config_manager.get_model_hub_item(target_tag)
            provider = config_manager.get_provider(model_item.provider_id) if model_item else None
            if provider and getattr(provider, "max_retries", None) is not None:
                max_retries = provider.max_retries
            else:
                max_retries = getattr(app_cfg.llm, "max_retries", 3)

        if max_retries is None or max_retries < 0:
            max_retries = 3
        
        last_error = None
        for attempt in range(max_retries + 1):
            current_key = keys[attempt % len(keys)]
            if current_key:
                headers["Authorization"] = f"Bearer {current_key}"
                
            start_time = time.time()
            try:
                import httpx
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(endpoint, json=payload, headers=headers)

                latency_ms = int((time.time() - start_time) * 1000)
                if resp.status_code != 200:
                    err_msg = f"HTTP {resp.status_code}: {resp.text[:300]}"
                    raise RuntimeError(f"LLM Error: {err_msg}")

                raw_text = resp.text.strip()
                if not raw_text:
                    raise RuntimeError(f"上游模型返回了空响应 (HTTP {resp.status_code})")

                content_type = resp.headers.get("content-type", "").lower()
                reply_text = ""
                usage = {}

                # 兼容某些网关（如 OneAPI/New-API 默认流式或强制流式渠道）返回的 text/event-stream (SSE) 格式
                if "text/event-stream" in content_type or raw_text.startswith("data:"):
                    reply_text, usage = self._parse_sse_response(raw_text)
                else:
                    try:
                        data = resp.json()
                    except Exception as je:
                        raise RuntimeError(f"上游返回非标准 JSON 响应: {raw_text[:200]}") from je
                    
                    choices = data.get("choices", [])
                    tool_calls = None
                    if choices:
                        msg = choices[0].get("message", {})
                        reply_text = msg.get("content") or ""
                        tool_calls = msg.get("tool_calls")
                        # 兼容部分思考模型将答案放入 reasoning_content 或仅输出 reasoning
                        if not reply_text and msg.get("reasoning_content"):
                            reply_text = msg.get("reasoning_content") or ""
                    usage = data.get("usage", {})

                usage = data.get("usage", {}) if isinstance(data, dict) else {}
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

                stats_tracker.record_usage(
                    session_type=session_type,
                    target_id=target_id,
                    user_id=user_id,
                    model=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    latency_ms=latency_ms,
                    status="success",
                )
                return reply_text.strip(), {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "latency_ms": latency_ms,
                    "model": model_name,
                    "tool_calls": tool_calls,
                }
            except Exception as e:
                last_error = e
                print(f"[LLM Client] 第 {attempt + 1} 次请求大模型失败 ({model_name}): {e}")
                if attempt < max_retries:
                    import asyncio
                    await asyncio.sleep(1)
                else:
                    latency_ms = int((time.time() - start_time) * 1000)
                    if not isinstance(e, RuntimeError):
                        stats_tracker.record_usage(
                            session_type=session_type,
                            target_id=target_id,
                            user_id=user_id,
                            model=model_name,
                            prompt_tokens=0,
                            completion_tokens=0,
                            total_tokens=0,
                            latency_ms=latency_ms,
                            status="error",
                            error_message=str(e)[:300],
                        )
                    raise last_error

llm_client = LLMClient()
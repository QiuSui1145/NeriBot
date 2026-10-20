"""
主动回复决策引擎，通过 LLM 评估群聊流并决定是否插话
"""

import json
import re
import random
from pathlib import Path
from typing import Optional, Tuple

from src.config import config_manager
from src.context_manager import context_manager
from src.llm_client import llm_client
from src.prompting import load_decision_prompt


def parse_decision_response(reply_raw: str) -> Tuple[bool, float, str, str]:
    """强健的多层防御 JSON 决策结果解析器。
    支持去除思考标签、过滤 Markdown、自动修复尾随逗号与单引号，
    并在 JSON 格式不合规时通过正则降级提取关键字段，确保零崩溃。
    返回: (should_reply: bool, confidence: float, reason: str, suggested_topic: str)
    """
    if not reply_raw or not reply_raw.strip():
        return False, 0.0, "响应为空", ""

    text = reply_raw.strip()

    # 1. 过滤思考标签 <think>...</think>, <thought>...</thought>
    text = re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'<thought>[\s\S]*?</thought>', '', text, flags=re.IGNORECASE).strip()
    # 处理未闭合的思考标签：如果后面紧接着 JSON 对象（以 { 开头），仅截除思考头直到 {
    text = re.sub(r'<(?:think|thought)>[\s\S]*?(?=\{)', '', text, flags=re.IGNORECASE).strip()
    # 如果依然残留未闭合且无后续 JSON 的思考标签，截断尾部
    if not re.search(r'\{[\s\S]*\}', text):
        text = re.sub(r'<(?:think|thought)>[\s\S]*$', '', text, flags=re.IGNORECASE).strip()

    # 2. 尝试提取 ```json ... ``` 或最外层大括号
    m_block = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text, re.IGNORECASE)
    if m_block:
        candidate = m_block.group(1).strip()
    else:
        s_idx = text.find("{")
        e_idx = text.rfind("}")
        if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
            candidate = text[s_idx:e_idx+1].strip()
        else:
            candidate = text

    # 3. 规范化清洗候选 JSON 字符串
    cleaned = candidate
    # 去除 // 行注释 与 /* 块注释 */
    cleaned = re.sub(r'//[^\n]*', '', cleaned)
    cleaned = re.sub(r'/\*[\s\S]*?\*/', '', cleaned)
    # 修复常见尾随逗号: ,} -> } 或 ,] -> ]
    cleaned = re.sub(r',\s*([\]}])', r'\1', cleaned)
    # 修复 Python 布尔与空值
    cleaned = re.sub(r'\bTrue\b', 'true', cleaned)
    cleaned = re.sub(r'\bFalse\b', 'false', cleaned)
    cleaned = re.sub(r'\bNone\b', 'null', cleaned)

    # 尝试一: 直接标准 JSON 解析
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            should_reply = bool(data.get("should_reply", False))
            confidence = float(data.get("confidence", 0.0))
            reason = str(data.get("reason", "")).strip()
            topic = str(data.get("suggested_topic", "")).strip()
            return should_reply, confidence, reason, topic
    except Exception:
        pass

    # 尝试二: 单引号替换与弱修复解析
    try:
        fixed = cleaned.replace("'", '"')
        fixed = re.sub(r',\s*([\]}])', r'\1', fixed)
        data = json.loads(fixed)
        if isinstance(data, dict):
            should_reply = bool(data.get("should_reply", False))
            confidence = float(data.get("confidence", 0.0))
            reason = str(data.get("reason", "")).strip()
            topic = str(data.get("suggested_topic", "")).strip()
            return should_reply, confidence, reason, topic
    except Exception:
        pass

    # 尝试三: 正则终极保底提取（即使整个 JSON 语法严重破碎）
    # 提取 should_reply
    should_reply = False
    m_reply = re.search(r'(?:should_reply|回复|插话)["\']?\s*[:=：]\s*(true|false|1|0|True|False|是|否)', text, re.IGNORECASE)
    if m_reply:
        val = m_reply.group(1).lower()
        if val in ("true", "1", "是"):
            should_reply = True

    # 提取 confidence
    confidence = 0.0
    m_conf = re.search(r'(?:confidence|置信度)["\']?\s*[:=：]\s*([0-9]+(?:\.[0-9]+)?)', text, re.IGNORECASE)
    if m_conf:
        try:
            confidence = float(m_conf.group(1))
        except Exception:
            confidence = 0.0

    # 提取 reason
    reason = ""
    m_reason = re.search(r'(?:reason|理由|原因)["\']?\s*[:=：]\s*["\'“]?([^,"\'”\}\n\r]+)["\'”]?', text, re.IGNORECASE)
    if m_reason:
        reason = m_reason.group(1).strip()

    # 提取 suggested_topic
    topic = ""
    m_topic = re.search(r'(?:suggested_topic|话题|建议话题)["\']?\s*[:=：]\s*["\'“]?([^,"\'”\}\n\r]+)["\'”]?', text, re.IGNORECASE)
    if m_topic:
        topic = m_topic.group(1).strip()

    if m_reply or m_conf or reason:
        return should_reply, confidence, reason, topic

    return False, 0.0, "未能从决策模型输出解析出有效JSON", ""


class ActiveReplyEngine:
    def __init__(self, prompts_root: Path = Path("prompts")):
        self.prompts_root = prompts_root
        self._message_counters: dict[int, int] = {}

    def should_check_group(self, group_id: int) -> bool:
        cfg = config_manager.config.active_reply
        if not cfg.enabled:
            return False
        if group_id not in cfg.whitelist:
            return False
            
        if cfg.strategy == "probability":
            return random.random() < cfg.probability
            
        self._message_counters[group_id] = self._message_counters.get(group_id, 0) + 1
        if self._message_counters[group_id] >= cfg.frequency:
            self._message_counters[group_id] = 0
            return True
        return False

    async def evaluate(self, group_id: int) -> Tuple[bool, str]:
        cfg = config_manager.config.active_reply
        
        if cfg.strategy == "probability":
            return True, f"随机概率触发 (P={cfg.probability})"

        msgs = context_manager.get_unreplied_group_messages(group_id)
        if not msgs:
            msgs = getattr(context_manager, "unreplied_group_messages", {}).get(group_id, [])
        if not msgs:
            return False, "无近期聊天记录"

        lines = []
        for msg in msgs[-20:]:
            if isinstance(msg, dict):
                nick = msg.get("nickname") or msg.get("user_name") or str(msg.get("user_id", "群友"))
                content = msg.get("content", "")
            else:
                nick = getattr(msg, "user_name", getattr(msg, "nickname", "群友"))
                content = getattr(msg, "content", "")
            if content:
                lines.append(f"{nick}: {content}")
        if not lines:
            return False, "无有效群聊内容"
        chat_text = "\n".join(lines)

        decision_sys_prompt = load_decision_prompt(self.prompts_root)
        user_prompt = f"以下是群里近期的聊天记录：\n\n{chat_text}\n\n请严格按系统设定判断并只返回标准 JSON。直接以 {{ 开始你的输出，不要输出任何英文思考、分析过程或多余解释。"

        messages = [
            {"role": "system", "content": decision_sys_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            reply_raw, _ = await llm_client.chat_completion(
                messages=messages,
                session_type="group_decision",
                target_id=group_id,
                user_id=0,
                is_decision=True,
                max_tokens_override=600,
            )

            should_reply, confidence, reason, _ = parse_decision_response(reply_raw)
            if should_reply and confidence >= cfg.min_confidence:
                return True, reason
            return False, f"置信度不足或判定不回复 ({reason or f'置信度={confidence}'})"
        except Exception as e:
            return False, f"决策大模型异常: {e}"


active_reply_engine = ActiveReplyEngine()

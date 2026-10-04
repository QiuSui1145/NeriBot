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

            # 强健的 JSON 提取逻辑
            import re
            text = reply_raw.strip()
            # 过滤思考标签 <think>...</think>
            text = re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE).strip()
            # 尝试正则匹配 markdown 代码块
            m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
            if m:
                text = m.group(1)
            else:
                # 尝试直接匹配大括号内容
                m2 = re.search(r'\{.*\}', text, re.DOTALL)
                if m2:
                    text = m2.group(0)
            
            start_idx = text.find("{")
            end_idx = text.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = text[start_idx:end_idx+1]
                data = json.loads(json_str)
                should_reply = bool(data.get("should_reply", False))
                confidence = float(data.get("confidence", 0.0))
                reason = data.get("reason", "")
                if should_reply and confidence >= cfg.min_confidence:
                    return True, reason
                return False, f"置信度不足或判定不回复 ({reason})"
            print(f"[ActiveReply Debug] RAW: {reply_raw}")
            return False, "决策模型未返回标准JSON"
        except Exception as e:
            return False, f"决策大模型异常: {e}"


active_reply_engine = ActiveReplyEngine()

"""会话上下文与历史记忆多分支管理器。
支持单会话多上下文分支自由切换（/new 指令、/chatlist 指令）、持久化存储、滑动窗口压缩及多模态图文材料组装。
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

SESSIONS_STORAGE_PATH = Path("data/sessions_context.json")


class MessageItem:
    """单条消息单元，支持文本与多模态图片。"""

    def __init__(
        self,
        role: str,
        content: str,
        user_name: str = "",
        timestamp: Optional[float] = None,
        images: Optional[List[str]] = None,
    ):
        self.role = role  # "user" / "assistant" / "system"
        self.content = content
        self.user_name = user_name
        self.timestamp = timestamp or time.time()
        self.images: List[str] = images or []

    def to_dict(self, supports_vision: bool = False) -> dict:
        """根据模型是否支持识图组装消息体。在多人聊天场景下呈现说话人昵称，避免模型将多方对话混淆。"""
        text = self.content
        if self.role == "user" and self.user_name and not text.startswith(f"{self.user_name}:"):
            text = f"{self.user_name}: {text}"

        if supports_vision and self.images and self.role == "user":
            content_parts = []
            if text:
                content_parts.append({"type": "text", "text": text})
            for img_url in self.images:
                content_parts.append({"type": "image_url", "image_url": {"url": img_url}})
            return {"role": self.role, "content": content_parts}
        return {"role": self.role, "content": text}

    def serialize(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "user_name": self.user_name,
            "timestamp": self.timestamp,
            "images": self.images,
        }

    @classmethod
    def deserialize(cls, data: dict) -> "MessageItem":
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            user_name=data.get("user_name", ""),
            timestamp=data.get("timestamp"),
            images=data.get("images", []),
        )


class ContextBranch:
    """单个上下文分支。"""

    def __init__(
        self,
        branch_id: int,
        name: str = "",
        created_at: Optional[float] = None,
        history: Optional[List[MessageItem]] = None,
        rolling_summary: str = "",
    ):
        self.branch_id = branch_id
        self.name = name or f"上下文_{branch_id}"
        self.created_at = created_at or time.time()
        self.history: List[MessageItem] = history or []
        self.rolling_summary: str = rolling_summary

    def serialize(self) -> dict:
        return {
            "branch_id": self.branch_id,
            "name": self.name,
            "created_at": self.created_at,
            "rolling_summary": self.rolling_summary,
            "history": [msg.serialize() for msg in self.history],
        }

    @classmethod
    def deserialize(cls, data: dict) -> "ContextBranch":
        history = [MessageItem.deserialize(m) for m in data.get("history", [])]
        return cls(
            branch_id=data.get("branch_id", 1),
            name=data.get("name", "默认上下文"),
            created_at=data.get("created_at"),
            history=history,
            rolling_summary=data.get("rolling_summary", ""),
        )


class SessionContext:
    """会话上下文实例，支持多分支管理。"""

    def __init__(self, session_id: str, max_rounds: int = 12):
        self.session_id = session_id
        self.max_rounds = max_rounds
        self.branch_counter: int = 1
        self.active_branch_id: int = 1
        self.branches: Dict[int, ContextBranch] = {
            1: ContextBranch(branch_id=1, name="默认上下文", created_at=time.time())
        }
        self.last_active_time: float = time.time()
        self.unreplied_group_messages: List[dict] = []

    def get_active_branch(self) -> ContextBranch:
        if self.active_branch_id not in self.branches:
            if not self.branches:
                self.branches[1] = ContextBranch(branch_id=1, name="默认上下文")
                self.active_branch_id = 1
            else:
                self.active_branch_id = min(self.branches.keys())
        return self.branches[self.active_branch_id]

    @property
    def history(self) -> List[MessageItem]:
        return self.get_active_branch().history

    @property
    def rolling_summary(self) -> str:
        return self.get_active_branch().rolling_summary

    @rolling_summary.setter
    def rolling_summary(self, val: str):
        self.get_active_branch().rolling_summary = val

    def create_branch(self, name: str = "") -> ContextBranch:
        """创建全新的上下文分支并自动切换激活。"""
        self.branch_counter += 1
        new_id = self.branch_counter
        branch_name = name.strip() if name and name.strip() else f"上下文_{new_id}"
        new_branch = ContextBranch(branch_id=new_id, name=branch_name, created_at=time.time())
        self.branches[new_id] = new_branch
        self.active_branch_id = new_id
        self.last_active_time = time.time()
        return new_branch

    def switch_branch(self, identifier: Any) -> Optional[ContextBranch]:
        """按序号(ID)或分支名称切换上下文。"""
        # 1. 尝试匹配数字 ID
        id_str = str(identifier).strip()
        if id_str.isdigit():
            target_id = int(id_str)
            if target_id in self.branches:
                self.active_branch_id = target_id
                self.last_active_time = time.time()
                return self.branches[target_id]

        # 2. 尝试精确或模糊匹配名称
        query = id_str.lower()
        for b in self.branches.values():
            if b.name.lower() == query:
                self.active_branch_id = b.branch_id
                self.last_active_time = time.time()
                return b

        for b in self.branches.values():
            if query in b.name.lower():
                self.active_branch_id = b.branch_id
                self.last_active_time = time.time()
                return b

        return None

    def list_branches(self) -> List[dict]:
        """列出所有分支简报。"""
        res = []
        for b in sorted(self.branches.values(), key=lambda x: x.branch_id):
            res.append({
                "id": b.branch_id,
                "name": b.name,
                "created_at": b.created_at,
                "message_count": len(b.history),
                "is_active": (b.branch_id == self.active_branch_id),
            })
        return res

    def delete_branch(self, branch_id: int) -> bool:
        """删除指定分支。若只剩一个分支则只清空不删除。"""
        if branch_id not in self.branches:
            return False
        if len(self.branches) <= 1:
            self.branches[branch_id].history.clear()
            self.branches[branch_id].rolling_summary = ""
            return True

        del self.branches[branch_id]
        if self.active_branch_id == branch_id:
            self.active_branch_id = min(self.branches.keys())
        return True

    def add_message(
        self,
        role: str,
        content: str,
        user_name: str = "",
        images: Optional[List[str]] = None,
    ) -> List[MessageItem]:
        branch = self.get_active_branch()
        branch.history.append(MessageItem(role, content, user_name, images=images))
        self.last_active_time = time.time()
        if len(branch.history) > self.max_rounds * 2:
            return self._compact()
        return []

    def _compact(self) -> List[MessageItem]:
        """轻量级上下文截断与滑动窗口维护。返回被截断的历史供异步总结。"""
        branch = self.get_active_branch()
        keep_count = self.max_rounds
        if len(branch.history) <= keep_count:
            return []
        evicted = branch.history[:-keep_count]
        branch.history = branch.history[-keep_count:]
        return evicted

    def clear(self):
        """清空当前激活上下文分支的记忆。"""
        branch = self.get_active_branch()
        branch.history.clear()
        branch.rolling_summary = ""
        self.unreplied_group_messages.clear()
        self.last_active_time = time.time()

    def get_llm_messages(self, system_prompt: str, supports_vision: bool = False) -> List[dict]:
        """组装带系统提示词与历史记录的调用材料。"""
        branch = self.get_active_branch()
        messages = [{"role": "system", "content": system_prompt}]
        if branch.rolling_summary:
            messages.append({
                "role": "system",
                "content": f"【前期重要记忆摘要】：{branch.rolling_summary}",
            })
        merged_history: List[dict] = []
        for msg in branch.history:
            if msg.role not in ["user", "assistant", "system"]:
                continue
            item = msg.to_dict(supports_vision=supports_vision)
            # 合并连续的 user 消息轮次，使提示词契合大模型标准交替对话分布，杜绝连续user触发分析模式
            if merged_history and merged_history[-1]["role"] == "user" and item["role"] == "user":
                prev = merged_history[-1]
                prev_c = prev.get("content")
                curr_c = item.get("content")
                if isinstance(prev_c, str) and isinstance(curr_c, str):
                    prev["content"] = prev_c + "\n" + curr_c
                    continue
                elif isinstance(prev_c, list) and isinstance(curr_c, list):
                    prev["content"] = prev_c + curr_c
                    continue
                elif isinstance(prev_c, list) and isinstance(curr_c, str):
                    prev["content"].append({"type": "text", "text": curr_c})
                    continue
                elif isinstance(prev_c, str) and isinstance(curr_c, list):
                    prev["content"] = [{"type": "text", "text": prev_c}] + curr_c
                    continue
            merged_history.append(item)

        messages.extend(merged_history)
        return messages

    def serialize(self) -> dict:
        return {
            "session_id": self.session_id,
            "max_rounds": self.max_rounds,
            "branch_counter": self.branch_counter,
            "active_branch_id": self.active_branch_id,
            "branches": {str(k): v.serialize() for k, v in self.branches.items()},
            "last_active_time": self.last_active_time,
        }

    @classmethod
    def deserialize(cls, data: dict) -> "SessionContext":
        sess = cls(session_id=data.get("session_id", "default"), max_rounds=data.get("max_rounds", 12))
        sess.branch_counter = data.get("branch_counter", 1)
        sess.active_branch_id = data.get("active_branch_id", 1)
        branches = {}
        for k, bdata in data.get("branches", {}).items():
            b = ContextBranch.deserialize(bdata)
            branches[b.branch_id] = b
        if branches:
            sess.branches = branches
        sess.last_active_time = data.get("last_active_time", time.time())
        return sess


class ContextManager:
    """全局会话管理器，提供内存管理与自动持久化存储。"""

    def __init__(self, storage_path: Path = SESSIONS_STORAGE_PATH):
        self.storage_path = storage_path
        self.sessions: Dict[str, SessionContext] = {}
        self._load()

    def _load(self):
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                for sid, sdata in data.items():
                    self.sessions[sid] = SessionContext.deserialize(sdata)
            except Exception as e:
                print(f"[ContextManager] 加载会话历史数据失败: {e}")

    def save(self):
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {sid: sess.serialize() for sid, sess in self.sessions.items()}
            self.storage_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[ContextManager] 保存会话历史数据失败: {e}")

    def get_session(self, session_type: str, target_id: int) -> SessionContext:
        key = f"{session_type}_{target_id}"
        if key not in self.sessions:
            self.sessions[key] = SessionContext(key)
        return self.sessions[key]

    def reset_session(self, session_type: str, target_id: int) -> None:
        key = f"{session_type}_{target_id}"
        if key in self.sessions:
            self.sessions[key].clear()
            self.save()

    def record_group_chatter(self, group_id: int, user_id: int, nickname: str, content: str):
        """记录群聊中群友发言，供决策模型分析语境。"""
        sess = self.get_session("group", group_id)
        sess.unreplied_group_messages.append({
            "user_id": user_id,
            "nickname": nickname or str(user_id),
            "content": content,
            "time": time.time(),
        })
        if len(sess.unreplied_group_messages) > 15:
            sess.unreplied_group_messages = sess.unreplied_group_messages[-15:]

    @property
    def unreplied_group_messages(self) -> Dict[int, List[dict]]:
        """向后兼容属性字典：返回所有群聊未回复发言。"""
        result = {}
        for key, sess in self.sessions.items():
            if key.startswith("group_"):
                try:
                    gid = int(key.split("_")[1])
                    result[gid] = sess.unreplied_group_messages
                except (ValueError, IndexError):
                    pass
        return result

    def get_unreplied_group_messages(self, group_id: int) -> List[dict]:
        """获取指定群未回复的消息列表。"""
        sess = self.get_session("group", group_id)
        return list(sess.unreplied_group_messages)

    def clear_unreplied_group_messages(self, group_id: int) -> None:
        """清空指定群未回复的消息列表。"""
        sess = self.get_session("group", group_id)
        sess.unreplied_group_messages.clear()


context_manager = ContextManager()

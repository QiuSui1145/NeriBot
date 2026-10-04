"""轻量 SQLite 记忆系统驱动插件实现。
实现 BaseMemoryDriver，展示完全不同于 ChromaDB 的第二种独立记忆存储架构。
"""

import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional
import uuid

from src.plugins.base import BasePlugin
from src.plugins.memory.base import BaseMemoryDriver


class SQLiteMemoryDriver(BaseMemoryDriver):
    """基于轻量级 SQLite 的记忆驱动实现。"""

    def __init__(self, db_path: Path):
        super().__init__(
            driver_id="sqlite_fts",
            display_name="SQLite 轻量关系型记忆引擎 (免Torch极速)",
            description="基于 Python 原生 SQLite3，纯本地零依赖，轻巧快速且便于跨平台备份",
        )
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    target_id TEXT,
                    content TEXT,
                    type TEXT,
                    importance REAL,
                    created_at REAL,
                    last_accessed REAL,
                    access_count INTEGER,
                    is_forgotten INTEGER
                )
                """
            )
            conn.commit()

    async def search_memories(
        self, session_id: str, query: str, top_k: int = 2
    ) -> List[str]:
        # 中英文自适应关键词检索切分
        q = query.strip()
        tokens = []
        if " " in q:
            tokens.extend([t.strip() for t in q.split() if len(t.strip()) > 1])
        else:
            # 针对中文自然语言切分 2-gram 关键词片段
            if len(q) >= 2:
                tokens.extend([q[i : i + 2] for i in range(len(q) - 1)])
            elif q:
                tokens.append(q)

        results = []
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if tokens:
                # 构造模糊匹配条件
                clauses = " OR ".join(["content LIKE ?"] * len(tokens))
                params = [f"%{t}%" for t in tokens]
                sql = f"""
                    SELECT id, content, importance, created_at, access_count 
                    FROM memories 
                    WHERE is_forgotten = 0 AND ({clauses})
                    ORDER BY importance DESC, created_at DESC 
                    LIMIT ?
                """
                rows = cursor.execute(sql, (*params, top_k)).fetchall()
            else:
                sql = """
                    SELECT id, content, importance, created_at, access_count 
                    FROM memories 
                    WHERE is_forgotten = 0
                    ORDER BY importance DESC, created_at DESC 
                    LIMIT ?
                """
                rows = cursor.execute(sql, (top_k,)).fetchall()

            for r in rows:
                results.append(r["content"])
                # 累加命中频次
                cursor.execute(
                    "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                    (time.time(), r["id"]),
                )
            conn.commit()
        return results

    async def add_memory(
        self,
        session_id: str,
        content: str,
        importance: float = 1.0,
        mem_type: str = "episode",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        mem_id = f"mem_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO memories (id, target_id, content, type, importance, created_at, last_accessed, access_count, is_forgotten)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)
                """,
                (mem_id, str(session_id), content, mem_type, importance, now, now),
            )
            conn.commit()
        return mem_id

    async def forget_memory(self, memory_id: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE memories SET is_forgotten = 1 WHERE id = ?", (memory_id,))
            conn.commit()
            return cur.rowcount > 0

    async def list_memories(
        self,
        session_id: Optional[str] = None,
        mem_type: Optional[str] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            where_parts = ["is_forgotten = 0"]
            params = []
            if mem_type:
                where_parts.append("type = ?")
                params.append(mem_type)
            if query:
                where_parts.append("content LIKE ?")
                params.append(f"%{query}%")

            where_sql = " AND ".join(where_parts)
            cur = conn.cursor()
            total = cur.execute(f"SELECT COUNT(*) FROM memories WHERE {where_sql}", params).fetchone()[0]

            offset = (page - 1) * page_size
            sql = f"SELECT * FROM memories WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?"
            rows = cur.execute(sql, (*params, page_size, offset)).fetchall()

            items = [dict(r) for r in rows]
            return {"total": total, "page": page, "page_size": page_size, "items": items}

    async def get_timeline(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM memories WHERE is_forgotten = 0 ORDER BY created_at ASC LIMIT 100"
            ).fetchall()
            return [dict(r) for r in rows]

    async def get_graph(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        # 为 SQLite 记忆快速生成知识拓扑节点
        nodes = []
        edges = []
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT id, content, type FROM memories WHERE is_forgotten = 0 LIMIT 50").fetchall()
            for r in rows:
                nodes.append({
                    "id": r["id"],
                    "label": r["content"][:15] + "...",
                    "group": r["type"],
                    "title": r["content"],
                })
        return {"nodes": nodes, "edges": edges}

    async def factory_reset(self) -> bool:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM memories")
            conn.commit()
        return True

    async def export_data(self) -> bytes:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM memories").fetchall()
            data = [dict(r) for r in rows]
            return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    async def get_status(self) -> Dict[str, Any]:
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM memories WHERE is_forgotten = 0").fetchone()[0]
            total_all = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            return {
                "driver": "sqlite_fts",
                "total_active_memories": total,
                "grand_total_memories": total_all,
                "db_path": str(self.db_path),
                "healthy": True,
            }


class MemorySQLitePlugin(BasePlugin):
    """SQLite 记忆插件主入口。"""

    async def on_load(self) -> bool:
        db_file = self.context.data_dir / "memories.db"
        driver = SQLiteMemoryDriver(db_path=db_file)
        self.register_memory_driver(driver)
        return True

    async def on_enable(self) -> None:
        self.context.logger.info("SQLite 记忆驱动已成功就绪，可在 WebUI 或配置中切换激活！")

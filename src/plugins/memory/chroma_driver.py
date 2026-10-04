"""默认 ChromaDB + 本地 BGE 向量记忆系统驱动实现。
无缝桥接现有的 vector_store.py 引擎，保持知识图谱、时间线和语义检索无损。
"""

from typing import Any, Dict, List, Optional
from src.memory.vector_store import vector_store
from src.plugins.memory.base import BaseMemoryDriver


class ChromaVectorMemoryDriver(BaseMemoryDriver):
    """基于 ChromaDB 与 BGE Embedding 的默认向量记忆驱动。"""

    def __init__(self):
        super().__init__(
            driver_id="chroma_default",
            display_name="ChromaDB 向量深度记忆引擎 (默认内置)",
            description="基于本地离线 BGE-small-zh 嵌入模型与持久化 ChromaDB 的高性能语义联想记忆库",
        )

    async def search_memories(
        self, session_id: str, query: str, top_k: int = 2
    ) -> List[str]:
        # vector_store 内部支持数字与字符串 target_id
        target = int(session_id) if str(session_id).isdigit() else 0
        return vector_store.search_relevant_memories(target, query=query, top_k=top_k)

    async def add_memory(
        self,
        session_id: str,
        content: str,
        importance: float = 1.0,
        mem_type: str = "episode",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        target = int(session_id) if str(session_id).isdigit() else 0
        return vector_store.add_memory(target, content=content, importance=importance, mem_type=mem_type)

    async def forget_memory(self, memory_id: str) -> bool:
        return vector_store.forget_memory(memory_id)

    async def list_memories(
        self,
        session_id: Optional[str] = None,
        mem_type: Optional[str] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        target = int(session_id) if session_id and str(session_id).isdigit() else None
        return vector_store.list_memories(
            target_id=target, mem_type=mem_type, query=query, page=page, page_size=page_size
        )

    async def get_timeline(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        target = int(session_id) if session_id and str(session_id).isdigit() else None
        return vector_store.get_memory_timeline(target_id=target)

    async def get_graph(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        target = int(session_id) if session_id and str(session_id).isdigit() else None
        return vector_store.get_memory_graph(target_id=target)

    async def factory_reset(self) -> bool:
        return vector_store.factory_reset()

    async def export_data(self) -> bytes:
        return vector_store.export_data()

    async def get_status(self) -> Dict[str, Any]:
        return vector_store.get_status()

    async def self_test(self) -> Dict[str, Any]:
        return vector_store.run_self_test()


chroma_default_memory_driver = ChromaVectorMemoryDriver()

"""可插拔记忆系统驱动抽象基类 (BaseMemoryDriver) 与统一数据模型。
支持任意异构记忆架构（ChromaDB向量库、Mem0、GraphRAG、SQLite-FTS、Neo4j、本地 Markdown 库等）。
"""

from abc import ABC, abstractmethod
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class MemoryFragment(BaseModel):
    """标准化单条记忆片段对象。"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(..., description="记忆唯一ID")
    content: str = Field(..., description="记忆陈述内容")
    type: str = Field(default="episode", description="类型: fact (事实/偏好), episode (事件/经历), archive (归档)")
    importance: float = Field(default=1.0, description="重要度权重 (1.0~5.0)")
    created_at: float = Field(default_factory=time.time, description="创建时间戳")
    last_accessed: float = Field(default_factory=time.time, description="最后一次被检索命中时间戳")
    access_count: int = Field(default=0, description="被检索命中次数")
    is_forgotten: bool = Field(default=False, description="是否已被淡化/遗忘")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="驱动专属扩展元数据")


class BaseMemoryDriver(ABC):
    """可插拔记忆系统驱动抽象基类。"""

    def __init__(self, driver_id: str, display_name: str, description: str = ""):
        self.driver_id = driver_id
        self.display_name = display_name
        self.description = description

    @abstractmethod
    async def search_memories(
        self, session_id: str, query: str, top_k: int = 2
    ) -> List[str]:
        """
        根据用户输入检索最相关的长期/深层记忆片段。
        返回字符串列表，将被无缝注入到当前 LLM System Prompt 中。
        """
        pass

    @abstractmethod
    async def add_memory(
        self,
        session_id: str,
        content: str,
        importance: float = 1.0,
        mem_type: str = "episode",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """存储单条新记忆，返回生成的记忆ID。"""
        pass

    @abstractmethod
    async def forget_memory(self, memory_id: str) -> bool:
        """根据 ID 标记遗忘或彻底删除指定记忆。"""
        pass

    @abstractmethod
    async def list_memories(
        self,
        session_id: Optional[str] = None,
        mem_type: Optional[str] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """按类型、关键词分页查询记忆列表供 WebUI 列表展示。"""
        pass

    @abstractmethod
    async def get_timeline(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取结构化记忆时间线数据供 WebUI 时间轴展示。"""
        pass

    @abstractmethod
    async def get_graph(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """获取知识图谱节点与连线数据 (nodes, edges) 供 WebUI 3D/2D 图谱展示。"""
        pass

    @abstractmethod
    async def factory_reset(self) -> bool:
        """擦除全部记忆数据，恢复至出厂设置。"""
        pass

    @abstractmethod
    async def export_data(self) -> bytes:
        """全量导出记忆库数据包 (Zip 字节流或 JSON 字符串)。"""
        pass

    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """获取该驱动的运行状态、存储条数、底层引擎状态等诊断指标。"""
        pass

    async def self_test(self) -> Dict[str, Any]:
        """驱动自检逻辑，默认执行简单读写验证。"""
        return {"status": "ok", "message": f"{self.display_name} 运行正常"}

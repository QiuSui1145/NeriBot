"""向 ChromaDB 向量记忆库永久固化写入《星空列车与白的旅行》全 17 章节全真核心编年史记忆。
支持针对 Master QQ 以及全局索引 (0) 写入高权重 (importance=5.0)、不可磨灭 (is_immutable=True) 的核心正史记忆。
"""

import sys
import os

# 确保项目根目录在 sys.path 中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.memory.vector_store import vector_store, CANON_MEMORIES

def seed_memories():
    print(f"==================================================")
    print(f" 开始固化注入《星空列车与白的旅行》全 {len(CANON_MEMORIES)} 章节全真核心记忆...")
    print(f"==================================================")
    
    total_injected = vector_store.seed_canon_memories(force_reseed=True)
    
    print(f"\n[OK] 原作全 17 章核心编年史记忆全部固化写入完毕！共注入/更新 {total_injected} 条核心正史记忆。")

if __name__ == "__main__":
    seed_memories()

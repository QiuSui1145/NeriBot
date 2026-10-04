import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.memory.vector_store import vector_store

vector_store.add_memory(999, "钟城晓(哥哥)最喜欢吃煎蛋卷了！", 5.0, "fact")
vector_store.add_memory(999, "今天天气真好，去散步了。", 1.0, "episode")

res = vector_store.search_relevant_memories(999, "哥哥喜欢吃什么？", top_k=1)
print(f"Retrieved: {res}")

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.context_manager import context_manager
from src.bot_service import bot_service
from src.config import config_manager
import time

async def main():
    session_type = "private"
    target_id = 999
    
    # 获取测试会话
    sess = context_manager.get_session(session_type, target_id)
    sess.clear()
    
    # 模拟快速添加 25 条消息（假设 max_rounds 为 12，2*12=24）
    print("Adding 24 messages...")
    for i in range(24):
        sess.add_message("user", f"这是测试消息 {i}")
        
    print(f"Current history length: {len(sess.history)}")
    
    # 再加 1 条，触发压缩
    print("Adding 25th message to trigger eviction...")
    evicted_user = sess.add_message("user", "这是测试消息 24，应该触发压缩")
    evicted_assistant = sess.add_message("assistant", "收到，开始压缩。")
    
    evicted_all = evicted_user + evicted_assistant
    if evicted_all:
        print(f"Evicted {len(evicted_all)} messages. Triggering async summarize...")
        await bot_service._summarize_context_async(session_type, target_id, evicted_all)
        
    print(f"New history length: {len(sess.history)}")
    print(f"Summary generated: {sess.rolling_summary[:100]}...")

if __name__ == "__main__":
    asyncio.run(main())

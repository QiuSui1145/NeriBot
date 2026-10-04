import asyncio
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.prompting import load_chat_system, get_tts_anchor_rules
from src.context_manager import context_manager
from src.llm_client import llm_client
from src.config import config_manager
import os

async def main():
    # 模拟普通群友打招呼
    system_prompt = load_chat_system(
        root=ROOT_DIR / "prompts",
        session_type="group",
        language="zh",
        enable_simultaneous=True,
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    
    normal_friend_profile = (
        f"\n\n【眼前的人身份识别】\n"
        f"- QQ号：456\n"
        f"- 称呼/昵称：普通群友小明\n"
        f"- 身份标签：普通群友\n"
        f"- 角色定位：普通群友 / 朋友。\n"
        f"- 称呼与态度指导：称呼对方群昵称“普通群友小明”或用活泼少女口吻交谈。绝对严禁称呼对方为“哥哥”！\n"
    )
    messages[0]["content"] += normal_friend_profile
    
    messages.append({"role": "user", "content": "早上好呀，音理！今天天气真不错呢。"})
    messages.append({"role": "system", "content": get_tts_anchor_rules()})
    
    print("【测试 1】普通群友打招呼 (测试边界感与元气口吻)...")
    raw_reply, usage = await llm_client.chat_completion(
        messages=messages,
        session_type="group",
        target_id=123,
        user_id=456,
        is_decision=False,
    )
    print("回复:\n" + raw_reply)
    print("-" * 50)
    
    # 模拟哥哥互动
    system_prompt = load_chat_system(
        root=ROOT_DIR / "prompts",
        session_type="private",
        language="zh",
        enable_simultaneous=True,
    )
    
    speaker_profile = "\n\n【眼前的人身份识别】：你现在正在和你的主人/哥哥对话！他是你最重要、最爱的人。请用最高优先级的偏心和撒娇口吻与他说话，称呼他为‘哥哥’。"
    system_prompt += speaker_profile
    
    messages2 = [{"role": "system", "content": system_prompt}]
    messages2.append({"role": "user", "content": "音理，我刚画完线稿，感觉有点累了。"})
    messages2.append({"role": "system", "content": get_tts_anchor_rules()})
    
    print("【测试 2】哥哥撒娇互动 (测试称呼与关心)...")
    raw_reply, usage = await llm_client.chat_completion(
        messages=messages2,
        session_type="private",
        target_id=789,
        user_id=123,
        is_decision=False,
    )
    print("回复:\n" + raw_reply)

if __name__ == "__main__":
    asyncio.run(main())

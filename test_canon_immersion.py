"""测试音理全真沉浸人设输出，模拟与哥哥（钟城晓）的对话，检验是否彻底杜绝说书人童话腔，展现亲历羁绊。"""

import asyncio
import os
import sys

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.prompting import load_chat_system, get_tts_anchor_rules
from src.bot_service import bot_service
from src.llm_client import llm_client
from pathlib import Path

async def test_dialogue():
    prompts_root = Path("prompts")
    system_prompt = load_chat_system(
        root=prompts_root,
        session_type="private",
        language="zh",
        enable_simultaneous=False,
    )
    
    # 注入哥哥档案
    speaker_profile, is_master = bot_service.build_speaker_profile(10001, "哥哥")
    system_prompt += speaker_profile
    
    test_queries = [
        "音理，我好无聊啊，给我讲个故事听听呗。",
        "今天分镜又被退稿了，感觉自己好没用……",
        "真白现在身体怎么样了？",
        "今晚吃炸鸡配冰啤酒，爽翻了！"
    ]
    
    print("=" * 60)
    print("【开始音理全真沉浸测试】")
    print(f"System Prompt 总字符数: {len(system_prompt)}")
    print("=" * 60)
    
    from src.plugins.manager import plugin_manager
    from src.plugins.memory.chroma_driver import chroma_default_memory_driver
    plugin_manager.register_memory_driver(chroma_default_memory_driver)
    active_mem_driver = plugin_manager.get_active_memory_driver()
    
    for query in test_queries:
        print(f"\n[用户/哥哥输入]: {query}")
        
        # 召回核心记忆
        cur_sys = system_prompt
        retrieved = await active_mem_driver.search_memories("10001", query=query, top_k=2)
        if retrieved:
            mem_str = "\n".join([f"- {m}" for m in retrieved])
            cur_sys += f"\n\n【脑海中闪回的深层记忆片段】\n{mem_str}"
            
        messages = [
            {"role": "system", "content": cur_sys},
            {"role": "user", "content": query},
            {"role": "system", "content": get_tts_anchor_rules()}
        ]
        
        reply, usage = await llm_client.chat_completion(
            messages=messages,
            session_type="private",
            target_id=10001,
            user_id=10001,
            is_decision=False,
        )
        
        print(f"[音理回复]: {reply}")
        print(f"[Token消耗]: Prompt={usage.get('prompt_tokens', 0)}, Completion={usage.get('completion_tokens', 0)}")
        
        # 检验红线
        bad_phrases = ["我给哥哥讲星空列车的故事好不好", "有一列银色的车厢", "传说中有一列", "银色的车厢划过银河"]
        has_bad = any(bp in reply for bp in bad_phrases)
        if has_bad:
            print("  ❌ [警告] 包含第三方童话腔！")
        else:
            print("  ✅ [通过] 未触发童话说书人腔调，还原真实羁绊！")

if __name__ == "__main__":
    asyncio.run(test_dialogue())

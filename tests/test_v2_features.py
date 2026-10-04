"""测试 V2 功能：群聊/私聊提示词动态切换、说话者身份识别与档案、群聊日志持久化、WebSocket配置"""
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.config import config_manager, IdentityBinding
from src.prompting import load_chat_system
from src.statistics import stats_tracker
from src.bot_service import BotService

def test_all():
    print("[1] 测试配置加载...")
    cfg = config_manager.config
    print(f"  Bot Name: {cfg.onebot.nickname}")
    print(f"  OneBot Mode: {cfg.onebot.mode}")
    print(f"  Forward WS URL: {cfg.onebot.forward_ws_url}")
    print(f"  Master QQ: {cfg.security.master_qq}")
    print(f"  Admin List: {cfg.security.admin_list}")

    print("\n[2] 测试群聊/私聊动态提示词加载...")
    prompts_dir = ROOT_DIR / "prompts"
    group_prompt = load_chat_system(prompts_dir, session_type="group")
    private_prompt = load_chat_system(prompts_dir, session_type="private")

    assert "群聊特定场景交互规范" in group_prompt, "群聊提示词缺失群聊规范"
    assert "私聊特定场景交互规范" in private_prompt, "私聊提示词缺失私聊规范"
    assert "群聊特定场景交互规范" not in private_prompt, "私聊提示词中不应出现群聊规范"
    assert "私聊特定场景交互规范" not in group_prompt, "群聊提示词中不应出现私聊规范"
    print(f"  群聊提示词长度: {len(group_prompt)} 字符 (校验通过)")
    print(f"  私聊提示词长度: {len(private_prompt)} 字符 (校验通过)")

    print("\n[3] 测试说话者人物识别与身份档案生成...")
    bot = BotService(prompts_dir)
    
    # 模拟普通群友
    prof_user, is_master_user = bot.build_speaker_profile(999999, "路人群友小张")
    assert not is_master_user, "普通群友不应该判定为Master"
    assert "【普通群友 / 朋友】" in prof_user
    assert "绝对严禁对对方叫“哥哥”" in prof_user
    assert "路人群友小张" in prof_user
    print("  普通群友识别与严禁叫哥哥规则: 校验通过")

    # 模拟管理员/主人
    cfg.security.admin_list = [10001]
    prof_admin, is_master_admin = bot.build_speaker_profile(10001, "晓哥")
    assert is_master_admin, "管理员应该判定为Master"
    assert "【主人 / 哥哥（钟城 晓）】" in prof_admin
    assert "必须称呼对方为“哥哥”" in prof_admin
    print("  管理员识别为主人/哥哥规则: 校验通过")

    # 模拟自定义身份绑定 (非Master)
    cfg.security.identity_bindings.append(
        IdentityBinding(
            qq=888888,
            nickname="小野",
            identity_tag="美术社同学 / 漫画助手",
            custom_notes="经常跟音理借画画工具，喜欢吃布丁",
            is_master=False
        )
    )
    prof_custom, is_master_custom = bot.build_speaker_profile(888888, "小野")
    assert not is_master_custom
    assert "美术社同学 / 漫画助手" in prof_custom
    assert "经常跟音理借画画工具" in prof_custom
    assert "小野" in prof_custom
    print("  自定义身份绑定识别档案: 校验通过")

    print("\n[4] 测试白名单群聊日志记录与检索...")
    test_group = 123456789
    stats_tracker.record_group_message(
        group_id=test_group,
        group_name="星轨列车测试群",
        user_id=888888,
        nickname="小野",
        raw_message="音理，今天社团集合吗？"
    )
    logs = stats_tracker.get_group_messages(test_group, limit=5)
    assert len(logs) > 0, "未能检索到刚刚写入的群聊日志"
    last_log = logs[0]
    assert last_log["user_id"] == 888888
    assert last_log["raw_message"] == "音理，今天社团集合吗？"
    print(f"  群日志记录检索成功: [{last_log['nickname']}] {last_log['raw_message']}")

    # 更新回复
    stats_tracker.update_group_message_reply(last_log["id"], "嗯！放学后在老画室见哦~")
    updated_logs = stats_tracker.get_group_messages(test_group, limit=1)
    assert updated_logs[0]["bot_reply_content"] == "嗯！放学后在老画室见哦~"
    print(f"  群日志回复回填成功: {updated_logs[0]['bot_reply_content']}")

    print("\n==========================================")
    print("ALL V2 UNIT & INTEGRATION TESTS PASSED!")
    print("==========================================")

if __name__ == "__main__":
    test_all()

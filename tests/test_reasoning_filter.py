"""
测试思维链路、分析思路与思考标签拦截与净化机制。
验证大模型在主动回复或常规对话中泄露思考分析时的多层防御策略。
"""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.tts_client import tts_client


class TestReasoningFilter(unittest.TestCase):
    def setUp(self):
        # 真实线上 ID 1734 事故样本
        self.incident_sample_1734 = (
            "用户发送了一系列消息，看起来是在群聊中。让我分析一下上下文：\n\n"
            "1. 用户说\"心理有点精神问题，再加上有点纠结，暂时走了\" - 似乎要离开群聊\n"
            "2. 发送了几张图片\n"
            "3. \"过意不去，所以回来了\" - 回来了\n"
            "4. \"回来挨炒了\" - 回来被骂/调侃了\n"
            "5. 又发送了几张图片\n\n"
            "系统提示让我结合群友聊天内容，自然地插话参与，进行一句简短可爱的吐槽或回复。\n\n"
            "作为音理，我是元气开朗的邻家少女，面对普通群友，我会用"
        )
        # 真实线上 ID 2166 事故样本
        self.incident_sample_2166 = (
            "用户在群聊中分享了《我的世界》服务器的残存影像，展示了一个还原《巧可甜恋》中 Setaria 咖啡馆的建筑。"
            "其他人对此表示赞叹或提及燃尽感。作为音理，我需要以普通群友的身份自然地插话参与，进行一句简短可爱的吐槽或接话，"
            "不能叫哥哥，语气要元气开朗。我可以夸赞这个建筑还原得很棒，或者顺着 MaoyuQWQ 说的'建完燃尽'来一句调侃。"
        )

    def test_strip_thinking_tags(self):
        # 闭合 think 标签
        raw1 = "<think>这是思考过程\n分析上下文</think>[TEXT]你好呀！[/TEXT]"
        self.assertEqual(tts_client.strip_thinking_and_analysis(raw1), "[TEXT]你好呀！[/TEXT]")

        # 未闭合 think 标签 (截断情况)
        raw2 = "<think>由于达到 max_tokens 未闭合的思考内容..."
        self.assertEqual(tts_client.strip_thinking_and_analysis(raw2), "")

        # thought 标签
        raw3 = "<thought>内部思考过程</thought>音理在呢！"
        self.assertEqual(tts_client.strip_thinking_and_analysis(raw3), "音理在呢！")

        # markdown 代码块思考
        raw4 = "```thought\n这是思维链\n```[TEXT]哥哥快去休息！[/TEXT]"
        self.assertEqual(tts_client.strip_thinking_and_analysis(raw4), "[TEXT]哥哥快去休息！[/TEXT]")

    def test_incident_sample_detection(self):
        # 必须能够准确识别出 ID 1734 与 ID 2166 的分析思路泄露
        self.assertTrue(tts_client.is_pure_reasoning_or_analysis(self.incident_sample_1734))
        self.assertTrue(tts_client.is_pure_reasoning_or_analysis(self.incident_sample_2166))

        # 变体分析思路
        self.assertTrue(tts_client.is_pure_reasoning_or_analysis("让我分析一下群友在聊什么。从上下文来看，大家都在讨论宵夜。"))
        self.assertTrue(tts_client.is_pure_reasoning_or_analysis("系统提示让我回复群友。角色设定：音理需要元气回复。"))
        self.assertTrue(tts_client.is_pure_reasoning_or_analysis("Thinking Process:\n1. User said hello\n2. Reply politely"))
        self.assertTrue(tts_client.is_pure_reasoning_or_analysis("As Neri, I need to respond to the group chat."))

        # 正常台词绝不能被误判
        self.assertFalse(tts_client.is_pure_reasoning_or_analysis("你们在聊什么好吃的呀？音理也想吃！"))
        self.assertFalse(tts_client.is_pure_reasoning_or_analysis("哥哥辛苦啦，今天画室的工作顺利吗？"))
        self.assertFalse(tts_client.is_pure_reasoning_or_analysis("哼，笨蛋晓又在偷偷熬夜了！快去睡觉！"))

    def test_parse_dual_track_prevention(self):
        # 事故样本无标签 -> 必须完全拦截并返回空文本
        disp1, voice1 = tts_client.parse_dual_track(self.incident_sample_1734)
        self.assertEqual(disp1, "")
        self.assertEqual(voice1, "")

        disp2, voice2 = tts_client.parse_dual_track(self.incident_sample_2166)
        self.assertEqual(disp2, "")
        self.assertEqual(voice2, "")

        # 前置分析 + 正式标签 -> 必须丢弃所有前置分析，只提取标签内台词
        mixed_sample = (
            "用户在讨论周末去哪玩。让我分析一下，作为音理我应该表现出好奇。\n"
            "[TEXT]周末去游乐园怎么样？音理也想坐摩天轮！[/TEXT]"
            "[VOICE]週末に遊園地はどうかな？観覧車に乗りたいな！[/VOICE]"
        )
        disp3, voice3 = tts_client.parse_dual_track(mixed_sample)
        self.assertEqual(disp3, "周末去游乐园怎么样？音理也想坐摩天轮！")
        self.assertIn("遊園地", voice3)
        self.assertNotIn("分析", disp3)
        self.assertNotIn("用户", disp3)

    def test_clean_text_safety(self):
        # 事故样本清洗后变为空字符串
        self.assertEqual(tts_client._clean_text(self.incident_sample_1734), "")
        self.assertEqual(tts_client._clean_text(self.incident_sample_2166), "")

        # 正常台词清洗正常
        cleaned_normal = tts_client._clean_text("（拉开窗帘）今天的天气真好呀！✨")
        self.assertEqual(cleaned_normal, "今天的天气真好呀！")


from unittest.mock import patch, AsyncMock
from src.bot_service import bot_service
from src.context_manager import context_manager


class TestBotServiceInterception(unittest.IsolatedAsyncioTestCase):
    async def test_active_reply_reasoning_silently_aborted(self):
        # 模拟主动回复时，LLM 返回了事故分析样本
        incident_sample = (
            "用户发送了一系列消息，看起来是在群聊中。让我分析一下上下文：\n\n"
            "1. 用户说... \n"
            "系统提示让我结合群友聊天内容，自然地插话参与。\n"
            "作为音理，我是元气开朗的邻家少女，面对普通群友，我会用"
        )
        test_group = 999888
        sess = context_manager.get_session("group", test_group)
        sess.clear()

        dispatched_messages = []
        async def mock_dispatch(*args, **kwargs):
            dispatched_messages.append((args, kwargs))

        with patch("src.llm_client.llm_client.chat_completion", new=AsyncMock(return_value=(incident_sample, {}))), \
             patch.object(bot_service, "_dispatch_output", new=mock_dispatch):
            await bot_service._process_chat(
                session_type="group",
                target_id=test_group,
                user_id=123,
                nickname="群友小张",
                user_text="大家都在聊什么",
                message_type="group",
                is_active_reply=True,
            )

        # 验证：1. 没有外发任何消息
        self.assertEqual(len(dispatched_messages), 0)
        # 验证：2. 助手历史中没有将事故样本作为 assistant 回复存入
        history = sess.history
        assistant_msgs = [m for m in history if m.role == "assistant"]
        self.assertEqual(len(assistant_msgs), 0)
        # 验证：3. 记录了 planner 的拦截日志
        planner_msgs = [m for m in history if m.role == "planner"]
        self.assertTrue(any("静默拦截" in m.content for m in planner_msgs))

    async def test_active_reply_incident_2166_silently_aborted(self):
        # 模拟主动回复时，LLM 返回了 ID 2166 事故样本 (无 [TEXT] 标签且包含大量分析)
        sample_2166 = (
            "用户在群聊中分享了《我的世界》服务器的残存影像，展示了一个还原《巧可甜恋》中 Setaria 咖啡馆的建筑。"
            "其他人对此表示赞叹或提及燃尽感。作为音理，我需要以普通群友的身份自然地插话参与，进行一句简短可爱的吐槽或接话，"
            "不能叫哥哥，语气要元气开朗。我可以夸赞这个建筑还原得很棒，或者顺着 MaoyuQWQ 说的'建完燃尽'来一句调侃。"
        )
        test_group = 888777
        sess = context_manager.get_session("group", test_group)
        sess.clear()

        dispatched_messages = []
        async def mock_dispatch(*args, **kwargs):
            dispatched_messages.append((args, kwargs))

        with patch("src.llm_client.llm_client.chat_completion", new=AsyncMock(return_value=(sample_2166, {}))), \
             patch.object(bot_service, "_dispatch_output", new=mock_dispatch):
            await bot_service._process_chat(
                session_type="group",
                target_id=test_group,
                user_id=123,
                nickname="MaoyuQWQ",
                user_text="[图片] 建完燃尽了",
                message_type="group",
                is_active_reply=True,
            )

        # 绝对红线拦截：由于缺少 [TEXT] 且为分析内容，绝对不外发任何消息！
        self.assertEqual(len(dispatched_messages), 0)
        history = sess.history
        assistant_msgs = [m for m in history if m.role == "assistant"]
        self.assertEqual(len(assistant_msgs), 0)
        planner_msgs = [m for m in history if m.role == "planner"]
        self.assertTrue(any("已静默拦截" in m.content for m in planner_msgs))

    async def test_user_chat_reasoning_fallback(self):
        # 模拟普通用户@机器人时，LLM 输出纯分析，系统自动兜底为可爱台词，绝不输出分析思路
        incident_sample = "让我分析一下用户的意图。用户说你好，我应该元气回复。"
        test_user = 777666
        sess = context_manager.get_session("private", test_user)
        sess.clear()

        dispatched_messages = []
        async def mock_dispatch(*args, **kwargs):
            dispatched_messages.append((args, kwargs))

        with patch("src.llm_client.llm_client.chat_completion", new=AsyncMock(return_value=(incident_sample, {}))), \
             patch.object(bot_service, "_dispatch_output", new=mock_dispatch):
            await bot_service._process_chat(
                session_type="private",
                target_id=test_user,
                user_id=test_user,
                nickname="用户A",
                user_text="你好",
                message_type="private",
                is_active_reply=False,
            )

        # 验证：外发了兜底回复
        self.assertEqual(len(dispatched_messages), 1)
        kwargs = dispatched_messages[0][1]
        self.assertEqual(kwargs.get("display_text"), "诶？音理刚才走神了一下下……")
        self.assertNotIn("分析", kwargs.get("display_text", ""))


if __name__ == "__main__":
    unittest.main()

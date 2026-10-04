"""聊天内快速指令解析与分发模块。
支持前缀指令（如 /reset、/help、/status、/tts、/mode）及管理员特权指令。
"""

from typing import Optional, Tuple

from src.config import config_manager
from src.context_manager import context_manager
from src.statistics import stats_tracker
from src.tts_client import tts_client


class CommandHandler:
    """聊天内指令处理器。"""

    def is_command(self, raw_text: str) -> bool:
        prefix = config_manager.config.commands.prefix
        cleaned = raw_text.strip()
        return cleaned.startswith(prefix)

    async def handle_command(
        self,
        raw_text: str,
        session_type: str,
        target_id: int,
        user_id: int,
    ) -> Optional[str]:
        """处理快速指令，返回应答文本；若不是指令或无需回复则返回 None。"""
        cfg = config_manager.config
        prefix = cfg.commands.prefix
        text = raw_text.strip()
        if not text.startswith(prefix):
            return None

        cmd_body = text[len(prefix) :].strip()
        parts = cmd_body.split()
        if not parts:
            return None

        cmd = parts[0].lower()
        args = parts[1:]
        is_admin = user_id in cfg.security.admin_list

        # 1. 重置上下文记忆指令
        if cmd in ["reset", "重置", "清空记忆", "清除上下文"]:
            if not cfg.commands.enable_reset:
                return "当前指令已被管理员禁用哦。"
            context_manager.reset_session(session_type, target_id)
            return "音理的记忆已经唰地一下刷新啦！刚才聊的都清空咯，接下来要和音理聊什么呢？"

        # 2. 上下文分支管理指令 (/new, /chatlist)
        if cmd == "new":
            if not cfg.commands.enable_new:
                return "当前指令已被管理员禁用哦。"
            sess = context_manager.get_session(session_type, target_id)
            if not args:
                # /new: 创建全新上下文
                new_branch = sess.create_branch()
                context_manager.save()
                return f"已为当前会话创建并切换到全新上下文「{new_branch.name}」(序号: {new_branch.branch_id})！旧记忆已安全归档。"
            else:
                # /new <名称或序号>: 切换或创建
                target_ident = " ".join(args).strip()
                # 尝试切换
                switched = sess.switch_branch(target_ident)
                if switched:
                    context_manager.save()
                    return f"已成功切换至上下文「{switched.name}」(序号: {switched.branch_id})！"
                else:
                    # 创建指定名称的分支
                    new_branch = sess.create_branch(name=target_ident)
                    context_manager.save()
                    return f"已创建并切换至新上下文「{new_branch.name}」(序号: {new_branch.branch_id})！"

        if cmd in ["chatlist", "contexts", "上下文列表"]:
            if not cfg.commands.enable_chatlist:
                return "当前指令已被管理员禁用哦。"
            sess = context_manager.get_session(session_type, target_id)
            branches = sess.list_branches()
            lines = ["【当前会话可用上下文列表】"]
            for b in branches:
                active_mark = "▶ [当前使用中] " if b["is_active"] else "   "
                lines.append(f"{active_mark}序号 {b['id']}: {b['name']} ({b['message_count']} 条消息)")
            lines.append(f"💡 提示：使用 {prefix}new <序号或名称> 切换，或输入 {prefix}new 创建新上下文。")
            return "\n".join(lines)

        # 3. 模型查看与切换指令 (/model, /model <序号>)
        if cmd in ["model", "模型"]:
            if not cfg.commands.enable_model:
                return "当前指令已被管理员禁用哦。"
            hub = cfg.model_hub
            sess_cfg = cfg.get_session_config(session_type, target_id)
            current_tag = sess_cfg.model_id or cfg.active_model_id or cfg.llm.model

            if not args:
                if not hub:
                    return f"系统模型库为空，当前运行模型为默认模型：{current_tag}。\n可在 WebUI 模型库中添加更多模型！"
                lines = ["【系统模型库可用列表】"]
                for i, item in enumerate(hub, start=1):
                    tag = item.id
                    is_active = (tag == current_tag)
                    active_mark = "▶ [使用中] " if is_active else "   "
                    vision_mark = " [图]" if item.supports_vision else ""
                    audio_mark = " [音]" if item.supports_audio else ""
                    video_mark = " [视]" if item.supports_video else ""
                    lines.append(f"{active_mark}{i}. {item.display_name or item.model_name}{vision_mark}{audio_mark}{video_mark} (tag: {tag})")
                lines.append(f"💡 提示：使用 {prefix}model <序号> 可为此会话切换模型。")
                return "\n".join(lines)

            # /model <序号或tag>
            target_arg = args[0].strip()
            selected_item = None
            if target_arg.isdigit():
                idx = int(target_arg)
                if 1 <= idx <= len(hub):
                    selected_item = hub[idx - 1]
                else:
                    return f"序号超出范围，请输入 1 到 {len(hub)} 之间的数字。"
            else:
                # 尝试按 tag 或 model_name 匹配
                for item in hub:
                    if item.id.lower() == target_arg.lower() or item.model_name.lower() == target_arg.lower():
                        selected_item = item
                        break

            if not selected_item:
                return f"未找到匹配的模型「{target_arg}」，输入 {prefix}model 查看所有可用列表。"

            config_manager.update_session_config(session_type, target_id, model_id=selected_item.id)
            return f"当前会话对话模型已成功切换为：\n{selected_item.display_name or selected_item.model_name}\n(标识: {selected_item.id})！"

        # 4. 聊天功能开关 (/chat on, /chat off)
        if cmd in ["chat", "聊天"]:
            if not cfg.commands.enable_chat_onoff:
                return "当前指令已被管理员禁用哦。"
            if not args:
                sess_cfg = cfg.get_session_config(session_type, target_id)
                status_str = "开启" if sess_cfg.chat_enabled else "关闭"
                return f"当前会话自动聊天功能状态为：【{status_str}】\n使用 {prefix}chat on 开启，{prefix}chat off 关闭。"

            sub = args[0].lower()
            if sub in ["on", "开启", "开"]:
                config_manager.update_session_config(session_type, target_id, chat_enabled=True)
                return "已开启当前会话的 LLM 对话功能！音理可以正常回复大家啦。"
            elif sub in ["off", "关闭", "关"]:
                config_manager.update_session_config(session_type, target_id, chat_enabled=False)
                return "已关闭当前会话的 LLM 对话功能！音理将进入安静待机模式（仍可响应指令与控制台人工干预消息）。"
            else:
                return f"用法：{prefix}chat on (开启) 或 {prefix}chat off (关闭)"

        # 5. 帮助指令
        if cmd in ["help", "帮助", "菜单"]:
            if not cfg.commands.enable_help:
                return None
            return (
                f"【音理的指令小手册】\n"
                f"{prefix}new [名称] - 创建或切换对话上下文\n"
                f"{prefix}chatlist - 列出此会话所有可用上下文\n"
                f"{prefix}model [序号] - 查看或切换会话使用的LLM模型\n"
                f"{prefix}chat on/off - 开启/关闭当前会话的LLM自动聊天\n"
                f"{prefix}reset - 刷新当前上下文记忆\n"
                f"{prefix}status - 查询机器人运行状态与Token消耗\n"
                f"{prefix}tts on/off - 快捷开启或关闭当前语音合成\n"
                f"{prefix}mode [sim|text|voice] - 切换输出模式(同传/纯文本/纯语音)\n"
                f"{prefix}help - 显示本指令菜单"
            )

        # 6. 状态查询指令
        if cmd in ["status", "状态", "info"]:
            if not cfg.commands.enable_status:
                return None
            summary = stats_tracker.get_summary()
            tts_ok, tts_desc = await tts_client.ping()
            sess = context_manager.get_session(session_type, target_id)
            sess_cfg = cfg.get_session_config(session_type, target_id)
            active_b = sess.get_active_branch()
            current_model = sess_cfg.model_id or cfg.active_model_id or cfg.llm.model
            chat_state = "开启" if sess_cfg.chat_enabled else "关闭"
            return (
                f"【音理的当前运行状态】\n"
                f"当前会话模型：{current_model}\n"
                f"聊天功能：{chat_state}\n"
                f"当前上下文分支：{active_b.name} (序号: {active_b.branch_id})\n"
                f"TTS服务：{'正常' if tts_ok else '异常'} ({tts_desc})\n"
                f"输出模式：{cfg.tts.mode}\n"
                f"当前分支消息数：{len(active_b.history)}\n"
                f"今日消耗Token：{summary['today_total_tokens']} (共 {summary['today_calls']} 次)\n"
                f"历史总Token：{summary['grand_total_tokens']}"
            )

        # 7. 语音开关
        if cmd in ["tts"]:
            if not args:
                return f"当前 TTS 状态：{'开启' if cfg.tts.enabled else '关闭'}，模式：{cfg.tts.mode}"
            sub = args[0].lower()
            if sub in ["on", "开启", "开"]:
                config_manager.update({"tts": {"enabled": True}})
                return "音理的语音配音功能已开启！"
            elif sub in ["off", "关闭", "关"]:
                config_manager.update({"tts": {"enabled": False}})
                return "音理的语音配音功能已关闭，接下来只发文字啦。"

        # 8. 模式切换
        if cmd in ["mode", "模式"]:
            if not args:
                return f"当前模式为：{cfg.tts.mode} (可选: sim, text, voice, text_and_voice)"
            m = args[0].lower()
            mode_map = {
                "sim": "simultaneous",
                "同传": "simultaneous",
                "text": "text_only",
                "文本": "text_only",
                "voice": "voice_only",
                "语音": "voice_only",
                "both": "text_and_voice",
                "双轨": "text_and_voice",
            }
            if m in mode_map:
                new_mode = mode_map[m]
                config_manager.update({"tts": {"mode": new_mode, "enabled": True}})
                return f"已成功切换模式为：{new_mode}！"
            return "未知模式，请选择: sim(同声传译), text(纯文本), voice(纯语音), both(同文同音)"

        # 9. 管理员高级指令
        if is_admin and cmd == "admin":
            if not args:
                return "管理员指令用法：admin [reload|whitelist]"
            admin_sub = args[0].lower()
            if admin_sub == "reload":
                # 重新载入配置
                config_manager._load()
                return "系统配置及提示词包已强制重新加载！"
            elif admin_sub == "whitelist" and len(args) >= 3:
                # admin whitelist add/del user/group <id>
                action, target_type, target_val = args[1].lower(), args[2].lower(), int(args[3])
                sec = cfg.security
                if target_type in ["user", "private"]:
                    wl = list(sec.private_whitelist)
                    if action == "add" and target_val not in wl:
                        wl.append(target_val)
                    elif action == "del" and target_val in wl:
                        wl.remove(target_val)
                    config_manager.update({"security": {"private_whitelist": wl}})
                    return f"私聊白名单已更新: {wl}"
                elif target_type in ["group"]:
                    gwl = list(sec.group_whitelist)
                    if action == "add" and target_val not in gwl:
                        gwl.append(target_val)
                    elif action == "del" and target_val in gwl:
                        gwl.remove(target_val)
                    config_manager.update({"security": {"group_whitelist": gwl}})
                    return f"群聊白名单已更新: {gwl}"

        return None


command_handler = CommandHandler()

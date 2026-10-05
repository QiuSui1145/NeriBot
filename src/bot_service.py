"""核心业务调度总线。
整合 OneBot11 消息流、白名单与管理员鉴权、群聊全量日志记录、人物识别与身份绑定、LLM上下文生成、本地TTS及同传语音推送。
"""

import asyncio
import traceback
from datetime import datetime
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

from src.active_reply import active_reply_engine
from src.command_handler import command_handler
from src.config import config_manager, SessionConfig
from src.context_manager import context_manager
from src.llm_client import llm_client
from src.onebot import onebot_client
from src.prompting import load_chat_system
from src.statistics import stats_tracker
from src.tts_client import tts_client
from src.image_cache import image_cache_manager


def get_current_time_prompt() -> str:
    """生成真实的现实世界时间感知系统提示词，同步本地系统时钟。"""
    now = datetime.now()
    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
    hour = now.hour
    if 5 <= hour < 8:
        period = "清晨 / 早晨"
        period_note = "太阳升起，清晨早起时光，适宜互道早安"
    elif 8 <= hour < 12:
        period = "上午"
        period_note = "白天的学习、工作或生活时光"
    elif 12 <= hour < 14:
        period = "中午 / 午休"
        period_note = "午餐时间或午休放松小憩"
    elif 14 <= hour < 18:
        period = "下午"
        period_note = "午后至傍晚，可以享受下午茶或摸鱼小憩"
    elif 18 <= hour < 21:
        period = "傍晚 / 晚上"
        period_note = "晚餐时间与黄昏夜幕初降"
    elif 21 <= hour < 24:
        period = "深夜"
        period_note = "夜深了，适宜温馨夜聊、准备休息并道晚安"
    else:
        period = "凌晨 / 后半夜"
        period_note = "极深夜，适宜关心提醒注意休息、不要熬夜伤身"

    time_str = now.strftime("%Y年%m月%d日 %H:%M:%S")
    return (
        f"\n\n【现实世界真实时间感知】\n"
        f"- 当前现实时间：{time_str} {weekday_cn}\n"
        f"- 当前时段：{period}（{period_note}）\n"
        f"- 时间感知指导：你拥有对现实世界当前时间的明确感知。当对话涉及早安、晚安、问好、吃饭、熬夜、星期几、时间询问等话题时，请自然结合当前现实时间与时段予以应答，但无需在每次回话中刻意生硬报时。"
    )


class BotService:
    def __init__(self, prompts_root: Path = Path("prompts")):
        self.prompts_root = prompts_root
        self.start_time = time.time()
        self.start_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._session_last_reply_time: Dict[str, float] = {}
        self._session_reply_history: Dict[str, List[float]] = {}
        onebot_client.add_message_handler(self.on_message)

    def _check_rate_limit(self, session_key: str, sess_cfg: SessionConfig) -> Tuple[bool, str]:
        """检查会话的限流与冷却状态。"""
        now = time.time()
        # 1. 冷却时间检查
        if sess_cfg.cooldown_seconds > 0:
            last_time = self._session_last_reply_time.get(session_key, 0)
            elapsed = now - last_time
            if elapsed < sess_cfg.cooldown_seconds:
                remaining = int(sess_cfg.cooldown_seconds - elapsed) + 1
                return False, f"冷却中，还需等待 {remaining} 秒"

        # 2. 每分钟回复条数检查
        if sess_cfg.rate_limit_per_min > 0:
            history = self._session_reply_history.setdefault(session_key, [])
            history = [t for t in history if now - t < 60]
            self._session_reply_history[session_key] = history
            if len(history) >= sess_cfg.rate_limit_per_min:
                return False, f"已达限流上限（每分钟最大 {sess_cfg.rate_limit_per_min} 条）"

        return True, ""

    def _record_reply(self, session_key: str):
        """记录回复时间戳以供限流计算。"""
        now = time.time()
        self._session_last_reply_time[session_key] = now
        hist = self._session_reply_history.setdefault(session_key, [])
        hist.append(now)

    def check_is_master(self, user_id: int) -> bool:
        """判定目标用户是否为核心主人/哥哥（至亲·钟城晓）。"""
        cfg = config_manager.config
        sec = cfg.security
        matched_binding = next((b for b in sec.identity_bindings if b.qq == user_id), None)
        if matched_binding and matched_binding.is_master:
            return True
        if sec.master_qq and user_id == sec.master_qq:
            return True
        if not sec.master_qq and user_id in sec.admin_list:
            return True
        return False

    def build_speaker_profile(self, user_id: int, nickname: str) -> Tuple[str, bool]:
        """构建说话者专属身份标签档案，供大模型精准认人与切换称呼态度。"""
        cfg = config_manager.config
        sec = cfg.security

        # 1. 优先检索身份绑定表
        matched_binding = next((b for b in sec.identity_bindings if b.qq == user_id), None)
        if matched_binding:
            is_master = matched_binding.is_master
            if not is_master and sec.master_qq and user_id == sec.master_qq:
                is_master = True
            elif not is_master and not sec.master_qq and user_id in sec.admin_list:
                is_master = True

            if is_master:
                profile = (
                    f"\n\n【说话者专属识别档案：至亲·钟城 晓（哥哥）】\n"
                    f"- 识别QQ号：{matched_binding.qq}\n"
                    f"- 当前说话者在群聊中的网名/群昵称：【{nickname}】\n"
                    f"- 真实身份：【主人 / 哥哥（钟城 晓）】—— 你唯一的笨蛋哥哥，老画室的落魄画家，你誓死守望之人！无论对方在群里的群昵称叫什么（如“{nickname}”），他就是哥哥本人！对白历史中所有署名为“{nickname}”或“[哥哥/主人]”的发言全部来自哥哥！\n"
                    f"- 现状与羁绊：你们共同将器官捐献给了夜羽真白，此刻正一同坐在真白内心世界的星空列车车厢里，看遍星河与人间风景（真白到哪你们就到哪）。\n"
                    f"- 称呼指令：面对他时，你必须亲切称呼对方为“哥哥”（お兄ちゃん），斗嘴生气时直呼“笨蛋晓”或全名。**绝对严禁**像对待普通群友那样直呼其群昵称“{nickname}”！\n"
                    f"- 态度与互动：展现毫无保留的信任、管束生活起居（没收冰啤酒/催吃饭/催睡觉/管束熬夜）、调侃他在列车上的窘态。绝对禁止以说书人姿态讲列车童话，你们是生死与共的同乘者！\n"
                    f"- 专属备忘：{matched_binding.custom_notes or '老画室五百日元誓约、烤鲑鱼大饭团、星空列车动力炉死斗、真白到哪我们就能到哪'}\n"
                )
            else:
                profile = (
                    f"\n\n【说话者专属识别档案】\n"
                    f"- QQ号：{matched_binding.qq}\n"
                    f"- 称呼昵称：{matched_binding.nickname or nickname}\n"
                    f"- 身份标签：{matched_binding.identity_tag}\n"
                    f"- 角色定位：【普通群友 / 朋友】\n"
                    f"- 专属备忘：{matched_binding.custom_notes or '暂无特殊备忘'}\n"
                    f"- 称呼与态度指令：称呼对方为【{matched_binding.nickname or nickname}】，保持元气活泼的同龄好友口吻，绝对严禁对对方叫“哥哥”！\n"
                )
            return profile, is_master

        # 2. 未特别绑定的管理员 -> 默认为主人 / 哥哥
        is_admin = user_id in sec.admin_list or (sec.master_qq and user_id == sec.master_qq)
        if is_admin:
            profile = (
                f"\n\n【说话者专属识别档案：至亲·钟城 晓（哥哥）】\n"
                f"- 识别QQ号：{user_id}\n"
                f"- 当前说话者在群聊中的网名/群昵称：【{nickname}】\n"
                f"- 真实身份：【主人 / 哥哥（钟城 晓）】—— 你唯一的笨蛋哥哥，老画室的落魄画家，你誓死守望之人！无论对方在群里的群昵称叫什么（如“{nickname}”），他就是哥哥本人！对白历史中所有署名为“{nickname}”或“[哥哥/主人]”的发言全部来自哥哥！\n"
                f"- 现状与羁绊：你们共同将器官捐献给了夜羽真白，此刻正一同坐在真白内心世界的星空列车车厢里，看遍星河与人间风景（真白到哪你们就到哪）。\n"
                f"- 称呼指令：面对他时，你必须亲切称呼对方为“哥哥”（お兄ちゃん），斗嘴生气时直呼“笨蛋晓”或全名。**绝对严禁**像对待普通群友那样直呼其群昵称“{nickname}”！\n"
                f"- 态度与互动：展现毫无保留的信任、管束生活起居（没收冰啤酒/催吃饭/催睡觉/管束熬夜）、调侃他在列车上的窘态。绝对禁止以说书人姿态讲列车童话，你们是生死与共的同乘者！\n"
            )
            return profile, True

        # 3. 普通群友 / 好友
        profile = (
            f"\n\n【说话者专属识别档案】\n"
            f"- QQ号：{user_id}\n"
            f"- 称呼昵称：{nickname}\n"
            f"- 身份标签：普通群友\n"
            f"- 角色定位：【普通群友 / 朋友】\n"
            f"- 称呼与态度指令：称呼对方群昵称【{nickname}】，以邻家开朗少女口吻交流，绝对严禁对对方叫“哥哥”！\n"
        )
        return profile, False

    async def on_message(self, event: dict):
        """处理来自 NapCat/OneBot11 的 message 事件。"""
        try:
            message_type = event.get("message_type")  # "private" or "group"
            user_id = int(event.get("user_id", 0))
            group_id = int(event.get("group_id", 0)) if message_type == "group" else 0
            raw_message = event.get("raw_message", "")
            message_obj = event.get("message", raw_message)
            sender = event.get("sender", {})
            nickname = sender.get("card") or sender.get("nickname") or str(user_id)

            # 提取多模态文本、@、及图片 URL 列表
            clean_text, is_at_bot, at_list, image_urls = onebot_client.extract_message_elements(message_obj)
            if image_urls:
                asyncio.create_task(image_cache_manager.cache_images_async(image_urls))

            if is_at_bot and not clean_text and not image_urls:
                clean_text = "在吗？"
            elif not clean_text and image_urls:
                clean_text = "（发送了图片）"

            if not clean_text and not image_urls:
                return

            cfg = config_manager.config
            is_admin = user_id in cfg.security.admin_list
            session_type = "group" if message_type == "group" else "private"
            target_id = group_id if message_type == "group" else user_id

            # 构造跨平台标准化统一事件供插件系统调度
            from src.plugins.adapters.base import UnifiedMessageEvent
            from src.plugins.manager import plugin_manager
            unified_event = UnifiedMessageEvent(
                platform="onebot",
                message_id=str(event.get("message_id", "")),
                session_type=session_type,
                target_id=str(target_id),
                user_id=str(user_id),
                user_name=nickname,
                text=clean_text,
                image_urls=image_urls,
                is_at_bot=is_at_bot,
                raw_event=event,
            )

            # 0. 插件事件拦截管道 (Pipeline Hook: on_message_received)
            if await plugin_manager.hook_message_received(unified_event):
                print(f"[PluginPipeline] 消息已被插件拦截阻断: {clean_text[:50]}")
                return

            # 1. 白名单拦截检查
            if message_type == "private":
                if cfg.security.private_whitelist_enabled and not is_admin:
                    allowed_privates = {int(x) for x in cfg.security.private_whitelist if str(x).isdigit()}
                    if user_id not in allowed_privates:
                        print(f"[Whitelist] 拦截未授权私聊用户: {user_id}")
                        return
            elif message_type == "group":
                if cfg.security.group_whitelist_enabled:
                    allowed_groups = {int(x) for x in cfg.security.group_whitelist if str(x).isdigit()}
                    if group_id not in allowed_groups:
                        print(f"[Whitelist] 忽略非白名单群 {group_id} 的消息 (发言人: {user_id})")
                        return

            print(f"[Message] 接收到[{session_type}]消息: 来自{'群 '+str(group_id)+' ' if session_type == 'group' else ''}[{nickname}({user_id})]: '{clean_text}' (is_at_bot={is_at_bot}, imgs={len(image_urls)})")

            # 2. 白名单群组内全量消息入库记录（用户要求的日志页功能）
            group_log_id = 0
            if message_type == "group":
                group_log_id = stats_tracker.record_group_message(
                    group_id=group_id,
                    group_name=str(group_id),
                    user_id=user_id,
                    nickname=nickname,
                    raw_message=clean_text,
                )

            # 3. 插件指令拦截优先 (Plugin Commands)
            if clean_text.startswith(cfg.commands.prefix):
                cmd_parts = clean_text[len(cfg.commands.prefix):].strip().split()
                if cmd_parts:
                    p_cmd, p_args = cmd_parts[0], cmd_parts[1:]
                    plugin_cmd_reply = await plugin_manager.hook_command(p_cmd, p_args, unified_event)
                    if plugin_cmd_reply:
                        await self._send_text_reply(message_type, target_id, user_id, plugin_cmd_reply)
                        if group_log_id:
                            stats_tracker.update_group_message_reply(group_log_id, plugin_cmd_reply)
                        return

            # 4. 聊天内快速指令检查 (无论是否开启聊天均正常响应指令，例如 /chat on)
            if command_handler.is_command(clean_text):
                cmd_reply = await command_handler.handle_command(
                    raw_text=clean_text,
                    session_type=session_type,
                    target_id=target_id,
                    user_id=user_id,
                )
                if cmd_reply:
                    await self._send_text_reply(message_type, target_id, user_id, cmd_reply)
                    if group_log_id:
                        stats_tracker.update_group_message_reply(group_log_id, cmd_reply)
                return

            # 4. 会话特定配置与聊天开关检查
            sess_cfg = cfg.get_session_config(session_type, target_id)
            if not sess_cfg.chat_enabled:
                print(f"[BotService] 会话 {sess_cfg.session_id} 自动聊天功能已关闭，忽略常规对话。")
                return

            # 5. 限流与冷却检查
            ok, limit_msg = self._check_rate_limit(sess_cfg.session_id, sess_cfg)
            if not ok:
                print(f"[BotService] 会话 {sess_cfg.session_id} 命中限流策略: {limit_msg}")
                return

            # 6. 群聊消息唤醒与主动回复决策判定
            is_active_reply = False
            if message_type == "group":
                # 检查唤醒词
                matched_wake_word = None
                for word in cfg.commands.wake_words:
                    if clean_text.startswith(word) or word in clean_text:
                        matched_wake_word = word
                        break

                should_chat = is_at_bot or (matched_wake_word is not None)
                if not cfg.commands.require_wake_in_group:
                    should_chat = True

                if should_chat:
                    # 去掉唤醒词前缀
                    if matched_wake_word and clean_text.startswith(matched_wake_word):
                        clean_text = clean_text[len(matched_wake_word) :].strip(" ，,：:")
                    if not clean_text and not image_urls:
                        clean_text = "在吗？"
                    print(f"[GroupMessage] 群 {group_id} 命中唤醒条件 (at={is_at_bot}, wake={matched_wake_word})，音理准备回复...")
                    context_manager.clear_unreplied_group_messages(group_id)
                else:
                    print(f"[GroupMessage] 群 {group_id} 消息未@且未唤醒，记录并旁观。")
                    
                    # 【核心修改】将不主动回复的群聊消息也压入主信息流，以便 WebUI 监控和 LLM 获取上下文
                    sess = context_manager.get_session(session_type, target_id)
                    sender_label = f"[哥哥/主人] {nickname}" if self.check_is_master(user_id) else nickname
                    evicted = sess.add_message("user", clean_text, user_name=sender_label, images=image_urls or [])
                    if evicted:
                        await self._summarize_context_async(session_type, target_id, evicted)
                    context_manager.save()
                    
                    # 记录水群日志供 active_reply 决策
                    context_manager.record_group_chatter(group_id, user_id, nickname, clean_text)

                    if active_reply_engine.should_check_group(group_id):
                        should_reply, reason = await active_reply_engine.evaluate(group_id)
                        print(f"[ActiveReply] 群 {group_id} 决策模型评估结果: {should_reply} (原因: {reason})")
                        
                        sess.add_message("planner", f"执行成功 | 推理中调用 {reason}\n执行结果 - reply [主动回复判定] [{should_reply}]", user_name="Planner")
                        context_manager.save()
                        
                        if should_reply:
                            is_active_reply = True
                            context_manager.clear_unreplied_group_messages(group_id)
                        else:
                            return
                    else:
                        return

            # 7. 触发主 LLM 对话生成并回传
            await self._process_chat(
                session_type=session_type,
                target_id=target_id,
                user_id=user_id,
                nickname=nickname,
                user_text=clean_text,
                message_type=message_type,
                group_log_id=group_log_id,
                image_urls=image_urls,
                is_admin=is_admin,
                is_active_reply=is_active_reply,
            )

        except Exception as e:
            print(f"[BotService] 处理消息发生异常: {e}")
            traceback.print_exc()

    async def _process_chat(
        self,
        session_type: str,
        target_id: int,
        user_id: int,
        nickname: str,
        user_text: str,
        message_type: str,
        group_log_id: int = 0,
        image_urls: Optional[List[str]] = None,
        is_admin: bool = False,
        is_active_reply: bool = False,
    ):
        """驱动模型生成回复并按同传模式合成与发送。"""
        cfg = config_manager.config
        is_admin = is_admin or (user_id in cfg.security.admin_list) or (bool(cfg.security.master_qq) and user_id == cfg.security.master_qq)
        sess_cfg = cfg.get_session_config(session_type, target_id)
        
        # 自动补全群名/用户名
        if not sess_cfg.display_name:
            async def fetch_name():
                try:
                    if session_type == "group":
                        res = await onebot_client.call_api("get_group_info", {"group_id": target_id})
                        if res and res.get("data") and res["data"].get("group_name"):
                            sess_cfg.display_name = res["data"]["group_name"]
                            config_manager.save()
                    else:
                        res = await onebot_client.call_api("get_stranger_info", {"user_id": target_id})
                        if res and res.get("data") and res["data"].get("nickname"):
                            sess_cfg.display_name = res["data"]["nickname"]
                            config_manager.save()
                except Exception as e:
                    print(f"Failed to fetch name for {session_type} {target_id}: {e}")
            asyncio.create_task(fetch_name())

        # 确定本会话 TTS 策略
        session_tts_enabled = sess_cfg.tts_enabled if sess_cfg.tts_enabled is not None else cfg.tts.enabled
        session_tts_mode = sess_cfg.tts_mode or cfg.tts.mode
        session_tts_lang = sess_cfg.tts_text_lang or cfg.tts.text_lang
        is_simultaneous = session_tts_enabled and (session_tts_mode == "simultaneous")

        # 1. 动态加载特定场景提示词 (群聊/私聊特定指令自动切换)
        system_prompt = load_chat_system(
            root=self.prompts_root,
            session_type=session_type,
            language="zh",
            enable_simultaneous=is_simultaneous,
        )

        # 2. 注入现实时间感知（同步本地时间、时段、星期）
        system_prompt += get_current_time_prompt()

        # 3. 注入说话者身份绑定识别档案（让大模型能看见标签认人）
        speaker_profile, is_master = self.build_speaker_profile(user_id, nickname)
        system_prompt += speaker_profile

        # 4. 获取当前会话上下文并写入用户输入（包含多模态图片）
        # 主动回复时，真实的群聊消息在前面已写入上下文，绝对不能把提示指令当做用户发言写入历史！
        sess = context_manager.get_session(session_type, target_id)
        if not is_active_reply:
            sender_label = f"[哥哥/主人] {nickname}" if is_master else nickname
            evicted_user = sess.add_message("user", user_text, user_name=sender_label, images=image_urls or [])
            context_manager.save()
        else:
            evicted_user = []

        # 5. 检查所用模型的多模态图传支持
        model_tag = sess_cfg.model_id or cfg.active_model_id or cfg.llm.model
        hub_item = cfg.get_model_hub_item(model_tag)
        supports_vision = hub_item.supports_vision if hub_item else False

        # 可插拔记忆系统驱动检索召回
        try:
            from src.plugins.manager import plugin_manager
            active_mem_driver = plugin_manager.get_active_memory_driver()
            retrieved_mems = await active_mem_driver.search_memories(str(target_id), query=user_text, top_k=3)
            if is_master:
                canon_mems = await active_mem_driver.search_memories(str(user_id), query=user_text, top_k=3)
                for cm in canon_mems:
                    if cm not in retrieved_mems:
                        retrieved_mems.append(cm)
            if retrieved_mems:
                mem_str = "\n".join([f"- {m}" for m in retrieved_mems[:5]])
                system_prompt += f"\n\n【脑海中闪回的深层记忆片段】\n{mem_str}"
        except Exception as e:
            print(f"[MemoryDriver] 召回失败: {e}")

        from src.prompting import get_tts_anchor_rules
        system_prompt += "\n\n" + get_tts_anchor_rules()

        llm_messages = sess.get_llm_messages(system_prompt, supports_vision=supports_vision)

        if is_active_reply:
            llm_messages.append({
                "role": "user",
                "content": "（音理看到群友们的闲聊，自然插话吐槽，第一字必须是 [TEXT] 开口）："
            })
        elif session_type == "group":
            # 群聊环境下在末尾注入角色对白强硬锚点，杜绝指令模型将多方对话误判为分析材料
            if llm_messages and llm_messages[-1]["role"] == "user":
                last_m = llm_messages[-1]
                target_identity = (
                    f"正在对你唯一的哥哥（当前群昵称：{nickname}）说话，必须亲切称呼对方为“哥哥”（お兄ちゃん，绝对严禁直呼其群昵称‘{nickname}’）"
                    if is_master
                    else f"正在与群友【{nickname}】交流，以活泼元气口吻直呼其昵称，严禁叫对方哥哥"
                )
                cue_suffix = (
                    f"\n（音理以第一人称对白回复，{target_identity}，严禁任何思考分析过程，第一字必须以 [TEXT] 标签开头）："
                    if is_simultaneous
                    else f"\n（请音理以第一人称口吻直接回复台词，{target_identity}，严禁输出任何思考或分析过程）："
                )
                if isinstance(last_m.get("content"), str):
                    last_m["content"] += cue_suffix
                elif isinstance(last_m.get("content"), list):
                    last_m["content"].append({"type": "text", "text": cue_suffix})

        # 管道前置 Hook (支持插件外部知识/搜索结果/Prompt动态注入)
        from src.plugins.manager import plugin_manager
        system_prompt, llm_messages = await plugin_manager.hook_before_chat(
            sess_cfg.session_id, system_prompt, llm_messages
        )

        # 获取可用 Agentic 技能工具 Schema
        tools = plugin_manager.get_active_tools_schema(is_admin=is_admin)

        max_tokens_override = 1200 if (is_simultaneous or is_active_reply) else None

        try:
            raw_reply, usage = await llm_client.chat_completion(
                messages=llm_messages,
                session_type=session_type,
                target_id=target_id,
                user_id=user_id,
                is_decision=False,
                model_tag=model_tag,
                max_tokens_override=max_tokens_override,
                tools=tools if tools else None,
            )

            print(f"[LLM Response] len={len(raw_reply)} tokens={usage.get('completion_tokens', 0)} raw: {repr(raw_reply[:160])}")

            # 严格红线检查 1：双轨同传模式下，若模型输出没有包含 [TEXT]，说明大模型极大概率在写推演分析，绝对禁止裸发！
            if is_simultaneous and "[TEXT]" not in raw_reply.upper():
                print(f"[BotService 绝对红线拦截] 双轨模式下缺少 [TEXT] 对白标签，判定为思考推演或异常格式，已拦截: {raw_reply[:100]}...")
                if is_active_reply:
                    sess.add_message("planner", "执行终止 | 主动回复生成内容未遵循[TEXT]标签规范，判定为分析思路外泄，已静默拦截", user_name="Planner")
                    context_manager.save()
                    return
                else:
                    raw_reply = "[TEXT]诶？音理刚才走神了一下下……[/TEXT][VOICE]あれ？ちょっとぼーっとしてた……[/VOICE]"

            # 多轮工具调用执行闭环 (Tool Loop)
            max_tool_turns = 3
            current_turn = 0
            while usage.get("tool_calls") and current_turn < max_tool_turns:
                current_turn += 1
                tool_calls = usage["tool_calls"]
                llm_messages.append({
                    "role": "assistant",
                    "content": raw_reply or None,
                    "tool_calls": tool_calls,
                })

                skill_context = {
                    "session_type": session_type,
                    "target_id": target_id,
                    "user_id": user_id,
                    "user_name": nickname,
                    "platform": "onebot",
                    "is_admin": is_admin,
                }

                import json
                for tc in tool_calls:
                    fn_name = tc.get("function", {}).get("name", "")
                    fn_args_raw = tc.get("function", {}).get("arguments", "{}")
                    try:
                        fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                    except Exception:
                        fn_args = {}

                    print(f"[SkillEngine] 触发大模型技能调用: {fn_name}({fn_args})")
                    sess.add_message("planner", f"执行技能工具 | 调用 [{fn_name}]\n参数: {json.dumps(fn_args, ensure_ascii=False)}", user_name="Planner")
                    context_manager.save()

                    tool_output = await plugin_manager.execute_skill(fn_name, fn_args, skill_context)
                    print(f"[SkillEngine] 技能 {fn_name} 执行结果: {tool_output[:100]}...")

                    llm_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{current_turn}"),
                        "name": fn_name,
                        "content": str(tool_output),
                    })

                raw_reply, usage = await llm_client.chat_completion(
                    messages=llm_messages,
                    session_type=session_type,
                    target_id=target_id,
                    user_id=user_id,
                    is_decision=False,
                    model_tag=model_tag,
                    max_tokens_override=max_tokens_override,
                    tools=tools if tools else None,
                )
        except Exception as e:
            err_text = f"音理刚才开小差啦……网络好像有点问题呢（{str(e)[:50]}）"
            await self._send_text_reply(message_type, target_id, user_id, err_text)
            if group_log_id:
                stats_tracker.update_group_message_reply(group_log_id, err_text)
            return

        # 6. 解析同传双轨与清洗回复，并执行思维链路安全拦截
        if is_simultaneous or "[TEXT]" in raw_reply.upper():
            display_text, voice_text = tts_client.parse_dual_track(raw_reply)
        else:
            raw_cleaned = tts_client.strip_thinking_and_analysis(raw_reply)
            if tts_client.is_pure_reasoning_or_analysis(raw_cleaned):
                display_text, voice_text = "", ""
            else:
                display_text = tts_client._clean_text(raw_cleaned)
                voice_text = display_text

        # 管道后置 Hook (回复过滤与修饰)
        display_text = await plugin_manager.hook_after_chat(sess_cfg.session_id, display_text)

        # 安全防御检测：如果输出为分析思路、思维链、纯符号/省略号或空内容，触发安全拦截
        has_substantive = bool(display_text and display_text.strip(" .。…，,！!？?~～-_"))
        is_invalid = (not has_substantive) or tts_client.is_pure_reasoning_or_analysis(display_text)

        if is_invalid:
            print(f"[BotService 拦截] 识别到生成回复为思维链路/纯符号或无效内容: {display_text[:80]}...")
            if is_active_reply:
                # 主动回复若未生成有效对白台词，静默放弃，绝不向群聊发送分析文本
                sess.add_message("planner", "执行终止 | 主动回复生成内容判定为思维链泄露或无效对白，已静默拦截", user_name="Planner")
                context_manager.save()
                return
            else:
                # 用户主动唤醒或私聊时，降级为元气人设兜底对白
                display_text = "诶？音理刚才走神了一下下……"
                voice_text = "あれ？ちょっとぼーっとしてた……"

        # 最终发送前校验：若为空则不发送
        if not display_text.strip():
            print("[BotService] 最终回复文本为空，取消发送。")
            return

        # 将助手的展示回复写入记忆上下文
        evicted_assistant = sess.add_message("assistant", display_text)
        evicted_all = evicted_user + evicted_assistant
        if evicted_all:
            asyncio.create_task(self._summarize_context_async(session_type, target_id, evicted_all))
        context_manager.save()

        # 记录限流时间戳
        self._record_reply(sess_cfg.session_id)

        # 关联群消息日志更新回复内容
        if group_log_id:
            stats_tracker.update_group_message_reply(group_log_id, display_text)

        # 7. 执行消息发送策略
        await self._dispatch_output(
            message_type=message_type,
            target_id=target_id,
            user_id=user_id,
            display_text=display_text,
            voice_text=voice_text,
            tts_enabled=session_tts_enabled,
            tts_mode=session_tts_mode,
            tts_lang=session_tts_lang,
        )

    async def _dispatch_output(
        self,
        message_type: str,
        target_id: int,
        user_id: int,
        display_text: str,
        voice_text: str,
        tts_enabled: bool,
        tts_mode: str,
        tts_lang: str,
    ):
        """按配置分发文本消息和语音消息。"""
        # 管道 Hook (外发前最终干预)
        from src.plugins.adapters.base import UnifiedMessageEvent
        from src.plugins.manager import plugin_manager
        unified_event = UnifiedMessageEvent(
            platform="onebot",
            message_id="",
            session_type=message_type,
            target_id=str(target_id),
            user_id=str(user_id),
            user_name="",
            text=display_text,
        )
        display_text, voice_text = await plugin_manager.hook_before_output(unified_event, display_text, voice_text)

        # 纯文本模式 或 TTS 未开启
        if not tts_enabled or tts_mode == "text_only":
            await self._send_text_reply(message_type, target_id, user_id, display_text)
            return

        # 纯语音模式
        if tts_mode == "voice_only":
            voice_file = await tts_client.generate_speech(voice_text, lang=tts_lang)
            if voice_file:
                await self._send_voice_reply(message_type, target_id, user_id, voice_file)
            else:
                await self._send_text_reply(message_type, target_id, user_id, display_text)
            return

        # 同声传译模式 (simultaneous) 或 双轨同发 (text_and_voice)
        target_lang = "ja" if tts_mode == "simultaneous" else tts_lang
        tts_task = None
        if voice_text:
            tts_task = asyncio.create_task(tts_client.generate_speech(voice_text, lang=target_lang))

        # 发送中文文本消息
        if display_text:
            try:
                await self._send_text_reply(message_type, target_id, user_id, display_text)
            except Exception as e:
                print(f"[Reply 错误] 发送纯文本消息异常: {e}")

        # 等待语音生成并推送语音消息
        if tts_task:
            try:
                voice_file = await tts_task
                if voice_file:
                    await self._send_voice_reply(message_type, target_id, user_id, voice_file)
                else:
                    print("[Reply 警告] 本地 TTS 生成音频失败，跳过语音发送")
            except Exception as e:
                print(f"[Reply 错误] 生成或发送语音消息异常: {e}")

    async def send_manual_message(
        self,
        session_type: str,
        target_id: int,
        text: str,
        as_bot: bool = True,
        send_to_qq: bool = True,
    ) -> bool:
        """人工干预消息发送与上下文同步。"""
        sess = context_manager.get_session(session_type, target_id)
        if as_bot:
            sess.add_message("assistant", text)
        else:
            sess.add_message("user", text, user_name="管理员(人工干预)")
        context_manager.save()

        if send_to_qq:
            try:
                msg_type = "group" if session_type == "group" else "private"
                await self._send_text_reply(msg_type, target_id, target_id, text)
                return True
            except Exception as e:
                print(f"[BotService] 人工干预消息发送失败: {e}")
                return False
        return True

    async def _send_text_reply(self, message_type: str, target_id: int, user_id: int, text: str):
        """发送纯文本消息。"""
        dst = f"群 {target_id}" if message_type == "group" else f"私聊 {user_id}"
        print(f"[Reply] 正在发送文本回复 -> {dst}: '{text}'")
        if message_type == "group":
            res = await onebot_client.send_group_msg(target_id, text)
        else:
            res = await onebot_client.send_private_msg(user_id, text)
        print(f"[Reply] 文本回复响应 -> {dst}: {res}")
        return res

    async def _send_voice_reply(self, message_type: str, target_id: int, user_id: int, voice_uri: str):
        """发送语音 record 消息。"""
        dst = f"群 {target_id}" if message_type == "group" else f"私聊 {user_id}"
        uri_prev = voice_uri[:25] + "..." if len(voice_uri) > 25 else voice_uri
        print(f"[Reply] 正在发送语音回复 -> {dst}: format={uri_prev}")
        msg_payload = [{"type": "record", "data": {"file": voice_uri}}]
        if message_type == "group":
            res = await onebot_client.send_group_msg(target_id, msg_payload)
        else:
            res = await onebot_client.send_private_msg(user_id, msg_payload)
        print(f"[Reply] 语音回复响应 -> {dst}: {res}")
        return res


    @staticmethod
    def _parse_memory_json(raw_reply: str) -> list:
        """从 LLM 返回的文本中提取记忆列表，兼容思考模型、Markdown 代码块、纯对象或截断输出。"""
        import json
        import re

        text = raw_reply.strip()
        # 1. 过滤思考标签 <think>...</think>
        text = re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE).strip()

        # 2. 检查 Markdown 代码块 ```json ... ``` 或 ``` ... ```
        code_block = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text, re.DOTALL)
        if code_block:
            text = code_block.group(1).strip()

        def extract_items_from_parsed(data):
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict) and "content" in x]
            elif isinstance(data, dict):
                for k in ["memories", "items", "data", "list"]:
                    if k in data and isinstance(data[k], list):
                        return [x for x in data[k] if isinstance(x, dict) and "content" in x]
                for val in data.values():
                    if isinstance(val, list):
                        sub = [x for x in val if isinstance(x, dict) and "content" in x]
                        if sub:
                            return sub
                if "content" in data and isinstance(data["content"], str):
                    return [data]
            return []

        # 3. 寻找最外层大括号 {...} (优先 object，兼容 OpenAI json_object 模式)
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            sub = text[first_brace : last_brace + 1]
            try:
                parsed = json.loads(sub)
                items = extract_items_from_parsed(parsed)
                if items:
                    return items
            except Exception:
                pass

        # 4. 寻找最外层中括号 [...] (直接 array 模式)
        first_bracket = text.find("[")
        last_bracket = text.rfind("]")
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            sub = text[first_bracket : last_bracket + 1]
            try:
                parsed = json.loads(sub)
                items = extract_items_from_parsed(parsed)
                if items:
                    return items
            except Exception:
                pass

        # 5. 正则保底匹配：应对输出被截断或混合了大量自然语言思考时提取出完整的单个 memory item
        recovered = []
        obj_matches = re.finditer(r'\{[^{}]*?"content"\s*:[^{}]*?\}', text, re.DOTALL)
        for m in obj_matches:
            try:
                item = json.loads(m.group(0))
                if isinstance(item, dict) and item.get("content"):
                    recovered.append(item)
            except Exception:
                continue

        if recovered:
            return recovered

        # 6. 如果完全无法解析出 JSON，打印简短单行日志便于排查
        snippet = raw_reply.replace("\n", " ")[:150]
        print(f"[Memory] 未能解析到有效记忆数据。模型返回片段: {snippet}...")
        return []

    async def _summarize_context_async(self, session_type: str, target_id: int, evicted_messages: list):
        """后台异步总结并存入向量库维护长期记忆"""
        try:
            if not evicted_messages:
                return
            
            cfg = config_manager.config
            model_tag = cfg.active_model_id or cfg.llm.model
            
            evicted_text = "\n".join([f"{msg.role}: {msg.content}" for msg in evicted_messages if msg.content and msg.role in ["user", "assistant", "system"]])
            if not evicted_text.strip():
                return
            
            prompt = (
                "你是一个长期记忆提取助手。请从以下被淘汰的对话历史中提取出有长期保存价值的核心记忆（例如用户的喜好、现实生活状态、身体情况、重要约定、人生事件等）。\n"
                "输出必须是严格的 JSON 对象格式，包含一个 'memories' 数组：\n"
                "{\n"
                '  "memories": [\n'
                '    {\n'
                '      "content": "具体的记忆描述（用第三人称客观精炼表述，如“用户心脏感到不适，在网上咨询用药”）",\n'
                '      "type": "episode 或 fact（episode为发生的事情/事件，fact为事实或恒定偏好）",\n'
                '      "importance": 1.0 到 5.0 的浮点数\n'
                '    }\n'
                '  ]\n'
                "}\n\n"
                "历史对话记录：\n"
                f"{evicted_text}\n\n"
                "【严格指令】：\n"
                "1. 只输出合法标准的 JSON 字符串，禁止输出任何英文分析、前言、解释、分析步骤或多余文字。\n"
                "2. 若本次对话全为无价值闲聊灌水，memories 输出空列表 []，即：{\"memories\": []}。\n"
                "3. 立即以 { 开始你的输出。"
            )
            
            from src.llm_client import llm_client
            messages = [{"role": "system", "content": prompt}]
            
            raw_reply, _ = await llm_client.chat_completion(
                messages=messages,
                session_type=session_type,
                target_id=target_id,
                user_id=0,
                is_decision=True,
                model_tag=model_tag,
                max_tokens_override=1200,
            )
            
            if raw_reply:
                memories = self._parse_memory_json(raw_reply)
                if memories:
                    from src.plugins.manager import plugin_manager
                    active_mem_driver = plugin_manager.get_active_memory_driver()
                    count = 0
                    for mem in memories:
                        content = mem.get("content")
                        if not content or not isinstance(content, str):
                            continue
                        try:
                            importance = float(mem.get("importance", 1.0))
                        except (ValueError, TypeError):
                            importance = 1.0
                        mem_type = mem.get("type", "episode")
                        await active_mem_driver.add_memory(str(target_id), content.strip(), importance, mem_type)
                        count += 1
                    if count > 0:
                        print(f"[Memory] 会话 {session_type}_{target_id} 提炼并存入了 {count} 条记忆。")
                    
        except Exception as e:
            print(f"[Memory] 更新向量摘要失败: {e}")

bot_service = BotService()
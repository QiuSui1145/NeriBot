"""Token 消耗统计与调用日志持久化模块。
使用内置 SQLite，具备高吞吐量与聚合查询能力。
"""

import datetime
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path("data/stats.db")


class StatsTracker:
    """统计与调用日志记录器。"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS token_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    session_type TEXT,
                    target_id INTEGER,
                    user_id INTEGER,
                    model TEXT,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    total_tokens INTEGER,
                    latency_ms INTEGER,
                    status TEXT,
                    error_message TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_records_time ON token_records(created_at)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS group_messages_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    group_id INTEGER,
                    group_name TEXT,
                    user_id INTEGER,
                    nickname TEXT,
                    raw_message TEXT,
                    is_bot_reply INTEGER DEFAULT 0,
                    bot_reply_content TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_group_log_time ON group_messages_log(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_group_log_gid ON group_messages_log(group_id)"
            )
            conn.commit()

    def record_usage(
        self,
        session_type: str,
        target_id: int,
        user_id: int,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        latency_ms: int = 0,
        status: str = "success",
        error_message: Optional[str] = None,
    ) -> None:
        """记录一次 LLM 请求的 Token 消耗与指标。"""
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO token_records (
                    session_type, target_id, user_id, model,
                    prompt_tokens, completion_tokens, total_tokens,
                    latency_ms, status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_type,
                    target_id,
                    user_id,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    latency_ms,
                    status,
                    error_message,
                ),
            )
            conn.commit()

    def get_summary(self) -> Dict[str, Any]:
        """获取 Token 综合概览指标。"""
        today_start = datetime.date.today().strftime("%Y-%m-%d 00:00:00")
        with self._get_conn() as conn:
            # 历史总量
            total_row = conn.execute(
                """
                SELECT 
                    COUNT(*) as total_calls,
                    COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) as total_completion_tokens,
                    COALESCE(SUM(total_tokens), 0) as grand_total_tokens,
                    COALESCE(AVG(latency_ms), 0) as avg_latency_ms
                FROM token_records WHERE status = 'success'
                """
            ).fetchone()

            # 今日总量
            today_row = conn.execute(
                """
                SELECT 
                    COUNT(*) as today_calls,
                    COALESCE(SUM(prompt_tokens), 0) as today_prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) as today_completion_tokens,
                    COALESCE(SUM(total_tokens), 0) as today_total_tokens
                FROM token_records 
                WHERE status = 'success' AND created_at >= ?
                """,
                (today_start,),
            ).fetchone()

            # 错误次数
            err_row = conn.execute(
                "SELECT COUNT(*) as err_count FROM token_records WHERE status = 'error'"
            ).fetchone()

        return {
            "total_calls": total_row["total_calls"],
            "total_prompt_tokens": total_row["total_prompt_tokens"],
            "total_completion_tokens": total_row["total_completion_tokens"],
            "grand_total_tokens": total_row["grand_total_tokens"],
            "avg_latency_ms": round(total_row["avg_latency_ms"], 1),
            "today_calls": today_row["today_calls"],
            "today_prompt_tokens": today_row["today_prompt_tokens"],
            "today_completion_tokens": today_row["today_completion_tokens"],
            "today_total_tokens": today_row["today_total_tokens"],
            "error_calls": err_row["err_count"],
        }

    def get_chart_data(self, range_type: str = "7d", days: int = 7) -> List[Dict[str, Any]]:
        """获取多时间维度的 Token 走势数据 (24h / 7d / 30d / 12m)。"""
        now = datetime.datetime.now()
        with self._get_conn() as conn:
            if range_type == "24h":
                # 按小时统计过去 24 小时
                start_dt = now - datetime.timedelta(hours=23)
                start_str = start_dt.strftime("%Y-%m-%d %H:00:00")
                rows = conn.execute(
                    """
                    SELECT 
                        strftime('%Y-%m-%d %H:00', created_at) as slot,
                        COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                        COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                        COALESCE(SUM(total_tokens), 0) as total_tokens,
                        COUNT(*) as call_count
                    FROM token_records
                    WHERE created_at >= ? AND status = 'success'
                    GROUP BY slot
                    ORDER BY slot ASC
                    """,
                    (start_str,),
                ).fetchall()
                slot_map = {row["slot"]: dict(row) for row in rows}
                result = []
                for i in range(24):
                    slot_dt = start_dt + datetime.timedelta(hours=i)
                    slot_key = slot_dt.strftime("%Y-%m-%d %H:00")
                    label = slot_dt.strftime("%H:00")
                    if slot_key in slot_map:
                        item = dict(slot_map[slot_key])
                        item["day"] = slot_key
                        item["label"] = label
                        result.append(item)
                    else:
                        result.append({
                            "day": slot_key,
                            "label": label,
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                            "call_count": 0,
                        })
                return result

            elif range_type == "12m":
                # 按月份统计过去 12 个月
                cur_year = now.year
                cur_month = now.month
                months = []
                for i in range(11, -1, -1):
                    y = cur_year
                    m = cur_month - i
                    while m <= 0:
                        m += 12
                        y -= 1
                    months.append(f"{y:04d}-{m:02d}")

                start_month_str = f"{months[0]}-01 00:00:00"
                rows = conn.execute(
                    """
                    SELECT 
                        strftime('%Y-%m', created_at) as slot,
                        COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                        COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                        COALESCE(SUM(total_tokens), 0) as total_tokens,
                        COUNT(*) as call_count
                    FROM token_records
                    WHERE created_at >= ? AND status = 'success'
                    GROUP BY slot
                    ORDER BY slot ASC
                    """,
                    (start_month_str,),
                ).fetchall()
                slot_map = {row["slot"]: dict(row) for row in rows}
                result = []
                for m_str in months:
                    if m_str in slot_map:
                        item = dict(slot_map[m_str])
                        item["day"] = m_str
                        item["label"] = m_str
                        result.append(item)
                    else:
                        result.append({
                            "day": m_str,
                            "label": m_str,
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                            "call_count": 0,
                        })
                return result

            else:
                # 按天统计 (7d 或 30d 或 自定义天数)
                num_days = 30 if range_type == "30d" else (days if days > 0 else 7)
                start_date = (
                    datetime.date.today() - datetime.timedelta(days=num_days - 1)
                ).strftime("%Y-%m-%d 00:00:00")
                rows = conn.execute(
                    """
                    SELECT 
                        strftime('%Y-%m-%d', created_at) as day,
                        COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                        COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                        COALESCE(SUM(total_tokens), 0) as total_tokens,
                        COUNT(*) as call_count
                    FROM token_records
                    WHERE created_at >= ? AND status = 'success'
                    GROUP BY day
                    ORDER BY day ASC
                    """,
                    (start_date,),
                ).fetchall()
                date_map = {row["day"]: dict(row) for row in rows}
                result = []
                for i in range(num_days):
                    d_obj = datetime.date.today() - datetime.timedelta(days=num_days - 1 - i)
                    d_str = d_obj.strftime("%Y-%m-%d")
                    label = d_obj.strftime("%m-%d")
                    if d_str in date_map:
                        item = dict(date_map[d_str])
                        item["label"] = label
                        result.append(item)
                    else:
                        result.append({
                            "day": d_str,
                            "label": label,
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                            "call_count": 0,
                        })
                return result

    def get_daily_chart(self, days: int = 7) -> List[Dict[str, Any]]:
        """向下兼容历史调用的 7 天/N 天图表接口。"""
        return self.get_chart_data(range_type="7d", days=days)

    def get_cost_summary(self, model_prices: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
        """根据配置的模型价格计算今日、本月和历史总成本。"""
        today_start = datetime.date.today().strftime("%Y-%m-%d 00:00:00")
        month_start = datetime.date.today().strftime("%Y-%m-01 00:00:00")
        with self._get_conn() as conn:
            # 1. 历史各模型使用量
            total_rows = conn.execute(
                """
                SELECT 
                    model,
                    COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                    COALESCE(SUM(total_tokens), 0) as total_tokens,
                    COUNT(*) as call_count
                FROM token_records
                WHERE status = 'success'
                GROUP BY model
                """
            ).fetchall()

            # 2. 今日各模型使用量
            today_rows = conn.execute(
                """
                SELECT 
                    model,
                    COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                    COALESCE(SUM(total_tokens), 0) as total_tokens,
                    COUNT(*) as call_count
                FROM token_records
                WHERE status = 'success' AND created_at >= ?
                GROUP BY model
                """,
                (today_start,),
            ).fetchall()

            # 3. 本月各模型使用量
            month_rows = conn.execute(
                """
                SELECT 
                    model,
                    COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                    COALESCE(SUM(total_tokens), 0) as total_tokens,
                    COUNT(*) as call_count
                FROM token_records
                WHERE status = 'success' AND created_at >= ?
                GROUP BY model
                """,
                (month_start,),
            ).fetchall()

        today_map = {r["model"]: dict(r) for r in today_rows}
        month_map = {r["model"]: dict(r) for r in month_rows}

        today_cost = 0.0
        month_cost = 0.0
        total_cost = 0.0
        breakdown = []

        all_models = set(r["model"] for r in total_rows)
        for k in model_prices.keys():
            all_models.add(k)

        for m in sorted(all_models):
            p_info = model_prices.get(m, {})
            if not p_info and "/" in m:
                raw_m = m.split("/", 1)[1]
                p_info = model_prices.get(raw_m, {})
            p_price = float(p_info.get("prompt_price_per_1m", 0.0) or (float(p_info.get("prompt_price_per_1k", 0.0)) * 1000.0) or 0.0)
            c_price = float(p_info.get("completion_price_per_1m", 0.0) or (float(p_info.get("completion_price_per_1k", 0.0)) * 1000.0) or 0.0)

            t_row = today_map.get(m, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "call_count": 0})
            m_row = month_map.get(m, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "call_count": 0})
            tot_row = next((r for r in total_rows if r["model"] == m), None)
            tot_dict = dict(tot_row) if tot_row else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "call_count": 0}

            # 按照 ¥ / 1M Tokens (元/百万Tokens) 计算成本
            m_today_cost = (t_row["prompt_tokens"] * p_price + t_row["completion_tokens"] * c_price) / 1000000.0
            m_month_cost = (m_row["prompt_tokens"] * p_price + m_row["completion_tokens"] * c_price) / 1000000.0
            m_total_cost = (tot_dict["prompt_tokens"] * p_price + tot_dict["completion_tokens"] * c_price) / 1000000.0

            today_cost += m_today_cost
            month_cost += m_month_cost
            total_cost += m_total_cost

            if tot_dict["total_tokens"] > 0 or p_price > 0 or c_price > 0:
                breakdown.append({
                    "model": m,
                    "prompt_price": p_price,
                    "completion_price": c_price,
                    "today_tokens": t_row["total_tokens"],
                    "today_cost": round(m_today_cost, 4),
                    "month_tokens": m_row["total_tokens"],
                    "month_cost": round(m_month_cost, 4),
                    "total_tokens": tot_dict["total_tokens"],
                    "total_calls": tot_dict["call_count"],
                    "total_cost": round(m_total_cost, 4),
                })

        breakdown.sort(key=lambda x: (x["total_cost"], x["total_tokens"]), reverse=True)

        return {
            "today_cost": round(today_cost, 4),
            "month_cost": round(month_cost, 4),
            "total_cost": round(total_cost, 4),
            "currency": "¥",
            "unit": "¥/1M Tokens",
            "breakdown": breakdown,
        }

    def get_models_distribution(self) -> List[Dict[str, Any]]:
        """获取模型调用与 Token 分布占比。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT 
                    model,
                    COUNT(*) as call_count,
                    COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                    COALESCE(SUM(total_tokens), 0) as total_tokens
                FROM token_records
                WHERE status = 'success'
                GROUP BY model
                ORDER BY total_tokens DESC
                """
            ).fetchall()

        total_tokens_all = sum(r["total_tokens"] for r in rows)
        total_calls_all = sum(r["call_count"] for r in rows)

        result = []
        for r in rows:
            t_pct = round((r["total_tokens"] / total_tokens_all * 100), 1) if total_tokens_all > 0 else 0
            c_pct = round((r["call_count"] / total_calls_all * 100), 1) if total_calls_all > 0 else 0
            result.append({
                "model": r["model"],
                "calls": r["call_count"],
                "calls_percent": c_pct,
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "total_tokens": r["total_tokens"],
                "tokens_percent": t_pct,
            })
        return result


    def get_recent_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近的 LLM 请求记录。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT 
                    id, created_at, session_type, target_id, user_id,
                    model, prompt_tokens, completion_tokens, total_tokens,
                    latency_ms, status, error_message
                FROM token_records
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def clear_records(self) -> None:
        """清空统计记录。"""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM token_records")
            conn.commit()

    def record_group_message(
        self,
        group_id: int,
        group_name: str,
        user_id: int,
        nickname: str,
        raw_message: str,
        is_bot_reply: int = 0,
        bot_reply_content: str = "",
    ) -> int:
        """记录群聊内消息至日志库，返回插入记录 ID。"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO group_messages_log (
                    created_at, group_id, group_name, user_id, nickname,
                    raw_message, is_bot_reply, bot_reply_content
                ) VALUES (datetime('now', 'localtime'), ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    group_id,
                    group_name,
                    user_id,
                    nickname,
                    raw_message,
                    is_bot_reply,
                    bot_reply_content,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def update_group_message_reply(self, log_id: int, bot_reply_content: str) -> None:
        """更新某条群消息关联的音理回复内容。"""
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE group_messages_log 
                SET is_bot_reply = 1, bot_reply_content = ?
                WHERE id = ?
                """,
                (bot_reply_content, log_id),
            )
            conn.commit()

    def get_group_messages(
        self,
        group_id: Optional[int] = None,
        keyword: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """查询白名单群聊历史消息记录。"""
        query = "SELECT * FROM group_messages_log WHERE 1=1"
        params: List[Any] = []
        if group_id:
            query += " AND group_id = ?"
            params.append(group_id)
        if keyword:
            query += " AND (raw_message LIKE ? OR nickname LIKE ? OR bot_reply_content LIKE ?)"
            kw = f"%{keyword}%"
            params.extend([kw, kw, kw])
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._get_conn() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]

    def clear_group_messages(self, group_id: Optional[int] = None) -> None:
        """清空指定群或全部群聊消息日志。"""
        with self._get_conn() as conn:
            if group_id:
                conn.execute("DELETE FROM group_messages_log WHERE group_id = ?", (group_id,))
            else:
                conn.execute("DELETE FROM group_messages_log")
            conn.commit()


stats_tracker = StatsTracker()

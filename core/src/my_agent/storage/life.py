"""生活类数据仓储：记账与提醒。

这两块数据的共同点是「量小、结构简单、纯本地」，因此直接放 SQLite，
不引入额外存储。记账的分类用一个关键词表做启发式推断——模型往往只给出
「中午吃饭 35 元」这样的口语描述，让用户每次都手动选分类不现实。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from .db import Database

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 分类推断
# --------------------------------------------------------------------------- #
EXPENSE_CATEGORIES = [
    "餐饮",
    "交通",
    "购物",
    "居住",
    "娱乐",
    "医疗",
    "教育",
    "人情",
    "通讯",
    "其他",
]

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "餐饮": (
        "饭", "餐", "午饭", "晚饭", "早餐", "夜宵", "外卖", "奶茶", "咖啡", "水果",
        "火锅", "烧烤", "零食", "食堂", "饮料", "星巴克", "拉面", "米线", "快餐",
        "面包", "蛋糕", "面条", "吃",
    ),
    "交通": (
        "地铁", "公交", "打车", "出租", "滴滴", "高铁", "火车", "机票", "飞机",
        "加油", "油费", "停车", "共享单车", "高速", "车票", "网约车",
    ),
    "购物": (
        "买", "购物", "淘宝", "京东", "拼多多", "衣服", "鞋", "裤子", "日用品",
        "化妆品", "数码", "家电", "快递",
    ),
    "居住": ("房租", "水费", "电费", "燃气", "物业", "宽带", "取暖", "房贷", "保洁"),
    "娱乐": ("电影", "游戏", "唱歌", "ktv", "演出", "门票", "旅游", "健身", "会员", "订阅"),
    "医疗": ("医院", "药", "挂号", "体检", "看病", "牙医", "疫苗", "门诊", "打针"),
    "教育": ("书", "课程", "培训", "学费", "考试", "文具", "网课", "辅导", "课本"),
    "人情": ("红包", "礼物", "请客", "随礼", "份子钱", "孝敬"),
    "通讯": ("话费", "流量", "充值", "电话费", "手机费"),
}

# 平局时的优先级：越具体的分类排在越前面。
# 例如「买药」同时命中「买」（购物）与「药」（医疗），显然应归为医疗；
# 「买书」同理应归为教育。没有这张表就只能靠字典序，结果会随分类名而变化。
CATEGORY_PRIORITY = ["医疗", "教育", "居住", "交通", "通讯", "人情", "娱乐", "餐饮", "其他", "购物"]
_PRIORITY_INDEX = {name: index for index, name in enumerate(CATEGORY_PRIORITY)}


def guess_category(text: str) -> str:
    """按关键词猜分类，猜不到归入「其他」。

    打分规则：同一分类命中的关键词**长度之和**（越长越具体、越可信）；
    分数相同则按 ``CATEGORY_PRIORITY`` 决定，保证结果稳定可预测。
    """
    haystack = (text or "").lower()
    if not haystack:
        return "其他"

    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(len(keyword) for keyword in keywords if keyword in haystack)
        if score:
            scores[category] = score

    if not scores:
        return "其他"
    return min(scores, key=lambda name: (-scores[name], _PRIORITY_INDEX.get(name, 99)))


# --------------------------------------------------------------------------- #
# 周期解析
# --------------------------------------------------------------------------- #
def period_range(period: str, *, today: date | None = None) -> tuple[str, str] | None:
    """把周期名解析成 ``(start_date, end_date)``（含两端），``all`` 返回 None。"""
    base = today or date.today()
    normalized = (period or "month").strip().lower()

    if normalized in ("all", "全部", "所有"):
        return None
    if normalized in ("today", "今天", "今日", "day"):
        return base.isoformat(), base.isoformat()
    if normalized in ("yesterday", "昨天"):
        target = base - timedelta(days=1)
        return target.isoformat(), target.isoformat()
    if normalized in ("week", "本周", "最近7天", "近7天", "7d"):
        start = base - timedelta(days=base.weekday())
        return start.isoformat(), base.isoformat()
    if normalized in ("lastweek", "上周"):
        end = base - timedelta(days=base.weekday() + 1)
        start = end - timedelta(days=6)
        return start.isoformat(), end.isoformat()
    if normalized in ("month", "本月", "这个月"):
        return base.replace(day=1).isoformat(), base.isoformat()
    if normalized in ("lastmonth", "上个月", "上月"):
        first_this = base.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return last_prev.replace(day=1).isoformat(), last_prev.isoformat()
    if normalized in ("year", "今年"):
        return base.replace(month=1, day=1).isoformat(), base.isoformat()
    if normalized in ("30d", "最近30天"):
        return (base - timedelta(days=29)).isoformat(), base.isoformat()

    raise ValueError(
        f"无法识别的周期「{period}」。可用值：today / yesterday / week / lastweek / "
        f"month / lastmonth / year / 30d / all"
    )


# --------------------------------------------------------------------------- #
# 记账
# --------------------------------------------------------------------------- #
@dataclass
class ExpenseRecord:
    id: int
    amount: float
    category: str
    note: str
    spent_on: str
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "amount": round(self.amount, 2),
            "category": self.category,
            "note": self.note,
            "spent_on": self.spent_on,
            "created_at": self.created_at,
        }


class ExpenseRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(
        self,
        *,
        amount: float,
        note: str = "",
        category: str | None = None,
        spent_on: str | None = None,
    ) -> ExpenseRecord:
        final_category = (category or "").strip() or guess_category(note)
        final_date = (spent_on or "").strip() or date.today().isoformat()
        # 统一成 YYYY-MM-DD，模型可能给出 2026/9/17 这类写法
        final_date = _normalize_date(final_date)

        new_id = await self._db.insert(
            "INSERT INTO expenses (amount, category, note, spent_on, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (float(amount), final_category, note or "", final_date, time.time()),
        )
        # 用刚拿到的 rowid 精确回查，而不是 ``ORDER BY id DESC LIMIT 1`` ——
        # 后者在并发下会取到别人刚插入的那条（见 Database.insert 的说明）
        row = await self._db.fetch_one("SELECT * FROM expenses WHERE id = ?", (new_id,))
        assert row is not None
        return self._row(row)

    async def list(
        self,
        *,
        period: str = "month",
        category: str | None = None,
        limit: int = 50,
    ) -> list[ExpenseRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        span = period_range(period)
        if span:
            clauses.append("spent_on BETWEEN ? AND ?")
            params.extend(span)
        if category:
            clauses.append("category = ?")
            params.append(category)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(limit, 500)))
        rows = await self._db.fetch_all(
            f"SELECT * FROM expenses {where} ORDER BY spent_on DESC, id DESC LIMIT ?", params
        )
        return [self._row(row) for row in rows]

    async def summary(self, *, period: str = "month", category: str | None = None) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        span = period_range(period)
        if span:
            clauses.append("spent_on BETWEEN ? AND ?")
            params.extend(span)
        if category:
            clauses.append("category = ?")
            params.append(category)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        total_row = await self._db.fetch_one(
            f"SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS n FROM expenses {where}",
            params,
        )
        total = float(total_row["total"]) if total_row else 0.0
        count = int(total_row["n"]) if total_row else 0

        by_category = await self._db.fetch_all(
            f"""
            SELECT category, SUM(amount) AS total, COUNT(*) AS n
            FROM expenses {where}
            GROUP BY category
            ORDER BY total DESC
            """,
            params,
        )
        by_day = await self._db.fetch_all(
            f"""
            SELECT spent_on, SUM(amount) AS total
            FROM expenses {where}
            GROUP BY spent_on
            ORDER BY spent_on
            """,
            params,
        )

        return {
            "period": period,
            "category": category,
            "range": {"start": span[0], "end": span[1]} if span else None,
            "total": round(total, 2),
            "count": count,
            "average": round(total / count, 2) if count else 0.0,
            "by_category": [
                {
                    "category": row["category"],
                    "total": round(float(row["total"]), 2),
                    "count": int(row["n"]),
                    "ratio": round(float(row["total"]) / total, 4) if total else 0.0,
                }
                for row in by_category
            ],
            "by_day": [
                {"date": row["spent_on"], "total": round(float(row["total"]), 2)}
                for row in by_day
            ],
        }

    async def delete(self, expense_id: int) -> bool:
        row = await self._db.fetch_one("SELECT id FROM expenses WHERE id = ?", (expense_id,))
        if row is None:
            return False
        await self._db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        return True

    async def categories(self) -> list[str]:
        rows = await self._db.fetch_all(
            "SELECT category, COUNT(*) AS n FROM expenses GROUP BY category ORDER BY n DESC"
        )
        used = [row["category"] for row in rows]
        return used + [item for item in EXPENSE_CATEGORIES if item not in used]

    @staticmethod
    def _row(row: dict[str, Any]) -> ExpenseRecord:
        return ExpenseRecord(
            id=int(row["id"]),
            amount=float(row["amount"]),
            category=row["category"],
            note=row.get("note") or "",
            spent_on=row["spent_on"],
            created_at=float(row.get("created_at") or 0),
        )


def _normalize_date(value: str) -> str:
    text = value.strip().replace("/", "-").replace(".", "-")
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%m-%d", "%Y%m%d"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == "%m-%d":
            parsed = parsed.replace(year=date.today().year)
        return parsed.date().isoformat()
    # 解析不了就用今天，并在日志里留痕而不是直接抛错打断记账
    logger.warning("无法解析日期 %r，按今天处理", value)
    return date.today().isoformat()


# --------------------------------------------------------------------------- #
# 提醒
# --------------------------------------------------------------------------- #
@dataclass
class ReminderRecord:
    id: int
    content: str
    remind_at: float
    base_at: float
    advance_min: int = 0
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    fired_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "remind_at": self.remind_at,
            "remind_at_text": _format_ts(self.remind_at),
            "base_at": self.base_at,
            "base_at_text": _format_ts(self.base_at),
            "advance_min": self.advance_min,
            "status": self.status,
            "created_at": self.created_at,
            "fired_at": self.fired_at,
        }


def _format_ts(value: float) -> str:
    if not value:
        return ""
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")


class ReminderRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        *,
        content: str,
        remind_at: float,
        base_at: float,
        advance_min: int = 0,
    ) -> ReminderRecord:
        now = time.time()
        new_id = await self._db.insert(
            "INSERT INTO reminders (content, remind_at, base_at, advance_min, status, created_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?)",
            (content, remind_at, base_at, int(advance_min), now),
        )
        row = await self._db.fetch_one("SELECT * FROM reminders WHERE id = ?", (new_id,))
        assert row is not None
        return self._row(row)

    async def list(self, *, status: str | None = None, limit: int = 50) -> list[ReminderRecord]:
        if status:
            rows = await self._db.fetch_all(
                "SELECT * FROM reminders WHERE status = ? ORDER BY remind_at DESC LIMIT ?",
                (status, max(1, min(limit, 200))),
            )
        else:
            rows = await self._db.fetch_all(
                "SELECT * FROM reminders ORDER BY remind_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            )
        return [self._row(row) for row in rows]

    async def upcoming(self, *, limit: int = 20) -> list[ReminderRecord]:
        rows = await self._db.fetch_all(
            "SELECT * FROM reminders WHERE status = 'pending' ORDER BY remind_at LIMIT ?",
            (max(1, min(limit, 100)),),
        )
        return [self._row(row) for row in rows]

    async def due(self, *, now: float | None = None) -> list[ReminderRecord]:
        """取出所有到点且尚未触发的提醒。"""
        moment = now if now is not None else time.time()
        rows = await self._db.fetch_all(
            "SELECT * FROM reminders WHERE status = 'pending' AND remind_at <= ? ORDER BY remind_at",
            (moment,),
        )
        return [self._row(row) for row in rows]

    async def mark_fired(self, reminder_id: int) -> bool:
        """标记提醒已触发；返回 False 表示它已被触发过或已取消。

        把「先 SELECT 查状态、再 UPDATE」压成一条带条件 UPDATE：
        原写法两步之间隔着 await，而调度循环是定时跑的 —— 上一轮还没走完
        下一轮就进来了，同一条提醒会被触发**两次**，用户收到重复提醒。
        """
        affected = await self._db.execute_affected(
            "UPDATE reminders SET status = 'fired', fired_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (time.time(), reminder_id),
        )
        return affected > 0

    async def cancel(self, reminder_id: int) -> bool:
        """取消提醒；返回 False 表示它不存在或已经不在待触发状态。"""
        affected = await self._db.execute_affected(
            "UPDATE reminders SET status = 'cancelled' WHERE id = ? AND status = 'pending'",
            (reminder_id,),
        )
        return affected > 0

    async def delete(self, reminder_id: int) -> bool:
        row = await self._db.fetch_one("SELECT id FROM reminders WHERE id = ?", (reminder_id,))
        if row is None:
            return False
        await self._db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        return True

    @staticmethod
    def _row(row: dict[str, Any]) -> ReminderRecord:
        return ReminderRecord(
            id=int(row["id"]),
            content=row["content"],
            remind_at=float(row["remind_at"]),
            base_at=float(row["base_at"]),
            advance_min=int(row.get("advance_min") or 0),
            status=row["status"],
            created_at=float(row.get("created_at") or 0),
            fired_at=row.get("fired_at"),
        )

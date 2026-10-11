"""时间的展示格式。

## 为什么单独放一个模块

时间要出现在好几个地方：给模型的历史消息前缀、「现在」、摘要文本、长期记忆条目、
群聊历史、审计与日志。各处各写一遍 ``strftime`` 的下场是**同一件事出现两种格式** ——
模型会以为它们含义不同（``09-26 14:32`` 和 ``2026/9/26 下午2点32分`` 看起来像两种东西），
而维护者要在四个地方同步改。

## 两条口径

- **一律本地时区**：用户说"今天早上"指的是他墙上的钟。存的是 epoch 秒（无时区歧义），
  只在这里转成人看的形状。
- **两种粒度各司其职**：历史消息用短的（同一天里反复出现，长短一样占地方）；
  「现在」用长的 —— 它是判断新旧的**尺子**，必须带上年月日与星期，否则模型没法算
  "这是三天前还是三个月前"。
"""

from __future__ import annotations

from datetime import UTC, datetime

_WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def format_message_time(ts: float) -> str:
    """``09-26 14:32``。给历史消息当前缀。"""
    local = datetime.fromtimestamp(ts)
    return f"{local:%m-%d %H:%M}"


def format_now(ts: float) -> str:
    """``2026-09-26 14:32（周六）``。给「现在」用。"""
    local = datetime.fromtimestamp(ts)
    return f"{local:%Y-%m-%d %H:%M}（{_WEEKDAYS[local.weekday()]}）"


def format_day(ts: float) -> str:
    """``2026-09-26``。给"某一天"的场合（记忆条目、审计分组）。"""
    return f"{datetime.fromtimestamp(ts):%Y-%m-%d}"


def format_stamp(ts: float | None) -> str:
    """行前缀 ``[09-26 14:32] ``；时间是 ``None`` 就返回空串。

    集中成一处，是为了让**"没时间就不加前缀"这个决定只做一次** —— 各处各写一个
    三元表达式的话，迟早有人写成"没有时间就填一个默认时间"，而那是假信息。
    """
    return f"[{format_message_time(ts)}] " if ts is not None else ""


def now_iso() -> str:
    """当前时刻的 ISO 8601（带时区）。

    与群事件落库用的形状一致（见 ``storage/group_events.py``）：群聊上下文里那份
    时间和数据库里那份要是**同一种写法**，恢复历史时才不用做格式猜测。
    """
    return datetime.now(UTC).isoformat()


def parse_iso(text: str | None) -> float | None:
    """把 ISO 8601 时间解析成 epoch 秒；解析不了返回 ``None``。"""
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return None


def parse_day(text: str | None) -> float | None:
    """把 ``YYYY-MM-DD`` / ``YYYY/MM/DD`` 解析成**当天 00:00 的本地时刻**。

    解析不出来返回 ``None``（调用方据此忽略这个条件），而不是抛错把整次检索搞失败 ——
    模型给的时间写法千奇百怪，"这条范围条件用不上"远好过"什么都查不出来"。
    """
    raw = (text or "").strip().replace("/", "-")
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").timestamp()
    except ValueError:
        return None


def day_range(start: str | None, end: str | None) -> tuple[float | None, float | None]:
    """把 ``YYYY-MM-DD`` 的起止日期化成 epoch 区间。

    **结束日算到当天最后一刻**：用户说"到 9 月 26 号"指的是**含**那一天。直接把
    00:00 当上界会把当天发生的事全漏掉，而这种"少一天"的错误很难被察觉 ——
    用户只会觉得"怎么最近几天都查不到"。
    """
    since = parse_day(start)
    until = parse_day(end)
    return since, (until + 86_399.999 if until is not None else None)

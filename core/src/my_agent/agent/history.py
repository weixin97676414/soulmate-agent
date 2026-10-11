"""跨来源的统一检索：群聊记录 / 单聊历史 / 搭子长期记忆。

## 为什么要有它

这三份数据住在三个地方（群事件表、会话仓储、向量库），而用户问的是同一件事：
「上周我们定的那个方案是怎么说的」。没有它，模型只能挨个技能试，试到哪算哪 ——
很容易只翻到一半就回答，而那正是用户说的"别把旧的当当下聊"。

## 时间口径沿用上次的做法（不另起一套）

- 入参是 ``YYYY-MM-DD``，**结束日含当天**（``utils.timefmt.day_range`` 统一处理，
  免得每个调用点各算一次"少一天"）；
- 每条结果都给**可读时间**（``when``），不给 epoch —— 模型算不明白 epoch；
- 时间戳不可信的老数据**不补假时间**，如实留空，并在 ``notes`` 里说明有几条
  因为"没有时间戳"被跳过了（加了时间筛选时）。

## 为什么"检索"这件事单独放一个门面

技能拿不到 runtime（也不该拿到），而这三份数据又分别挂在 runtime 上。这个门面
就是那层"只读窗口"：只有 search 一个入口，没有任何写操作。
"""

from __future__ import annotations

import logging
from typing import Any

from ..utils.timefmt import format_stamp, parse_iso

logger = logging.getLogger(__name__)

# 单个群最多回放多少条事件（与 group_events 的回放上限一致）
MAX_GROUP_EVENTS = 4000
# 最多翻多少个会话。会话是**按最近更新排序**的，所以截断丢的是最老的那些 ——
# 而"最近聊过什么"才是绝大多数提问的对象。截断了会在 notes 里如实说明。
MAX_SESSIONS = 30
# 每条结果带多少字的正文（给模型看的是片段，完整的在库里）
SNIPPET = 300


class HistorySearch:
    """只读的跨来源检索门面（技能通过 ``ctx.service("history")`` 取到它）。"""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    async def search(
        self,
        *,
        query: str,
        scope: str = "all",
        group_id: str = "",
        author: str = "",
        since: float | None = None,
        until: float | None = None,
        limit: int = 50,
        assistant_id: str | None = None,
    ) -> dict[str, Any]:
        keyword = (query or "").strip()
        if not keyword:
            return {"count": 0, "results": [], "message": "没有给检索关键词。"}

        notes: list[str] = []
        hits: list[dict[str, Any]] = []
        unknown_time = 0

        if scope in ("all", "group"):
            found, unknown = await self._from_groups(keyword, group_id, author, since, until)
            hits.extend(found)
            unknown_time += unknown
        if scope in ("all", "chat"):
            found, unknown, note = await self._from_chats(keyword, author, since, until)
            hits.extend(found)
            unknown_time += unknown
            if note:
                notes.append(note)
        if scope in ("all", "memory"):
            found, note = await self._from_memory(keyword, since, until, assistant_id, group_id)
            hits.extend(found)
            if note:
                notes.append(note)

        # 新的排前面：用户问"上次那个"时，最近说过的那句才是他要的
        hits.sort(key=lambda item: item.get("_at") or 0, reverse=True)
        for item in hits:
            item.pop("_at", None)

        if unknown_time:
            notes.append(
                f"有 {unknown_time} 条更早的记录没有时间戳，无法判断是否落在你给的时间段里，已跳过。"
            )

        return {
            "count": min(len(hits), limit),
            "total": len(hits),
            "results": hits[:limit],
            "notes": notes or None,
            "message": (
                "没有找到相关记录。换一个关键词，或者把时间范围放宽一点试试。"
                if not hits
                else None
            ),
        }

    # ------------------------------------------------------------------ #
    # 群聊记录
    # ------------------------------------------------------------------ #
    async def _from_groups(
        self,
        keyword: str,
        group_id: str,
        author: str,
        since: float | None,
        until: float | None,
    ) -> tuple[list[dict[str, Any]], int]:
        runtime = self._runtime
        if not getattr(runtime, "db_ready", False):
            return [], 0

        groups = (
            [runtime.groups.get(group_id)]
            if group_id
            else list(runtime.groups.groups)
        )
        hits: list[dict[str, Any]] = []
        unknown = 0
        for group in groups:
            if group is None:
                continue
            try:
                # ⚠️ 第二个参数是**对话 id**，传 `None` = 该群**所有对话**。
                # 这里必须传 None（现在一个群可以有多条对话）：
                # 检索是"在这个群的记录里找"，不该因为那句话在另一条对话里就搜不到。
                events = await runtime.group_event_repo.list_events(
                    group.id, None, MAX_GROUP_EVENTS
                )
            except Exception as exc:  # noqa: BLE001 - 单个群读不出来不该让整次检索失败
                logger.warning("群记录读取失败 group=%s: %s", group.id, exc)
                continue
            for item in events:
                data = item.get("data") or {}
                if item.get("event") not in ("topic", "message", "summary"):
                    continue
                content = str(data.get("content") or "").strip()
                if not content or keyword.lower() not in content.lower():
                    continue
                who = "用户" if item.get("event") == "topic" else str(data.get("name") or "搭子")
                if author and author not in who:
                    continue
                at = parse_iso(item.get("created_at"))
                if (since is not None or until is not None) and at is None:
                    unknown += 1
                    continue
                if at is not None and since is not None and at < since:
                    continue
                if at is not None and until is not None and at > until:
                    continue
                hits.append(
                    {
                        "source": "群聊",
                        "where": group.name,
                        "author": who,
                        "when": format_stamp(at),
                        "text": content[:SNIPPET],
                        "_at": at or 0,
                    }
                )
        return hits, unknown

    # ------------------------------------------------------------------ #
    # 单聊历史
    # ------------------------------------------------------------------ #
    async def _from_chats(
        self,
        keyword: str,
        author: str,
        since: float | None,
        until: float | None,
    ) -> tuple[list[dict[str, Any]], int, str]:
        runtime = self._runtime
        summaries = runtime.sessions.list()
        note = ""
        if len(summaries) > MAX_SESSIONS:
            note = (
                f"单聊只翻了最近 {MAX_SESSIONS} 个会话（共 {len(summaries)} 个）；"
                "更早的会话没有检索。"
            )
        hits: list[dict[str, Any]] = []
        unknown = 0
        for summary in summaries[:MAX_SESSIONS]:
            session_id = str(summary.get("id") or "")
            if not session_id:
                continue
            try:
                session = await runtime.sessions.get(session_id)
            except Exception as exc:  # noqa: BLE001 - 某个会话读不出来不该让整次检索失败
                logger.warning("会话读取失败 session=%s: %s", session_id, exc)
                continue
            who_assistant = self._assistant_name(session.assistant_id)
            title = session.title or "（未命名对话）"
            for message in session.history():
                content = str(message.get("content") or "").strip()
                if not content or keyword.lower() not in content.lower():
                    continue
                is_user = message.get("role") == "user"
                who = "我" if is_user else who_assistant
                if author and author not in who:
                    continue
                at = message.get("created_at")
                at = float(at) if isinstance(at, (int, float)) and at else None
                if (since is not None or until is not None) and at is None:
                    unknown += 1
                    continue
                if at is not None and since is not None and at < since:
                    continue
                if at is not None and until is not None and at > until:
                    continue
                hits.append(
                    {
                        "source": "单聊",
                        "where": title,
                        "author": who,
                        "when": format_stamp(at),
                        "text": content[:SNIPPET],
                        "_at": at or 0,
                    }
                )
        return hits, unknown, note

    # ------------------------------------------------------------------ #
    # 长期记忆
    # ------------------------------------------------------------------ #
    async def _from_memory(
        self,
        keyword: str,
        since: float | None,
        until: float | None,
        assistant_id: str | None,
        group_id: str = "",
    ) -> tuple[list[dict[str, Any]], str]:
        runtime = self._runtime
        settings = runtime.config.settings
        if not settings.memory.long_term_enabled:
            # 如实说明"为什么这次没查记忆"，而不是让模型以为记忆里也没有
            return [], "长期记忆没有打开（设置 → 安全与通用 → 长期记忆），本次没有检索它。"

        # ⚠️ 记忆是**分库**的：搭子是 ``assistant_<id>``、群是 ``assistant_group_<id>``，
        # 当前搭子那份、当前群那份、全局那份是三个库 —— 只查其中一个都会漏掉别的。
        sources: list[tuple[str, Any]] = []
        if assistant_id:
            sources.append(("当前搭子", runtime.memory_for(assistant_id)))
        # 群记忆是**群内成员共享**的。
        joined_groups: list[str] = []
        if group_id:
            # 群聊：只查**当前这个群**。把别的群的记忆也灌进这场讨论，等于让
            # A 群看到 B 群的事 —— 那不叫共同记忆，叫串台。
            sources.append(("当前群", runtime.memory_for_group(group_id)))
        elif assistant_id:
            # 单聊：这个搭子**参与过的所有群**的共同记忆也读进来（
            # 明确要求"群记忆也要出现在单聊里"）—— 他在群里经历过的事，跟他单聊
            # 时是相关的，没理由单聊就装作没发生过。
            #
            # ⚠️ 代价：参与群多了之后每次检索要顺序扫很多个库（个人使用场景可接受，
            # 用户已确认）。这不是静默的 —— hits 里每条都标着来自哪个群。
            joined_groups = runtime.groups_for_assistant(assistant_id)
            for joined in joined_groups:
                sources.append(
                    (f"群「{self._group_name(joined)}」", runtime.memory_for_group(joined))
                )
        sources.append(("全局", runtime.memory_for(None)))

        hits: list[dict[str, Any]] = []
        seen: set[str] = set()
        unavailable = 0
        # 换过嵌入模型的库要先把向量用新模型重建一遍才查得了（见 LongTermMemory.rebuild）。
        # ⚠️ 和 `unavailable` **分开计数**：那一个是"坏了"，这一个是"正在好起来"，
        # 对用户要说的话完全不同 —— 混成一句会让他以为记忆出了故障。
        rebuilding = 0
        for label, memory in sources:
            if not getattr(memory, "available", False):
                unavailable += 1
                continue
            if getattr(memory, "rebuilding", False):
                rebuilding += 1
                continue
            try:
                # 不写死条数：用设置里的「默认检索条数」（LongTermMemory.default_top_k）。
                # 以前这里硬编码 20 —— 那是**用户最常触发的那条检索**，所以设置页
                # 那个输入框改了完全没效果，看起来就像个摆设。
                found = await memory.search(keyword, since=since, until=until)
            except Exception as exc:  # noqa: BLE001 - 检索失败不该让整次检索崩掉
                logger.warning("长期记忆检索失败（%s）: %s", label, exc)
                unavailable += 1
                continue
            for hit in found:
                if hit.id in seen:
                    continue
                seen.add(hit.id)
                tags = str(hit.metadata.get("tags") or "").strip()
                hits.append(
                    {
                        "source": "长期记忆",
                        "where": f"{label}·{tags}" if tags else label,
                        "author": "",
                        "when": format_stamp(hit.ts),
                        "text": hit.text[:SNIPPET],
                        "score": round(hit.score, 4),
                        "_at": hit.ts or 0,
                    }
                )
        note = ""
        if rebuilding:
            note = (
                "长期记忆正在用当前模型重建向量（嵌入方式换过），这几个库这次先跳过；"
                "原文都还在库里，重建完就能照常检索。"
            )
        if len(joined_groups) > 3:
            # 单聊时并入了好几个群：如实说出来 —— 否则用户要么奇怪"怎么搜出来一堆
            # 群里的东西"，要么反过来以为"我明明在那个群说过，怎么没有"（群特别多
            # 的时候，检索确实可能被稀释）。
            extra = f"本次检索并入了 {len(joined_groups)} 个群的共同记忆。"
            note = f"{note}{extra}" if note else extra
        if unavailable:
            extra = (
                f"有 {unavailable} 个长期记忆库当前不可用（没装 chromadb 或读取出错），"
                "本次没有检索它们（详见应用日志）。"
            )
            note = f"{note}{extra}" if note else extra
        return hits, note

    def _group_name(self, group_id: str) -> str:
        """群名（拿不到就退回 id）。

        检索结果里要标清"这条记忆来自哪个群" —— 单聊时并进来的群可能有好几个，
        只写「群记忆」的话用户分不清是哪件事发生在哪。
        """
        if not group_id:
            return ""
        try:
            group = self._runtime.groups.get(group_id)
        except Exception:  # noqa: BLE001 - 群被删掉/配置读不出来都不该影响检索
            return group_id
        name = str(getattr(group, "name", "") or "").strip()
        return name or group_id

    def _assistant_name(self, assistant_id: str | None) -> str:
        if not assistant_id:
            return "搭子"
        profile = self._runtime.assistants.get(assistant_id)
        if profile is None:
            return "搭子"
        return profile.nickname or profile.name

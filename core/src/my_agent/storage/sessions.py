"""会话与消息仓储。

落盘策略：**两种模式，调用方显式选**（第 87 批 B 组，M-04）。

* ``mode="replace"``（默认）：整体替换该会话的全部消息。清理、改人设、新建这类
  **会删消息**的路径必须用它 —— 它们正是靠"先 DELETE 再 INSERT"把旧行删掉的。
* ``mode="append"``：只把**内存里新增的尾巴**追加进去，
  且**必须先过前缀指纹校验**（见 :meth:`SessionRepository._stored_prefix_len`）。

为什么要有 append：以前每轮对话都整体重写整条会话，而它随会话长度线性增长 ——
一个 500 条的会话每轮要 DELETE 500 行 + INSERT 501 行，写放大是 O(n²)，
长会话会明显卡顿并放大 WAL。append 把每轮开销降到"新增几条就写几条"。

为什么 append 需要守卫：内存消息会比库里**少**（``pop_last_assistant()`` 回滚重试）、
也可能整个被换掉（``clear_history()`` / 改系统提示词先 ``memory.clear()``）。
无脑追加的后果是**旧消息留在库里**，重启后用户看到已经删掉的对话又回来了。
所以指纹对不上就**退回整体替换** —— 正确性永远优先于性能。

时间戳：每条消息的 `created_at` 由 ``MemoryManager`` 在它**产生的那一刻**打上，
这里只负责把它带下去、再读回来。**不要再在这里用同一个 now 覆盖所有消息** ——
那正是"每轮对话把全部历史时间刷成刚刚"这个缺陷的原始写法（见 db.py 的 SCHEMA_V8）。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..llm.base import Message, ToolCall
from .db import Database

logger = logging.getLogger(__name__)

DELETE_MESSAGES = "DELETE FROM messages WHERE session_id = ?"
INSERT_MESSAGE = """
INSERT INTO messages
    (session_id, seq, role, content, reasoning_content, tool_calls, tool_call_id, name,
     created_at, ts_trusted, plan)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
#: 追加模式的**前缀指纹**：只读 ``(seq, role, 正文长度)``，不读正文 ——
#: 有它就能发现"条数变少 / 角色错位 / 某条长度变了"，而代价是一次小结果集的 SELECT
#: （相对于全量重写的 n 次 INSERT，可以忽略）。
MESSAGE_FINGERPRINT = (
    "SELECT seq, role, length(content) AS content_len FROM messages "
    "WHERE session_id = ? ORDER BY seq"
)
#: 前缀里**最后一条的正文**。只多读一条，用来挡住"条数没变、最后一条被换掉"
#: （``pop_last_assistant()`` 回滚重试那条路径，长度有可能恰好相等）。
LAST_MESSAGE_CONTENT = (
    "SELECT content FROM messages WHERE session_id = ? ORDER BY seq DESC LIMIT 1"
)
UPSERT_SESSION = """
INSERT INTO sessions
    (id, title, model_id, system_prompt, enabled_skills, assistant_id,
     context_summary, context_summary_upto, reasoning_effort,
     message_count, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    title = excluded.title,
    model_id = excluded.model_id,
    system_prompt = excluded.system_prompt,
    enabled_skills = excluded.enabled_skills,
    assistant_id = excluded.assistant_id,
    context_summary = excluded.context_summary,
    context_summary_upto = excluded.context_summary_upto,
    reasoning_effort = excluded.reasoning_effort,
    message_count = excluded.message_count,
    updated_at = excluded.updated_at
"""


@dataclass
class SessionRecord:
    """会话元数据（不含消息体）。"""

    id: str
    title: str = "新对话"
    model_id: str | None = None
    system_prompt: str = ""
    enabled_skills: list[str] | None = None
    assistant_id: str | None = None
    # 早期对话的摘要，以及它覆盖到第几条消息（见 memory/short_term.py）。
    # 必须落库：不存的话重开一个长会话就退回到"模型只能看到最近几条"，
    # 而用户看到的是完整历史 —— 这种不一致会让模型表现得很莫名其妙。
    context_summary: str = ""
    context_summary_upto: int = 0
    # 会话级的思考强度："low" / "medium" / "high"；空表示不发送该参数。
    # 落库是必须的：不存的话重开一个会话就退回"没调过"，而用户明明调过 ——
    # 那种"设置自己变回去了"的现象最容易让人怀疑整个应用。
    reasoning_effort: str | None = None
    message_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


def _plan_to_json(plan: dict[str, Any] | None) -> str | None:
    """把计划落成一列 JSON；没有计划就写 NULL（绝大多数消息如此）。"""
    if not plan:
        return None
    return json.dumps(plan, ensure_ascii=False)


def _plan_from_json(raw: str | None) -> dict[str, Any] | None:
    """读回计划。**损坏一律当没有计划**，不让一条坏数据把整个会话卡死。"""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("消息中的 plan 字段损坏，已忽略: %s", raw[:120])
        return None
    return data if isinstance(data, dict) else None


def _tool_calls_to_json(tool_calls: list[ToolCall] | None) -> str | None:
    if not tool_calls:
        return None
    return json.dumps(
        [
            {
                "id": call.id,
                "name": call.name,
                "arguments": call.arguments,
                "raw_arguments": call.raw_arguments,
            }
            for call in tool_calls
        ],
        ensure_ascii=False,
    )


def _tool_calls_from_json(raw: str | None) -> list[ToolCall] | None:
    if not raw:
        return None
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("消息中的 tool_calls 字段损坏，已忽略: %s", raw[:120])
        return None
    if not isinstance(items, list):
        return None
    calls: list[ToolCall] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        calls.append(
            ToolCall(
                id=str(item.get("id") or ""),
                name=str(item["name"]),
                arguments=item.get("arguments") or {},
                raw_arguments=str(item.get("raw_arguments") or ""),
            )
        )
    return calls or None


class SessionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ------------------------------------------------------------------ #
    # 会话元数据
    # ------------------------------------------------------------------ #
    async def list_sessions(self) -> list[SessionRecord]:
        rows = await self._db.fetch_all(
            "SELECT * FROM sessions ORDER BY updated_at DESC"
        )
        return [self._row_to_record(row) for row in rows]

    async def get_session(self, session_id: str) -> SessionRecord | None:
        row = await self._db.fetch_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return self._row_to_record(row) if row else None

    async def count_sessions(self) -> int:
        row = await self._db.fetch_one("SELECT COUNT(*) AS n FROM sessions")
        return int(row["n"]) if row else 0

    @staticmethod
    def _row_to_record(row: dict[str, Any]) -> SessionRecord:
        raw_skills = row.get("enabled_skills")
        skills: list[str] | None = None
        if raw_skills:
            try:
                parsed = json.loads(raw_skills)
                if isinstance(parsed, list):
                    skills = [str(item) for item in parsed]
            except json.JSONDecodeError:
                skills = None
        return SessionRecord(
            id=row["id"],
            title=row["title"],
            model_id=row.get("model_id"),
            system_prompt=row.get("system_prompt") or "",
            enabled_skills=skills,
            assistant_id=row.get("assistant_id"),
            context_summary=row.get("context_summary") or "",
            context_summary_upto=int(row.get("context_summary_upto") or 0),
            # 空值一律归成 None：列里可能是 ""，而 "" 会被当成"用户选过一个空档位"
            reasoning_effort=row.get("reasoning_effort") or None,
            message_count=int(row.get("message_count") or 0),
            created_at=float(row.get("created_at") or 0),
            updated_at=float(row.get("updated_at") or 0),
        )

    # ------------------------------------------------------------------ #
    # 落盘
    # ------------------------------------------------------------------ #
    async def save_session(
        self,
        record: SessionRecord,
        messages: list[Message] | None = None,
        *,
        mode: str = "replace",
    ) -> None:
        """写入会话元数据；``messages`` 不为 None 时按 ``mode`` 写消息。

        ``mode="replace"``（默认）**整体替换**消息列表 —— 所有会删消息的路径都用它。
        ``mode="append"`` 只追加新增的尾巴，**必须过前缀指纹校验**；
        校验不过就自动退回整体替换（见模块 docstring 与 ``_stored_prefix_len``）。
        """
        enabled = (
            json.dumps(record.enabled_skills, ensure_ascii=False)
            if record.enabled_skills
            else None
        )
        statements: list[tuple[str, tuple[Any, ...]]] = [
            (
                UPSERT_SESSION,
                (
                    record.id,
                    record.title,
                    record.model_id,
                    record.system_prompt,
                    enabled,
                    record.assistant_id,
                    record.context_summary,
                    record.context_summary_upto,
                    record.reasoning_effort,
                    record.message_count,
                    record.created_at,
                    record.updated_at,
                ),
            )
        ]

        if messages is not None:
            now = time.time()
            # 只有确认"库里已存的那一段就是内存里的前缀"时才跳过 DELETE、只写尾巴；
            # 其它一切情况（包括条数变少、前插、就地改写）都退回整体替换。
            #
            # ⚠️ 初值必须是 None（= 走整体替换），不能是 0 ——
            # `None` 才会挂上 DELETE。写成 0 的后果是**所有 replace 调用都不删旧行**，
            # 于是"清空历史""改人设"看起来成功、重启后旧消息全回来了。
            prefix: int | None = None
            if mode == "append":
                prefix = await self._stored_prefix_len(record.id, messages)
                if prefix is None:
                    logger.info(
                        "会话 %s 的消息前缀与库里对不上（疑似回滚/清空/改写），本次退回全量重写",
                        record.id,
                    )
            if prefix is None:
                prefix = 0
                statements.append((DELETE_MESSAGES, (record.id,)))
            # ⚠️ 时间戳取**消息自己**的，不再拿一个 now 盖给所有消息。
            #
            # 这里曾经是"一个 now 盖全部" —— 后果是每轮对话都把整条会话的历史时间
            # 刷成"刚刚"，消息时间戳彻底失去意义（见 db.py 的 SCHEMA_V8 说明）。
            # 消息的 created_at 由 MemoryManager 在它产生的那一刻打上，这里只是带下去。
            #
            # 拿不到时间的（从老库读回来的、system 或引擎合成的提示）标成"不可信"：
            # 读出去时一律当不知道 —— 宁可没有时间，也不能给模型一个假时间。
            statements.extend(
                (
                    INSERT_MESSAGE,
                    (
                        record.id,
                        seq,
                        message.role,
                        message.content,
                        message.reasoning_content,
                        _tool_calls_to_json(message.tool_calls),
                        message.tool_call_id,
                        message.name,
                        message.created_at if message.created_at is not None else now,
                        1 if message.created_at is not None else 0,
                        _plan_to_json(message.plan),
                    ),
                )
                # ``seq`` 沿用它在下标里的值：追加时从 prefix 续上，替换时从 0 开始
                for seq, message in enumerate(messages)
                if seq >= prefix
            )

        await self._db.transaction(statements)

    async def _stored_prefix_len(
        self, session_id: str, messages: list[Message]
    ) -> int | None:
        """库里已存的、与 ``messages`` **逐条对得上**的前缀长度；对不上返回 ``None``。

        ⚠️ 这是 append 模式的**唯一安全阀**，三种情况必须挡下来：

        1. **内存比库里少**（``pop_last_assistant()`` 回滚重试、``memory.clear()``）——
           无脑追加会把已经删掉的消息留在库里，重启后它们**又回来了**；
        2. **角色错位**（改系统提示词会 ``del _messages[0]`` / ``insert(0, ...)``）——
           此时 ``seq`` 整体挪位，追加会把内容插到错误的序号上；
        3. **某条被就地改写**（长度会变）。

        还要单独比一次**最后一条的正文**：``pop_last_assistant()`` 之后引擎会补一条新的
        assistant 消息，条数不变、长度可能恰好相等 —— 只比长度的话就会把旧内容留在库里。

        ⚠️ **已知残余**：中间某条消息被改成**长度完全相同**的内容时这里发现不了
        （要发现就得把全部正文读回来比对，那又回到 O(n)）。当前代码里没有这种路径
        （聊天界面没有"重新生成"，``_messages`` 的元素只在尾部增删），
        将来若加了就地改写，必须同时把这里改成整体替换。
        """
        rows = await self._db.fetch_all(MESSAGE_FINGERPRINT, (session_id,))
        if len(rows) > len(messages):
            return None
        for index, row in enumerate(rows):
            message = messages[index]
            if row["role"] != message.role:
                return None
            if int(row.get("content_len") or 0) != len(message.content or ""):
                return None
        if rows:
            last = await self._db.fetch_one(LAST_MESSAGE_CONTENT, (session_id,))
            if last is None or (last.get("content") or "") != (
                messages[len(rows) - 1].content or ""
            ):
                return None
        return len(rows)

    async def load_messages(self, session_id: str) -> list[Message]:
        rows = await self._db.fetch_all(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY seq", (session_id,)
        )
        return [
            Message(
                role=row["role"],
                content=row["content"] or "",
                tool_calls=_tool_calls_from_json(row.get("tool_calls")),
                tool_call_id=row.get("tool_call_id"),
                name=row.get("name"),
                reasoning_content=row.get("reasoning_content") or "",
                # 只有标了可信的才把时间带回去：老行里那个时间"最后一次保存的时刻"，
                # 不是这条消息产生的时刻 —— 带出去等于让模型把旧事当当下（见 SCHEMA_V8）。
                created_at=float(row["created_at"]) if row.get("ts_trusted") else None,
                # 老行没有 plan 列的值（迁移前写入的），取到 None 即"这条消息没有计划"
                plan=_plan_from_json(row.get("plan")),
            )
            for row in rows
        ]

    async def clear_messages(self, session_id: str, *, updated_at: float | None = None) -> None:
        await self._db.transaction(
            [
                (DELETE_MESSAGES, (session_id,)),
                (
                    "UPDATE sessions SET message_count = 0, updated_at = ? WHERE id = ?",
                    (updated_at or time.time(), session_id),
                ),
            ]
        )

    async def delete_session(self, session_id: str) -> bool:
        existing = await self.get_session(session_id)
        if existing is None:
            return False
        # messages 表有 ON DELETE CASCADE，但依赖 PRAGMA foreign_keys 生效，
        # 这里显式再删一次，避免 pragma 被意外关掉时留下孤儿消息。
        await self._db.transaction(
            [
                (DELETE_MESSAGES, (session_id,)),
                ("DELETE FROM sessions WHERE id = ?", (session_id,)),
            ]
        )
        return True

    async def delete_sessions(self, session_ids: list[str]) -> int:
        """批量删除会话。

        原先是逐个 ``delete_session``，每个会话要两次往返（查存在性 + 事务），
        删 50 个就是 100 次数据库往返。这里改成「先一次查存在性、再一次事务删完」，
        往返次数与**会话数无关**。
        """
        if not session_ids:
            return 0

        placeholders = ",".join("?" for _ in session_ids)
        params = tuple(session_ids)
        rows = await self._db.fetch_all(
            f"SELECT id FROM sessions WHERE id IN ({placeholders})", params
        )
        existing = [str(row["id"]) for row in rows]
        if not existing:
            return 0

        # 只删真实存在的那些：返回的 deleted 才能反映实际删掉的条数，
        # 调用方（界面）据此提示"已删除 N 个会话"
        placeholders = ",".join("?" for _ in existing)
        params = tuple(existing)
        # messages 有 ON DELETE CASCADE，但依赖 PRAGMA foreign_keys 生效；
        # 显式删一次，避免 pragma 被意外关掉时留下孤儿消息
        await self._db.transaction(
            [
                (f"DELETE FROM messages WHERE session_id IN ({placeholders})", params),
                (f"DELETE FROM sessions WHERE id IN ({placeholders})", params),
            ]
        )
        return len(existing)

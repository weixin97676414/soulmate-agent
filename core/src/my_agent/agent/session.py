"""会话管理。

对应《智能体框架开发文档》7.6 节。每个会话拥有独立的记忆与 Agent 参数，
从而实现多会话隔离。

**持久化策略**（P1 引入）：
- 启动时只从数据库载入**会话元数据**（标题、模型、消息数），不载入消息体——
  否则用户有几百个历史会话时会拖慢启动；
- 消息在首次访问该会话时**懒加载**，此后常驻内存；
- 每轮对话结束后由服务层调用 ``persist()`` 整体替换该会话的消息，
  保证数据库与内存始终一致。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..errors import SessionNotFoundError
from ..memory.short_term import MemoryManager, is_internal

logger = logging.getLogger(__name__)

DEFAULT_SESSION_TTL = 60 * 60 * 24 * 7  # 仅用于内存缓存回收，不影响数据库


@dataclass
class Session:
    id: str
    title: str = "新对话"
    model_id: str | None = None
    system_prompt: str = ""
    enabled_skills: set[str] | None = None
    assistant_id: str | None = None
    # 会话级的思考强度："low" / "medium" / "high"；None = 不发送该参数
    reasoning_effort: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    memory: MemoryManager = field(default_factory=MemoryManager)
    # 未加载消息体时用它给界面展示正确的消息数
    message_count: int = 0
    # 上下文摘要的**数据库快照**。
    #
    # 运行期的唯一真相来源是 ``memory``（见 persist 里的同步），这两个字段只负责
    # 「懒加载之前把摘要带回来」。分开的原因见 _ensure_loaded 与 persist 的注释。
    context_summary: str = ""
    context_summary_upto: int = 0
    # 同一会话的对话必须**串行**执行。
    #
    # 一个 Session 只有一个 MemoryManager 实例，而 /v1/chat 每次都拿它新建
    # Agent。并发请求会交错 add_user/add_assistant/add_tool，并且各自的收尾
    # 都会 persist（整体替换消息），后写的把先写的**整轮覆盖掉** ——
    # LLM 上下文错乱 + 对话丢失。
    #
    # 锁的持有范围是「跑 Agent + 落盘」的完整周期，见 routes/chat.py。
    # 注意这是**会话级**锁而不是全局锁：不同会话之间仍然完全并行。
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self) -> None:
        self.updated_at = time.time()

    def apply_assistant(self, profile: Any) -> None:
        """把会话切换到某个助手。

        **刻意不清空历史。** 换人设时清库看起来"干净"，但代价是毁掉用户
        正在进行的对话，且不可逆。实际上也不需要：``Agent.run_stream``
        每轮都会调 ``memory.ensure_system()`` 就地替换 system 消息，
        列表里永远只有一条 system，不存在"两套人设"共存的问题。

        模型只在助手明确指定时才覆盖，留空表示"跟随全局默认"，
        不会把用户当前选的模型抹掉。
        """
        self.assistant_id = profile.id
        self.system_prompt = profile.system_prompt
        # ⚠️ 这里存的是"用户勾了哪几个"的**原始记录**，不是"实际可用的技能"。
        # 新口径下它为空表示"一个都没勾"，**不等于"全开"**（
        # "没有默认加载全部技能的搭子了"）。实际可用集合由
        # `SkillManager.allowed_names` 在装配时展开（内置 ∪ 自己的专属 ∪ 勾选的通用/我的），
        # 见 `skill/groups.py`；这里保留 ``None`` 只是不去动历史数据的表示。
        self.enabled_skills = set(profile.enabled_skills) or None
        if profile.model_id:
            self.model_id = profile.model_id
        # 思考强度：搭子设过就作为**会话默认**，单聊也能生效。
        #
        # 只在搭子**真的设过**时才写：留空表示"跟随全局"，不该把用户在输入框上
        # 手动选的档位抹掉。
        #
        # 顺序上也安全 —— ``routes/chat.py`` 里客户端显式传来的档位是在
        # 调用本方法**之后**才写入的（而且它只在客户端真的带了该字段时才改），
        # 所以"用户这一轮手动选的"永远优先于"搭子的默认值"。
        if getattr(profile, "reasoning_effort", None):
            self.reasoning_effort = profile.reasoning_effort
        self.touch()

    def auto_title(self, first_message: str) -> None:
        """用首条用户消息生成标题（P4 可改为让模型总结）。"""
        if self.title != "新对话" or not first_message.strip():
            return
        text = " ".join(first_message.strip().split())
        self.title = text[:24] + ("…" if len(text) > 24 else "")

    def recount(self) -> int:
        """按当前记忆重算「界面上可见的消息数」（不含 system 与 tool）。"""
        self.message_count = sum(
            1 for message in self.memory.messages if message.role in ("user", "assistant")
        )
        return self.message_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "model_id": self.model_id,
            "assistant_id": self.assistant_id,
            # 前端要拿它回显"这个对话的思考强度"，所以必须一起返回 ——
            # 否则重开对话时控件显示"未设置"，而用户明明调过
            "reasoning_effort": self.reasoning_effort,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
        }

    def history(self) -> list[dict[str, Any]]:
        """导出给前端的消息列表（跳过 system、工具消息与引擎合成的内部提示）。"""
        out: list[dict[str, Any]] = []
        for message in self.memory.messages:
            if message.role not in ("user", "assistant"):
                continue
            if message.role == "assistant" and not message.content and not message.plan:
                # 只有工具调用的中间态不展示。
                # ⚠️ 带计划的那条**必须放行**：计划阶段的第一次 add_assistant 可能是
                # 空正文（模型直接去调工具了），若按"空正文就跳过"滤掉，用户重开对话
                # 就再也看不到那张计划卡片 —— 而他自己是点过「开始执行」的。
                continue
            if message.role == "user" and is_internal(message.content):
                continue  # 「空回复催促语」之类的合成消息，用户没发过
            # created_at 一并给前端：气泡上显示的时间就用它。
            # None = 不知道（更早版本落盘的老消息）—— 那种情况界面上不显示时间，
            # 而不是拿一个假的时间糊上去。
            item: dict[str, Any] = {
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
            }
            # 计划只在有值时带上：老消息没有它，前端见不到就不画卡片
            if message.plan:
                item["plan"] = message.plan
            out.append(item)
        return out


class SessionManager:
    """多会话容器，可选接入持久化仓储。"""

    def __init__(
        self,
        *,
        repository: Any = None,
        ttl_seconds: int = DEFAULT_SESSION_TTL,
        on_persist_error: Callable[[Session, Exception], None] | None = None,
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._repo = repository
        self._ttl = ttl_seconds
        # 记录「内存中的消息与数据库一致」的会话；不在集合里表示需要懒加载
        self._loaded: set[str] = set()
        # 落盘失败的外部通知。**没有它，失败就是完全静默的**：
        # 内存认为已保存、界面显示正常，而重启后发现这一轮对话没了 ——
        # 用户只会觉得"这软件会丢数据"，却完全无从下手。
        self._on_persist_error = on_persist_error

    @property
    def persistent(self) -> bool:
        return self._repo is not None

    # ------------------------------------------------------------------ #
    # 启动载入
    # ------------------------------------------------------------------ #
    async def initialize(self) -> int:
        """从数据库恢复会话列表（仅元数据）。"""
        if self._repo is None:
            return 0
        records = await self._repo.list_sessions()
        for record in records:
            self._sessions[record.id] = Session(
                id=record.id,
                title=record.title,
                model_id=record.model_id,
                system_prompt=record.system_prompt,
                enabled_skills=set(record.enabled_skills) if record.enabled_skills else None,
                assistant_id=record.assistant_id,
                reasoning_effort=record.reasoning_effort,
                created_at=record.created_at,
                updated_at=record.updated_at,
                message_count=record.message_count,
                context_summary=record.context_summary,
                context_summary_upto=record.context_summary_upto,
            )
        if records:
            logger.info("已恢复 %s 个历史会话", len(records))
        return len(records)

    # ------------------------------------------------------------------ #
    # 增删查
    # ------------------------------------------------------------------ #
    async def create(
        self, *, model_id: str | None = None, title: str = "新对话"
    ) -> Session:
        session = Session(id=uuid.uuid4().hex[:12], title=title, model_id=model_id)
        self._sessions[session.id] = session
        self._loaded.add(session.id)
        await self.persist(session, include_messages=True)
        return session

    async def get(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(f"会话不存在或已过期: {session_id}")
        await self._ensure_loaded(session)
        return session

    async def get_or_create(
        self, session_id: str | None, *, model_id: str | None = None
    ) -> Session:
        if not session_id:
            return await self.create(model_id=model_id)

        session = self._sessions.get(session_id)
        if session is None:
            session = await self._restore_or_create(session_id, model_id=model_id)
        await self._ensure_loaded(session)
        return session

    async def _restore_or_create(
        self, session_id: str, *, model_id: str | None = None
    ) -> Session:
        """把数据库里的会话重新载入内存；**确认不存在**才新建。

        这里必须先查库。会话不在 `_sessions` 里不代表它不存在 ——
        内存缓存被回收（``evict_expired``）或换了数据库文件时，
        数据库里仍有完整记录。如果直接按同一 id 新建一个空会话并
        ``persist(include_messages=True)``，而 ``save_session`` 是
        「先 DELETE 再 INSERT」，就会把这个会话的历史消息**全部删掉**。
        这类静默数据丢失比报错更难发现，所以宁可多查一次库。
        """
        record = None
        if self._repo is not None:
            record = await self._repo.get_session(session_id)

        if record is not None:
            session = Session(
                id=record.id,
                title=record.title,
                model_id=record.model_id or model_id,
                system_prompt=record.system_prompt,
                enabled_skills=set(record.enabled_skills) if record.enabled_skills else None,
                assistant_id=record.assistant_id,
                reasoning_effort=record.reasoning_effort,
                created_at=record.created_at,
                updated_at=record.updated_at,
                message_count=record.message_count,
                context_summary=record.context_summary,
                context_summary_upto=record.context_summary_upto,
            )
            # 刻意**不**加入 _loaded：元数据已就绪，但消息体仍需懒加载
            self._sessions[session_id] = session
            logger.info("会话 %s 已从数据库重新载入内存", session_id)
            return session

        # 前端传来了一个确实不存在的 session_id（例如换了数据库），
        # 按该 id 新建，保证对话不中断。
        session = Session(id=session_id, model_id=model_id)
        self._sessions[session_id] = session
        self._loaded.add(session_id)
        await self.persist(session, include_messages=True)
        return session

    def list(self) -> list[dict[str, Any]]:
        sessions = sorted(self._sessions.values(), key=lambda item: item.updated_at, reverse=True)
        return [session.to_dict() for session in sessions]

    async def rename(self, session_id: str, title: str) -> Session:
        session = await self.get(session_id)
        session.title = title.strip() or session.title
        session.touch()
        await self.persist(session)
        return session

    async def update_meta(
        self,
        session_id: str,
        *,
        model_id: str | None = None,
        system_prompt: str | None = None,
        enabled_skills: set[str] | None = None,
    ) -> Session:
        session = await self.get(session_id)
        if model_id is not None:
            session.model_id = model_id
        if system_prompt is not None:
            session.system_prompt = system_prompt
            # 系统提示词变了，历史上下文必须重来，否则模型会看到两套人设
            session.memory.clear(keep_system=False)
        if enabled_skills is not None:
            session.enabled_skills = enabled_skills or None
        session.touch()
        await self.persist(session, include_messages=system_prompt is not None)
        return session

    async def delete(self, session_id: str) -> bool:
        existed = self._sessions.pop(session_id, None) is not None
        self._loaded.discard(session_id)
        if self._repo is not None:
            removed = await self._repo.delete_session(session_id)
            return existed or removed
        return existed

    async def delete_many(self, session_ids: list[str]) -> int:
        # 注意：生成器表达式里不能 await，这里必须写成显式循环
        deleted = 0
        for session_id in session_ids:
            if await self.delete(session_id):
                deleted += 1
        return deleted

    async def clear_history(self, session_id: str) -> Session:
        session = await self.get(session_id)
        session.memory.clear(keep_system=True)
        session.recount()
        session.touch()
        await self.persist(session, include_messages=True)
        return session

    # ------------------------------------------------------------------ #
    # 持久化
    # ------------------------------------------------------------------ #
    async def _ensure_loaded(self, session: Session) -> None:
        if session.id in self._loaded:
            return
        if self._repo is None:
            self._loaded.add(session.id)
            return
        messages = await self._repo.load_messages(session.id)
        # 摘要必须一起恢复：否则重开一个长会话时，模型只能看到最近几条消息，
        # 而界面上用户看到的是完整历史 —— 模型会突然"忘记"早先的约定，
        # 表现得像是变笨了，而不是缺少上下文
        session.memory.replace(
            messages,
            summary=session.context_summary,
            summary_upto=session.context_summary_upto,
        )
        self._loaded.add(session.id)

    async def persist(
        self,
        session: Session,
        *,
        include_messages: bool = False,
        mode: str = "replace",
    ) -> None:
        """把会话写回数据库。

        ``include_messages`` 为真时同时写消息，**写法由 ``mode`` 决定**：

        * ``"replace"``（默认）：整体替换。**所有会删消息的路径都必须用它** ——
          ``clear_history()``、改系统提示词（先 ``memory.clear()`` 再落盘）、
          新建会话都靠"先 DELETE 再 INSERT"把旧行删干净。
        * ``"append"``：只追加内存里新增的尾巴（对话增长路径用它，见
          ``AppRuntime.persist_session``）。库里存着的前缀与内存对不上时会**自动
          退回整体替换**，所以它不会把已删消息留在库里。

        两者都只是"怎么写"，可选值刻意不做成常量枚举：调用点只有两处语义明确的场景，
        传错时 ``save_session`` 会按默认的 ``replace`` 走（安全的那一侧）。
        """
        if self._repo is None:
            return
        if session.id in self._loaded:
            # 内存是摘要的唯一真相来源。**只在已加载时同步**：
            # 未加载的会话 memory 是空的，无脑同步会让一次 rename / 改标题
            # 就把数据库里已有的摘要抹成空字符串。
            session.context_summary = session.memory.summary
            session.context_summary_upto = session.memory.summary_upto
        session.recount()
        record = self._to_record(session)
        try:
            await self._repo.save_session(
                record,
                session.memory.messages if include_messages else None,
                mode=mode if include_messages else "replace",
            )
        except Exception as exc:  # noqa: BLE001
            # 落盘失败不应中断正在进行的对话，但**必须让用户知道**：
            # 只写日志的话，界面一切正常，直到重启才发现这一轮对话没了
            logger.error("会话落盘失败 session=%s: %s", session.id, exc)
            if self._on_persist_error is not None:
                # 通知本身出问题不能盖住原始错误，也不能再往上抛
                with contextlib.suppress(Exception):
                    self._on_persist_error(session, exc)

    @staticmethod
    def _to_record(session: Session):
        from ..storage.sessions import SessionRecord

        return SessionRecord(
            id=session.id,
            title=session.title,
            model_id=session.model_id,
            system_prompt=session.system_prompt,
            enabled_skills=sorted(session.enabled_skills) if session.enabled_skills else None,
            assistant_id=session.assistant_id,
            reasoning_effort=session.reasoning_effort,
            context_summary=session.context_summary,
            context_summary_upto=session.context_summary_upto,
            message_count=session.message_count,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    # ------------------------------------------------------------------ #
    # 内存回收
    # ------------------------------------------------------------------ #
    def evict_expired(self) -> int:
        """只回收内存缓存，**不删除数据库记录**。"""
        now = time.time()
        expired = [
            key
            for key, session in self._sessions.items()
            if now - session.updated_at > self._ttl and key in self._loaded
        ]
        for key in expired:
            del self._sessions[key]
            self._loaded.discard(key)
        return len(expired)

    def __len__(self) -> int:
        return len(self._sessions)

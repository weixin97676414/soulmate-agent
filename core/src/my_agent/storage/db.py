"""SQLite 连接与表结构管理。

设计取舍：
- **不引入 aiosqlite**：本项目写入量很小（每轮对话几行），用
  ``asyncio.to_thread`` 把同步 sqlite3 调用挪到线程池，配合一把
  ``asyncio.Lock`` 串行化，既不阻塞事件循环也不引入额外依赖；
- **WAL 模式**：读写不互相阻塞，异常退出后也能恢复；
- **版本化迁移**：用 ``PRAGMA user_version`` 记录版本，升级时按需执行迁移。
"""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 13

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS sessions (
    id             TEXT PRIMARY KEY,
    title          TEXT NOT NULL DEFAULT '新对话',
    model_id       TEXT,
    system_prompt  TEXT NOT NULL DEFAULT '',
    enabled_skills TEXT,
    message_count  INTEGER NOT NULL DEFAULT 0,
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT NOT NULL,
    seq               INTEGER NOT NULL,
    role              TEXT NOT NULL,
    content           TEXT NOT NULL DEFAULT '',
    reasoning_content TEXT NOT NULL DEFAULT '',
    tool_calls        TEXT,
    tool_call_id      TEXT,
    name              TEXT,
    created_at        REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, seq);

CREATE TABLE IF NOT EXISTS audit_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ts               REAL NOT NULL,
    session_id       TEXT,
    skill_name       TEXT NOT NULL,
    permission_level TEXT NOT NULL DEFAULT 'safe',
    params           TEXT,
    status           TEXT NOT NULL,
    duration_ms      REAL,
    detail           TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id);

CREATE TABLE IF NOT EXISTS files (
    id            TEXT PRIMARY KEY,
    original_name TEXT NOT NULL,
    kind          TEXT NOT NULL DEFAULT 'upload',
    size          INTEGER NOT NULL DEFAULT 0,
    mime          TEXT,
    session_id    TEXT,
    note          TEXT,
    created_at    REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_created ON files(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_files_kind ON files(kind, created_at DESC);
"""

SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS expenses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    amount     REAL NOT NULL,
    category   TEXT NOT NULL DEFAULT '其他',
    note       TEXT,
    spent_on   TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(spent_on DESC);
CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);

CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content     TEXT NOT NULL,
    remind_at   REAL NOT NULL,
    base_at     REAL NOT NULL,
    advance_min INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  REAL NOT NULL,
    fired_at    REAL
);

CREATE INDEX IF NOT EXISTS idx_reminders_at ON reminders(remind_at);
CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status, remind_at);
"""

# v3：会话记录它用的是哪个助手（切换助手后会话列表与重开对话都能延续）
SCHEMA_V3 = """
ALTER TABLE sessions ADD COLUMN assistant_id TEXT;
"""

# v4：Token 用量与费用流水。
#
# 单独一张表而不是塞进 messages 或 audit_log：
# - 一次对话有**多轮**模型调用，用量是"每次调用的量"，不是"每条消息的量"；
# - 审计可以按保留期清理，用量需要长期留存才能做月度统计，两者生命周期不同。
#
# cached_tokens（缓存命中）必须单独存：它的单价可能只有未命中的 1/10，
# 不分开记就永远算不准费用，也无法验证前缀缓存优化是否生效。
SCHEMA_V4 = """
CREATE TABLE IF NOT EXISTS usage_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT,
    trace_id            TEXT,
    model_id            TEXT,
    provider            TEXT,
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    completion_tokens   INTEGER NOT NULL DEFAULT 0,
    cached_tokens       INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens  INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens    INTEGER NOT NULL DEFAULT 0,
    cost                REAL,
    currency            TEXT NOT NULL DEFAULT 'CNY',
    duration_ms         REAL,
    iterations          INTEGER NOT NULL DEFAULT 0,
    created_at          REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_log(created_at);
CREATE INDEX IF NOT EXISTS idx_usage_session ON usage_log(session_id);
CREATE INDEX IF NOT EXISTS idx_usage_model ON usage_log(model_id, created_at);
"""

# v5：长期对话的上下文摘要。
#
# 超长对话不能只靠"丢掉最旧的消息"——那会让模型对早期约定（用户偏好、
# 已确认的文件名、已排除的方案）彻底失忆。压缩成一段摘要后：
# - 早期信息保住；
# - 消息条数大幅减少，每轮请求的输入成本下降；
# - 只在**超限时压一次**，不是每轮都压，所以不会把成本翻倍。
#
# ``context_summary_upto`` 记录摘要覆盖到第几条消息（含 system，从 0 数），
# 这样重新打开会话时能精确复原"哪些消息已经进过摘要"，不必重新计算。
SCHEMA_V5 = """
ALTER TABLE sessions ADD COLUMN context_summary TEXT;
ALTER TABLE sessions ADD COLUMN context_summary_upto INTEGER NOT NULL DEFAULT 0;
"""

# v6：会话级的"思考强度"。
#
# 放在会话上而不是全局设置里：用户对"这一轮值不值得多想一会儿"的判断是按对话来的
# —— 需要琢磨的那条对话调"高"，随口问问的那条不调。而且切走再回来应当保持上次的选择。
#
# 允许为空：为空表示**不发送**这个参数（多数网关不认识它），而不是"用默认值"。
SCHEMA_V6 = """
ALTER TABLE sessions ADD COLUMN reasoning_effort TEXT;
"""

# v7：群聊记录持久化。
#
# 群聊原先只有内存态（`runtime._group_history`）—— 用户切走页面再回来、
# 或者重启应用，讨论记录就没了（反馈 #6）。这里把它落库。
#
# **为什么存"事件"而不是存"消息"**：前端渲染群聊本来就是在消费一串 SSE 事件
# （topic / speaker / delta / message / vote …）。把事件原样存下来，恢复时
# 直接重放一遍即可复用同一套渲染逻辑，不需要为"从数据库读"再写一条并行的
# 构造路径（两条路径迟早会长歪）。
#
# ⚠️ **`delta`（逐字分片）不落库**：一条发言能产生上千个分片，
# 存下来既没意义、又会把库撑爆。真正的内容在收尾的 `message` / `summary`
# 事件里是完整的，重放时天然还原。
SCHEMA_V7 = """
CREATE TABLE IF NOT EXISTS group_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id   TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    event      TEXT NOT NULL,
    data       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_group_events_group ON group_events(group_id, seq);
"""

# v8：消息时间戳的**可信标记**。
#
# 背景（这是个真缺陷，不是优化）：v8 之前落盘是「整表删除 + 重插」，写的时候用一个
# `now` 盖给该会话的**所有**消息。于是 `messages.created_at` 列里有值，但值是
# "最后一次保存的时刻"——每次对话都会把所有历史消息的时间一起刷新，而且同一条会话
# 里所有消息的时间**完全一样**。读的时候又根本不把它读回来。
#
# 为什么必须标出来而不能就这么用：用户要的是"记忆有时间维度，AI 能分清现在和以前"。
# 拿这种假时间喂给模型，比不给时间更糟 —— 它会把三个月前的事按"刚才"来讲。
#
# 老数据**无法还原**（真实发生时刻从来没有被记下来），所以这里不伪造：
# 新写入的行标 1，老行保持默认 0；读出来时 0 一律按"不知道"处理（不给模型加时间
# 前缀、界面也不显示时间）。老会话照样能用，只是没有时间维度。
SCHEMA_V8 = """
ALTER TABLE messages ADD COLUMN ts_trusted INTEGER NOT NULL DEFAULT 0;
"""

# v9：未完成运行的进度（断点续跑）。
#
# 用户的要求：「任务跑到一半某个搭子挂了、或用户手动叫停，要能保存进度、下次接着跑，
# 别一次失败全白干」。原先定时任务中途失败**完全不落盘**（只在整轮跑完后才 persist），
# 群讨论与单聊也没有"进度"这个概念。
#
# 这张表**只存没跑完的**：正常结束就把行删掉（不需要续跑），失败/叫停才留下
# "跑到第几步、最后做了什么、接着哪个会话"。语义清楚了，它就不会无限增长。
# 而"历史上失败过哪些"归 audit_log —— 一个要能删，一个要可查，别混在一起。
SCHEMA_V9 = """
CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    ref_id      TEXT NOT NULL DEFAULT '',
    session_id  TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'running',
    step        INTEGER NOT NULL DEFAULT 0,
    last_action TEXT NOT NULL DEFAULT '',
    error       TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_updated ON runs(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_kind ON runs(kind, ref_id);
"""

# v10：把留痕从"只记技能调用"扩到**全量实体操作**。
#
# 用户的要求是：「操作留痕可回溯：哪个搭子在什么时候做了什么，出了问题能查」。
# 原先 audit_log 只覆盖技能/工具调用那一层 —— 搭子/群/会话/任务的增删改、群讨论的
# 起止、定时任务的每次执行、用户叫停，**全都没有留痕**。
#
# 为什么加列而不是另起一张表：这两类记录用户要在**同一个地方**按时间排着看
# （"九点半那个任务失败前，他先删了个会话" —— 跨表的顺序看不出来）。
# 用 ``kind`` 区分来源即可：skill / assistant / group / session / task / permission。
#
# ``skill_name`` 对实体操作留空字符串（列是 NOT NULL）：空即"这不是一次技能调用"。
SCHEMA_V10 = """
ALTER TABLE audit_log ADD COLUMN kind TEXT NOT NULL DEFAULT 'skill';
ALTER TABLE audit_log ADD COLUMN actor_id TEXT;
ALTER TABLE audit_log ADD COLUMN action TEXT;
ALTER TABLE audit_log ADD COLUMN target TEXT;
"""

# v11：内置搭子改过 id（office → RelationBuddy、lovebuddy → LoveBuddy），
# 会话归属列里存的是旧 id，不改的话升级用户的历史会话会"找不到搭子"
# （会话栏显示不出搭子名、点开会话也关联不上人设）。
#
# **只迁移"当前数据"，不改写审计历史**：``audit_log`` 里记的是"当时确实发生了
# 这件事"，改写它等于篡改记录；历史记录的搭子名靠 ``AssistantsConfig.get`` 里的
# 旧 id → 新 id 兜底解析（见 config/schemas.py）。
#
# 为什么用 UPDATE ... WHERE 旧值：天然幂等（跑第二次匹配不到任何行），
# 而且**非破坏** —— 不认得的值一个都不动。
SCHEMA_V11 = """
UPDATE sessions SET assistant_id = 'RelationBuddy' WHERE assistant_id = 'office';
UPDATE sessions SET assistant_id = 'LoveBuddy' WHERE assistant_id = 'lovebuddy';
"""

# v12：助手消息上挂"执行计划"。
#
# 用户的要求：「计划随消息存进会话，重开对话还能看到当时的分步与完成情况」。
# 计划（目标 + 步骤 + 每步状态）是**过程性内容**，与正文分开存一列 JSON，
# 这样重开对话时能原样把那张卡片画回来。
#
# 为什么不用新表：它**从属于**某一条消息，生命周期完全一致（消息删了计划就该没），
# 单独建表只会多一次 join 与一套外键约束，换不来任何东西。
#
# 老数据 plan 为 NULL —— 前端见不到计划就不渲染卡片，与「没有过计划」表现一致。
SCHEMA_V12 = """
ALTER TABLE messages ADD COLUMN plan TEXT;
"""

# v13：群聊的「多对话」。
#
# 在此之前一个群只有**一条**事件流 —— `group_events` 的唯一分组键就是
# `group_id`。现在给它加一条 `thread_id`，语义与单聊的 `sessions` 一一对应
# （产品要求："每个群可能产生多个对话"）。
#
# ## 为什么是「新表 + 加列」而不是「只加列」
#
# 对话本身要存**标题和时间**（列表里要显示），而事件表是追加型的：
# 靠 `SELECT DISTINCT thread_id` 只能派生出 id 与首末时间，标题得再去捞首条
# `topic` 事件，还拿不到"刚建好、还没说话"的空对话。所以另起一张
# `group_threads`，与单聊的 `sessions` 表同构 —— 那张表已经证明了这个形状够用。
#
# ## ⚠️ 老数据怎么办（本次最要紧的一点）
#
# `thread_id` 的默认值是**空串**，所以升级时既有事件行会全部落进 `''`。
# 后端把 `''` 视为"默认对话"（见 GroupThreadRepository 与 routes/groups.py），
# 于是**历史群消息一条都不会丢**，只是被归进一条对话里。
#
# 反过来说：这里若是让老行变成 NULL、或者建完列再用 `WHERE thread_id = ?`
# 去查而不兜底空串，那些行就全成了孤儿 —— 用户升级后看到的是
# "我群里的历史全没了"。这个字段的默认值是**数据安全的边界**，不要改。
SCHEMA_V13 = """
CREATE TABLE IF NOT EXISTS group_threads (
    id         TEXT PRIMARY KEY,
    group_id   TEXT NOT NULL,
    title      TEXT NOT NULL DEFAULT '新对话',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_group_threads_group ON group_threads(group_id, updated_at DESC);

ALTER TABLE group_events ADD COLUMN thread_id TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_group_events_thread ON group_events(group_id, thread_id, seq);
"""

# 版本号 -> 该版本要执行的建表脚本。升级时按序执行缺失的版本。
MIGRATIONS: dict[int, str] = {
    1: SCHEMA_V1,
    2: SCHEMA_V2,
    3: SCHEMA_V3,
    4: SCHEMA_V4,
    5: SCHEMA_V5,
    6: SCHEMA_V6,
    7: SCHEMA_V7,
    8: SCHEMA_V8,
    9: SCHEMA_V9,
    10: SCHEMA_V10,
    11: SCHEMA_V11,
    12: SCHEMA_V12,
    13: SCHEMA_V13,
}

# 用来判断 ALTER TABLE ADD COLUMN 是否已经生效过（见 _already_applied）
_ADD_COLUMN = re.compile(
    r"ALTER\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*)\s+ADD\s+COLUMN\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def _split_statements(script: str) -> list[str]:
    """把迁移脚本拆成单条语句。

    刻意**不用** ``executescript``：它会在执行前隐式提交当前事务，
    于是「DDL 和 user_version」就没法作为一个原子单元提交了（见 _migrate）。
    迁移脚本里没有含分号的字符串字面量，按 ``;`` 拆是安全的。
    """
    return [chunk.strip() for chunk in script.split(";") if chunk.strip()]


def _already_applied(conn: sqlite3.Connection, statement: str) -> bool:
    """ALTER TABLE ADD COLUMN 是否已经生效过。

    兜住「上一次迁移执行了 DDL 但没能提交 user_version」的残留状态：
    这种情况重放迁移会报 ``duplicate column name``，让整个库初始化失败。
    CREATE TABLE / CREATE INDEX 都带 IF NOT EXISTS，不需要这道检查。
    """
    matched = _ADD_COLUMN.match(statement.strip())
    if not matched:
        return False
    table, column = matched.group(1), matched.group(2)
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.Error:
        return False
    return any(row["name"] == column for row in rows)


class DatabaseError(RuntimeError):
    """数据库操作失败。"""


class Database:
    """极简异步 SQLite 封装。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    async def connect(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._connect_sync)

    def _connect_sync(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.Error as exc:  # pragma: no cover
            conn.close()
            raise DatabaseError(f"初始化 SQLite 失败: {exc}") from exc
        try:
            self._migrate(conn)
        except sqlite3.Error as exc:
            # 迁移失败必须关掉连接：否则连接泄漏，而且后续每个操作都会撞在
            # 一个"迁到一半"的库上，错误信息会越来越难懂。
            conn.close()
            raise DatabaseError(f"数据库迁移失败: {exc}") from exc
        self._conn = conn
        logger.info("SQLite 已就绪: %s", self.path)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """按版本号顺序补齐缺失的迁移。

        用逐版本累加而不是"一把梭最新建表语句"，是为了让已经跑过早期版本的
        用户升级时不会丢掉数据（老库的 user_version=1，只需要补执行 v2）。

        **每个版本一个事务，DDL 与 user_version 一起提交。**

        这不是洁癖：``executescript`` 会在执行前隐式提交，于是「ALTER 已执行、
        user_version 还没写」之间存在一个真实的崩溃窗口。断电或强杀正好落在
        那里的话，下次启动会重放同一个迁移，``ALTER TABLE ... ADD COLUMN``
        直接报 ``duplicate column name`` → 数据库初始化失败 →
        ``runtime.initialize`` 兜底降级成**纯内存模式** → 用户的历史会话
        全部"消失"。这类问题平时完全测不到，只有崩溃时才浮现。
        """
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= SCHEMA_VERSION:
            return

        for target in range(version + 1, SCHEMA_VERSION + 1):
            script = MIGRATIONS.get(target)
            if not script:
                continue
            try:
                conn.execute("BEGIN IMMEDIATE")
                for statement in _split_statements(script):
                    if _already_applied(conn, statement):
                        logger.warning("迁移 v%s 的目标列已存在，跳过: %s", target, statement)
                        continue
                    conn.execute(statement)
                # user_version 不能用参数占位符，只能拼字符串；
                # target 来自 range(...)，是受控整数，没有注入面。
                # 它参与事务，所以和上面的 DDL 是同生共死的。
                conn.execute(f"PRAGMA user_version = {target}")
                conn.commit()
            except sqlite3.Error:
                conn.rollback()
                raise
            logger.info("已应用数据库迁移 v%s", target)

    async def close(self) -> None:
        async with self._lock:
            if self._conn is None:
                return
            await asyncio.to_thread(self._conn.close)
            self._conn = None

    @property
    def connected(self) -> bool:
        return self._conn is not None

    # ------------------------------------------------------------------ #
    # 操作
    # ------------------------------------------------------------------ #
    async def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        async with self._lock:
            await asyncio.to_thread(self._execute_sync, sql, params)

    def _execute_sync(self, sql: str, params: Sequence[Any]) -> None:
        conn = self._require()
        try:
            conn.execute(sql, params)
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"SQL 执行失败: {exc}") from exc

    async def insert(self, sql: str, params: Sequence[Any] = ()) -> int:
        """执行一条 INSERT 并返回新行的 rowid。

        用来取代「INSERT 之后 ``SELECT ... ORDER BY id DESC LIMIT 1``」这种写法：
        两次调用之间隔着 await，并发时后一次会把**别人的**那条取回来。
        取错记录不会报错，只会把张冠李戴的数据返回给用户 —— 记账金额串到
        另一个人头上的那种问题，事后极难复现。
        """
        async with self._lock:
            return await asyncio.to_thread(self._insert_sync, sql, params)

    def _insert_sync(self, sql: str, params: Sequence[Any]) -> int:
        conn = self._require()
        try:
            cursor = conn.execute(sql, params)
            conn.commit()
            return int(cursor.lastrowid or 0)
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"SQL 执行失败: {exc}") from exc

    async def execute_affected(self, sql: str, params: Sequence[Any] = ()) -> int:
        """执行一条写语句并返回**受影响行数**。

        用于把「先 SELECT 判断状态、再 UPDATE」压成一条原子语句：
        那两步之间隔着 await，定时调度重入时会把同一个动作做两遍
        （例如同一条提醒触发两次）。
        """
        async with self._lock:
            return await asyncio.to_thread(self._execute_affected_sync, sql, params)

    def _execute_affected_sync(self, sql: str, params: Sequence[Any]) -> int:
        conn = self._require()
        try:
            cursor = conn.execute(sql, params)
            conn.commit()
            return int(cursor.rowcount or 0)
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"SQL 执行失败: {exc}") from exc

    async def execute_many(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        payload = list(rows)
        if not payload:
            return
        async with self._lock:
            await asyncio.to_thread(self._execute_many_sync, sql, payload)

    def _execute_many_sync(self, sql: str, rows: list[Sequence[Any]]) -> None:
        conn = self._require()
        try:
            conn.executemany(sql, rows)
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"批量 SQL 执行失败: {exc}") from exc

    async def transaction(self, statements: list[tuple[str, Sequence[Any]]]) -> None:
        """在**同一个事务**里执行多条语句。

        会话落盘需要「删旧消息 + 写新消息 + 更新会话元数据」原子完成，
        否则中途失败会留下半截对话。
        """

        async with self._lock:
            await asyncio.to_thread(self._transaction_sync, statements)

    def _transaction_sync(self, statements: list[tuple[str, Sequence[Any]]]) -> None:
        conn = self._require()
        try:
            with conn:  # 进入 with 即开启事务，异常自动回滚
                for sql, params in statements:
                    conn.execute(sql, params)
        except sqlite3.Error as exc:
            raise DatabaseError(f"事务执行失败: {exc}") from exc

    async def fetch_all(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._fetch_all_sync, sql, params)

    def _fetch_all_sync(self, sql: str, params: Sequence[Any]) -> list[dict[str, Any]]:
        conn = self._require()
        try:
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            raise DatabaseError(f"查询失败: {exc}") from exc

    async def fetch_one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        async with self._lock:
            return await asyncio.to_thread(self._fetch_one_sync, sql, params)

    def _fetch_one_sync(self, sql: str, params: Sequence[Any]) -> dict[str, Any] | None:
        conn = self._require()
        try:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row is not None else None
        except sqlite3.Error as exc:
            raise DatabaseError(f"查询失败: {exc}") from exc

    def _require(self) -> sqlite3.Connection:
        if self._conn is None:
            raise DatabaseError("数据库尚未连接")
        return self._conn

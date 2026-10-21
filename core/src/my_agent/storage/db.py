









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


SCHEMA_V3 = """
ALTER TABLE sessions ADD COLUMN assistant_id TEXT;
"""









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











SCHEMA_V5 = """
ALTER TABLE sessions ADD COLUMN context_summary TEXT;
ALTER TABLE sessions ADD COLUMN context_summary_upto INTEGER NOT NULL DEFAULT 0;
"""







SCHEMA_V6 = """
ALTER TABLE sessions ADD COLUMN reasoning_effort TEXT;
"""














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














SCHEMA_V8 = """
ALTER TABLE messages ADD COLUMN ts_trusted INTEGER NOT NULL DEFAULT 0;
"""










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












SCHEMA_V10 = """
ALTER TABLE audit_log ADD COLUMN kind TEXT NOT NULL DEFAULT 'skill';
ALTER TABLE audit_log ADD COLUMN actor_id TEXT;
ALTER TABLE audit_log ADD COLUMN action TEXT;
ALTER TABLE audit_log ADD COLUMN target TEXT;
"""











SCHEMA_V11 = """
UPDATE sessions SET assistant_id = 'RelationBuddy' WHERE assistant_id = 'office';
UPDATE sessions SET assistant_id = 'LoveBuddy' WHERE assistant_id = 'lovebuddy';
"""











SCHEMA_V12 = """
ALTER TABLE messages ADD COLUMN plan TEXT;
"""























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


_ADD_COLUMN = re.compile(
    r"ALTER\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*)\s+ADD\s+COLUMN\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def _split_statements(script: str) -> list[str]:






    return [chunk.strip() for chunk in script.split(";") if chunk.strip()]


def _already_applied(conn: sqlite3.Connection, statement: str) -> bool:






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
    pass


class Database:


    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    
    
    
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
        except sqlite3.Error as exc:  
            conn.close()
            raise DatabaseError(f"初始化 SQLite 失败: {exc}") from exc
        try:
            self._migrate(conn)
        except sqlite3.Error as exc:
            
            
            conn.close()
            raise DatabaseError(f"数据库迁移失败: {exc}") from exc
        self._conn = conn
        logger.info("SQLite 已就绪: %s", self.path)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:














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






        async with self._lock:
            await asyncio.to_thread(self._transaction_sync, statements)

    def _transaction_sync(self, statements: list[tuple[str, Sequence[Any]]]) -> None:
        conn = self._require()
        try:
            with conn:  
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

"""持久化层：SQLite 连接、会话/消息仓储、审计日志、工作区文件。"""

from .audit import AuditRepository
from .db import Database, DatabaseError
from .files import FileRecord, WorkspaceError, WorkspaceStore
from .life import (
    EXPENSE_CATEGORIES,
    ExpenseRecord,
    ExpenseRepository,
    ReminderRecord,
    ReminderRepository,
    guess_category,
    period_range,
)
from .sessions import SessionRecord, SessionRepository

__all__ = [
    "EXPENSE_CATEGORIES",
    "AuditRepository",
    "Database",
    "DatabaseError",
    "ExpenseRecord",
    "ExpenseRepository",
    "FileRecord",
    "ReminderRecord",
    "ReminderRepository",
    "SessionRecord",
    "SessionRepository",
    "WorkspaceError",
    "WorkspaceStore",
    "guess_category",
    "period_range",
]

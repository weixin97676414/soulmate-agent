















from __future__ import annotations

from contextvars import ContextVar


current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)


def bind_session(session_id: str):





    return current_session_id.set(session_id)







from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...errors import SessionNotFoundError
from ..deps import get_runtime
from ..runtime import AppRuntime

router = APIRouter(tags=["sessions"], prefix="/v1/sessions")


class CreateSessionRequest(BaseModel):
    title: str = "新对话"
    model_id: str | None = None


class UpdateSessionRequest(BaseModel):
    title: str | None = None
    model_id: str | None = None
    system_prompt: str | None = None
    enabled_skills: list[str] | None = Field(
        None, description="该会话额外勾选的技能（通用 / 我的）；传空列表 = 只用内置技能"
    )


class SessionIdsRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)


async def _load(runtime: AppRuntime, session_id: str):
    try:
        return await runtime.sessions.get(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.get("")
async def list_sessions(request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    return {
        "sessions": runtime.sessions.list(),
        "persistent": runtime.sessions.persistent,
    }


@router.post("")
async def create_session(payload: CreateSessionRequest, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    session = await runtime.sessions.create(model_id=payload.model_id, title=payload.title)
    return session.to_dict()


@router.get("/{session_id}/context")
async def session_context(session_id: str, request: Request) -> dict[str, Any]:











    runtime: AppRuntime = get_runtime(request)
    session = await _load(runtime, session_id)

    
    
    model_id = session.model_id or runtime.registry.default_id
    limit = runtime.effective_context_tokens(model_id)
    used = session.memory.context_tokens()
    threshold = runtime.config.settings.agent.compress_threshold

    return {
        "used_tokens": used,
        "limit_tokens": limit,
        "remaining_tokens": max(limit - used, 0),
        "ratio": (used / limit) if limit > 0 else 0.0,
        
        "compress_threshold": threshold,
        "summary_chars": len(session.memory.summary),
    }


@router.post("/{session_id}/compress")
async def compress_session(session_id: str, request: Request) -> dict[str, Any]:







    runtime: AppRuntime = get_runtime(request)
    session = await _load(runtime, session_id)

    if len(runtime.registry) == 0:
        raise HTTPException(
            status_code=400,
            detail="还没有配置任何模型，无法压缩（压缩要请模型写摘要）。",
        )

    agent_cfg = runtime.config.settings.agent
    from ...agent.context import ContextGuard, ContextPolicy

    guard = ContextGuard(
        ContextPolicy(
            keep_recent=agent_cfg.keep_recent_messages,
            compress_threshold=agent_cfg.compress_threshold,
        )
    )
    model_id = session.model_id or runtime.registry.default_id
    llm = runtime.registry.get(model_id)

    start, end = session.memory.compressible_range(keep_recent=agent_cfg.keep_recent_messages)
    if end <= start:
        return {
            "ok": True,
            "compressed": False,
            "message": "当前没有可压缩的内容 —— 对话还很短，或最近的消息需要保留。",
        }

    
    
    ok = await guard.compress(
        runtime.utility_llm(llm),
        session.memory,
        token_limit=runtime.effective_context_tokens(model_id),
    )
    if not ok:
        raise HTTPException(status_code=502, detail="压缩失败（模型调用出错），上下文未改动。")

    
    await runtime.sessions.persist(session)
    return {
        "ok": True,
        "compressed": True,
        "summary_chars": len(session.memory.summary),
        "message": f"已压缩：较早的 {session.memory.summary_upto} 条消息折叠成了摘要。",
    }


@router.post("/batch-delete")
async def batch_delete(payload: SessionIdsRequest, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    for session_id in payload.ids:
        runtime.cancel_session_tasks(session_id)
    deleted = await runtime.sessions.delete_many(payload.ids)
    return {"ok": True, "deleted": deleted}


@router.patch("/{session_id}")
async def update_session(
    session_id: str, payload: UpdateSessionRequest, request: Request
) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    await _load(runtime, session_id)

    if payload.title is not None:
        await runtime.sessions.rename(session_id, payload.title)

    if (
        payload.model_id is not None
        or payload.system_prompt is not None
        or payload.enabled_skills is not None
    ):
        session = await runtime.sessions.update_meta(
            session_id,
            model_id=payload.model_id,
            system_prompt=payload.system_prompt,
            enabled_skills=set(payload.enabled_skills) if payload.enabled_skills else None,
        )
        return session.to_dict()

    return (await runtime.sessions.get(session_id)).to_dict()


@router.delete("/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    runtime.cancel_session_tasks(session_id)
    deleted = await runtime.sessions.delete(session_id)
    if deleted:
        await runtime.audit.op(
            kind="session", action="delete", target=session_id, detail="删除会话及其全部消息"
        )
    return {"ok": deleted}


@router.get("/{session_id}/messages")
async def session_messages(session_id: str, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    session = await _load(runtime, session_id)
    return {
        "session_id": session_id,
        "title": session.title,
        "model_id": session.model_id,
        "messages": session.history(),
    }


@router.delete("/{session_id}/messages")
async def clear_session_messages(session_id: str, request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    await _load(runtime, session_id)
    runtime.cancel_session_tasks(session_id)
    session = await runtime.sessions.clear_history(session_id)
    await runtime.audit.op(
        kind="session",
        action="clear",
        target=session_id,
        session_id=session_id,
        detail="清空会话的对话历史（保留会话本身）",
    )
    return {"ok": True, "session": session.to_dict()}

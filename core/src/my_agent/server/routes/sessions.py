"""会话接口。

P1 起会话与消息由 SQLite 持久化（`SessionManager` 内部完成），
路由层只负责参数校验与错误映射。
"""

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
    """这个会话**当前**的上下文占用。

    单独开一个接口而不是让前端自己加加减减，是因为"实际会发给模型的量"只有后端
    算得准：它要算上系统提示词、已生成的历史摘要、以及图片占的 token
    （见 ``memory/short_term.py`` 的 ``context_tokens``）。前端拿消息的
    usage 相加会得出一个偏小的数，而用户据此以为"还很空"，正好错过压缩时机。

    ``used_tokens`` 取的是 ``context_tokens()`` 而**不是** ``estimated_tokens()``：
    压缩之后完整历史仍然很长（消息不删除），但真正发送的内容已经短了很多，
    拿完整历史去显示会让人以为"一直快满了"。
    """
    runtime: AppRuntime = get_runtime(request)
    session = await _load(runtime, session_id)

    # 会话可能记着自己的模型，也可能是路由刚换过的那个 —— 与压缩判定用同一个数，
    # 否则会出现"界面显示 5%、实际已经在 3.2 万处裁剪"的分裂行为
    model_id = session.model_id or runtime.registry.default_id
    limit = runtime.effective_context_tokens(model_id)
    used = session.memory.context_tokens()
    threshold = runtime.config.settings.agent.compress_threshold

    return {
        "used_tokens": used,
        "limit_tokens": limit,
        "remaining_tokens": max(limit - used, 0),
        "ratio": (used / limit) if limit > 0 else 0.0,
        # 前端据此提示"接近多少会自动压缩"，而不是让用户对着一个百分比猜
        "compress_threshold": threshold,
        "summary_chars": len(session.memory.summary),
    }


@router.post("/{session_id}/compress")
async def compress_session(session_id: str, request: Request) -> dict[str, Any]:
    """手动触发上下文压缩（输入区的 ``/compact`` 命令）。

    自动压缩只在用量超过阈值时触发；用户有时想**主动**把较早的内容折叠掉
    （比如长对话跑完一个阶段），这个接口就是那个入口。复用与自动压缩
    **同一个** ``ContextGuard.compress``：参数、摘要合并、失败回落全部一致，
    不另写一条压缩路径 —— 两套实现迟早长歪。
    """
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

    # 手动压缩与自动压缩走**同一个**辅助模型设置：两处不一致的话，
    # 用户会发现"自动压缩便宜、手点一下却按主模型计费"这种说不清的现象
    ok = await guard.compress(
        runtime.utility_llm(llm),
        session.memory,
        token_limit=runtime.effective_context_tokens(model_id),
    )
    if not ok:
        raise HTTPException(status_code=502, detail="压缩失败（模型调用出错），上下文未改动。")

    # 摘要落库：否则重启后压缩成果丢失，模型又"想起"全部历史
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
    """清空某会话的对话历史（保留会话本身与标题）。"""
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

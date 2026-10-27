











from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from ...agent.context import ContextPolicy
from ...agent.engine import Agent, AgentConfig, AgentEvent
from ...llm.base import ImagePart
from ...llm.router import ModelRouter
from ...observability.metrics import METRICS
from ...observability.request_context import bind_session, current_session_id
from ...observability.tracer import Tracer
from ...skill.base import ConfirmRequest, InteractionRequest, SkillContext
from ...skill.custom import persona_with_instructions




from ...storage.images import ImageSourceError, encode_data_url
from ..deps import get_runtime
from ..runtime import AppRuntime
from ..sse import format_sse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


ATTACHMENT_OPEN = "[附件]"
ATTACHMENT_CLOSE = "[/附件]"


class ChatRequest(BaseModel):
    
    
    
    
    message: str = Field(
        "",
        description="用户输入；**可以为空**（只发附件时），但 attachments / images 至少要有一个",
    )
    session_id: str | None = None
    model_id: str | None = None
    assistant_id: str | None = Field(
        None, description="助手预设 id；显式传入即把会话切到该助手"
    )
    attachments: list[str] = Field(
        default_factory=list,
        description="工作区文件 id 列表（由 /v1/files/upload 返回）",
    )
    images: list[str] = Field(
        default_factory=list,
        description=(
            "作为**图片**附加到本轮消息的工作区文件 id 列表。"
            "与 attachments 的区别：attachments 只是把文件名与路径写进文字里，"
            "images 会把图片本身发给模型（需要模型支持图片输入）。"
        ),
    )
    reasoning_effort: Literal["low", "medium", "high"] | None = Field(
        None,
        description=(
            "思考强度：low / medium / high；空串表示关掉。"
            "**字段缺席表示不改变会话当前的设置** —— 这与空串是两回事，"
            "靠 pydantic 的 model_fields_set 区分，避免老客户端把用户调过的档位清掉。"
        ),
    )

    @field_validator("reasoning_effort", mode="before")
    @classmethod
    def _blank_reasoning_effort_means_off(cls, value: Any) -> Any:











        if isinstance(value, str) and not value.strip():
            return None
        return value


class ConfirmDecision(BaseModel):
    request_id: str
    approved: bool


class PlanDecision(BaseModel):






    plan_id: str = Field(..., description="计划 id，来自 plan 事件，前端原样回传")
    approved: bool = Field(False, description="True = 「开始执行」")
    feedback: str = Field(
        "",
        description=(
            "approved=False 时使用：**非空**表示「改一下」并带上用户的意见，"
            "AI 会据此重拟计划；**空**表示「不用了」，本次任务到此为止。"
        ),
    )


class StopRequest(BaseModel):
    task_id: str | None = None
    session_id: str | None = None




_sse = format_sse


async def build_attachment_block(runtime: AppRuntime, file_ids: list[str]) -> str | None:








    lines: list[str] = []
    for file_id in file_ids:
        record = await runtime.workspace.get(file_id)
        if record is None:
            lines.append(f"- 附件 {file_id} 不存在或已被删除")
            continue
        try:
            path = runtime.workspace.resolve(record.id, record.kind)
        except Exception:  
            lines.append(f"- 附件 {record.original_name} 已丢失")
            continue
        lines.append(f"- {record.original_name}\n  路径: {path}")

    if not lines:
        return None
    return f"{ATTACHMENT_OPEN}\n用户上传了以下文件，可据此操作：\n" + "\n".join(lines) + f"\n{ATTACHMENT_CLOSE}"




















TURN_QUEUE_SIZE = 512

MAX_IMAGES_PER_TURN = 4


MAX_IMAGE_BYTES = 8 * 1024 * 1024


async def build_image_parts(runtime: AppRuntime, file_ids: list[str]) -> list[ImagePart]:







    parts: list[ImagePart] = []
    for file_id in file_ids[:MAX_IMAGES_PER_TURN]:
        record = await runtime.workspace.get(file_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"图片附件 {file_id} 不存在")
        try:
            path = runtime.workspace.resolve(record.id, record.kind)
            
            
            
            size = path.stat().st_size
            if size > MAX_IMAGE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"图片「{record.original_name}」{size // 1024 // 1024}MB，"
                        f"超过 {MAX_IMAGE_BYTES // 1024 // 1024}MB 上限。请先压缩后再上传。"
                    ),
                )
            
            
            
            
            raw = await asyncio.to_thread(path.read_bytes)
        except HTTPException:
            
            raise
        except Exception as exc:  
            raise HTTPException(
                status_code=422, detail=f"图片附件 {record.original_name} 无法读取：{exc}"
            ) from exc

        
        
        
        try:
            mime, data_url = encode_data_url(
                raw, max_bytes=MAX_IMAGE_BYTES, label=f"图片「{record.original_name}」"
            )
        except ImageSourceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        parts.append(ImagePart(mime=mime, data_url=data_url, name=record.original_name))
    return parts


@router.post("/v1/chat")
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    runtime: AppRuntime = get_runtime(request)
    settings = runtime.config.settings

    
    if not payload.message.strip() and not payload.attachments and not payload.images:
        raise HTTPException(
            status_code=400,
            detail="既没有输入文字，也没有附件 —— 请说点什么，或者加一个附件。",
        )

    session = await runtime.get_session(payload.session_id, model_id=payload.model_id)

    
    
    
    profile = None
    if payload.assistant_id:
        profile = runtime.resolve_assistant(payload.assistant_id)
        if profile is None:
            raise HTTPException(
                status_code=404, detail=f"助手「{payload.assistant_id}」不存在"
            )
        session.apply_assistant(profile)
    elif session.assistant_id:
        
        
        profile = runtime.resolve_assistant(session.assistant_id)
        if profile is not None:
            session.apply_assistant(profile)

    
    
    
    
    if "reasoning_effort" in payload.model_fields_set:
        session.reasoning_effort = (payload.reasoning_effort or "").strip() or None

    
    
    
    requested_model = payload.model_id or session.model_id
    model_id = requested_model or runtime.config.models.default_model

    if requested_model is None and settings.agent.enable_model_routing:
        routed = ModelRouter(
            default_id=runtime.config.models.default_model,
            candidates=runtime.config.models.models,
        ).pick(
            text=payload.message,
            need_tools=len(runtime.skills) > 0,
        )
        if routed:
            model_id = routed

    if len(runtime.registry) == 0:
        
        
        
        raise HTTPException(
            status_code=400,
            detail="还没有配置任何模型。请先在「设置 → 模型服务商」里添加一个，或重新运行首次引导。",
        )
    llm = runtime.registry.get(model_id)

    session.model_id = model_id
    session.auto_title(payload.message)
    session.touch()

    
    user_text = payload.message
    if payload.attachments:
        block = await build_attachment_block(runtime, payload.attachments)
        if block:
            user_text = f"{block}\n\n{payload.message}"

    
    spec = runtime.config.models.get(model_id)
    supports_vision = bool(spec and spec.supports_vision)
    image_parts: list[ImagePart] = []
    vision_notice = ""

    if payload.images:
        if supports_vision:
            image_parts = await build_image_parts(runtime, payload.images)
        else:
            
            
            
            
            vision_notice = (
                f"本轮附带的 {len(payload.images)} 张图片没有被发送："
                f"模型「{model_id}」未标记为支持图片输入。"
                "可在「设置 → 模型」中为该模型勾选「支持图片」。"
            )

    tracer = Tracer(enabled=settings.trace_enabled)
    
    queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue(maxsize=TURN_QUEUE_SIZE)

    
    async def emit_confirm(confirm: ConfirmRequest) -> None:
        await queue.put(
            AgentEvent(
                "permission_request",
                {
                    "request_id": confirm.request_id,
                    "skill_name": confirm.skill_name,
                    "display_name": confirm.display_name,
                    "description": confirm.description,
                    "permission_level": confirm.permission_level,
                    "params": confirm.params,
                    "prompt": confirm.prompt,
                },
            )
        )

    async def confirm_callback(confirm: ConfirmRequest) -> bool:
        return await runtime.request_confirm(confirm, emit_confirm, owner=session.id)

    
    
    
    
    
    async def emit_interaction(interaction: InteractionRequest) -> None:
        await queue.put(AgentEvent("interaction_request", interaction.to_dict()))

    async def interaction_callback(interaction: InteractionRequest) -> dict[str, Any]:
        return await runtime.request_interaction(interaction, emit_interaction, owner=session.id)

    
    
    
    
    async def plan_decider(plan: dict[str, Any]) -> tuple[bool, str]:








        return await runtime.request_plan_decision(str(plan.get("id") or uuid4().hex), owner=session.id)

    ctx = SkillContext(
        settings=settings,
        tracer=tracer,
        paths=runtime.paths,
        confirm=confirm_callback,
        interaction=interaction_callback,
        audit=runtime.audit.record,
        session_id=session.id,
        assistant_id=session.assistant_id,
        workspace=runtime.workspace,
        path_policy=runtime.path_policy,
        extra=runtime.skill_services_for(session.assistant_id),
        logger=logging.getLogger("my_agent.skill"),
        
        
        
        
        
        
        
        
        
        
        
        confirm_mode=lambda: runtime.assistant_confirm_mode(session.assistant_id),
    )

    agent_cfg = settings.agent
    agent = Agent(
        llm=llm,
        
        utility_llm=runtime.utility_llm(llm),
        skill_manager=runtime.skills,
        memory=session.memory,
        config=AgentConfig(
            
            
            max_iterations=(
                profile.max_iterations if profile and profile.max_iterations else agent_cfg.max_iterations
            ),
            max_tool_calls_per_turn=(
                profile.max_tool_calls_per_turn
                if profile and profile.max_tool_calls_per_turn
                else agent_cfg.max_tool_calls_per_turn
            ),
            temperature=(
                profile.temperature
                if profile and profile.temperature is not None
                else agent_cfg.temperature
            ),
            
            
            
            top_p=agent_cfg.top_p,
            frequency_penalty=agent_cfg.frequency_penalty,
            presence_penalty=agent_cfg.presence_penalty,
            
            
            
            reasoning_effort=session.reasoning_effort,
            
            
            
            
            
            
            
            
            persona=lambda: persona_with_instructions(  
                runtime, session.assistant_id, session.enabled_skills
            ),
            same_tool_failure_tolerance=agent_cfg.same_tool_failure_tolerance,
            
            
            
            enabled_skills=runtime.skills.allowed_names(
                assistant_id=session.assistant_id,
                enabled_skills=session.enabled_skills,
            ),
            
            
            target_assistant=session.assistant_id or "",
            
            
            
            
            
            token_limit=runtime.effective_context_tokens(model_id),
            
            supports_vision=getattr(llm, "supports_vision", False),
            context_policy=ContextPolicy(
                keep_recent=agent_cfg.keep_recent_messages,
                compress_threshold=agent_cfg.compress_threshold,
            ),
            
            
            
            
            
            
            
            
            
            enable_planner=True,
            plan_decider=plan_decider,
            enable_reflection=agent_cfg.enable_reflection,
            reflection_rounds=agent_cfg.reflection_rounds,
        ),
        ctx=ctx,
        tracer=tracer,
    )

    
    run_stats: dict[str, Any] = {}

    
    async def produce() -> None:
        try:
            async for event in agent.run_stream(user_text, images=image_parts):
                if event.type == "done":
                    run_stats["iterations"] = int(event.data.get("iterations") or 0)
                await queue.put(event)
        except asyncio.CancelledError:
            logger.info("任务已取消 session=%s", session.id)
            raise
        except Exception as exc:  
            
            
            
            
            logger.exception(
                "Agent 执行失败 session=%s model=%s trace=%s",
                session.id,
                model_id,
                tracer.trace_id,
            )
            await queue.put(
                AgentEvent(
                    "error",
                    {
                        "code": getattr(exc, "code", "internal_error"),
                        "message": getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}",
                    },
                )
            )
        finally:
            
            
            
            await queue.put(None)

    
    async def event_stream() -> AsyncIterator[str]:






        slot = await runtime.acquire_chat_slot()
        if slot is None:
            
            
            
            limit = settings.agent.max_concurrent_chats
            yield _sse(
                "error",
                {
                    "code": "too_many_concurrent",
                    "message": (
                        f"同时进行的对话已达上限（{limit} 个），本次排队超时未执行。"
                        "请等其中一个结束后重试。"
                    ),
                },
            )
            return
        try:
            async for chunk in _stream_events():
                yield chunk
        finally:
            runtime.release_chat_slot(slot)

    async def _stream_events() -> AsyncIterator[str]:
        
        
        
        async with session.lock:
            started = asyncio.get_running_loop().time()
            
            
            
            
            
            
            run_id = await runtime.runs.start(
                kind="chat", ref_id=session.id, session_id=session.id
            )
            
            
            step = 0
            last_action = ""
            
            
            completed = False
            error_code = ""
            error_message = ""
            partial = False
            
            
            
            
            
            
            context_token = bind_session(session.id)
            task = asyncio.create_task(produce(), name=f"agent-{session.id}")
            running = runtime.register_task(session.id, task)
            try:
                yield _sse(
                    "meta",
                    {
                        "session_id": session.id,
                        "task_id": running.id,
                        "trace_id": tracer.trace_id,
                        "model_id": model_id,
                    },
                )
                if vision_notice:
                    
                    
                    yield _sse("warning", {"message": vision_notice})

                while True:
                    event = await queue.get()
                    if event is None:
                        completed = True
                        break
                    data = event.data
                    
                    
                    
                    if event.type == "tool_result":
                        step += 1
                        last_action = str(
                            data.get("display_name") or data.get("name") or ""
                        )
                        await runtime.runs.progress(run_id, step=step, last_action=last_action)
                    elif event.type == "error":
                        error_code = str(data.get("code") or "error")
                        error_message = str(data.get("message") or "")
                    elif event.type == "done" and data.get("partial"):
                        
                        
                        partial = True
                    yield _sse(event.type, data)
                if settings.trace_enabled:
                    yield _sse("trace", tracer.export())
            finally:
                
                
                
                
                
                
                
                stopped = task.cancelled()
                
                if not task.done():
                    task.cancel()
                
                
                
                
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.gather(task, return_exceptions=True)
                
                runtime.reject_pending(session.id)
                runtime.unregister_task(running.id)
                
                
                await runtime.persist_session(session)

                
                
                last_user = ""
                last_assistant = ""
                for item in session.history():
                    if item["role"] == "user":
                        last_user = item["content"]
                    elif item["role"] == "assistant":
                        last_assistant = item["content"]
                await runtime.archive_turn(
                    assistant_id=session.assistant_id,
                    session_id=session.id,
                    user_text=last_user,
                    assistant_text=last_assistant,
                )

                
                
                
                if settings.trace_enabled:
                    runtime.traces.put(tracer.trace_id, tracer.export())

                
                
                current_session_id.reset(context_token)

                
                
                
                
                await runtime.usage.record(
                    session_id=session.id,
                    model_id=model_id,
                    usage=tracer.usage,
                    trace_id=tracer.trace_id,
                    duration_ms=round(
                        (asyncio.get_running_loop().time() - started) * 1000, 2
                    ),
                    iterations=int(run_stats.get("iterations", 0)),
                )

                
                
                
                
                
                
                
                
                
                if stopped:
                    outcome = "cancelled"
                elif error_code == "agent_max_iterations" or partial:
                    outcome = "incomplete"
                elif error_code:
                    outcome = "failed"
                elif completed:
                    outcome = ""
                else:
                    
                    outcome = "cancelled"
                if outcome:
                    
                    
                    
                    
                    
                    
                    METRICS.inc("turn_failed_total", model=model_id, reason=outcome)
                    await runtime.runs.interrupt(
                        run_id,
                        status=outcome,
                        step=step,
                        last_action=last_action,
                        error=(
                            "你点了停止（或界面断开了连接）"
                            if outcome == "cancelled"
                            else error_message
                        ),
                    )
                else:
                    await runtime.runs.finish(run_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/v1/confirm")
async def confirm(payload: ConfirmDecision, request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    resolved = runtime.resolve_confirm(payload.request_id, payload.approved)
    if not resolved:
        return {"ok": False, "message": "确认请求不存在或已超时"}
    return {"ok": True, "approved": payload.approved}


@router.post("/v1/plan/decision")
async def plan_decision(payload: PlanDecision, request: Request) -> dict[str, Any]:





    runtime: AppRuntime = get_runtime(request)
    feedback = payload.feedback.strip()
    resolved = runtime.resolve_plan(payload.plan_id, payload.approved, feedback)
    if not resolved:
        
        
        return {"ok": False, "message": "这个计划已经不在等待中了（可能已开始执行或被取消）"}
    if payload.approved:
        action = "approved"
    elif feedback:
        action = "revise"
    else:
        action = "aborted"
    return {"ok": True, "action": action}


class InteractionDecision(BaseModel):








    request_id: str
    answer: dict[str, Any] = Field(default_factory=dict)


@router.post("/v1/interaction/decision")
async def interaction_decision(payload: InteractionDecision, request: Request) -> dict[str, Any]:






    runtime: AppRuntime = get_runtime(request)
    resolved = runtime.resolve_interaction(payload.request_id, payload.answer)
    if not resolved:
        
        
        return {"ok": False, "message": "这次交互已经不在等待中了（可能已作答或被取消）"}
    return {"ok": True}


@router.post("/v1/stop")
async def stop(payload: StopRequest, request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    cancelled = 0
    if payload.task_id:
        
        
        
        
        
        
        
        
        owner = runtime.tasks.get(payload.task_id)
        cancelled = 1 if runtime.cancel_task(payload.task_id) else 0
        owner_session = owner.session_id if owner is not None else ""
        if owner_session:
            runtime.reject_pending(owner_session)
    elif payload.session_id:
        cancelled = runtime.cancel_session_tasks(payload.session_id)
        runtime.reject_pending(payload.session_id)
    return {"ok": True, "cancelled": cancelled}

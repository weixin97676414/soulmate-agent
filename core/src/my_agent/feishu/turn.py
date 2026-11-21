























from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..agent.engine import Agent, AgentEvent
from ..agent.turn_builder import build_agent_config
from ..observability.tracer import Tracer
from ..skill.base import SkillContext

if TYPE_CHECKING:  
    from ..server.runtime import AppRuntime
    from .session import Session

logger = logging.getLogger(__name__)



MAX_REPLY_CHARS = 12_000


class TurnFailed(RuntimeError):
    pass


async def run_turn_silently(
    runtime: AppRuntime,
    session: Session,
    text: str,
    *,
    file_ids: list[str] | None = None,
) -> str:












    settings = runtime.config.settings
    model_id = session.model_id or runtime.config.models.default_model
    if len(runtime.registry) == 0:
        raise TurnFailed(
            "还没有配置任何模型。请在客户端的「设置 → 模型服务商」里添加一个。"
        )
    llm = runtime.registry.get(model_id)
    if llm is None:
        raise TurnFailed(f"模型「{model_id}」不可用，请在客户端里检查配置。")

    profile = runtime.resolve_assistant(session.assistant_id)
    tracer = Tracer(enabled=settings.trace_enabled)

    
    denied: list[str] = []

    async def deny_confirm(confirm: Any) -> bool:
        name = getattr(confirm, "display_name", "") or getattr(confirm, "skill_name", "")
        denied.append(str(name or "某个操作"))
        logger.info("飞书路径拒绝了确认请求：%s", name)
        return False

    async def no_interaction(_interaction: Any) -> dict[str, Any]:

        return {}

    ctx = SkillContext(
        settings=settings,
        tracer=tracer,
        paths=runtime.paths,
        confirm=deny_confirm,
        interaction=no_interaction,
        audit=runtime.audit.record,
        session_id=session.id,
        assistant_id=session.assistant_id,
        workspace=runtime.workspace,
        path_policy=runtime.path_policy,
        extra=runtime.skill_services_for(session.assistant_id),
        logger=logging.getLogger("my_agent.skill"),
        
        
        confirm_mode=lambda: runtime.assistant_confirm_mode(session.assistant_id),
    )

    agent = Agent(
        llm=llm,
        utility_llm=runtime.utility_llm(llm),
        skill_manager=runtime.skills,
        memory=session.memory,
        config=build_agent_config(
            runtime=runtime,
            session=session,
            profile=profile,
            model_id=model_id,
            llm=llm,
            
            plan_decider=None,
        ),
        ctx=ctx,
        tracer=tracer,
    )

    
    
    
    
    
    from ..server.routes.chat import build_attachment_block, build_image_parts

    attachments = file_ids or []
    image_parts: list[Any] = []
    user_text = text
    if attachments:
        block = await build_attachment_block(runtime, attachments)
        if block:
            user_text = f"{block}\n\n{text}" if text else block
        
        
        image_parts = await build_image_parts(runtime, attachments)

    
    
    
    
    

    parts: list[str] = []
    error_text = ""
    async for event in agent.run_stream(user_text, images=image_parts):
        if not isinstance(event, AgentEvent):
            continue
        if event.type == "delta":
            
            
            
            
            
            data = event.data or {}
            chunk = data.get("text") or data.get("content")
            if isinstance(chunk, str):
                parts.append(chunk)
        elif event.type == "error":
            error_text = str((event.data or {}).get("message") or "模型调用失败")

    reply = "".join(parts).strip()

    if not reply:
        
        if error_text:
            raise TurnFailed(f"这轮没跑成：{error_text}")
        raise TurnFailed("模型返回了空回复（可能是上下文过长或模型异常）。")

    if denied:
        reply += (
            "\n\n---\n"
            f"有 {len(denied)} 个操作需要你确认才能执行（{'、'.join(denied[:3])}）。"
            "飞书里没法点确认，请在客户端的同一个对话里再发一次。"
        )

    if len(reply) > MAX_REPLY_CHARS:
        reply = reply[:MAX_REPLY_CHARS] + (
            f"\n\n…（这条回复超过 {MAX_REPLY_CHARS} 字，完整内容在客户端的这个对话里）"
        )

    
    
    
    
    
    
    await runtime.sessions.persist(session, include_messages=True)
    return reply

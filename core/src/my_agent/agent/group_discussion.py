



























from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from ..protocol import format_sse
from ..security.confirm import ConfirmRequest
from ..security.interaction import InteractionRequest
from ..skill.custom import persona_with_instructions
from .group_domain import (
    MAX_ROUNDS,
    ROLE_LABELS,
    can_end_vote,
    confirm_owner,
    effective_roles,
    history_line,
    parse_control,
    role_rules,
    say,
    skill_owners,
    summary_owner,
    vote_passed,
)

if TYPE_CHECKING:  
    
    from ..config.schemas import GroupProfile
    from ..server.runtime import AppRuntime

logger = logging.getLogger(__name__)


_sse = format_sse


def _who(member: Any | None) -> dict[str, str] | None:








    if member is None:
        return None
    return {"assistant_id": member.id, "name": member.name}




_GROUP_KEEP_RECENT = 10


def _render_group_history(history: list[dict[str, str]]) -> str:

    return "\n".join(history_line(item) for item in history)


async def _summarize_group_history(llm: Any, history: list[dict[str, str]]) -> str:

    from ..llm.base import Message

    transcript = _render_group_history(history)
    system = (
        "你是群聊记录压缩器。把这段群聊讨论压缩成简短摘要，只保留事实性内容："
        "话题与目标、已达成的共识、关键数据与数字、已经排除的方案及原因、"
        "尚未解决的问题。不要复述寒暄，不要评论，直接给摘要正文。"
        "时间用绝对日期（每条发言前有 [月-日 时:分]，遇到相对说法请换算成日期）。"
        "用简体中文，条目式，尽量紧凑。"
    )
    response = await llm.chat(
        [Message(role="system", content=system), Message(role="user", content=transcript)],
        None,
        temperature=0.2,
    )
    return (response.content or "").strip()


async def compressed_group_history_text(
    runtime: AppRuntime,
    group: GroupProfile,
    thread_id: str,
    history: list[dict[str, str]],
    llm: Any,
    token_limit: int,
    *,
    keep_recent: int | None = None,
    full: bool = False,
) -> str:











    if not history:
        return ""

    if full:
        
        return _render_group_history(history)

    keep = keep_recent if keep_recent and keep_recent > 0 else _GROUP_KEEP_RECENT

    total_chars = sum(len(item.get("content", "")) for item in history)
    threshold_chars = max(4000, int(token_limit * 0.6))
    if total_chars <= threshold_chars or len(history) <= keep:
        return _render_group_history(history)

    
    
    older = history[:-_GROUP_KEEP_RECENT]
    recent = history[-keep:]

    summary = runtime._group_history_summary.get((group.id, thread_id))
    if summary is None:
        try:
            summary = await _summarize_group_history(llm, older)
        except Exception:  
            summary = ""
        if summary:
            runtime._group_history_summary[(group.id, thread_id)] = summary

    if summary:
        return (
            f"以下是本群**更早**讨论的摘要：\n{summary}\n\n"
            f"以下是本群**最近**的对话：\n{_render_group_history(recent)}"
        )
    
    return _render_group_history(recent)


def _keep_recent_for_role(role: str) -> int:






    if role == "reviewer":
        return 10
    if role == "advisor":
        return 3
    return 5


async def build_group_agent(
    runtime: AppRuntime,
    group: GroupProfile,
    member: Any,
    history: list[Any],
    thread_id: str,
    *,
    background: bool = False,
    role: str = "",
    can_end_vote: bool = False,
) -> Any:







    from ..memory.short_term import MemoryManager
    from ..skill.base import SkillContext
    from .engine import Agent, AgentConfig

    settings = runtime.config.settings
    model_id = member.model_id or runtime.config.models.default_model
    llm = runtime.registry.get(model_id or None)

    names = "、".join(
        item.name
        for item in runtime.assistants.assistants
        if item.id in group.member_assistant_ids
    )
    persona = persona_with_instructions(runtime, member.id, list(member.enabled_skills) or None)
    role_text = ROLE_LABELS.get(role, "成员") if role else "成员"
    rules = (
        "\n\n## 你正在参加一个多搭子群聊\n"
        f"群名：「{group.name}」；成员：{names}。\n"
        f"你在这个群里的角色：**{role_text}**。\n"
        "规则：\n"
        "- 用户抛出话题后，大家**轮流发言**讨论，目标是聊到意见统一并给出结论。\n"
        "- 每次发言简短（1~3 句），像群聊一样自然，不要长篇大论。\n"
        "- 可以用 @名字 请某位成员补充发言。\n"
        "- 别人发起结束投票后，你在发言**最后**写 [AGREE] 或 [DISAGREE]（同意/不同意结束）。\n"
        "- 讨论收尾时，由**会话发起人（发言顺序的首位）**做最终总结交付给用户；\n"
        "- 你不是这个人时不要抢着总结，也不要在自己的发言里替它交付。\n"
        "- 审核员验收通过，讨论就结束了 —— 接下来直接由会话发起人给出最终总结。\n"
        "- 你可以使用自己的工具（技能、MCP）来核实或补充信息。\n"
        + role_rules(role, can_end_vote=can_end_vote)
    )
    
    
    system = rules.lstrip("\n")
    if persona:
        system = f"{system}\n\n{persona}"

    memory = MemoryManager()
    if history:
        
        
        assigned = runtime._group_context_plan.get((group.id, thread_id, member.id))
        if assigned:
            memory.add_user("总管给这次讨论分配给你的上下文（只读这部分即可）：\n\n" + assigned)
        else:
            
            
            history_text = await compressed_group_history_text(
                runtime,
                group,
                thread_id,
                history,
                llm,
                token_limit=llm.token_limit,
                keep_recent=_keep_recent_for_role(role),
                full=role == "coordinator",
            )
            if history_text:
                memory.add_user("以下是本群到目前为止的对话记录：\n\n" + history_text)

    
    
    
    
    
    
    
    async def emit_confirm(confirm: ConfirmRequest) -> None:
        runtime.events.publish(
            "permission_request",
            group_id=group.id,
            group_name=group.name,
            assistant_id=member.id,
            assistant_name=member.name,
            **confirm.to_dict(),
        )

    async def confirm_callback(confirm: ConfirmRequest) -> bool:
        
        
        
        if runtime.events.subscriber_count == 0:
            logger.warning(
                "群聊确认无人可送达（没有客户端在监听事件流），按拒绝处理 group=%s skill=%s",
                group.id,
                confirm.skill_name,
            )
            return False
        return await runtime.request_confirm(confirm, emit_confirm, owner=confirm_owner(group.id))

    
    
    
    
    async def emit_interaction(interaction: InteractionRequest) -> None:
        runtime.events.publish(
            "interaction_request",
            group_id=group.id,
            group_name=group.name,
            assistant_id=member.id,
            assistant_name=member.name,
            **interaction.to_dict(),
        )

    async def interaction_callback(interaction: InteractionRequest) -> dict[str, Any]:
        
        
        
        if runtime.events.subscriber_count == 0:
            logger.warning(
                "群聊交互无人可送达（没有客户端在监听事件流），按未作答降级 group=%s skill=%s",
                group.id,
                interaction.skill_name,
            )
            return {"cancelled": True, "reason": "no_subscriber"}
        return await runtime.request_interaction(
            interaction, emit_interaction, owner=confirm_owner(group.id)
        )

    def live_confirm_mode() -> str | None:








        current = runtime.groups.get(group.id) or group
        
        
        
        
        
        
        
        return current.confirm_mode or runtime.assistant_confirm_mode(member.id)

    ctx = SkillContext(
        settings=settings,
        paths=runtime.paths,
        confirm=confirm_callback,
        interaction=interaction_callback,
        audit=runtime.audit.record,
        session_id=f"group:{group.id}",
        assistant_id=member.id,
        
        
        
        group_id=group.id,
        workspace=runtime.workspace,
        path_policy=runtime.path_policy,
        
        extra=runtime.skill_services_for(member.id, group_id=group.id),
        
        
        confirm_mode="auto_approve" if background else live_confirm_mode,
        
        
        
        allow_admin=background,
    )
    config = AgentConfig(
        
        
        max_iterations=settings.agent.max_iterations,
        max_tool_calls_per_turn=settings.agent.max_tool_calls_per_turn,
        
        
        reasoning_effort=group.reasoning_effort or member.reasoning_effort,
        temperature=member.temperature if member.temperature is not None else 0.7,
        
        
        
        
        persona=system,
        
        
        enabled_skills=runtime.skills.allowed_names(
            assistant_id=member.id,
            enabled_skills=member.enabled_skills,
        ),
        
        
        target_assistant=member.id,
        token_limit=llm.token_limit,
        
        supports_vision=getattr(llm, "supports_vision", False),
        enable_planner=False,
        enable_reflection=False,
    )
    return Agent(
        llm=llm,
        
        utility_llm=runtime.utility_llm(llm),
        skill_manager=runtime.skills,
        memory=memory,
        config=config,
        ctx=ctx,
    )
async def run_member(
    runtime: AppRuntime,
    group: GroupProfile,
    member: Any,
    history: list[Any],
    user_input: str,
    thread_id: str,
    images: list[Any] | None = None,
    *,
    background: bool = False,
    role: str = "",
    can_end_vote: bool = False,
) -> AsyncIterator[tuple[str, Any]]:














    agent = await build_group_agent(
        runtime,
        group,
        member,
        history,
        thread_id,
        background=background,
        role=role,
        can_end_vote=can_end_vote,
    )
    
    
    
    allowed = runtime.skills.allowed_names(
        assistant_id=member.id, enabled_skills=member.enabled_skills
    )
    text = ""
    started = asyncio.get_running_loop().time()
    iterations = 0
    async for event in agent.run_stream(user_input, images=list(images or [])):
        if event.type == "delta":
            piece = str(event.data.get("text") or "")
            if piece:
                text += piece
                yield "delta", piece
        elif event.type == "done":
            iterations = int(event.data.get("iterations") or 0)
        elif event.type == "reasoning":
            
            
            
            
            
            
            
            
            piece = str(event.data.get("text") or "")
            if piece:
                yield "reasoning", piece
        elif event.type == "tool_call":
            
            
            
            
            
            
            yield "tool_call", {
                "id": str(event.data.get("id") or ""),
                "name": str(event.data.get("name") or ""),
                "display_name": str(event.data.get("display_name") or event.data.get("name") or ""),
                "description": str(event.data.get("description") or ""),
                "permission_level": str(event.data.get("permission_level") or ""),
            }
            
            
            
            
            
            
            name = str(event.data.get("name") or "")
            if name and name not in allowed:
                yield "out_of_scope", name
        elif event.type == "tool_result":
            
            
            
            
            yield "tool_result", {
                "id": str(event.data.get("id") or ""),
                "status": str(event.data.get("status") or ""),
                "result": str(event.data.get("result") or ""),
                "duration_ms": event.data.get("duration_ms"),
            }
        elif event.type == "error":
            yield "error", str(event.data.get("message") or "生成失败")

    
    
    
    
    
    
    
    
    
    
    
    clean_text, _, _ = parse_control(text)
    if clean_text:
        await runtime.archive_group_turn(
            group_id=group.id, speaker=member.name, text=clean_text
        )

    yield "final", text

    
    
    
    
    
    
    
    
    
    
    if agent.tracer.usage.prompt_tokens or agent.tracer.usage.completion_tokens:
        
        
        await runtime.usage.record(
            session_id=group.id,
            
            
            
            
            
            model_id=str(getattr(member, "model_id", "") or "")
            or runtime.config.models.default_model,
            usage=agent.tracer.usage,
            trace_id=agent.tracer.trace_id,
            duration_ms=round((asyncio.get_running_loop().time() - started) * 1000, 2),
            iterations=iterations,
        )

        
        
        
        
        
        if runtime.config.settings.trace_enabled:
            runtime.traces.put(agent.tracer.trace_id, agent.tracer.export())











async def discuss_stream(
    runtime: AppRuntime,
    group: GroupProfile,
    members: list[Any],
    topic: str,
    thread_id: str,
    *,
    attachment_block: str = "",
    images: list[Any] | None = None,
    background: bool = False,
) -> AsyncIterator[str]:
    
    
    history = runtime._group_history.setdefault((group.id, thread_id), [])
    
    
    
    
    if topic.strip() or attachment_block or images:
        
        
        content = f"{attachment_block}\n\n{topic.strip()}" if attachment_block else topic.strip()
        say(history, role="user", name="用户", content=content)
        
        yield _sse("topic", {"content": topic.strip() or "（只发了附件）"})
    elif not history:
        yield _sse("error", {"message": "还没有任何话题，请先抛出一个话题。"})
        yield _sse("done", {"reason": "empty"})
        return

    names = "、".join(member.name for member in members)
    
    roles = effective_roles(members)
    end_vote_by = ""
    votes: dict[str, bool] = {}

    for round_index in range(MAX_ROUNDS):
        for member in members:
            role = roles.get(member.id, "")
            may_end_vote = can_end_vote(members, member)
            yield _sse(
                "speaker",
                {
                    "assistant_id": member.id,
                    "name": member.name,
                    "round": round_index + 1,
                    "role": role,
                    "role_label": ROLE_LABELS.get(role, ""),
                },
            )
            if end_vote_by:
                hint = " 有人发起了结束投票：请在发言最后写 [AGREE] 或 [DISAGREE]。"
            elif may_end_vote:
                hint = " 若你认为讨论已充分、可以收尾，请在发言最后单独一行写 [END_VOTE]。"
            else:
                
                hint = " 该收尾时请 @ 首位发言者或末序发言者提出，由他们发起结束投票。"
            user_input = (
                f"群成员：{names}。现在轮到你（{member.name}）发言，请接着说。" + hint
            )
            text = ""
            async for kind, piece in run_member(
                runtime,
                group,
                member,
                history,
                user_input,
                thread_id,
                images=images,
                background=background,
                role=role,
                can_end_vote=may_end_vote,
            ):
                if kind == "delta":
                    yield _sse("delta", {"assistant_id": member.id, "text": piece})
                elif kind == "reasoning":
                    
                    yield _sse(
                        "reasoning",
                        {"assistant_id": member.id, "name": member.name, "text": piece},
                    )
                elif kind == "tool_call":
                    
                    
                    yield _sse(
                        "tool_call",
                        {
                            "assistant_id": member.id,
                            "name": member.name,
                            "tool": piece,
                        },
                    )
                elif kind == "tool_result":
                    yield _sse(
                        "tool_result",
                        {
                            "assistant_id": member.id,
                            "name": member.name,
                            "tool": piece,
                        },
                    )
                elif kind == "error":
                    yield _sse("error", {"assistant_id": member.id, "message": piece})
                elif kind == "out_of_scope":
                    
                    yield _sse(
                        "out_of_scope",
                        {
                            "assistant_id": member.id,
                            "name": member.name,
                            "skill": piece,
                            "owners": skill_owners(members, piece),
                        },
                    )
                elif kind == "final":
                    text = piece

            clean, control, reason = parse_control(text)
            if clean:
                say(history, role="assistant", name=member.name, content=clean)
                yield _sse(
                    "message",
                    {"assistant_id": member.id, "name": member.name, "content": clean},
                )

            
            
            
            
            
            if control in ("pass", "reject") and role == "reviewer":
                
                
                passed = control == "pass"
                
                
                
                
                
                owner = summary_owner(members) if passed else None
                yield _sse(
                    "review",
                    {
                        "assistant_id": member.id,
                        "name": member.name,
                        "passed": passed,
                        "reason": reason,
                        
                        
                        "summary_by": _who(owner),
                    },
                )
                if not passed:
                    continue
                async for chunk in emit_summary(
                    runtime,
                    group,
                    members,
                    history,
                    owner,
                    thread_id,
                    reason="审核员已验收通过",
                    background=background,
                ):
                    yield chunk
                
                
                yield _sse("done", {"reason": "review_passed"})
                return

            if control == "end_vote" and not end_vote_by:
                if not may_end_vote:
                    
                    
                    yield _sse(
                        "vote_denied",
                        {
                            "assistant_id": member.id,
                            "name": member.name,
                            "reason": "结束投票只能由首位发言者（会话发起人）或末序发言者发起，请在发言里 @ 他们。",
                        },
                    )
                    continue
                end_vote_by = member.id
                votes = {}
                yield _sse(
                    "vote_request",
                    {"assistant_id": member.id, "name": member.name, "reason": reason},
                )
                continue

            if end_vote_by and control in ("agree", "disagree"):
                votes[member.id] = control == "agree"
                yield _sse(
                    "vote",
                    {
                        "assistant_id": member.id,
                        "name": member.name,
                        "agree": control == "agree",
                    },
                )
                others = [item.id for item in members if item.id != end_vote_by]
                all_voted = all(item in votes for item in others)
                passed = vote_passed(votes)
                if passed or all_voted:
                    
                    
                    
                    
                    
                    
                    owner = summary_owner(members) if passed else None
                    yield _sse("vote_result", {"passed": passed, "summary_by": _who(owner)})
                    if passed:
                        async for chunk in emit_summary(
                            runtime,
                            group,
                            members,
                            history,
                            owner,
                            thread_id,
                            reason="讨论已通过结束投票",
                            background=background,
                        ):
                            yield chunk
                        yield _sse("done", {"reason": "voted"})
                        return
                    
                    end_vote_by = ""
                    votes = {}

    yield _sse(
        "done",
        {"reason": "max_rounds", "message": f"已达到安全轮数上限（{MAX_ROUNDS} 轮），讨论自动结束。"},
    )
async def emit_summary(
    runtime: AppRuntime,
    group: GroupProfile,
    members: list[Any],
    history: list[Any],
    owner: Any | None,
    thread_id: str,
    *,
    reason: str = "讨论已收尾",
    images: list[Any] | None = None,
    background: bool = False,
) -> AsyncIterator[str]:











    if owner is None:
        
        
        logger.warning("最终总结：没有可交付的成员（members 为空），跳过 group=%s", group.id)
        return
    yield _sse("speaker", {"assistant_id": owner.id, "name": owner.name})
    summary = ""
    prompt = (
        f"{reason}，讨论到此结束。"
        "请你作为**本群的发起人**给出**最终总结**：把大家的结论收敛成一段清晰的交付"
        "（结论 + 关键理由），直接面向用户。"
        "⚠️ 这段交付必须由你**自己**产出：不要再 @ 别的成员、不要把交付推给别人，"
        "也不要再写 [END_VOTE] / [AGREE] 这类控制标记。"
    )
    
    
    roles = effective_roles(members)
    async for kind, piece in run_member(
        runtime,
        group,
        owner,
        history,
        prompt,
        thread_id,
        images=images,
        background=background,
        role=roles.get(owner.id, ""),
    ):
        if kind == "delta":
            yield _sse("delta", {"assistant_id": owner.id, "text": piece})
        elif kind == "final":
            summary = piece
    if summary:
        say(history, role="assistant", name=owner.name, content=summary)
        yield _sse(
            "summary",
            {"assistant_id": owner.id, "name": owner.name, "content": summary},
        )
async def discussion_source(
    runtime: AppRuntime,
    group: GroupProfile,
    members: list[Any],
    topic: str,
    thread_id: str,
    *,
    attachment_block: str = "",
    images: list[Any] | None = None,
    background: bool = False,
) -> AsyncIterator[str]:










    try:
        async for chunk in discuss_stream(
            runtime,
            group,
            members,
            topic,
            thread_id,
            attachment_block=attachment_block,
            images=images,
            background=background,
        ):
            yield chunk
    finally:
        pending = runtime.reject_pending(owner=confirm_owner(group.id))
        if pending:
            logger.info("群讨论收尾：已按拒绝收起 %s 个挂起的确认 group=%s", pending, group.id)





































from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from ..protocol import parse_sse
from ..utils.timefmt import format_stamp, now_iso, parse_iso

if TYPE_CHECKING:  
    
    
    from ..config.schemas import GroupProfile
    from ..server.runtime import AppRuntime

logger = logging.getLogger(__name__)


def ordered_members(runtime: AppRuntime, group: GroupProfile) -> list[Any]:

    ids = list(group.member_assistant_ids)
    ordered = [item for item in group.speaking_order if item in ids]
    rest = [item for item in ids if item not in ordered]
    members: list[Any] = []
    for member_id in ordered + rest:
        member = runtime.assistants.get(member_id)
        if member is not None:
            members.append(member)
    return members


def say(
    history: list[dict[str, str]],
    *,
    role: str,
    name: str,
    content: str,
    at: str = "",
) -> None:







    history.append({"role": role, "name": name, "content": content, "at": at or now_iso()})


def history_line(item: dict[str, str]) -> str:




    who = "用户" if item.get("role") == "user" else item.get("name", "搭子")
    return f"{format_stamp(parse_iso(item.get('at')))}{who}：{item.get('content', '')}"


def render_history(history: list[dict[str, str]], group_name: str, current_name: str) -> str:
    lines = [f"这是群聊「{group_name}」，你是其中的成员「{current_name}」。前面的对话："]
    lines.extend(history_line(item) for item in history)
    lines.append(f"现在轮到你（{current_name}）发言。请自然地接着聊，不要替别人发言。")
    return "\n".join(lines)


async def restore_history(
    runtime: AppRuntime, group_id: str, thread_id: str
) -> list[dict[str, str]]:








    key = (group_id, thread_id)
    existing = runtime._group_history.get(key)
    if existing is not None:
        return existing
    history: list[dict[str, str]] = []
    if runtime.db_ready:
        try:
            events = await runtime.group_event_repo.list_events(group_id, thread_id)
        except Exception as exc:  
            logger.warning("群聊历史读取失败 group=%s thread=%s: %s", group_id, thread_id, exc)
            events = []
        for item in events:
            event, data = item.get("event"), item.get("data") or {}
            content = str(data.get("content") or "").strip()
            if not content:
                continue
            
            
            at = str(item.get("created_at") or "")
            if event == "topic":
                say(history, role="user", name="用户", content=content, at=at)
            elif event in ("message", "summary"):
                say(
                    history,
                    role="assistant",
                    name=str(data.get("name") or ""),
                    content=content,
                    at=at,
                )
    runtime._group_history[key] = history
    return history


async def persisting_stream(
    runtime: AppRuntime,
    group_id: str,
    thread_id: str,
    source: AsyncIterator[str],
    *,
    background: bool = False,
) -> AsyncIterator[str]:













    run_id = await runtime.runs.start(
        kind="group", ref_id=group_id, session_id=f"group:{group_id}"
    )
    step = 0
    last_action = ""
    
    
    outcome = "cancelled"
    error = ""
    try:
        async for chunk in source:
            parsed = parse_sse(chunk)
            if parsed is not None:
                name, data = parsed
                if name in ("message", "summary"):
                    step += 1
                    last_action = f"{data.get('name') or '搭子'} 发言"
                    await runtime.runs.progress(run_id, step=step, last_action=last_action)
                elif name == "done":
                    outcome = "done"
                if name != "delta" and runtime.db_ready:
                    try:
                        await runtime.group_event_repo.append(group_id, thread_id, name, data)
                    except Exception as exc:  
                        logger.warning("群聊事件落库失败 group=%s: %s", group_id, exc)
                if background:
                    
                    
                    
                    
                    
                    
                    runtime.events.publish(
                        "group_event",
                        group_id=group_id,
                        thread_id=thread_id,
                        event=name,
                        data=data,
                    )
            yield chunk
    except Exception as exc:  
        outcome = "failed"
        error = str(exc)[:500]
        raise
    finally:
        
        if outcome == "done":
            await runtime.runs.finish(run_id)
        else:
            await runtime.runs.interrupt(
                run_id,
                status="failed" if outcome == "failed" else "cancelled",
                step=step,
                last_action=last_action,
                error=error or "讨论还没结束就中断了",
            )
        
        
        await runtime.audit.op(
            kind="group",
            action="discuss_done" if outcome == "done" else "discuss_interrupted",
            target=group_id,
            session_id=f"group:{group_id}",
            status="ok" if outcome == "done" else "error",
            detail=(
                f"讨论{'结束' if outcome == 'done' else '中断'}：共 {step} 条发言"
                + (f"，最后是 {last_action}" if last_action else "")
                + (f"；{error}" if error else "")
            )[:400],
        )


async def resolve_thread(runtime: AppRuntime, group_id: str, thread_id: str) -> str:










    wanted = thread_id.strip()
    if wanted:
        existing = await runtime.group_thread_repo.get(group_id, wanted)
        if existing is not None:
            return wanted
        
        
        logger.info("群 %s 收到未知对话 id %s，回退到最近一条", group_id, wanted)

    threads = await runtime.group_thread_repo.list_threads(group_id)
    if threads:
        return str(threads[0]["id"])
    created = await runtime.group_thread_repo.create(group_id)
    return str(created["id"])


MAX_ROUNDS = 60
def confirm_owner(group_id: str) -> str:






    return f"group:{group_id}"
def parse_control(text: str) -> tuple[str, str, str]:




    clean = (text or "").strip()
    if "[END_VOTE]" in clean:
        index = clean.index("[END_VOTE]")
        return clean[:index].strip(), "end_vote", clean[:index].strip()[-120:]
    if "[AGREE]" in clean:
        return clean.replace("[AGREE]", "").strip(), "agree", ""
    if "[DISAGREE]" in clean:
        return clean.replace("[DISAGREE]", "").strip(), "disagree", ""
    if "[PASS]" in clean:
        return clean.replace("[PASS]", "").strip(), "pass", ""
    if "[REJECT]" in clean:
        index = clean.index("[REJECT]")
        
        
        return clean[:index].strip(), "reject", clean[index + len("[REJECT]") :].strip()[:200]
    return clean, "", ""
def skill_owners(members: list[Any], skill: str) -> list[str]:





    return [item.name for item in members if skill in set(item.enabled_skills or [])]











ROLE_LABELS: dict[str, str] = {
    "coordinator": "协调者（总管）",
    "worker": "执行者",
    "advisor": "优化顾问",
    "reviewer": "审核员",
}
def effective_roles(members: list[Any]) -> dict[str, str]:

    roles: dict[str, str] = {}
    for index, member in enumerate(members):
        assigned = getattr(member, "group_role", "") or ""
        if assigned in ROLE_LABELS:
            roles[member.id] = assigned
        elif index == 0:
            roles[member.id] = "coordinator"
        elif index == len(members) - 1:
            roles[member.id] = "reviewer"
        elif index == len(members) - 2:
            roles[member.id] = "advisor"
        else:
            roles[member.id] = "worker"
    return roles
def can_end_vote(members: list[Any], member: Any) -> bool:





    if not members:
        return False
    return member.id in {members[0].id, members[-1].id}
def summary_owner(members: list[Any]) -> Any | None:





















    if not members:
        return None
    roles = effective_roles(members)
    first = members[0]
    if roles.get(first.id) not in ("reviewer", "advisor"):
        return first
    coordinator = next((item for item in members if roles.get(item.id) == "coordinator"), None)
    if coordinator is None:
        logger.warning(
            "最终总结：首位发言者 %s 的角色是 %s（不动手交付），但群里没有协调者可退，仍由它总结",
            first.name,
            roles.get(first.id),
        )
        return first
    logger.info(
        "最终总结：首位发言者 %s 的角色是 %s（不动手交付），改由协调者 %s 做",
        first.name,
        roles.get(first.id),
        coordinator.name,
    )
    return coordinator
def role_rules(role: str, *, can_end_vote: bool) -> str:






    common = (
        "- 只做**你自己职责范围内**的事：别人的活（写代码、做表、审核…）请用 @名字 交给"
        "对应成员，不要自己抢着做完 —— 越界调用别人的工具会在群里被标出来。\n"
    )
    if role == "coordinator":
        body = (
            "你在这场讨论里是**协调者（总管）**：\n"
            "- 开场先把任务拆成几条具体的事，明确每条交给谁（用 @名字），再往下走；\n"
            "- 有人把活退回来（审核不通过）时，你要照着反馈**重新分配**并说明改了什么；\n"
            "- 最后把大家的结论收敛成一份交付（结论 + 关键理由）。\n"
        )
    elif role == "reviewer":
        body = (
            "你在这场讨论里是**审核员**：\n"
            "- 别人给出交付后，你按能不能直接用的标准验收（完整性、有没有明显错漏）；\n"
            "- 达标：在发言最后单独一行写 [PASS]；\n"
            "- 不达标：写 [REJECT]，并在同一段里说清**具体缺什么、该怎么改**"
            "（总管会照着它重新安排）；\n"
            "- 优化顾问提出建议时**把关**：建议确实必要（不是可有可无的小改动）就批准并"
            " [REJECT] 打回完善；建议可有可无就不批准、直接按交付物本身 [PASS]/[REJECT]；\n"
            "- 不要自己动手改交付物 —— 指出问题、交回给总管。\n"
        )
    elif role == "advisor":
        body = (
            "你在这场讨论里是**优化顾问**：\n"
            "- 在交付出来后，审视它有没有**必要**的改进空间（明显更优的方案、遗漏的要点）；\n"
            "- 只提必要的、有分量的建议，可有可无的小改动一律不提；\n"
            "- 建议说清「改什么、为什么值得改、大概怎么改」，交给审核员把关；\n"
            "- 不替执行者动手改。\n"
        )
    else:
        body = (
            "你在这场讨论里是**执行者**：\n"
            "- 只做分配给你的那部分，做完把结果直接说出来；\n"
            "- 需要别人配合时 @ 他，不要越俎代庖。\n"
        )
    vote = (
        "- 你可以发起结束投票：认为讨论充分时，在发言最后单独一行写 [END_VOTE]。\n"
        if can_end_vote
        else "- 结束投票只能由**首位发言者（会话发起人）或末序发言者**发起；你认为该收尾时 @ 他们提出即可。\n"
    )
    return body + common + vote
def vote_passed(votes: dict[str, bool]) -> bool:

    if not votes:
        return False
    agree = sum(1 for value in votes.values() if value)
    return agree > len(votes) / 2

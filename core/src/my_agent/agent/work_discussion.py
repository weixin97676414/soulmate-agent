

























from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from ..protocol import format_sse
from .group_discussion import run_member
from .group_domain import (
    ROLE_LABELS,
    effective_roles,
    parse_control,
    parse_dispatch,
    say,
)

if TYPE_CHECKING:  
    from ..config.schemas import GroupProfile
    from ..server.runtime import AppRuntime

logger = logging.getLogger(__name__)

_sse = format_sse



MAX_WORK_ROUNDS = 3





def _coordinator_context(topic: str, deliverable: str, hint: str, hint_label: str) -> str:





    parts = [f"用户在群里的原始需求：\n{topic}"]
    if deliverable:
        parts.append(f"上一轮已经做出的交付物（判断该怎么改时参考）：\n---\n{deliverable}\n---")
    if hint:
        parts.append(f"{hint_label}：\n{hint}")
    return "\n\n".join(parts)


def _worker_context(
    topic: str, assignment: str, previous: str, hint: str, hint_label: str
) -> str:





    parts = [f"用户在群里的原始需求（供理解背景，你只需要做自己那一部分）：\n{topic}"]
    parts.append(f"总管这次分派给你的任务：\n{assignment}")
    if previous:
        parts.append(f"你上一轮做出的东西（这次在它的基础上改）：\n---\n{previous}\n---")
    if hint:
        parts.append(f"{hint_label}：\n{hint}")
    return "\n\n".join(parts)


def _review_context(topic: str, deliverable: str) -> str:

    return (
        f"用户在群里的原始需求：\n{topic}\n\n"
        f"本轮交付物（你要判断的就是它）：\n---\n{deliverable}\n---"
    )


def _merge_outputs(workers: list[Any], outputs: dict[str, str]) -> str:

    blocks: list[str] = []
    for worker in workers:
        body = (outputs.get(worker.id) or "").strip() or "（这一部分没有产出）"
        blocks.append(f"## {worker.name}\n{body}")
    return "\n\n".join(blocks)


def _fallback_assignments(topic: str, workers: list[Any]) -> dict[str, str]:




    shared = (
        f"总管没能把任务拆开，以下是整体需求，请**挑你能做的那部分**做扎实，"
        f"并在开头说明你负责的是哪一块：\n{topic}"
    )
    return {worker.id: shared for worker in workers}





def _say_frame(member: Any, role: str) -> str:
    return _sse(
        "speaker",
        {
            "assistant_id": member.id,
            "name": member.name,
            "role": role,
            "role_label": ROLE_LABELS.get(role, ""),
        },
    )


async def _speak(
    runtime: AppRuntime,
    group: GroupProfile,
    member: Any,
    history: list[Any],
    thread_id: str,
    *,
    role: str,
    context_text: str,
    user_input: str,
    background: bool,
    images: list[Any] | None = None,
) -> AsyncIterator[tuple[str, Any]]:





    yield "sse", _say_frame(member, role)
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
        can_end_vote=False,
        context_text=context_text,
    ):
        if kind == "delta":
            text += piece
            yield "sse", _sse("delta", {"assistant_id": member.id, "text": piece})
        elif kind == "reasoning":
            yield "sse", _sse(
                "reasoning", {"assistant_id": member.id, "name": member.name, "text": piece}
            )
        elif kind == "tool_call":
            yield "sse", _sse(
                "tool_call", {"assistant_id": member.id, "name": member.name, "tool": piece}
            )
        elif kind == "tool_result":
            yield "sse", _sse(
                "tool_result", {"assistant_id": member.id, "name": member.name, "tool": piece}
            )
        elif kind == "out_of_scope":
            yield "sse", _sse(
                "out_of_scope", {"assistant_id": member.id, "name": member.name, "skill": piece}
            )
        elif kind == "error":
            yield "sse", _sse("error", {"assistant_id": member.id, "message": piece})
        elif kind == "final":
            text = piece or text

    clean, control, reason = parse_control(text)
    if clean:
        say(history, role="assistant", name=member.name, content=clean)
        yield "sse", _sse(
            "message", {"assistant_id": member.id, "name": member.name, "content": clean}
        )
    yield "result", (clean, control, reason)


async def _collect(
    runtime: AppRuntime,
    group: GroupProfile,
    member: Any,
    history: list[Any],
    thread_id: str,
    *,
    role: str,
    context_text: str,
    user_input: str,
    background: bool,
    images: list[Any] | None = None,
) -> tuple[str, str, str]:





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
        can_end_vote=False,
        context_text=context_text,
    ):
        if kind == "delta":
            text += piece
        elif kind == "final":
            text = piece or text

    clean, control, reason = parse_control(text)
    if clean:
        say(history, role="assistant", name=member.name, content=clean)
    return clean, control, reason





async def work_stream(
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

    roles = effective_roles(members)
    coordinator = next((m for m in members if roles.get(m.id) == "coordinator"), None)
    workers = [m for m in members if roles.get(m.id) == "worker"]
    advisor = next((m for m in members if roles.get(m.id) == "advisor"), None)
    reviewer = next((m for m in members if roles.get(m.id) == "reviewer"), None)

    if coordinator is None:
        yield _sse("error", {"message": "这个工作群没有总管（Buddy Manager），流水线跑不起来。"})
        yield _sse("done", {"reason": "no_coordinator"})
        return
    if not workers:
        yield _sse("error", {"message": "这个工作群没有执行者，至少要有 1 个负责干活的搭子。"})
        yield _sse("done", {"reason": "no_worker"})
        return

    previous: dict[str, str] = {}
    deliverable = ""
    optimization_hint = ""
    reject_hint = ""
    summary_reason = "流水线跑完"

    for round_index in range(MAX_WORK_ROUNDS):
        last_round = round_index == MAX_WORK_ROUNDS - 1
        round_no = round_index + 1

        
        yield _sse(
            "stage",
            {"stage": "dispatch", "round": round_no, "label": f"第 {round_no} 轮 · 分发任务"},
        )
        dispatch_input = (
            "请把任务分派给执行者（只输出 [DISPATCH] 块，不要写别的）。"
            if round_no == 1
            else "请根据上面的交付物与改进要求，**重新分配任务**（只输出 [DISPATCH] 块）。"
        )
        ctx = _coordinator_context(
            topic,
            deliverable,
            optimization_hint or reject_hint,
            "优化员提出的改进要求" if optimization_hint else "审核员驳回的意见",
        )
        assignments: dict[str, str] = {}
        async for kind, payload in _speak(
            runtime,
            group,
            coordinator,
            history,
            thread_id,
            role="coordinator",
            context_text=ctx,
            user_input=dispatch_input,
            background=background,
        ):
            if kind == "sse":
                yield payload
        _ = assignments  

        
        
        raw_last = history[-1].get("content", "") if history else ""
        assignments = parse_dispatch(raw_last) or {}
        if not assignments:
            
            assignments = _fallback_assignments(topic, workers)
            yield _sse(
                "stage",
                {
                    "stage": "dispatch_fallback",
                    "round": round_no,
                    "label": "分发格式没解析出来，已按整体任务下发",
                },
            )

        
        yield _sse(
            "stage",
            {"stage": "execute", "round": round_no, "label": f"第 {round_no} 轮 · 执行中"},
        )
        for worker in workers:
            yield _sse(
                "speaker",
                {
                    "assistant_id": worker.id,
                    "name": worker.name,
                    "role": "worker",
                    "role_label": ROLE_LABELS.get("worker", ""),
                },
            )

        
        
        _assignments = dict(assignments)
        _hint = optimization_hint or reject_hint
        _hint_label = "这次要改的地方" if optimization_hint else "审核员驳回的意见"

        async def _run(
            worker: Any,
            _bound_assignments: dict[str, str] = _assignments,
            _bound_hint: str = _hint,
            _bound_label: str = _hint_label,
        ) -> tuple[str, str]:
            try:
                clean, _, _ = await _collect(
                    runtime,
                    group,
                    worker,
                    history,
                    thread_id,
                    role="worker",
                    context_text=_worker_context(
                        topic,
                        _bound_assignments.get(worker.id)
                        or _bound_assignments.get(worker.name)
                        or "（总管没给你单独的任务，按整体需求做你能做的那部分）",
                        previous.get(worker.id, ""),
                        _bound_hint,
                        _bound_label,
                    ),
                    user_input="请完成分派给你的任务，直接把成果写出来。",
                    background=background,
                    images=images,
                )
                return worker.id, clean
            except asyncio.CancelledError:
                raise
            except Exception as exc:  
                logger.warning("工作群执行者 %s 失败：%s", worker.id, exc)
                return worker.id, f"（执行失败：{exc}）"

        gathered = await asyncio.gather(
            *(_run(worker) for worker in workers), return_exceptions=True
        )
        outputs: dict[str, str] = {}
        for item in gathered:
            if isinstance(item, BaseException):
                logger.warning("工作群执行阶段异常：%s", item)
                continue
            worker_id, text = item
            outputs[worker_id] = text

        
        for worker in workers:
            body = (outputs.get(worker.id) or "").strip()
            if not body:
                continue
            yield _sse(
                "message",
                {"assistant_id": worker.id, "name": worker.name, "content": body},
            )
            previous[worker.id] = body

        if not any((outputs.get(worker.id) or "").strip() for worker in workers):
            yield _sse("error", {"message": "这一轮所有执行者都失败了，流水线中止。"})
            yield _sse("done", {"reason": "all_workers_failed"})
            return

        deliverable = _merge_outputs(workers, outputs)

        
        if not last_round and advisor is not None:
            yield _sse(
                "stage",
                {"stage": "optimize", "round": round_no, "label": f"第 {round_no} 轮 · 优化评审"},
            )
            opt_control = ""
            opt_reason = ""
            async for kind, payload in _speak(
                runtime,
                group,
                advisor,
                history,
                thread_id,
                role="advisor",
                context_text=_review_context(topic, deliverable),
                user_input="请看这份交付物，有必要的改进就写 [OPTIMIZE] 并给出具体建议，没有就写 [NO_OPTIMIZE]。",
                background=background,
            ):
                if kind == "sse":
                    yield payload
                else:
                    _, opt_control, opt_reason = payload
            if opt_control == "optimize" and opt_reason.strip():
                optimization_hint = opt_reason.strip()
                reject_hint = ""
                
                yield _sse(
                    "stage",
                    {
                        "stage": "decide_optimize",
                        "round": round_no,
                        "label": f"第 {round_no} 轮 · 总管决定是否采纳优化",
                    },
                )
                decision = ""
                async for kind, payload in _speak(
                    runtime,
                    group,
                    coordinator,
                    history,
                    thread_id,
                    role="coordinator",
                    context_text=(
                        f"用户需求：\n{topic}\n\n优化员提出的改进建议：\n{optimization_hint}\n\n"
                        f"当前交付物：\n---\n{deliverable}\n---"
                    ),
                    user_input="你采纳这条建议吗？采纳写 [ACCEPT_OPT]，不采纳写 [DECLINE_OPT]（只输出标记）。",
                    background=background,
                ):
                    if kind == "sse":
                        yield payload
                    else:
                        decision = payload[1]
                if decision == "accept_opt":
                    continue  
                optimization_hint = ""  

        
        verdict = ""
        verdict_reason = ""
        if reviewer is not None:
            yield _sse(
                "stage",
                {"stage": "review", "round": round_no, "label": f"第 {round_no} 轮 · 审核验收"},
            )
            async for kind, payload in _speak(
                runtime,
                group,
                reviewer,
                history,
                thread_id,
                role="reviewer",
                context_text=_review_context(topic, deliverable),
                user_input="这份交付物能直接交给用户用吗？达标写 [PASS]，不达标写 [REJECT] 并说清缺什么。",
                background=background,
            ):
                if kind == "sse":
                    yield payload
                else:
                    _, verdict, verdict_reason = payload

        if verdict == "pass":
            summary_reason = "审核员验收通过"
            break

        
        if last_round:
            
            summary_reason = "已达轮次上限，审核未通过仍进入总结"
            break
        if verdict != "reject":
            
            summary_reason = "审核未给出明确结论，按通过处理"
            break

        reject_hint = verdict_reason or "审核员未说明具体原因"
        optimization_hint = ""
        yield _sse(
            "stage",
            {
                "stage": "decide_reject",
                "round": round_no,
                "label": f"第 {round_no} 轮 · 总管决定是否重做",
            },
        )
        redo = ""
        async for kind, payload in _speak(
            runtime,
            group,
            coordinator,
            history,
            thread_id,
            role="coordinator",
            context_text=(
                f"用户需求：\n{topic}\n\n审核员的驳回意见：\n{reject_hint}\n\n"
                f"当前交付物：\n---\n{deliverable}\n---"
            ),
            user_input="你采纳这条驳回意见吗？采纳（重做）写 [REDO]，不采纳（照样交付）写 [FINAL]。",
            background=background,
        ):
            if kind == "sse":
                yield payload
            else:
                redo = payload[1]
        if redo != "redo":
            summary_reason = "总管不采纳驳回意见，直接总结"
            break
        

    
    yield _sse("stage", {"stage": "summary", "round": 0, "label": "总结交付"})
    summary_input = (
        f"这是最后的总结环节（{summary_reason}）。请把最终交付直接写给用户："
        "不要再 @ 任何成员、不要再输出 [DISPATCH] 这类标记，直接给成品与关键说明。"
    )
    async for kind, payload in _speak(
        runtime,
        group,
        coordinator,
        history,
        thread_id,
        role="coordinator",
        context_text=(
            f"用户需求：\n{topic}\n\n最终交付物：\n---\n{deliverable}\n---"
        ),
        user_input=summary_input,
        background=background,
        images=images,
    ):
        if kind == "sse":
            yield payload

    yield _sse("done", {"reason": summary_reason})

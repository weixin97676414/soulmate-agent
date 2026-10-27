









from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ..errors import LLMError, SkillPermissionError
from ..llm.base import BaseLLM, ImagePart, ToolCall, ToolSpec
from ..memory.short_term import MemoryManager, internal_hint
from ..observability.tracer import Tracer
from ..skill.base import SkillContext, wants_terminate
from ..skill.manager import SkillManager
from .context import ContextGuard, ContextPolicy, looks_like_context_overflow
from .planner import Plan, Planner, coerce_step_status, plan_hint
from .reflection import Reflector, revision_hint
from .text_tools import extract_text_tool_calls, render_tools_section

logger = logging.getLogger(__name__)




NUDGE_TEXT = "请针对我上一条消息给出明确的回复。"




PLAN_ABORTED_TEXT = "好，这次先不动手。需要的时候再说一声。"









_STAMP_CHAIN = re.compile(r"^(?:\[\d{1,2}-\d{1,2} \d{1,2}:\d{2}\]\s*)+")

_STAMP_PARTIAL = re.compile(r"\[\d{0,2}(?:-\d{0,2})?(?: \d{0,2})?(?::\d{0,2})?\]?")


def strip_timestamp_prefix(text: str) -> str:

    if not text:
        return text
    return _STAMP_CHAIN.sub("", text, count=1)



_NO_STAMP_RULE = (
    "\n\n## 输出格式的一条硬性规矩\n"
    "回复正文里**绝对不要**输出 `[09-28 18:00]` 这种时间戳前缀 —— "
    "那是对话记录的内部格式，界面会自动显示每条消息和每次工具调用的时刻，"
    "你写出来只会变成一串串的噪音。需要知道现在几点时，调用 system_time 技能。"
)


class _StampStripper:










    
    
    _MAX_PENDING = 20

    def __init__(self) -> None:
        self._pending = ""
        self._decided = False

    def feed(self, delta: str) -> str:

        if self._decided:
            return delta
        self._pending += delta
        
        while True:
            matched = _STAMP_CHAIN.match(self._pending)
            if not matched:
                break
            self._pending = self._pending[matched.end():]
        
        
        if self._pending == "":
            return ""
        
        if self._pending.startswith("["):
            partial = _STAMP_PARTIAL.match(self._pending)
            if partial and partial.end() == len(self._pending) <= self._MAX_PENDING:
                return ""
        self._decided = True
        text, self._pending = self._pending, ""
        return text

    def flush(self) -> str:

        text, self._pending = self._pending, ""
        self._decided = True
        return text


def _thinking_no_effect_notice() -> str:









    return (
        "你为这次对话选了「思考强度」，但模型没有返回任何思考内容。"
        "这通常说明这家服务商对思考参数的写法与我们发送的不一致 —— "
        "各家并不统一：OpenAI 用 reasoning_effort，通义用 enable_thinking + "
        "thinking_budget，智谱用 thinking 对象。"
        "回答质量本身不受影响，只是这个档位没有生效。"
    )









PlanDecider = Callable[[dict[str, Any]], Awaitable[tuple[bool, str]]]


def apply_plan_update(plan: Plan, arguments: dict[str, Any]) -> tuple[bool, str]:









    step_id = str(arguments.get("step") or "").strip()
    status = coerce_step_status(arguments.get("status"))
    note = str(arguments.get("note") or "").strip()

    step = plan.find(step_id)
    if step is None:
        available = "、".join(item.id for item in plan.steps) or "（无）"
        return False, (
            f"[无效步号] 计划里没有第 {step_id or '?'} 步，本次汇报没有生效。"
            f"可用的步号是：{available}。请用正确的步号重新调用 plan_update。"
        )
    step.status = status
    if note:
        step.note = note
    return True, f"第 {step_id} 步已标记为「{status}」。"


@dataclass
class AgentConfig:


    
    
    
    
    
    
    
    
    
    
    
    
    max_iterations: int = 500
    max_tool_calls_per_turn: int = 500
    temperature: float = 0.7
    max_tokens: int | None = None

    
    
    
    
    
    top_p: float | None = None
    
    frequency_penalty: float | None = None
    
    presence_penalty: float | None = None
    
    
    
    reasoning_effort: str | None = None
    
    
    
    
    
    
    
    
    
    
    persona: str | Callable[[], str] = ""
    same_tool_failure_tolerance: int = 3
    enabled_skills: set[str] | None = None

    
    
    
    
    target_assistant: str = ""

    
    token_limit: int = 32000
    context_policy: ContextPolicy = field(default_factory=ContextPolicy)

    
    
    
    supports_vision: bool = False

    
    
    enable_planner: bool = False
    enable_reflection: bool = False
    reflection_rounds: int = 1

    
    
    
    
    
    
    
    
    
    plan_decider: PlanDecider | None = None


@dataclass
class AgentEvent:


















    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> tuple[str, dict[str, Any]]:
        return self.type, self.data


class Agent:
    def __init__(
        self,
        *,
        llm: BaseLLM,
        skill_manager: SkillManager,
        memory: MemoryManager,
        config: AgentConfig,
        ctx: SkillContext,
        tracer: Tracer | None = None,
        utility_llm: BaseLLM | None = None,
    ) -> None:
        self.llm = llm
        
        
        
        
        
        
        
        
        self.utility_llm = utility_llm or llm
        self.skills = skill_manager
        self.memory = memory
        self.config = config
        self.ctx = ctx
        self.tracer = tracer or Tracer()
        self.context_guard = ContextGuard(config.context_policy)
        self.planner = Planner(enabled=config.enable_planner)
        self.reflector = Reflector(
            enabled=config.enable_reflection, max_rounds=config.reflection_rounds
        )
        
        
        
        
        
        self._active_plan: Plan | None = None
        
        
        self._plan_message = None
        
        
        
        self._tool_images: dict[str, list[ImagePart]] = {}

    
    
    
    async def run_stream(
        self, user_input: str, *, images: list[ImagePart] | None = None
    ) -> AsyncIterator[AgentEvent]:















        async with self.llm.lease():
            async for event in self._run_stream_impl(user_input, images=images):
                yield event

    async def _run_stream_impl(
        self, user_input: str, *, images: list[ImagePart] | None = None
    ) -> AsyncIterator[AgentEvent]:
        self.memory.add_user(user_input, images=images)
        
        self._tool_images.clear()
        
        
        self.memory.ensure_system(self._system_prompt())

        
        
        
        
        
        
        
        self._active_plan = None
        if self.config.plan_decider is not None and self.planner.should_plan(
            user_input, need_tools=self.llm.supports_tools
        ):
            async for event in self._plan_phase(user_input):
                yield event
            if self._active_plan is not None and self._active_plan.state == "aborted":
                
                
                
                
                
                self.memory.add_assistant(PLAN_ABORTED_TEXT)
                yield AgentEvent("message_start", {"iteration": 0})
                yield AgentEvent("delta", {"text": PLAN_ABORTED_TEXT})
                yield AgentEvent(
                    "message_end",
                    {"iteration": 0, "content": PLAN_ABORTED_TEXT, "tool_calls": []},
                )
                yield self._done_event(iterations=0)
                return
            if self._active_plan is not None:
                
                
                
                
                self.memory.add_user(plan_hint(self._active_plan))

        
        
        
        
        
        
        plan_pending = self._active_plan is not None and self._active_plan.state == "executing"
        self._plan_message = None

        
        failure_counts: dict[str, int] = {}
        disabled_tools: set[str] = set()
        empty_response_nudges = 0
        
        review_rounds = 0
        iteration = 0
        collected_text = ""
        collected_reasoning = ""
        
        
        
        
        
        
        
        saw_reasoning = False
        
        
        text_persisted = False

        try:
            while iteration < self.config.max_iterations:
                iteration += 1
                with self._span(f"step:{iteration}"):
                    yield AgentEvent("message_start", {"iteration": iteration})

                    collected_text = ""
                    collected_reasoning = ""
                    text_persisted = False
                    tool_calls: list[ToolCall] = []
                    usage: dict[str, Any] = {}
                    
                    
                    segment_stripper = _StampStripper()

                    
                    
                    
                    live_text = self.llm.supports_tools

                    
                    
                    if self.context_guard.should_compress(self.memory, self.config.token_limit):
                        if await self.context_guard.compress(
                            self.utility_llm, self.memory, token_limit=self.config.token_limit
                        ):
                            yield AgentEvent(
                                "context_compressed",
                                {"summary_chars": len(self.memory.summary)},
                            )

                    retried_for_overflow = False
                    
                    externalized_for_overflow = False
                    while True:
                        produced = False
                        try:
                            
                            
                            
                            async for chunk in self.llm.leased_stream(
                                self.memory.get_context(),
                                
                                
                                self._tool_specs(disabled_tools)
                                if self.llm.supports_tools
                                else None,
                                temperature=self.config.temperature,
                                max_tokens=self.config.max_tokens,
                                top_p=self.config.top_p,
                                frequency_penalty=self.config.frequency_penalty,
                                presence_penalty=self.config.presence_penalty,
                                reasoning_effort=self.config.reasoning_effort,
                            ):
                                produced = True
                                if chunk.reasoning_delta:
                                    saw_reasoning = True
                                    collected_reasoning += chunk.reasoning_delta
                                    yield AgentEvent(
                                        "reasoning", {"text": chunk.reasoning_delta}
                                    )
                                if chunk.delta:
                                    visible = segment_stripper.feed(chunk.delta)
                                    collected_text += visible
                                    if live_text and visible:
                                        yield AgentEvent("delta", {"text": visible})
                                if chunk.is_final:
                                    tool_calls = chunk.tool_calls or []
                                    usage = chunk.usage or {}
                            break
                        except LLMError as exc:
                            
                            
                            
                            
                            
                            
                            
                            
                            
                            
                            if not produced and looks_like_context_overflow(str(exc)):
                                if not retried_for_overflow:
                                    retried_for_overflow = True
                                    if await self.context_guard.compress(
                                        self.utility_llm,
                                        self.memory,
                                        token_limit=self.config.token_limit,
                                    ):
                                        logger.info("厂商报告上下文超限，已压缩历史后重试")
                                        continue
                                if not externalized_for_overflow:
                                    externalized_for_overflow = True
                                    if self.memory.externalize_oversized():
                                        continue
                            raise

                    if not live_text:
                        collected_text, text_calls = extract_text_tool_calls(collected_text)
                        collected_text = strip_timestamp_prefix(collected_text)
                        if collected_text:
                            yield AgentEvent("delta", {"text": collected_text})
                        if text_calls:
                            tool_calls = text_calls
                    else:
                        
                        
                        collected_text += segment_stripper.flush()

                    message = self.memory.add_assistant(
                        collected_text,
                        tool_calls,
                        collected_reasoning,
                        
                        plan=self._active_plan.to_dict() if plan_pending else None,
                    )
                    if plan_pending:
                        
                        
                        self._plan_message = message
                        plan_pending = False
                    text_persisted = True
                    self.tracer.add_usage(usage)
                    if usage:
                        yield AgentEvent("usage", usage)

                    yield AgentEvent(
                        "message_end",
                        {
                            "iteration": iteration,
                            "content": collected_text,
                            "tool_calls": [
                                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                                for tc in tool_calls
                            ],
                        },
                    )

                    
                    if not tool_calls:
                        if not collected_text.strip() and empty_response_nudges < 2:
                            
                            empty_response_nudges += 1
                            self.memory.add_user(internal_hint(NUDGE_TEXT))
                            continue
                        
                        
                        empty_response_nudges = 0

                        if self.reflector.should_review(
                            collected_text, rounds_done=review_rounds
                        ):
                            review_rounds += 1
                            review = await self.reflector.review(
                                self.utility_llm,
                                user_input=user_input,
                                answer=collected_text,
                                tool_summary=self._tool_summary(),
                            )
                            if review.needs_revision:
                                self.memory.add_user(revision_hint(review.feedback))
                                yield AgentEvent("reflection", {"feedback": review.feedback})
                                
                                continue

                        
                        
                        
                        
                        
                        
                        if self.config.reasoning_effort and not saw_reasoning:
                            yield AgentEvent(
                                "warning",
                                {"message": _thinking_no_effect_notice()},
                            )
                        yield self._done_event(iteration)
                        return

                    
                    terminated = False
                    async for event in self._execute_tool_calls(
                        tool_calls[: self.config.max_tool_calls_per_turn],
                        failure_counts,
                        disabled_tools,
                    ):
                        if event.type == "tool_result" and wants_terminate(
                            str(event.data.get("result", ""))
                        ):
                            terminated = True
                        yield event

                    if terminated:
                        logger.info("工具结果带终止标记，提前结束本轮任务")
                        yield self._done_event(iteration, terminated=True)
                        return

                    
                    empty_response_nudges = 0

                    
                    if len(tool_calls) > self.config.max_tool_calls_per_turn:
                        skipped = tool_calls[self.config.max_tool_calls_per_turn :]
                        for tc in skipped:
                            self.memory.add_tool(
                                tc.id,
                                tc.name,
                                f"[未执行] 单轮工具调用数已达上限"
                                f"（{self.config.max_tool_calls_per_turn}），请分批重试。",
                            )

            
            
            
            
            
            logger.warning("达到最大循环轮数 %s", self.config.max_iterations)
            yield AgentEvent(
                "error",
                {
                    "code": "agent_max_iterations",
                    "message": (
                        f"这一次任务已经来回执行了 {iteration} 步（模型↔工具往返），"
                        f"达到了当前上限 {self.config.max_iterations} 步，因此停下来了。"
                        "这不是出错，是防失控的兜底。"
                        "可以在「设置 → 模型与智能体」里调大「单次任务最大执行步数」，"
                        "或者把任务拆成几步分别交给它。"
                    ),
                    "iterations": iteration,
                    "limit": self.config.max_iterations,
                },
            )
            yield self._done_event(iteration, partial=True)

        except asyncio.CancelledError:
            
            
            
            if collected_text.strip() and not text_persisted:
                message = self.memory.add_assistant(
                    collected_text,
                    None,
                    collected_reasoning,
                    plan=self._active_plan.to_dict() if plan_pending else None,
                )
                if plan_pending:
                    self._plan_message = message
            
            
            
            
            sealed = self._seal_dangling_tool_calls()
            logger.info(
                "任务被用户中断（已完成 %s 轮，补齐 %s 个未回填的工具调用）", iteration, sealed
            )
            
            raise

    
    
    
    async def _plan_phase(self, user_input: str) -> AsyncIterator[AgentEvent]:








        decider = self.config.plan_decider
        if decider is None:  
            return

        feedback = ""
        while True:
            plan = await self.planner.make_plan(
                self.utility_llm,
                user_input=user_input,
                tool_names=self.skills.all_names(),
                feedback=feedback,
            )
            if plan is None:
                
                
                
                self._active_plan = None
                return

            
            
            plan.id = uuid4().hex
            plan.state = "awaiting"
            self._active_plan = plan
            yield AgentEvent("plan", plan.to_dict())

            approved, feedback = await decider(plan.to_dict())
            if approved:
                plan.state = "executing"
                yield AgentEvent("plan", plan.to_dict())
                return
            if not feedback.strip():
                
                plan.state = "aborted"
                yield AgentEvent("plan", plan.to_dict())
                return
            logger.info("用户对上一版计划提了修改意见，重拟一版")

    def _consume_plan_update(
        self, tc: ToolCall, outcome: tuple[str, str, float]
    ) -> tuple[tuple[str, str, float], AgentEvent | None]:





        if tc.name != "plan_update":
            return outcome, None
        status, _, duration_ms = outcome
        plan = self._active_plan
        if plan is None:
            
            
            return (
                status,
                "[本轮没有执行计划] plan_update 只在计划模式下有效，本次汇报未生效。"
                "请直接继续完成任务，不要再调用它。",
                duration_ms,
            ), None
        ok, message = apply_plan_update(plan, tc.arguments)
        if not ok:
            
            return (status, message, duration_ms), None
        if plan.state == "executing" and all(
            step.status in ("done", "failed") for step in plan.steps
        ):
            plan.state = "done"
        self._sync_plan_message()
        return (status, message, duration_ms), AgentEvent("plan_update", plan.to_dict())

    def _sync_plan_message(self) -> None:





        if self._plan_message is not None and self._active_plan is not None:
            self._plan_message.plan = self._active_plan.to_dict()

    
    
    
    def _seal_dangling_tool_calls(self) -> int:






        messages = self.memory.messages
        answered = {
            message.tool_call_id
            for message in messages
            if message.role == "tool" and message.tool_call_id
        }

        for message in reversed(messages):
            if message.role != "assistant":
                continue
            
            if not message.tool_calls:
                return 0
            missing = [call for call in message.tool_calls if call.id not in answered]
            for call in missing:
                self.memory.add_tool(
                    call.id, call.name, "[任务已中断] 该工具未执行完成，如需继续请重新提出。"
                )
            return len(missing)
        return 0

    
    
    
    async def _execute_tool_calls(
        self,
        tool_calls: list[ToolCall],
        failure_counts: dict[str, int],
        disabled_tools: set[str],
    ) -> AsyncIterator[AgentEvent]:







        prepared: list[tuple[ToolCall, Any, str]] = []

        
        
        for tc in tool_calls:
            meta = self.skills.get(tc.name).meta if self.skills.has(tc.name) else None
            display_name = (meta.display_name or tc.name) if meta else tc.name

            if tc.name in disabled_tools:
                message = f"工具 {tc.name} 已因连续失败被停用，请改用其他方案。"
                self.memory.add_tool(tc.id, tc.name, message)
                yield AgentEvent(
                    "tool_result",
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "display_name": display_name,
                        "status": "error",
                        "result": message,
                        "duration_ms": 0,
                    },
                )
                continue

            yield AgentEvent(
                "tool_call",
                {
                    "id": tc.id,
                    "name": tc.name,
                    "display_name": display_name,
                    "description": meta.description if meta else "",
                    "params": tc.arguments,
                    "permission_level": meta.permission_level if meta else "safe",
                    
                    
                    "started_at": time.time(),
                },
            )
            prepared.append((tc, meta, display_name))

        if not prepared:
            return

        if self._can_run_parallel(prepared):
            outcomes = await asyncio.gather(
                *(self._run_one(tc, failure_counts, disabled_tools) for tc, _, _ in prepared)
            )
            for (tc, _, display_name), outcome in zip(prepared, outcomes, strict=True):
                
                
                outcome, plan_event = self._consume_plan_update(tc, outcome)
                message = self.memory.add_tool(tc.id, tc.name, outcome[1])
                self._append_tool_images(tc)
                
                
                
                
                if message.injection_hits:
                    yield self._injection_event(tc, display_name, message.injection_hits)
                yield self._result_event(tc, display_name, *outcome)
                if plan_event is not None:
                    yield plan_event
            self._refresh_system_if_persona_changed(prepared, outcomes)
            return

        persona_touched = False
        for tc, _, display_name in prepared:
            outcome = await self._run_one(tc, failure_counts, disabled_tools)
            
            outcome, plan_event = self._consume_plan_update(tc, outcome)
            message = self.memory.add_tool(tc.id, tc.name, outcome[1])
            self._append_tool_images(tc)
            if message.injection_hits:
                yield self._injection_event(tc, display_name, message.injection_hits)
            if tc.name == "self_persona_update" and outcome[0] == "ok":
                persona_touched = True
            yield self._result_event(tc, display_name, *outcome)
            if plan_event is not None:
                yield plan_event
        if persona_touched:
            self._refresh_system_if_persona_changed()

    def _refresh_system_if_persona_changed(
        self,
        prepared: list[tuple[ToolCall, Any, str]] | None = None,
        outcomes: list[tuple[str, str, float]] | None = None,
    ) -> None:








        if prepared is not None and outcomes is not None:
            changed = any(
                tc.name == "self_persona_update" and outcome[0] == "ok"
                for (tc, _, _), outcome in zip(prepared, outcomes, strict=True)
            )
            if not changed:
                return
        self.memory.ensure_system(self._system_prompt())

    @staticmethod
    def _injection_event(
        tc: ToolCall, display_name: str, hits: list[str]
    ) -> AgentEvent:
        logger.warning("工具 %s 的返回内容疑似包含指令注入：%s", tc.name, "、".join(hits))
        return AgentEvent(
            "injection_suspected",
            {
                "id": tc.id,
                "name": tc.name,
                "display_name": display_name,
                
                
                "labels": list(hits),
            },
        )

    def _can_run_parallel(self, prepared: list[tuple[ToolCall, Any, str]]) -> bool:









        if len(prepared) < 2:
            return False

        names = [tc.name for tc, _, _ in prepared]
        if len(set(names)) != len(names):
            return False

        for _, meta, _ in prepared:
            if meta is None:
                continue
            if self.skills.guard.resolve_level(meta) != "safe":
                return False
        return True

    async def _run_one(
        self,
        tc: ToolCall,
        failure_counts: dict[str, int],
        disabled_tools: set[str],
    ) -> tuple[str, str, float]:

        started = asyncio.get_event_loop().time()
        status = "ok"
        
        outbox: list[ImagePart] = []
        self.ctx.set_image_outbox(outbox)
        try:
            result_text = await self.skills.execute(
                tc.name,
                tc.arguments,
                self.ctx,
                
                
                within=self.config.enabled_skills,
                
                for_assistant=self.config.target_assistant,
            )
            failure_counts.pop(tc.name, None)
        except SkillPermissionError as exc:
            status = "denied"
            result_text = f"[权限拒绝] {exc}"
        except asyncio.CancelledError:
            raise
        except Exception as exc:  
            status = "error"
            failure_counts[tc.name] = failure_counts.get(tc.name, 0) + 1
            result_text = f"[工具执行失败] {exc}"
            if failure_counts[tc.name] >= self.config.same_tool_failure_tolerance:
                disabled_tools.add(tc.name)
                result_text += (
                    f"\n（工具 {tc.name} 已连续失败 {failure_counts[tc.name]} 次，"
                    f"本轮任务内不再提供该工具，请换一种方案，或向用户说明原因。）"
                )
        finally:
            self.ctx.set_image_outbox(None)
        
        
        if outbox and status == "ok":
            if self.config.supports_vision:
                self._tool_images[tc.id] = outbox
            else:
                result_text += "\n（当前模型不支持看图，截图已保存到产物区。）"
        duration_ms = round((asyncio.get_event_loop().time() - started) * 1000, 2)
        return status, result_text, duration_ms

    def _append_tool_images(self, tc: ToolCall) -> None:






        images = self._tool_images.pop(tc.id, None)
        if not images:
            return
        self.memory.add_user("工具返回的截图如下，请据此判断界面。", images=images)

    @staticmethod
    def _result_event(
        tc: ToolCall, display_name: str, status: str, result_text: str, duration_ms: float
    ) -> AgentEvent:
        return AgentEvent(
            "tool_result",
            {
                "id": tc.id,
                "name": tc.name,
                "display_name": display_name,
                "status": status,
                "result": result_text,
                "duration_ms": duration_ms,
            },
        )

    
    
    
    def _system_prompt(self) -> str:






















        
        
        
        
        persona = self.config.persona
        if callable(persona):
            persona = persona()
        base = persona or ""
        
        
        
        
        
        base = f"{base}{_NO_STAMP_RULE}"
        if self.llm.supports_tools:
            return base
        section = render_tools_section(self._tool_specs(None) or [])
        return f"{base}\n\n{section}" if section else base

    def _tool_summary(self) -> str:










        lines: list[str] = []
        for message in self.memory.messages:
            if message.role != "tool":
                continue
            text = " ".join(message.content.split())
            lines.append(f"- {message.name or '工具'}：{text}")
        return "\n".join(lines)

    
    
    
    def _tool_specs(self, disabled_tools: set[str] | None) -> list[ToolSpec] | None:






        if len(self.skills) == 0:
            return None
        specs = self.skills.to_tool_specs(
            filter_names=self.config.enabled_skills,
            for_assistant=self.config.target_assistant,
        )
        if disabled_tools:
            specs = [s for s in specs if s.name not in disabled_tools]
        return specs or None

    def _done_event(self, iterations: int, **extra: Any) -> AgentEvent:
        return AgentEvent(
            "done",
            {
                "trace_id": self.tracer.trace_id,
                "iterations": iterations,
                
                
                "usage": self.tracer.usage.to_dict(),
                **extra,
            },
        )

    def _span(self, name: str, **meta: Any):
        return self.tracer.span(name, **meta)

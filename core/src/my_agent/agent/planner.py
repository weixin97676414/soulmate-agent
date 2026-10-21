





























from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from ..llm.base import BaseLLM, Message

logger = logging.getLogger(__name__)

_PLAN_SYSTEM = """你是一个任务规划器。用户会把一个任务交给你，请输出一份简短的执行计划。

只输出一个 JSON 对象，不要有任何额外文字，不要用 Markdown 代码块包裹：
{"goal": "这次任务要达成的一句话目标", "steps": ["第一步要做什么", "第二步要做什么"]}

要求：
1. steps 用 2~6 步，每步一句话，说明**要做什么**以及**用哪个工具**（如果已知）。
2. goal 用一句话概括任务目标，不要重复用户原话。
3. 如果任务其实很简单（一步就能完成），steps 只给一个。
4. 不要编造不存在的工具；没有合适工具时说明用普通回答完成。
5. 用简体中文。"""



STEP_STATUSES = ("pending", "doing", "done", "failed")


PLAN_STATES = ("awaiting", "executing", "done", "cancelled", "aborted")


_NUMBERED = re.compile(r"^\s*(?:\d+\s*[.、)]|[-*])\s*(.+?)\s*$")


@dataclass
class PlanStep:


    id: str
    text: str
    status: str = "pending"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        
        
        data: dict[str, Any] = {"id": self.id, "text": self.text, "status": self.status}
        if self.note:
            data["note"] = self.note
        return data


@dataclass
class Plan:


    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    state: str = "awaiting"
    
    
    id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "steps": [step.to_dict() for step in self.steps],
            "state": self.state,
        }

    @property
    def total(self) -> int:
        return len(self.steps)

    @property
    def finished(self) -> int:

        return sum(1 for step in self.steps if step.status in ("done", "failed"))

    def find(self, step_id: str) -> PlanStep | None:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None


def coerce_step_status(value: Any, default: str = "pending") -> str:

    text = str(value or "").strip().lower()
    return text if text in STEP_STATUSES else default


def _extract_json_object(text: str) -> dict[str, Any] | None:

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[A-Za-z]*\s*", "", cleaned)
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def parse_plan(text: str) -> Plan | None:








    raw = (text or "").strip()
    if not raw:
        return None

    data = _extract_json_object(raw)
    goal = ""
    items: list[Any] = []
    if data is not None:
        goal = str(data.get("goal") or "").strip()
        steps = data.get("steps")
        if isinstance(steps, list):
            items = steps

    if not items:
        items = [
            matched.group(1)
            for matched in (_NUMBERED.match(line) for line in raw.splitlines())
            if matched
        ]

    texts: list[str] = []
    for item in items:
        if isinstance(item, dict):
            value = str(item.get("text") or item.get("step") or item.get("title") or "").strip()
        else:
            value = str(item).strip()
        if value:
            texts.append(value)

    if len(texts) < 2:
        return None

    return Plan(
        goal=goal or texts[0],
        steps=[PlanStep(id=str(index + 1), text=text) for index, text in enumerate(texts)],
    )


class Planner:


    def __init__(self, *, enabled: bool = False, min_complexity: int = 4) -> None:
        self.enabled = enabled
        self.min_complexity = min_complexity

    def should_plan(self, text: str, *, need_tools: bool) -> bool:





        if not self.enabled:
            return False
        from ..llm.router import score_complexity

        return score_complexity(text, need_tools=need_tools) >= self.min_complexity

    async def make_plan(
        self,
        llm: BaseLLM,
        *,
        user_input: str,
        tool_names: list[str] | None = None,
        feedback: str = "",
    ) -> Plan | None:




        names = ", ".join(tool_names or []) or "（当前没有可用工具）"
        payload = f"可用工具：{names}\n\n任务：{user_input}"
        if feedback.strip():
            payload += (
                "\n\n用户看了上一版计划后提了修改意见，请据此重新给一份计划：\n"
                f"{feedback.strip()}"
            )
        try:
            response = await llm.chat(
                [
                    Message(role="system", content=_PLAN_SYSTEM),
                    Message(role="user", content=payload),
                ],
                None,
                
                temperature=0.3,
            )
        except Exception as exc:  
            logger.warning("生成执行计划失败，按原流程继续: %s", exc)
            return None

        plan = parse_plan(response.content or "")
        if plan is None:
            
            
            logger.info("本轮没有解析出多步计划（输出长度 %d），按原流程继续", len(response.content or ""))
        return plan


def plan_to_text(plan: Plan) -> str:

    lines = "\n".join(f"{step.id}. {step.text}" for step in plan.steps)
    return f"任务目标：{plan.goal}\n{lines}" if plan.goal else lines


def plan_hint(plan: Plan) -> str:





    from ..memory.short_term import internal_hint

    return internal_hint(
        "以下是用户已确认的执行计划，请按它推进；每完成一步都要调用 plan_update "
        "汇报该步进度。如果发现计划不适用，可以调整并说明原因：\n" + plan_to_text(plan)
    )

"""Planner：复杂任务先出计划，等用户点头再动手。

对应《智能体框架开发文档》7.4 节预留的扩展点（Plan & Execute）。

## 为什么值得做

ReAct 循环是"走一步看一步"：模型每次只决定下一个动作。面对**多步任务**时，
它容易在第 3 步忘记第 1 步的目标，或者顺序搞反（先写文件再去找数据）。
先让它写一份计划、把计划放进上下文，后面每一轮都有一个"目标锚点"。

## 与"隐形计划"的区别（本模块的定位）

早先的计划只是塞进上下文的 ``internal_hint``，**用户看不到、也无法干预**。
现在计划是**用户可见的**：引擎把它作为 ``plan`` 事件推给界面，停下等用户
点「开始执行」，之后每完成一步再由 ``plan_update`` 汇报进度。

于是这里产出的必须是**结构化**的 ``Plan``（目标 + 步骤清单），而不是一段文本——
文本没法逐项打勾，也没法回报"第几步怎么了"。

## 代价与默认值

计划本身要花一次 LLM 调用。所以：

1. **默认关闭**（``planner.enabled``）—— 不是所有任务都值得先规划，简单问答上纯属浪费；
   是否启用由**调用方**决定：单聊注入计划确认回调时才开启，群聊 / 命令行保持旧行为；
2. 开启时也只在**看起来是多步任务**时才触发（复用 ModelRouter 的零成本启发式，
   而不是再调一次模型判断"要不要规划"）；
3. 计划失败 / 解析不出多步不影响主流程：拿不到计划就按原来的 ReAct 走。
"""

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

# 步骤状态：未开始 / 进行中 / 已完成 / 失败。
# 取值同时是前端 ``PlanStepStatus`` 的字面量，改这里要同步改 desktop/src/types.ts。
STEP_STATUSES = ("pending", "doing", "done", "failed")

# 整份计划的状态。``awaiting`` = 等用户确认；``aborted`` = 用户点「不用了」。
PLAN_STATES = ("awaiting", "executing", "done", "cancelled", "aborted")

# 回退解析用的编号行：``1. xxx`` / ``1、xxx`` / ``- xxx``。
_NUMBERED = re.compile(r"^\s*(?:\d+\s*[.、)]|[-*])\s*(.+?)\s*$")


@dataclass
class PlanStep:
    """计划里的一步。``id`` 是稳定序号（"1"、"2"...），进度回报靠它定位。"""

    id: str
    text: str
    status: str = "pending"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        # ``note`` 只在有内容时带上：前端据此决定要不要渲染"失败原因"那一行，
        # 空字符串会让它多渲染一个空行。
        data: dict[str, Any] = {"id": self.id, "text": self.text, "status": self.status}
        if self.note:
            data["note"] = self.note
        return data


@dataclass
class Plan:
    """一次任务的执行计划（用户可见、可确认、可追踪）。"""

    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    state: str = "awaiting"
    # 计划 id：前端点「开始执行 / 改一下」时要原样回传，后端靠它找到在等的那一份。
    # 用户"改一下"后重拟会换一个新 id —— 免得旧卡片上的按钮还能唤醒新计划。
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
        """已完成 / 失败都算"这一步不用再做了"，进度条按它算。"""
        return sum(1 for step in self.steps if step.status in ("done", "failed"))

    def find(self, step_id: str) -> PlanStep | None:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None


def coerce_step_status(value: Any, default: str = "pending") -> str:
    """把模型给的 status 归一化成一个合法取值（不认识的一律回落到默认）。"""
    text = str(value or "").strip().lower()
    return text if text in STEP_STATUSES else default


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """从模型输出里抠出 JSON 对象（容忍 ```json 围栏与前后废话）。"""
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
    """把模型输出解析成结构化计划。

    两条路：优先 JSON（``_PLAN_SYSTEM`` 要求的主格式），
    失败则回退解析编号行 —— 小模型不听话是常态，回退保住"至少有计划"。

    **少于两步一律返回 None**：那说明这不是多步任务，不该弹卡片打扰用户
    （与产品口径"简单问答直接回答"一致）。
    """
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
    """按需生成执行计划。"""

    def __init__(self, *, enabled: bool = False, min_complexity: int = 4) -> None:
        self.enabled = enabled
        self.min_complexity = min_complexity

    def should_plan(self, text: str, *, need_tools: bool) -> bool:
        """判断这次值不值得先规划。

        复用 ``score_complexity`` 而不是让模型自己判断要不要规划：
        后者要再花一次调用，为了省钱先花钱逻辑上说不通。
        """
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
        """生成结构化计划；失败或不足两步返回 None（调用方按"没有计划"继续）。

        ``feedback`` 是用户点「改一下」时写下的意见，非空时请模型据此重拟。
        """
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
                # 规划要的是稳定，不是创造
                temperature=0.3,
            )
        except Exception as exc:  # noqa: BLE001 - 规划失败不该让任务失败
            logger.warning("生成执行计划失败，按原流程继续: %s", exc)
            return None

        plan = parse_plan(response.content or "")
        if plan is None:
            # 不静默：记一笔，排查"为什么这次没弹计划卡片"时有据可查。
            # 不写计划全文（可能含用户隐私），只记长度。
            logger.info("本轮没有解析出多步计划（输出长度 %d），按原流程继续", len(response.content or ""))
        return plan


def plan_to_text(plan: Plan) -> str:
    """把计划拍平成给人看的编号文本（注入上下文与日志都用它）。"""
    lines = "\n".join(f"{step.id}. {step.text}" for step in plan.steps)
    return f"任务目标：{plan.goal}\n{lines}" if plan.goal else lines


def plan_hint(plan: Plan) -> str:
    """把**已确认的**计划包装成注入上下文的内部提示。

    用 ``internal_hint`` 标记，展示层据此过滤 —— 用户看到的计划走的是 ``plan``
    事件的卡片，不是这段文字；不标记的话上下文里会出现一份和卡片重复的正文。
    """
    from ..memory.short_term import internal_hint

    return internal_hint(
        "以下是用户已确认的执行计划，请按它推进；每完成一步都要调用 plan_update "
        "汇报该步进度。如果发现计划不适用，可以调整并说明原因：\n" + plan_to_text(plan)
    )

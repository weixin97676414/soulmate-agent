"""系统类内置 Skill。

这些工具本身很小，但承担两个作用：
1. 解决模型「没有实时时间」「算数易错」这两个真实短板；
2. 作为 P0 阶段验证「工具调用卡片」全链路的载体。
"""

from __future__ import annotations

import ast
import asyncio
import math
import operator
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field

from ..base import BaseSkill, SkillContext
from ..decorator import skill

# --------------------------------------------------------------------------- #
# 当前时间
# --------------------------------------------------------------------------- #


class CurrentTimeParams(BaseModel):
    timezone_offset: int = Field(
        8,
        ge=-12,
        le=14,
        description="时区偏移小时数，中国大陆为 8，UTC 为 0",
    )


@skill(
    name="system_time",
    display_name="获取当前时间",
    description=(
        "获取当前的日期、时间和星期。当用户询问「今天几号」「现在几点」"
        "或需要以当前时间推算「明天」「本周」「下个月」等相对日期时使用。"
        "返回 ISO 格式的日期时间与星期。"
    ),
    params_model=CurrentTimeParams,
    category="system",
    permission_level="safe",
    tags=["时间"],
)
class CurrentTimeSkill(BaseSkill):
    """返回指定时区的当前时间。"""

    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = CurrentTimeParams(**params)
        tz = timezone(timedelta(hours=args.timezone_offset))
        now = datetime.now(tz)
        weekday = "一二三四五六日"[now.weekday()]
        return {
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"),
            "weekday": f"星期{weekday}",
            "timezone": f"UTC{args.timezone_offset:+d}",
            "timestamp": int(now.timestamp()),
        }


# --------------------------------------------------------------------------- #
# 计算器
# --------------------------------------------------------------------------- #

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_SAFE_NAMES = {
    "pi": math.pi,
    "e": math.e,
}
_SAFE_FUNCS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "floor": math.floor,
    "ceil": math.ceil,
}


# ``**`` 的指数上限。
#
# 允许 ``**`` 本身是合理的（复利、平方、立方都是常见需求），但 ``9**9**9``
# 这类表达式会让 CPython 在事件循环线程里**同步**算上几十秒并把内存吃光。
# 关键在于 ``asyncio.wait_for`` 的超时**无法中断同步代码** —— 整个服务就此卡死，
# 所有会话的 SSE 一起停摆。
#
# 而这条路径**不需要用户做错任何事**：calc 是 safe 级、不弹确认，
# 模型只要生成一个这样的表达式就够了。
#
# 1024 足够覆盖任何正常用途（``2**1024`` 已经是 10^308 量级），
# 而 ``9**9**9`` 的指数是 3.8 亿，离得很远。
_MAX_EXPONENT = 1024


def _guard_exponent(exponent: Any) -> None:
    """挡住会把进程卡死的那个指数。"""
    if not isinstance(exponent, (int, float)):
        raise ValueError("指数必须是数值")
    if not math.isfinite(exponent):
        raise ValueError("指数必须是有限数值")
    if abs(exponent) > _MAX_EXPONENT:
        raise ValueError(
            f"指数 {exponent} 过大（上限 {_MAX_EXPONENT}），为避免长时间计算已拒绝。"
            "如需估算数量级请改用 log。"
        )


def _eval_node(node: ast.AST) -> Any:
    """基于 AST 白名单求值，不用 eval，杜绝任意代码执行。"""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"不支持的字面量: {node.value!r}")
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"不支持的运算符: {type(node.op).__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow):
            # 必须在真正做幂运算**之前**检查，之后就没机会了
            _guard_exponent(right)
        return op(left, right)
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")
        return op(_eval_node(node.operand))
    if isinstance(node, ast.Name):
        if node.id in _SAFE_NAMES:
            return _SAFE_NAMES[node.id]
        raise ValueError(f"未知标识符: {node.id}")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_FUNCS:
            raise ValueError("只允许调用预置的数学函数")
        if node.keywords:
            raise ValueError("不支持关键字参数")
        return _SAFE_FUNCS[node.func.id](*[_eval_node(a) for a in node.args])
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval_node(e) for e in node.elts]
    raise ValueError(f"不支持的表达式类型: {type(node).__name__}")


class CalculatorParams(BaseModel):
    expression: str = Field(
        ...,
        description=(
            "要计算的数学表达式，使用 Python 语法，例如 '(1200-350)*0.13'、"
            "'sqrt(2)'、'round(1234.567, 2)'。支持 + - * / // % ** 与 sqrt/log/abs/round/min/max 等函数。"
        ),
    )


@skill(
    name="calc",
    display_name="精确计算",
    description=(
        "对数学表达式做精确计算。当需要进行多位数的四则运算、百分比、复利、"
        "统计汇总等容易算错的数值计算时使用。"
        "输入一个数学表达式字符串（如 '(1200-350)*0.13'），返回计算结果。"
        "不要用它做单位换算或日期推算。"
    ),
    params_model=CalculatorParams,
    category="system",
    permission_level="safe",
    tags=["计算"],
)
class CalculatorSkill(BaseSkill):
    """安全的数学表达式求值。"""

    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = CalculatorParams(**params)
        expression = args.expression.strip()
        try:
            # 放线程里算：白名单 + 指数上限已经挡住了绝大多数问题，
            # 但**同步求值无法被超时中断**。挪到线程之后，即使真的碰上
            # 一个慢表达式，``wait_for`` 也能按时返回，事件循环和别人的
            # SSE 不会被一起拖住（那个线程会被丢弃，进程不至于假死）。
            value = await asyncio.to_thread(_evaluate, expression)
        except (SyntaxError, ValueError, ZeroDivisionError, TypeError, OverflowError) as exc:
            raise ValueError(f"表达式无法计算：{exc}") from exc
        return {"expression": expression, "result": value}


def _evaluate(expression: str) -> Any:
    return _eval_node(ast.parse(expression, mode="eval"))

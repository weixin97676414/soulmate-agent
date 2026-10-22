






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














_MAX_EXPONENT = 1024


def _guard_exponent(exponent: Any) -> None:

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


    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = CalculatorParams(**params)
        expression = args.expression.strip()
        try:
            
            
            
            
            value = await asyncio.to_thread(_evaluate, expression)
        except (SyntaxError, ValueError, ZeroDivisionError, TypeError, OverflowError) as exc:
            raise ValueError(f"表达式无法计算：{exc}") from exc
        return {"expression": expression, "result": value}


def _evaluate(expression: str) -> Any:
    return _eval_node(ast.parse(expression, mode="eval"))

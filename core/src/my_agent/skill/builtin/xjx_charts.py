



























from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ..base import BaseSkill, SkillContext
from ..decorator import skill
from . import xjx
from .xjx_report import XjxGateway, XjxHttpResult


_TIMEOUT_CHART = httpx.Timeout(30.0, connect=10.0)

_TIMEOUT_DIVINE = httpx.Timeout(15.0, connect=8.0)

_OWNER_HINT = "算命占卜（西占 / 八字 / 梅花易数 / 塔罗）只为 Fortune telling Buddy 开放"


def _request_id(raw: str) -> str:
    text = (raw or "").strip()
    return text or uuid.uuid4().hex


def _body_of(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _message_of(text: str) -> str:

    data = _body_of(text)
    for key in ("error", "message", "detail"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return "参数不完整或地点无法识别，请补齐后重试。"


def _success(text: str) -> dict[str, Any]:
    payload = _body_of(text)
    
    payload.pop("billing", None)
    payload["ok"] = True
    return payload


def _failure(result: XjxHttpResult) -> dict[str, Any]:

    status = result.status
    if status == 401:
        return {"ok": False, "code": "need_login", "message": "需要用户先登录心鉴学账号"}
    if status == 402:
        return {
            "ok": False,
            "code": "need_recharge",
            "message": "社区贡献点不足：如实告知用户去客户端补充，不要报数字、不要提规则",
        }
    if status in (502, 503):
        return {"ok": False, "code": "upstream_busy", "message": "服务繁忙，稍后再试"}
    if status == 400:
        return {"ok": False, "code": "bad_request", "message": _message_of(result.text)}
    return {"ok": False, "code": "server_error", "message": _message_of(result.text)}


async def _post(
    gateway: XjxGateway, path: str, body: dict[str, Any], timeout: httpx.Timeout
) -> XjxHttpResult:

    result = await gateway.post_json(path, body, timeout=timeout)
    if result.status in (502, 503):
        result = await gateway.post_json(path, body, timeout=timeout)
    return result


def _require_owner(assistant_id: str | None, tool: str) -> None:
    if not xjx.may_use_tool(assistant_id, tool):
        raise SkillExecutionError(f"{_OWNER_HINT}：当前搭子不在归属名单里，无法使用。")


def _missing(names: list[tuple[str, Any]]) -> str:

    labels = {
        
        
        
        "birth_place": "出生地（越精确越好：国家 省/州 地级 区县；最少到城市）",
        "country": "出生国家",
        "gender": "性别（男 / 女）",
        "current_place": "当前所在地（越精确越好，最少到城市）",
        "current_country": "当前所在国家",
    }
    for key, value in names:
        label = labels.get(key, key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return f"还缺少「{label}」：先问用户，不要用默认值或猜测。"
    return ""





class AstroParams(BaseModel):
    report: str = Field("natal", description="natal=本命盘；transit=行运盘。用户要两种就分两次调用")
    birth_place: str = Field(
        ...,
        description=(
            "出生地，**越精确越好**：国家 省/州 地级 区县（有就带上），最少到城市。"
            "用户怎么说就怎么传，不要自己换成另一个城市。如「中国 浙江 杭州」或"
            "「中国 新疆维吾尔自治区 自治区直辖县级行政区 北屯市」"
        ),
    )
    country: str = Field(..., description="出生国家，如「中国」")
    year: int = Field(..., description="出生年（公历），如 1991")
    month: int = Field(..., description="出生月（公历），1-12")
    day: int = Field(..., description="出生日（公历），1-31")
    h: int = Field(..., description="出生时（24 小时制），0-23")
    m: int = Field(..., description="出生分，0-59")
    current_place: str = Field(
        "", description="仅 transit：当前所在地，越精确越好（最少到城市）"
    )
    current_country: str = Field("", description="仅 transit：当前所在国家")
    request_id: str = Field("", description="幂等键。一般留空，由客户端生成")


@skill(
    name=xjx.TOOL_FETCH_ASTRO,
    display_name="西占取盘",
    description=(
        "取回西洋占星的本命盘（report=natal）或行运盘（report=transit）。"
        "**调用前必须问齐出生地、出生国家、年月日时分**（行运还要问当前所在地）；"
        "出生地**越精确越好**（有区县/街道就带上，服务端自己会识别），最少给到城市；"
        "用户怎么报就怎么传，不要自己换成另一个城市。"
        "返回 report（原始盘数据）与 meta（钟表时间 / 真太阳时 / 排盘时间 / 地点）。"
        "解读请严格按技能正文里的规则，不要自己造盘。"
    ),
    params_model=AstroParams,
    category="life",
    permission_level="safe",
    timeout=35.0,
    tags=["心鉴学", "西占"],
)
class XjxFetchAstroSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> Any:
        _require_owner(ctx.assistant_id, xjx.TOOL_FETCH_ASTRO)
        report = str(params.get("report") or "natal").strip().lower()
        if report not in ("natal", "transit"):
            return {"ok": False, "code": "bad_request", "message": "report 只能是 natal 或 transit"}

        body: dict[str, Any] = {
            "birth_place": str(params.get("birth_place") or "").strip(),
            "country": str(params.get("country") or "").strip(),
            "year": params.get("year"),
            "month": params.get("month"),
            "day": params.get("day"),
            "h": params.get("h"),
            "m": params.get("m"),
            "request_id": _request_id(str(params.get("request_id") or "")),
        }
        gap = _missing([("birth_place", body["birth_place"]), ("country", body["country"])])
        if gap:
            return {"ok": False, "code": "bad_request", "message": gap}

        if report == "transit":
            body["current_place"] = str(params.get("current_place") or "").strip()
            body["current_country"] = str(params.get("current_country") or "").strip()
            gap = _missing(
                [
                    ("current_place", body["current_place"]),
                    ("current_country", body["current_country"]),
                ]
            )
            if gap:
                return {"ok": False, "code": "bad_request", "message": gap}

        gateway: XjxGateway = ctx.service("xjx")
        result = await _post(gateway, f"/api/astro/v1/{report}", body, _TIMEOUT_CHART)
        if result.status != 200:
            return _failure(result)
        return _success(result.text)





class BaziParams(BaseModel):
    birth_place: str = Field(
        ...,
        description=(
            "出生地，**越精确越好**：国家 省/州 地级 区县（有就带上），最少到城市；"
            "用户怎么说就怎么传，不要自己换成另一个城市。如「中国 浙江 杭州」"
        ),
    )
    country: str = Field(..., description="出生国家，如「中国」")
    year: int = Field(..., description="出生年（公历），如 1991")
    month: int = Field(..., description="出生月（公历），1-12")
    day: int = Field(..., description="出生日（公历），1-31")
    h: int = Field(..., description="出生时（24 小时制），0-23")
    m: int = Field(..., description="出生分，0-59")
    gender: str = Field(..., description="性别，只收「男」或「女」（大运顺逆由它决定）")


@skill(
    name=xjx.TOOL_FETCH_BAZI,
    display_name="八字排盘",
    description=(
        "排八字命盘：返回 data（四柱、五行占比、起运、十步大运与每年的流年五行）"
        "与 text（**成品文本，直接原样呈现给用户，不改写、不合并、不漏行**）。"
        "调用前必须问齐出生年月日时分、性别、出生地、国家；只收公历生日。"
        "⚠️ 无缓存：同参数重复调用会重复消耗一份报告，不要重试已成功的调用。"
    ),
    params_model=BaziParams,
    category="life",
    permission_level="safe",
    timeout=35.0,
    tags=["心鉴学", "八字"],
)
class XjxFetchBaziSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> Any:
        _require_owner(ctx.assistant_id, xjx.TOOL_FETCH_BAZI)
        gender = str(params.get("gender") or "").strip()
        if gender not in ("男", "女"):
            return {
                "ok": False,
                "code": "bad_request",
                "message": "gender 只收「男」或「女」：先问用户，填错整盘方向会反。",
            }

        body = {
            "birth_place": str(params.get("birth_place") or "").strip(),
            "country": str(params.get("country") or "").strip(),
            "year": params.get("year"),
            "month": params.get("month"),
            "day": params.get("day"),
            "h": params.get("h"),
            "m": params.get("m"),
            "gender": gender,
        }
        gap = _missing([("birth_place", body["birth_place"]), ("country", body["country"])])
        if gap:
            return {"ok": False, "code": "bad_request", "message": gap}

        gateway: XjxGateway = ctx.service("xjx")
        result = await _post(gateway, "/api/bazi/v1/chart", body, _TIMEOUT_CHART)
        if result.status != 200:
            return _failure(result)
        return _success(result.text)





class MeihuaParams(BaseModel):
    n1: int = Field(..., ge=1, description="上卦数：用户自报的第一个正整数")
    n2: int = Field(..., ge=1, description="下卦数：用户自报的第二个正整数")
    question: str = Field("", description="用户所问之事，原话即可（强烈建议带上）")
    current_place: str = Field(
        "", description="当前所在地，越精确越好（最少到城市）。给了按当地真太阳时取时辰"
    )
    current_country: str = Field("", description="当前所在国家")
    request_id: str = Field("", description="幂等键。一般留空")


@skill(
    name=xjx.TOOL_FETCH_MEIHUA,
    display_name="梅花起卦",
    description=(
        "按用户**自报的两个正整数**起卦（上卦数 / 下卦数），返回本卦、互卦、变卦、"
        "错卦、综卦、动爻、体用关系与卦象清单。"
        "**不要替用户随机取数、不要用时间起卦**：先请他想着一件事，报两个正整数。"
        "同一件事同一时辰内重复起卦会回放同一卦、不重复计费；**禁止短时间内对同一事件测两次**。"
    ),
    params_model=MeihuaParams,
    category="life",
    permission_level="safe",
    timeout=20.0,
    tags=["心鉴学", "梅花"],
)
class XjxFetchMeihuaSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> Any:
        _require_owner(ctx.assistant_id, xjx.TOOL_FETCH_MEIHUA)
        body: dict[str, Any] = {
            "n1": params.get("n1"),
            "n2": params.get("n2"),
            "question": str(params.get("question") or "").strip(),
            "request_id": _request_id(str(params.get("request_id") or "")),
        }
        current_place = str(params.get("current_place") or "").strip()
        current_country = str(params.get("current_country") or "").strip()
        if current_place:
            body["current_place"] = current_place
        if current_country:
            body["current_country"] = current_country

        gateway: XjxGateway = ctx.service("xjx")
        result = await _post(gateway, "/api/meihua/v1/chart", body, _TIMEOUT_DIVINE)
        if result.status != 200:
            return _failure(result)
        return _success(result.text)





class TarotParams(BaseModel):
    question: str = Field("", description="用户所问之事，原话即可")
    spread: str = Field("", description="牌阵编号，如 3.b / 5.n。从技能正文的牌阵表里选一个")
    request_id: str = Field("", description="幂等键。一般留空")


@skill(
    name=xjx.TOOL_FETCH_TAROT,
    display_name="塔罗洗牌",
    description=(
        "服务端只做**洗牌 + 切牌**，返回 78 张按位序排好的牌堆（牌名、正逆位、牌义、关键词）。"
        "流程：先在客户端问清所求并选一个牌阵 → 调用本工具 → **逐张问用户抽第几张** → "
        "按牌阵位次排牌 → 按技能正文的规则解牌。"
        "⚠️ 未抽到的牌不提前解读、不透露牌堆顺序；**禁止短时间内对同一事件测两次**。"
    ),
    params_model=TarotParams,
    category="life",
    permission_level="safe",
    timeout=20.0,
    tags=["心鉴学", "塔罗"],
)
class XjxFetchTarotSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> Any:
        _require_owner(ctx.assistant_id, xjx.TOOL_FETCH_TAROT)
        body: dict[str, Any] = {"request_id": _request_id(str(params.get("request_id") or ""))}
        question = str(params.get("question") or "").strip()
        spread = str(params.get("spread") or "").strip()
        if question:
            body["question"] = question
        if spread:
            body["spread"] = spread

        gateway: XjxGateway = ctx.service("xjx")
        result = await _post(gateway, "/api/tarot/v1/shuffle", body, _TIMEOUT_DIVINE)
        if result.status != 200:
            return _failure(result)
        return _success(result.text)


__all__ = [
    "AstroParams",
    "BaziParams",
    "MeihuaParams",
    "TarotParams",
    "XjxFetchAstroSkill",
    "XjxFetchBaziSkill",
    "XjxFetchMeihuaSkill",
    "XjxFetchTarotSkill",
]

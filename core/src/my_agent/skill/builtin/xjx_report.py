
























from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, Field

from ...config.lines import report_base
from ...errors import SkillExecutionError
from ...security.redact import redact
from ...utils.http import async_client
from ..base import BaseSkill, SkillContext
from ..decorator import skill
from . import xjx

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


_DATE_ONLY = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
_DATE_TIME = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}$")


@dataclass
class XjxHttpResult:


    status: int
    text: str
    offline: bool = False


class XjxGateway:







    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    
    @property
    def line(self) -> str:
        return str(getattr(self._runtime, "line", "") or xjx.LINE_CN)

    @property
    def has_token(self) -> bool:
        return bool(getattr(self._runtime, "session_token", ""))

    def base_url(self) -> str:
        return report_base(self.line)

    def endpoint(self, group: str) -> str:
        path = xjx.REPORT_PATHS[group]
        return f"{self.base_url()}/api/buddy/v1/{path}"

    
    async def post_report(self, group: str, person: dict[str, Any]) -> XjxHttpResult:






        return await self.post_json(
            f"/api/buddy/v1/{xjx.REPORT_PATHS[group]}",
            {"person": person},
            timeout=_TIMEOUT,
        )

    async def post_json(
        self, path: str, body: dict[str, Any], *, timeout: httpx.Timeout
    ) -> XjxHttpResult:





        if not self.has_token:
            return XjxHttpResult(
                401,
                "本机核心没有登录凭证：请让用户先在客户端登录心鉴学账号（登录态由客户端推送，"
                "模型无法代填、也不需要知道凭证）。",
            )

        url = f"{self.base_url()}{path}"
        headers = {
            "Authorization": f"Bearer {getattr(self._runtime, 'session_token', '')}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            
            
            
            async with async_client(timeout=timeout) as client:
                response = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            
            
            return XjxHttpResult(0, f"请求心鉴学服务失败：{type(exc).__name__}。请稍后重试。", True)

        return XjxHttpResult(response.status_code, redact(response.text or ""))





def _missing_fields(person: dict[str, Any]) -> list[str]:

    problems: list[str] = []

    birth = str(person.get("birth") or "").strip()
    if not birth:
        problems.append("birth（出生年月日，如 1995-08-04）")
    elif not (_DATE_ONLY.match(birth) or _DATE_TIME.match(birth)):
        problems.append("birth（格式应为 1995-08-04 或 1995-08-04 06:00）")

    gender = str(person.get("gender") or "").strip()
    if gender not in ("男", "女"):
        problems.append("gender（必须是「男」或「女」，不要猜）")

    if not str(person.get("current_place") or "").strip():
        problems.append("current_place（现居城市，规范写法如「中国 浙江省 杭州市」，先用 xjx_place_lookup 核对）")
    if not str(person.get("current_country") or "").strip():
        problems.append("current_country（现居国家，如「中国」）")

    
    if _DATE_TIME.match(birth):
        if not str(person.get("birth_place") or "").strip():
            problems.append(
                "birth_place（出生地：出生时间给到了时分，必须问——要按真太阳时校正，"
                "没有地点算出来的时段是错的，而用户看不出来）"
            )
        if not str(person.get("country") or "").strip():
            problems.append("country（出生国家，如「中国」）")

    return problems


class FetchReportParams(BaseModel):
    person: dict[str, Any] = Field(
        ...,
        description=(
            "要分析的人。必填：birth（1995-08-04 或 1995-08-04 06:00）、gender（男/女）、"
            "current_place（现居城市，如「中国 浙江省 杭州市」）、current_country（如「中国」）。"
            "出生时间给到时分时还必须给 birth_place 与 country。"
            "可选：name（怎么称呼这个人）、current（当前时间，不要主动传）。"
            "地点一律先用 xjx_place_lookup 核成规范写法。"
        ),
    )
    report: str = Field(
        "",
        description=(
            "要取哪种报告：soulmate（本人报告）或 buddies（人际关系报告）。"
            "一般不用填——你的能力决定了只能取其中一种，填错会被拒绝。"
        ),
    )


@skill(
    name=xjx.TOOL_FETCH_REPORT,
    display_name="报告代取",
    description=(
        "代你向心鉴学提交信息并取回报告。**凭证由核心持有，你看不到也不需要知道**。"
        "调用前先把地点用 xjx_place_lookup 核对成规范写法（如「中国 浙江省 杭州市」），"
        "并确认四项必填信息（出生年月日 / 性别 / 现居城市 / 现居国家）都问过用户了 ——"
        "缺任何一项都会被拒绝，而白提交一次是要扣用户 token 的。"
        "工具会把服务端返回**原样**交给你（含错误与计费信息），按它说的一步一步来。"
    ),
    params_model=FetchReportParams,
    category="knowledge",
    permission_level="safe",
    timeout=70.0,
    tags=["心鉴学", "报告"],
)
class XjxFetchReportSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> Any:
        
        
        
        if not xjx.may_use_tool(ctx.assistant_id, xjx.TOOL_FETCH_REPORT):
            raise SkillExecutionError(
                "报告代取只为 Soulmate（Soulmate专用）与 Love Buddy / Relation Buddy"
                "（人际关系运营）开放：当前搭子不在归属名单里，无法使用。"
            )

        
        
        gateway = ctx.service("xjx")
        group = xjx.group_for_assistant(ctx.assistant_id, gateway.line)
        if group is None:
            raise SkillExecutionError("当前线路下没有属于这个搭子的报告端点，无法取报告。")

        asked = str(params.get("report") or "").strip()
        if asked and asked != group:
            raise SkillExecutionError(
                f"这个搭子只能取「{group}」报告，不能取「{asked}」。"
                "请直接用你归属的那一种，不要指定别的。"
            )

        person = params.get("person") or {}
        if not isinstance(person, dict):
            raise SkillExecutionError("person 必须是一个对象（字段见工具说明）。")

        missing = _missing_fields(person)
        if missing:
            raise SkillExecutionError(
                "以下信息还没问过用户或写法不对，**先向用户确认后再提交**"
                "（白提交一次会扣用户的 token）：\n- " + "\n- ".join(missing)
            )

        result = await gateway.post_report(group, person)
        
        ctx.logger.info("心鉴学取报告：line=%s group=%s status=%s", gateway.line, group, result.status)

        payload: dict[str, Any] = {
            "ok": 200 <= result.status < 300,
            "status": result.status,
            "line": gateway.line,
            "report": group,
            "body": result.text,
        }
        if result.offline:
            payload["next_step"] = "网络没通：把失败如实告诉用户，并说明稍后可重试；不要反复重试。"
        elif result.status == 400:
            payload["next_step"] = (
                "服务端说地点无法识别：用 xjx_place_lookup 重核 current_place / birth_place "
                "（核不上就找相邻最近的城市逐级重试），改好**再提交一次**，不要盲目重试。"
            )
        elif result.status == 401:
            payload["next_step"] = "未登录或凭证过期：请用户重新登录后再试，不要向用户索要账号密码。"
        elif result.status == 402:
            payload["next_step"] = "余额不足：把服务端的原话告诉用户，不要在本地做任何补充猜测。"
        elif payload["ok"]:
            payload["next_step"] = (
                "取到了：按报告解读规则落到本搭子的文件并回复用户。"
                "如果响应里有 next_refresh_at_local，记下它作为下次拉取时刻。"
            )
        else:
            payload["next_step"] = "把服务端返回的原文如实转达用户，不要自行解释或改写错误。"
        return payload

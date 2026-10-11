"""心鉴学报告代取：凭证留在核心内存，模型只拿到报告。

## 为什么必须由核心代发（而不是让模型自己发 HTTP）

以前那条路是让模型用 `http_request` 自己拼请求。问题是：**凭证一旦进了模型的
上下文，它早晚会被写进回复、导出文件、或某一版日志里**。产品约定
是"凭证由核心代发"——模型从头到尾看不到钥匙，只看得到门后的东西。

所以：
- 凭证从 ``AppRuntime.session_token``（进程内存）取，**不落盘、不过 IPC 到渲染层**；
- 只在**请求头**里用一次，不写进任何返回值或日志（日志只记 status 与路径）；
- 服务端返回的内容再走一遍 ``security.redact`` —— 万一服务端把凭证回显了，
  也不能就这么交给模型。

## 为什么在本地先拦一道必填字段

``person`` 里那四项（出生年月日 / 性别 / 现居城市 / 现居国家）服务端会校验，
但**每次提交都要扣 token**（换分析对象更贵）。与其让用户白花一次，
不如在这里直接拦住并告诉模型"去问用户"——见 ``_missing_fields``。

字段口径与四份 SKILL.md 的《2.1 要问用户哪些信息》**保持一致**：
出生时间只到「年月日」时出生地可以不问；到「年月日时分」时必须问
（真太阳时校正需要地点，没有地点算出来的时段是错的，而用户看不出来）。
"""

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

# 出生时间的两种合法形态：只有日期，或日期 + 时分
_DATE_ONLY = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
_DATE_TIME = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}$")


@dataclass
class XjxHttpResult:
    """一次请求的结果。``status == 0`` 表示**压根没收到响应**（网络层失败）。"""

    status: int
    text: str
    offline: bool = False


class XjxGateway:
    """心鉴学服务端访问的**唯一出口**（作为 ``ctx.service("xjx")`` 注入给技能）。

    为什么要做成门面而不是把 runtime 直接给技能：把 runtime 递出去，技能就能
    顺手读到凭证、改线路、翻配置；将来再加一个技能时没人会记得"别那么干"。
    门面只开三个口：当前线路、有没有凭证、发一次报告请求。
    """

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    async def post_report(self, group: str, person: dict[str, Any]) -> XjxHttpResult:
        """带上核心内存里的凭证，把 ``person`` 提交给对应端点。

        返回**服务端原文**（已脱敏）而不是抛错：400「地点无法识别」/ 401「未登录」/
        402「余额不足」这些都是**给模型看的信息**，模型要据此决定下一步
        （补地点 / 让用户登录 / 告知余额）。抛成异常只会剩下一句"工具调用失败"。
        """
        if not self.has_token:
            return XjxHttpResult(
                401,
                "本机核心没有登录凭证：请让用户先在客户端登录心鉴学账号（登录态由客户端推送，"
                "模型无法代填、也不需要知道凭证）。",
            )

        url = self.endpoint(group)
        headers = {
            "Authorization": f"Bearer {getattr(self._runtime, 'session_token', '')}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            # 必须走 utils.http.async_client()：裸 httpx.AsyncClient 每次都要重建
            # SSL 上下文（Windows 上 ~500ms），而且不加载系统信任根 ——
            # 某些企业网络下会直接握手失败（见 test_http_client.py 的守卫）。
            async with async_client(timeout=_TIMEOUT) as client:
                response = await client.post(url, json={"person": person}, headers=headers)
        except httpx.HTTPError as exc:
            # 只是告诉模型"没连上"，**不带 URL 之外的任何请求细节**（免得把头上
            # 的东西漏进上下文）
            return XjxHttpResult(0, f"请求心鉴学服务失败：{type(exc).__name__}。请稍后重试。", True)

        return XjxHttpResult(response.status_code, redact(response.text or ""))


# --------------------------------------------------------------------------- #
# 必填字段闸门
# --------------------------------------------------------------------------- #
def _missing_fields(person: dict[str, Any]) -> list[str]:
    """列出缺失/不合法字段，附带给用户看的中文名（顺序即"该问的顺序"）。"""
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

    # 出生时间到时分 → 要按真太阳时校正，没有出生地就不准（见模块开头）
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
        if not xjx.may_use_tools(ctx.assistant_id):
            raise SkillExecutionError(
                "报告代取只为 Soulmate（Soulmate专用）与 Love Buddy / Relation Buddy"
                "（人际关系运营）开放：当前搭子不在归属名单里，无法使用。"
            )

        # 端点由**搭子 + 当前线路**决定，不由模型传参决定 —— 否则 Love Buddy
        # 传一句 report="soulmate" 就能去取 Soulmate 的报表
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
        # 日志只记状态与端点：凭证绝不能进日志
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

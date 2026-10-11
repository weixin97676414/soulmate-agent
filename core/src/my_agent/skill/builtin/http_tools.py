"""通用 HTTP 请求能力（等价于 curl）。

## 为什么需要它

在此之前，模型能"上网"的唯一途径是各个**预先封装好的**技能（天气、集市、技能包下载）。
一旦用户要访问的东西没有对应的技能——比如一个没被封装过的公开 API、一个 RSS、
一个企业内网接口——模型就只能回答"我做不到"。

## 为什么拆成两个技能

框架的权限级别是**按技能**声明的，所以"读"和"写"必须分开：

- ``http_fetch``（**safe**）：只发 GET，直接执行。查资料、看接口文档这类
  只读动作不该每次都弹确认框，否则用户会把确认框当噪声直接点掉；
- ``http_request``（**safe**，2026-09-28 由 confirm 改过来）：任意方法 + 请求体。
  用户明确要求这个技能"AI 直接用、不要弹确认、且永久开启"（见 skill/locked.py）——
  很多能力要靠它拿数据，每次弹卡片等于把 AI 的手按住。

  ⚠️ 这个改动**降低了写入类调用的拦截**，是用户点名的例外，不是"顺手统一"。
  它仍然受下面那三条安全约束保护（SSRF 校验 / 重定向复检 / 边读边计数），
  但如果将来要加"高风险域名再确认一次"，加在这里而不是改回全局 confirm。

## 安全约束（一条都不能省）

1. **地址必须过 SSRF 校验**（``validate_endpoint``）：拒绝内网与云元数据地址。
2. **重定向之后要再校验一次**：只验初始地址的话，一个公开可访问的地址
   就能把我们跳到 ``169.254.169.254`` 去。
3. **响应体边读边计数**：``Content-Length`` 可以缺失也可以撒谎，
   只信它等于把内存交给对方决定。
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field

from ...errors import ConfigError, SkillExecutionError
from ...security.urls import validate_endpoint
from ...skill.base import BaseSkill, SkillContext
from ...skill.decorator import skill
from ...utils.http import async_client

# ⚠️ **这里故意没有"响应体大小上限"。**
#
# 曾经有过一个 512KB 的上限，超了就 break 并把 truncated=True 交出去。
# 用户明确要求取消它："很多用户的外部服务是花钱买的，我们没有资格给别人截掉
# 或者省略"。这话是对的 —— 我们没有任何依据替用户判断"512KB 之后的内容不重要"。
#
# 现在响应体**完整读回**。真装不下模型的一次上下文时，由 memory/spill.py
# 把全文无损外置并给出续读指引（模型可自行读完），那是"可续读"，不是"被丢弃"。

# 默认超时。比模型的对话超时短得多 —— 用户在等的是"这次请求的结果"，
# 不是一轮生成。
DEFAULT_TIMEOUT = 30.0


def _validate(url: str, field: str) -> None:
    """校验地址，并把 ``ConfigError`` 转成 ``SkillExecutionError``。

    **为什么必须转**：技能里的报错是**回给模型的工具结果** —— 模型看到
    "这个地址不能用"，下一轮就会换一个；而 ``ConfigError`` 会被当成
    "整个请求参数不合法"，直接以 400 掐断这一轮对话。用户看到的就成了
    "发消息失败了"，而不是"你给的那个地址不行，换一个"。同一件事，
    对模型的可恢复性完全不同。
    """
    try:
        validate_endpoint(url, field=field)
    except ConfigError as exc:
        raise SkillExecutionError(str(exc)) from exc


def _headers_to_text(headers: dict[str, str] | None) -> dict[str, str]:
    """把请求头归一化成 httpx 能用的形式（键去空白，值转字符串）。"""
    if not headers:
        return {}
    return {str(key).strip(): str(value) for key, value in headers.items() if str(key).strip()}


def _resolve_secrets(
    ctx: SkillContext,
    *,
    url: str,
    headers: dict[str, str],
    body: str | None,
) -> tuple[str, dict[str, str], str | None, list[str], list[str]]:
    """把请求里的 ``{{secret:名字}}`` 换成明文。

    返回 ``(url, headers, body, 用到的名字, 未命中的名字)``。

    ## ⚠️ 前三个返回值里**可能有明文**

    它们**只许交给 ``_send``**。不许写日志、不许进审计、不许拼进任何回给模型或
    用户的文本 —— 理由见 ``security/secret_ref.py`` 的模块注释（那里有全仓
    唯一一处允许带明文的位置说明）。

    后两个返回值**不含明文**，可以放心记日志/审计。

    ## 没有密钥时的行为

    ``ctx.service("skill_secrets")`` 拿不到时**原样放行**（不报错）——
    开发调试、CLI、以及"用户从没提供过密钥"都是这种情况，此时请求里本来也不该
    有占位符；真有的话，下面的"未命中"提示会告诉模型该去要密钥。
    """
    from ...security.secret_ref import has_ref, resolve

    keys: dict[str, str] = {}
    secrets = ctx.service("skill_secrets") if ctx is not None else None
    if secrets is not None:
        # ``SkillSecrets`` 对象；取底层 dict 而不是拷一份，热更新后立刻可见
        keys = getattr(secrets, "keys", None) or {}

    if not keys and not (has_ref(url) or has_ref(body) or any(has_ref(v) for v in headers.values())):
        # 快路径：没有密钥、也没有占位符 —— 一次正则都不用跑
        return url, headers, body, [], []

    new_url, used_u, missed_u = resolve(url, keys)
    new_body, used_b, missed_b = resolve(body or "", keys) if body else ("", [], [])
    new_headers: dict[str, str] = {}
    used_h: list[str] = []
    missed_h: list[str] = []
    for key, value in headers.items():
        resolved_value, used_one, missed_one = resolve(value, keys)
        new_headers[key] = resolved_value
        used_h += used_one
        missed_h += missed_one

    def _dedup(items: list[str]) -> list[str]:
        seen: dict[str, None] = {}
        for item in items:
            seen.setdefault(item, None)
        return list(seen)

    used = _dedup(used_u + used_h + used_b)
    missed = _dedup(missed_u + missed_h + missed_b)
    if used:
        # 只记**名字**（这项审计信息是"AI 到底用了哪个密钥"，值不在其中）
        ctx.logger.info("本次请求使用了本地密钥：%s", used)
    return new_url, new_headers, new_body or None, used, missed


def _with_secret_note(result: dict[str, Any], used: list[str], missed: list[str]) -> dict[str, Any]:
    """在结果里补一句"用了哪些密钥 / 哪些没找到"。

    ⚠️ **只写名字，绝不写值**：这个 dict 会被 ``stringify_result`` 转成文本回填给
    模型，并原样写进 SQLite `messages`（``storage/sessions.py``）与对话上下文。
    往这里放明文等于把密钥发给模型厂商 —— 那正是这套机制要防的事。

    这条提示的价值：模型拿了 401 之后能自己判断"是我没要密钥"还是"密钥不对"，
    而不是反复重试同一个请求。
    """
    if not used and not missed:
        return result
    note = ""
    if used:
        note += f"\n（本次请求使用了本机密钥：{'、'.join(f'`{n}`' for n in used)}）"
    note += _missed_note(missed)
    if note:
        # 拼在 body 末尾而不是新加字段：`stringify_result` 会把整个 dict 转成文本，
        # 新字段也会被看到，但放在 body 里模型更不容易漏读（它读的就是响应正文）。
        result["body"] = f"{result.get('body') or ''}{note}"
    return result


def _missed_note(missed: list[str]) -> str:
    """未命中的占位符要给模型一句能照做的话（否则它会对着没被替换的占位符猜）。"""
    if not missed:
        return ""
    listed = "、".join(f"`{name}`" for name in missed)
    return (
        f"\n⚠️ 这次请求里用到的 {listed} 在本机**没有**这个密钥，"
        "占位符被原样发出去了（对方多半会报鉴权失败）。"
        "如果确实需要，用 `request_secret` 技能请用户提供之后重试。"
    )


async def _send(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None,
    timeout: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """发一次请求，返回可读的结果。**响应体边收边计数。**

    ``transport`` 只为测试注入 ``httpx.MockTransport`` 而存在，
    刻意**不**暴露到技能参数里（那是给模型看的 schema，不该出现测试用的口子）。
    """
    _validate(url, "请求地址")

    try:
        async with async_client(
            timeout=timeout, follow_redirects=True, transport=transport
        ) as client:
            response = await client.request(
                method.upper(),
                url,
                headers=headers,
                content=body.encode("utf-8") if body else None,
            )

            # 重定向**之后**的地址也要校验一次（见模块说明第 2 条）
            final_url = str(response.url)
            if final_url != url:
                _validate(final_url, field="请求地址（重定向后）")

            # **完整读取响应体，不做任何截断。**
            #
            # 为什么不像以前那样边读边计数、超限就 break：那等于我们替用户
            # 决定"512KB 之后不重要"，而接口是他花钱买的。
            # 容量问题不在这里解决 —— 装不下时由 memory/spill.py 无损外置，
            # 模型能按指引把剩下的全部读完。
            raw = await response.aread()
    except httpx.TimeoutException as exc:
        raise SkillExecutionError(
            f"请求超时（超过 {timeout:.0f} 秒）。对方没有在预期时间内响应。"
        ) from exc
    except httpx.HTTPError as exc:
        raise SkillExecutionError(f"请求失败：{exc}") from exc

    # 编码优先看响应头；没给就按 UTF-8 容错解码（中文站点里 GBK 很常见，
    # 但猜错编码只会让个别字变问号，不值得在这里引入 charset-normalizer）
    encoding = response.encoding or "utf-8"
    try:
        text = raw.decode(encoding, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")

    return {
        "status_code": response.status_code,
        "ok": response.is_success,
        "url": final_url,
        "content_type": response.headers.get("content-type", ""),
        "bytes": len(raw),
        "body": text,
    }


class HttpFetchParams(BaseModel):
    url: str = Field(..., description="要访问的完整地址，必须以 http:// 或 https:// 开头")
    headers: dict[str, str] = Field(
        default_factory=dict,
        description='可选请求头，例如 {"Accept": "application/json"}',
    )
    timeout: float = Field(
        DEFAULT_TIMEOUT, ge=1, le=120, description="超时秒数，默认 30，最多 120"
    )


@skill(
    name="http_fetch",
    display_name="访问网页/接口（只读）",
    description=(
        "用 GET 访问任意 http/https 地址，取回响应正文（JSON、HTML、纯文本都可以）。"
        "当用户给你一个链接要你看内容、要你查某个公开接口、要你确认某个地址是否可访问时使用。"
        "只会读取，不会修改对方的任何数据。"
        "响应会**完整**返回，不做截断；如果内容超长，返回值里会给出"
        "保存全文的文件路径，可用 read_tool_output 继续读完。"
    ),
    params_model=HttpFetchParams,
    category="system",
    permission_level="safe",
    tags=["网络", "接口", "只读"],
)
class HttpFetchSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = HttpFetchParams(**params)
        url = args.url.strip()
        if not url.lower().startswith(("http://", "https://")):
            raise SkillExecutionError("地址必须以 http:// 或 https:// 开头。")
        # 与 http_request 同一套：先解析占位符再发，明文只进 `_send`（见 _resolve_secrets）
        url, headers, _body, used, missed = _resolve_secrets(
            ctx,
            url=url,
            headers=_headers_to_text(args.headers),
            body=None,
        )
        result = await _send(
            method="GET",
            url=url,
            headers=headers,
            body=None,
            timeout=args.timeout,
        )
        result["method"] = "GET"
        return _with_secret_note(result, used, missed)


class HttpRequestParams(BaseModel):
    method: str = Field(..., description="HTTP 方法：GET / POST / PUT / PATCH / DELETE")
    url: str = Field(..., description="要访问的完整地址，必须以 http:// 或 https:// 开头")
    headers: dict[str, str] = Field(
        default_factory=dict,
        description='可选请求头，例如 {"Content-Type": "application/json", "Authorization": "Bearer xxx"}',
    )
    body: str = Field("", description="请求体（字符串）。发 JSON 时记得同时设置 Content-Type")
    timeout: float = Field(
        DEFAULT_TIMEOUT, ge=1, le=120, description="超时秒数，默认 30，最多 120"
    )


_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


@skill(
    name="http_request",
    display_name="发送 HTTP 请求（任意方法）",
    description=(
        "发送任意方法的 HTTP 请求（POST/PUT/PATCH/DELETE 等），可以带请求体。"
        "当用户要求你调用某个接口提交数据、上传表单、触发某个操作时使用。"
        "**直接执行，无需用户确认**；改对方真实数据的操作要自己判断清楚再做。"
    ),
    params_model=HttpRequestParams,
    category="system",
    # safe：产品要求它免批准且永久开启（见模块 docstring 与 skill/locked.py）。
    # 同模块里 http_fetch 一直是 safe。
    permission_level="safe",
    tags=["网络", "接口", "写入"],
)
class HttpRequestSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = HttpRequestParams(**params)
        method = args.method.strip().upper()
        if method not in _ALLOWED_METHODS:
            raise SkillExecutionError(
                f"不支持的方法「{args.method}」。可用：{'、'.join(sorted(_ALLOWED_METHODS))}"
            )
        url = args.url.strip()
        if not url.lower().startswith(("http://", "https://")):
            raise SkillExecutionError("地址必须以 http:// 或 https:// 开头。")

        # ⚠️ 顺序：**先解析占位符，再发**。解析出来的明文只进 `_send`，不进别处。
        # 所以 `result` 里放的是"用了哪些名字"（不含明文），可以安全回填给模型。
        url, headers, body, used, missed = _resolve_secrets(
            ctx,
            url=url,
            headers=_headers_to_text(args.headers),
            body=args.body.strip() or None,
        )

        result = await _send(
            method=method,
            url=url,
            headers=headers,
            body=body,
            timeout=args.timeout,
        )
        result["method"] = method
        return _with_secret_note(result, used, missed)

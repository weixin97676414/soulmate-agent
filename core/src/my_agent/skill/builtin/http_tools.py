






























from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field

from ...errors import ConfigError, SkillExecutionError
from ...security.urls import validate_endpoint
from ...skill.base import BaseSkill, SkillContext
from ...skill.decorator import skill
from ...utils.http import async_client












DEFAULT_TIMEOUT = 30.0


def _validate(url: str, field: str) -> None:








    try:
        validate_endpoint(url, field=field)
    except ConfigError as exc:
        raise SkillExecutionError(str(exc)) from exc


def _headers_to_text(headers: dict[str, str] | None) -> dict[str, str]:

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


















    from ...security.secret_ref import has_ref, resolve

    keys: dict[str, str] = {}
    secrets = ctx.service("skill_secrets") if ctx is not None else None
    if secrets is not None:
        
        keys = getattr(secrets, "keys", None) or {}

    if not keys and not (has_ref(url) or has_ref(body) or any(has_ref(v) for v in headers.values())):
        
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
        
        ctx.logger.info("本次请求使用了本地密钥：%s", used)
    return new_url, new_headers, new_body or None, used, missed


def _with_secret_note(result: dict[str, Any], used: list[str], missed: list[str]) -> dict[str, Any]:









    if not used and not missed:
        return result
    note = ""
    if used:
        note += f"\n（本次请求使用了本机密钥：{'、'.join(f'`{n}`' for n in used)}）"
    note += _missed_note(missed)
    if note:
        
        
        result["body"] = f"{result.get('body') or ''}{note}"
    return result


def _missed_note(missed: list[str]) -> str:

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

            
            final_url = str(response.url)
            if final_url != url:
                _validate(final_url, field="请求地址（重定向后）")

            
            
            
            
            
            
            raw = await response.aread()
    except httpx.TimeoutException as exc:
        raise SkillExecutionError(
            f"请求超时（超过 {timeout:.0f} 秒）。对方没有在预期时间内响应。"
        ) from exc
    except httpx.HTTPError as exc:
        raise SkillExecutionError(f"请求失败：{exc}") from exc

    
    
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

"""MCP 配置的**归一化**：把各家客户端五花八门的写法收成我们的内部口径（审计 H-06）。

## 为什么单独一层

这三个函数原先住在 ``server/routes/mcp.py`` 里，于是**领域层只能反向 import 路由层**：
``skill/install.py`` 想归一化一段 MCP 配置，得写
``from ..server.routes.mcp import _coerce_entry`` —— 一个 `_` 开头的"内部实现"
就这样成了事实上的公共 API，而且任何路由重构都会牵动技能层。

现在它们住在这里（纯数据变换，与 FastAPI / Request 无关）：
路由与技能层都**依赖这里**，方向正过来了。

## 关于命名

搬出来时去掉了前导下划线。它们本来就被跨模块调用，`_` 前缀只是"当初写在一个文件里"
留下的痕迹；继续留着私有会让下一个读者以为"外部不能用"，于是又有人在别处抄一份。
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ..config.schemas import McpServerConfig


def normalize_transport(declared: str, has_url: bool) -> str:
    """把各家客户端五花八门的传输声明归一化成我们内部三种之一。

    「应用适配任何 MCP，而不是让 MCP 适配我们」（用户要求）：Claude Desktop 用
    ``type: "http"``、Cursor 用 ``type: "sse"``、社区分享用 ``"streamableHttp"``
    或 ``"streamable-http"`` 或 ``transport: "streamable_http"``——这里全收。
    """
    d = (declared or "").strip().lower().replace("-", "_")
    if d in ("sse", "http_sse", "sse_http"):
        return "sse"
    if d == "stdio":
        return "stdio"
    # 有 url 且没明确声明 sse/stdio → 一律按 streamable_http（现代 MCP 默认）。
    # 覆盖 streamablehttp / streamable_http / http / 空 等写法。
    if has_url:
        return "streamable_http"
    return "stdio"


def coerce_entry(name: str, raw: Any) -> McpServerConfig:
    """把一段 MCP 配置转成 McpServerConfig。

    兼容两种常见写法：带 ``url`` 的远程端点，和带 ``command`` 的本机子进程。
    各家客户端（Claude Desktop / Cursor 等）导出的字段基本一致，差别主要在
    远程端点用 ``type`` 还是 ``transport`` 声明传输方式。
    """
    if not isinstance(raw, dict):
        raise ValueError("这一段不是一个对象")

    command = str(raw.get("command") or "").strip()
    url = str(raw.get("url") or "").strip()
    declared = str(raw.get("type") or raw.get("transport") or "")

    transport = normalize_transport(declared, has_url=bool(url))

    return McpServerConfig(
        name=name,
        transport=transport,  # type: ignore[arg-type]
        url=url,
        headers={str(k): str(v) for k, v in (raw.get("headers") or {}).items()}
        if isinstance(raw.get("headers"), dict)
        else {},
        command=command,
        args=[str(item) for item in (raw.get("args") or [])]
        if isinstance(raw.get("args"), list)
        else [],
        env={str(k): str(v) for k, v in (raw.get("env") or {}).items()}
        if isinstance(raw.get("env"), dict)
        else {},
        enabled=bool(raw.get("enabled", True)),
        description=str(raw.get("description") or ""),
    )


def first_error(exc: ValidationError) -> str:
    """取 pydantic 校验错误里最有用的一句。

    完整的 ValidationError 会打印一堆字段路径（英文），对普通用户毫无意义。
    这里只留"哪个字段 + 为什么"，例如「command：stdio 传输必须填写启动命令」。
    """
    try:
        issues = exc.errors()
    except Exception:  # noqa: BLE001
        return str(exc)
    if not issues:
        return str(exc)
    first = issues[0]
    field = ".".join(str(part) for part in first.get("loc") or [])
    message = str(first.get("msg") or "")
    return f"{field}：{message}" if field else message

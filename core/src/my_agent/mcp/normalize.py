

















from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ..config.schemas import McpServerConfig


def normalize_transport(declared: str, has_url: bool) -> str:






    d = (declared or "").strip().lower().replace("-", "_")
    if d in ("sse", "http_sse", "sse_http"):
        return "sse"
    if d == "stdio":
        return "stdio"
    
    
    if has_url:
        return "streamable_http"
    return "stdio"


def coerce_entry(name: str, raw: Any) -> McpServerConfig:






    if not isinstance(raw, dict):
        raise ValueError("这一段不是一个对象")

    command = str(raw.get("command") or "").strip()
    url = str(raw.get("url") or "").strip()
    declared = str(raw.get("type") or raw.get("transport") or "")

    transport = normalize_transport(declared, has_url=bool(url))

    return McpServerConfig(
        name=name,
        transport=transport,  
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





    try:
        issues = exc.errors()
    except Exception:  
        return str(exc)
    if not issues:
        return str(exc)
    first = issues[0]
    field = ".".join(str(part) for part in first.get("loc") or [])
    message = str(first.get("msg") or "")
    return f"{field}：{message}" if field else message

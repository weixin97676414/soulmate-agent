





from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from ...config.schemas import McpServerConfig
from ...errors import McpServerError
from ...mcp.normalize import coerce_entry, first_error
from ...mcp.presets import presets as build_presets
from ...mcp.skill import infer_permission_level, namespaced_name
from ..deps import get_runtime
from ..runtime import AppRuntime

router = APIRouter(tags=["mcp"], prefix="/v1/mcp")


class ToolPermissionRequest(BaseModel):
    tool: str = Field(..., description="MCP 侧的原始工具名（不含命名空间前缀）")
    permission_level: str = Field(..., description="safe / confirm / admin，空字符串表示恢复自动推断")


def _require_sdk(runtime: AppRuntime) -> None:

    if not runtime.mcp.sdk_available:
        raise HTTPException(
            status_code=501,
            detail={
                "code": "mcp_sdk_missing",
                "message": '未安装 MCP 依赖。请执行：pip install "my-agent-core[mcp]"',
            },
        )


class McpJsonImport(BaseModel):
    payload: str = Field("", description="粘贴的 JSON 文本")
    overwrite: bool = Field(False, description="同名服务已存在时是否覆盖")


@router.post("/import-json")
async def import_json(body: McpJsonImport, request: Request) -> dict[str, Any]:









    runtime: AppRuntime = get_runtime(request)
    _require_sdk(runtime)

    text = (body.payload or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="请先粘贴一段 JSON。")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        
        
        raise HTTPException(
            status_code=400, detail=f"JSON 格式不对（第 {exc.lineno} 行第 {exc.colno} 列：{exc.msg}）"
        ) from exc

    
    entries = parsed.get("mcpServers") if isinstance(parsed, dict) else None
    if not isinstance(entries, dict):
        entries = parsed if isinstance(parsed, dict) else None
    if not isinstance(entries, dict):
        raise HTTPException(
            status_code=400,
            detail='没找到可导入的服务。格式应形如：{"mcpServers": {"名字": {"command": "...", "args": [...]}}}',
        )

    added: list[str] = []
    errors: list[dict[str, str]] = []

    for name, raw in entries.items():
        key = str(name).strip()
        try:
            config = coerce_entry(key, raw)
        except (ValueError, ValidationError) as exc:
            
            
            message = first_error(exc) if isinstance(exc, ValidationError) else str(exc)
            errors.append({"name": key, "message": message})
            continue

        if runtime.mcp.status(key) is not None and not body.overwrite:
            errors.append({"name": key, "message": "已经存在（勾选覆盖可替换）"})
            continue

        try:
            if runtime.mcp.status(key) is not None:
                await runtime.mcp.update_server(config)
            else:
                await runtime.mcp.add_server(config)
            added.append(key)
        except McpServerError as exc:
            detail = exc.to_dict()
            errors.append({"name": key, "message": str(detail.get("message") or detail)})

    return {"ok": not errors, "added": added, "errors": errors, "total": len(entries)}


@router.get("/servers")
async def list_servers(request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    statuses = runtime.mcp.statuses()
    return {
        "servers": [status.to_dict() for status in statuses],
        "sdk_available": runtime.mcp.sdk_available,
        "tool_total": sum(status.tool_count for status in statuses if status.is_active),
        "presets": build_presets(runtime.paths),
    }


@router.get("/servers/{name}")
async def get_server(name: str, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    status = runtime.mcp.status(name)
    if status is None:
        raise HTTPException(status_code=404, detail=f"MCP 服务「{name}」不存在")
    return status.to_dict()


@router.post("/servers")
async def create_server(payload: McpServerConfig, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    _require_sdk(runtime)
    if runtime.mcp.status(payload.name) is not None:
        raise HTTPException(
            status_code=409, detail=f"MCP 服务「{payload.name}」已存在，请先删除或改名。"
        )
    try:
        status = await runtime.mcp.add_server(payload)
    except McpServerError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.to_dict()) from exc
    return status.to_dict()


@router.put("/servers/{name}")
async def update_server(name: str, payload: McpServerConfig, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    _require_sdk(runtime)
    if name != payload.name:
        raise HTTPException(status_code=422, detail="路径中的服务名与请求体不一致。")
    if runtime.mcp.status(name) is None:
        raise HTTPException(status_code=404, detail=f"MCP 服务「{name}」不存在")
    status = await runtime.mcp.update_server(payload)
    return status.to_dict()


@router.delete("/servers/{name}")
async def delete_server(name: str, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    removed = await runtime.mcp.remove_server(name)
    if not removed:
        raise HTTPException(status_code=404, detail=f"MCP 服务「{name}」不存在")
    return {"ok": True}


@router.post("/servers/{name}/restart")
async def restart_server(name: str, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    _require_sdk(runtime)
    status = await runtime.mcp.restart_server(name)
    if status is None:
        raise HTTPException(status_code=404, detail=f"MCP 服务「{name}」不存在")
    return status.to_dict()


@router.post("/servers/{name}/stop")
async def stop_server(name: str, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    status = await runtime.mcp.stop_server(name)
    if status is None:
        raise HTTPException(status_code=404, detail=f"MCP 服务「{name}」不存在")
    return status.to_dict()


@router.get("/servers/{name}/tools")
async def server_tools(name: str, request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    status = runtime.mcp.status(name)
    if status is None:
        raise HTTPException(status_code=404, detail=f"MCP 服务「{name}」不存在")
    return {
        "name": name,
        "state": status.state.value,
        "message": status.message,
        "tools": [tool.to_dict() for tool in status.tools],
    }


@router.patch("/servers/{name}/permission")
async def set_tool_permission(
    name: str, payload: ToolPermissionRequest, request: Request
) -> dict[str, Any]:





    runtime: AppRuntime = get_runtime(request)
    server = runtime.mcp.config.get(name)
    if server is None:
        raise HTTPException(status_code=404, detail=f"MCP 服务「{name}」不存在")

    if payload.permission_level:
        if payload.permission_level not in ("safe", "confirm", "admin"):
            raise HTTPException(status_code=422, detail="权限级别只能是 safe / confirm / admin")
        server.permission_overrides[payload.tool] = payload.permission_level
    else:
        server.permission_overrides.pop(payload.tool, None)

    runtime.config_store.save_mcp(runtime.mcp.config)

    
    
    
    
    skill_name = namespaced_name(name, payload.tool)
    if runtime.skills.has(skill_name):
        if payload.permission_level:
            runtime.skills.set_permission(skill_name, payload.permission_level)
        else:
            
            client = runtime.mcp.client(name)
            tool = next(
                (item for item in (client.status.tools if client else []) if item.name == payload.tool),
                None,
            )
            if tool is not None:
                runtime.skills.set_permission(skill_name, infer_permission_level(tool))

    return {
        "ok": True,
        "overrides": dict(server.permission_overrides),
        "skills": [
            meta.to_dict()
            for meta in runtime.skills.list_metas(enabled_only=False)
            if meta.source == "mcp" and meta.name.startswith(f"{name}__")
        ],
    }

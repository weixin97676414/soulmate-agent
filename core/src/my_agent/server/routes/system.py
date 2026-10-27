

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...config.lines import DEFAULT_LINE, ENDPOINTS, endpoints_for
from ...config.schemas import AppSettings, ConfirmMode
from ...version import __version__
from ..deps import get_runtime
from ..runtime import AppRuntime

router = APIRouter(tags=["system"])


class ConfirmModePayload(BaseModel):
    mode: ConfirmMode


class ConfirmModeState(BaseModel):
    mode: ConfirmMode
    """全局设置里的值（含 assistant_override 是否压过它）"""

    assistant_override: ConfirmMode | None = None
    effective: ConfirmMode


class LinePayload(BaseModel):


    line: str


@router.put("/v1/client/line")
async def set_line(payload: LinePayload, request: Request) -> dict[str, Any]:








    runtime: AppRuntime = get_runtime(request)
    line = payload.line.strip().lower() or DEFAULT_LINE
    if line not in ENDPOINTS:
        raise HTTPException(status_code=422, detail=f"未知线路：{payload.line}")
    runtime.line = line
    return {"ok": True, "line": line, "endpoints": endpoints_for(line)}


class SessionPayload(BaseModel):


    session_token: str = ""


@router.put("/v1/client/session")
async def set_session(payload: SessionPayload, request: Request) -> dict[str, Any]:









    runtime: AppRuntime = get_runtime(request)
    runtime.set_session_token(payload.session_token)
    return {"ok": True, "has_token": runtime.has_session_token}


@router.get("/v1/health")
async def health(request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    from ...mcp.client import sdk_available
    from ...memory.long_term import chromadb_available

    return {
        "status": "ok",
        
        
        "version": __version__,
        "default_model": runtime.registry.default_id,
        "models": runtime.registry.ids(),
        
        
        
        
        
        
        
        
        "skills": len(runtime.skills)  
        + sum(
            1
            
            
            for item in (getattr(runtime.custom_skills, "skills", None) or [])
            if getattr(item, "kind", "") == "instruction" and getattr(item, "enabled", True)
        ),
        "sessions": len(runtime.sessions),
        "running_tasks": len(runtime.tasks),
        "data_dir": str(runtime.paths.root),
        "persistent": runtime.db_ready,
        
        
        
        
        "optional": {
            "mcp": sdk_available(),
            "memory": chromadb_available(),
        },
        "long_term_enabled": runtime.config.settings.memory.long_term_enabled,
    }


@router.get("/v1/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    return runtime.config.settings.model_dump(mode="json")


@router.put("/v1/settings")
async def update_settings(
    payload: AppSettings, request: Request, clear_calendar_password: bool = False
) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    current = runtime.config.settings

    
    
    
    
    
    
    
    payload.agent.scheduled_tasks = list(current.agent.scheduled_tasks)

    
    
    
    
    if clear_calendar_password:
        payload.calendar.caldav_password = ""
    elif not payload.calendar.caldav_password:
        payload.calendar.caldav_password = current.calendar.caldav_password

    saved = runtime.apply_settings(payload)
    
    
    response = saved.model_dump(mode="json")
    response.setdefault("calendar", {})["caldav_password"] = ""
    return response


@router.get("/v1/security/confirm-mode")
async def get_confirm_mode(
    request: Request, assistant_id: str | None = None
) -> dict[str, Any]:






    runtime: AppRuntime = get_runtime(request)
    global_mode = runtime.config.settings.security.confirm_mode
    profile = runtime.resolve_assistant(assistant_id) if assistant_id else None
    override = profile.confirm_mode if profile else None
    return {
        "mode": global_mode,
        "assistant_override": override,
        "effective": override or global_mode,
    }


@router.put("/v1/security/confirm-mode")
async def set_confirm_mode(
    payload: ConfirmModePayload, request: Request
) -> dict[str, Any]:









    runtime: AppRuntime = get_runtime(request)
    current = runtime.config.settings
    updated = current.model_copy(
        update={"security": current.security.model_copy(update={"confirm_mode": payload.mode})}
    )
    saved = runtime.apply_settings(updated)
    return {"mode": saved.security.confirm_mode}


class PermissionOverridePayload(BaseModel):
    skill: str
    remember: bool = True


@router.get("/v1/security/overrides")
async def get_security_overrides(request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    return {"overrides": dict(runtime.config.settings.security.permission_overrides)}


@router.post("/v1/security/overrides")
async def add_security_override(
    payload: PermissionOverridePayload, request: Request
) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    skill = runtime.skills.get(payload.skill)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"没有叫「{payload.skill}」的技能")

    from ...security.permission import risk_of

    if risk_of(skill.meta) == "high":
        raise HTTPException(
            status_code=400,
            detail=f"「{payload.skill}」是高危操作（删除 / 命令 / 系统控制 / 密钥），不能记住。",
        )
    current = runtime.config.settings
    overrides = dict(current.security.permission_overrides)
    if payload.remember:
        overrides[payload.skill] = "safe"
    else:
        overrides.pop(payload.skill, None)
    updated = current.model_copy(
        update={
            "security": current.security.model_copy(update={"permission_overrides": overrides})
        }
    )
    saved = runtime.apply_settings(updated)
    return {"overrides": dict(saved.security.permission_overrides)}


@router.delete("/v1/security/overrides")
async def clear_security_overrides(request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    current = runtime.config.settings
    updated = current.model_copy(
        update={"security": current.security.model_copy(update={"permission_overrides": {}})}
    )
    saved = runtime.apply_settings(updated)
    return {"overrides": dict(saved.security.permission_overrides)}


@router.get("/v1/paths")
async def get_paths(request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    paths = runtime.paths
    return {
        "root": str(paths.root),
        "config": str(paths.config_dir),
        "data": str(paths.data_dir),
        "logs": str(paths.logs_dir),
        "workspace": str(paths.workspace_dir),
        "artifacts": str(paths.artifacts_dir),
        
        "allowed_dirs": [str(item) for item in runtime.path_policy.allowed_dirs],
        "restricted": runtime.path_policy.is_restricted,
    }


@router.post("/v1/shutdown")
async def shutdown(request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    await runtime.shutdown()

    server = getattr(request.app.state, "uvicorn_server", None)
    if server is not None:
        server.should_exit = True
    return {"ok": True}

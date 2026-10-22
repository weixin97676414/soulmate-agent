







from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from ...config.schemas import CustomSkillDef
from ...config.skill_secrets import parse_skill_secrets
from ...skill import locked
from ...skill.builtin import xjx
from ...skill.inbox import inbox_dir, scan_inbox_async
from ...skill.install import (
    SkillRejected,
    install_mcp_roots,
    install_package,
    package_file_list,
    remove_package_dir,
    validate_defn,
)
from ...skill.package import parse_directory, parse_package
from ..deps import get_runtime
from ..runtime import AppRuntime

logger = logging.getLogger(__name__)

router = APIRouter(tags=["skills"], prefix="/v1/skills")

VALID_PERMISSIONS = {"safe", "confirm", "admin"}


class SkillSecretsBody(BaseModel):










    keys: dict[str, str] = Field(default_factory=dict)


@router.post("/v1/skill-secrets")
async def set_skill_secrets(payload: SkillSecretsBody, request: Request) -> dict[str, Any]:













    runtime: AppRuntime = get_runtime(request)
    
    
    secrets = parse_skill_secrets({"keys": payload.keys})
    count = runtime.apply_skill_secrets(secrets)
    return {"ok": True, "count": count}





HIDDEN_SKILL_NAMES: frozenset[str] = xjx.XJX_TOOL_NAMES


def _xjx_entries(runtime: AppRuntime) -> list[dict[str, Any]]:

    return [xjx.describe(item) for item in xjx.active_skills(runtime.line)]


def _instruction_entries(runtime: AppRuntime) -> list[dict[str, Any]]:











    from ...skill import groups

    result: list[dict[str, Any]] = []
    for defn in getattr(runtime.custom_skills, "skills", []) or []:
        if defn.kind != "instruction":
            continue
        result.append(
            {
                "name": defn.id,
                "display_name": defn.name or defn.id,
                "description": defn.description,
                "parameters": {"type": "object", "properties": {}},
                "category": "custom",
                "permission_level": defn.permission_level,
                "timeout": defn.timeout,
                "enabled": defn.enabled,
                "tags": ["指导型"],
                "source": "custom",
                
                
                
                
                
                
                
                "bucket": groups.bucket_of(defn.id, "custom", defn.domain),
                "domain": defn.domain,
                
                
                
                
                
                
                
                
                
                "owners": list(groups.owners_of(defn.id)),
                "owner_label": groups.owner_label(groups.owners_of(defn.id)),
                "locked": groups.is_locked_instruction(defn.id),
                
                "instruction_only": True,
            }
        )
    return result


@router.get("")
async def list_skills(request: Request, enabled_only: bool = False) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    metas = [
        m
        for m in runtime.skills.list_metas(enabled_only=enabled_only)
        if m.name not in HIDDEN_SKILL_NAMES
    ]
    xjx_entries = _xjx_entries(runtime)
    
    instruction_entries = [
        item for item in _instruction_entries(runtime) if not enabled_only or item["enabled"]
    ]
    skills = [m.to_dict() for m in metas] + xjx_entries + instruction_entries
    return {
        
        
        "total": len(skills),
        "enabled": len([m for m in runtime.skills.list_metas() if m.name not in HIDDEN_SKILL_NAMES])
        + len(xjx_entries)
        + len([item for item in instruction_entries if item["enabled"]]),
        "skills": skills,
        "categories": sorted({item["category"] for item in skills}),
    }


class SkillPatch(BaseModel):








    enabled: bool | None = None
    permission_level: str | None = None


@router.patch("/{name}")
async def patch_skill(name: str, payload: SkillPatch, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)

    
    
    
    if xjx.is_xjx_skill(name):
        raise HTTPException(status_code=409, detail=xjx.locked_message(name))

    
    
    
    
    
    
    from ...skill import groups

    if groups.is_locked_instruction(name):
        display = name
        for defn in getattr(runtime.custom_skills, "skills", []) or []:
            if defn.id == name and defn.name:
                display = defn.name
                break
        raise HTTPException(
            status_code=409,
            detail=(
                f"「{display}」是内置或专属技能，按搭子归属自动生效、没有开关，"
                "不需要也无法手动关闭。"
            ),
        )

    if not runtime.skills.has(name):
        raise HTTPException(status_code=404, detail=f"Skill {name} 不存在")

    meta = runtime.skills.get(name).meta

    
    
    
    
    
    if meta.locked:
        display = meta.display_name or name
        
        wants_disable = payload.enabled is False
        wants_permission_change = (
            payload.permission_level is not None
            and payload.permission_level != meta.permission_level
        )
        if wants_disable or wants_permission_change:
            
            
            raise HTTPException(status_code=409, detail=locked.locked_message(display))

    if payload.permission_level is not None:
        if payload.permission_level not in VALID_PERMISSIONS:
            raise HTTPException(
                status_code=422,
                detail=f"权限级别必须是 {sorted(VALID_PERMISSIONS)} 之一",
            )
        
        
        runtime.skills.set_permission(name, payload.permission_level)

    if payload.enabled is not None:
        runtime.skills.set_enabled(name, payload.enabled)

    return runtime.skills.get(name).meta.to_dict()





class CustomSkillPayload(BaseModel):
    skill: CustomSkillDef


@router.get("/custom")
async def list_custom(request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    return {"skills": [item.model_dump(mode="json") for item in runtime.custom_skills.skills]}


def _validate_custom(runtime: AppRuntime, defn: CustomSkillDef) -> None:

    try:
        validate_defn(runtime, defn)
    except SkillRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/custom")
async def upsert_custom(payload: CustomSkillPayload, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    defn = payload.skill
    if not defn.source_format:
        
        
        defn = defn.model_copy(update={"source_format": "manual"})
    _validate_custom(runtime, defn)

    config = runtime.custom_skills.model_copy(deep=True)
    config.upsert(defn)
    runtime.config_store.save_custom_skills(config)
    total = runtime.reload_custom_skills(config)
    return {"ok": True, "skill": defn.model_dump(mode="json"), "total": total}


@router.delete("/custom/{skill_id}")
async def delete_custom(skill_id: str, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    config = runtime.custom_skills.model_copy(deep=True)
    if not config.remove(skill_id):
        raise HTTPException(status_code=404, detail=f"自定义技能「{skill_id}」不存在")
    
    remove_package_dir(runtime, skill_id)
    runtime.config_store.save_custom_skills(config)
    total = runtime.reload_custom_skills(config)
    return {"ok": True, "total": total}


@router.get("/custom/{skill_id}/files")
async def skill_files(skill_id: str, request: Request) -> dict[str, Any]:





    runtime: AppRuntime = get_runtime(request)
    root = runtime.paths.skills_dir / skill_id
    files = package_file_list(runtime, skill_id)
    entries: list[dict[str, Any]] = []
    for name in files:
        try:
            size = (root / name).stat().st_size
        except OSError:
            size = 0
        entries.append({"path": name, "size": size})
    return {"skill_id": skill_id, "dir": str(root), "files": entries}





@router.get("/custom/folder")
async def skill_folder(request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    root = inbox_dir(runtime)
    return {
        "skills_dir": str(runtime.paths.skills_dir),
        "inbox": str(root),
        "exists": root.is_dir(),
    }


class ScanRequest(BaseModel):


    only: str = Field("", description="只扫描投放区里这个名字的条目（留空 = 全部）")


@router.post("/custom/scan")
async def scan_folder(payload: ScanRequest, request: Request) -> dict[str, Any]:





    runtime: AppRuntime = get_runtime(request)
    outcome = await scan_inbox_async(runtime, only=payload.only.strip())
    outcome.pop("mcp_roots", None)
    return outcome















async def _install_package_bytes(
    runtime: AppRuntime, payload: bytes, package_name: str, filename: str = ""
) -> dict[str, Any]:





    try:
        parsed = parse_package(payload, package_name, filename=filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    outcome = install_package(runtime, parsed, source_label=filename or package_name)

    mcp_records = await install_mcp_roots(runtime, parsed.mcp_roots)
    if mcp_records:
        outcome["mcp"] = mcp_records
        ok = sum(1 for item in mcp_records if item.get("ok"))
        outcome["message"] = f"{outcome['message']}MCP 服务接入：{ok}/{len(mcp_records)} 个成功。"
    return outcome


@router.post("/custom/import")
async def import_package(
    request: Request, package: UploadFile = File(...)  
) -> dict[str, Any]:





    runtime: AppRuntime = get_runtime(request)
    payload = await package.read()
    filename = (package.filename or "skill.zip").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    package_name = filename.rsplit(".", 1)[0] or "skill"
    return await _install_package_bytes(runtime, payload, package_name, filename)


class ImportUrlRequest(BaseModel):


    url: str = Field(..., min_length=1, description="技能包（zip）的下载地址")


@router.post("/custom/import-url")
async def import_from_url(payload: ImportUrlRequest, request: Request) -> dict[str, Any]:





    import asyncio

    import httpx

    from ...security.urls import validate_endpoint
    from ...skill.archive import MAX_PACKAGE_BYTES
    from ...utils.http import async_client

    runtime: AppRuntime = get_runtime(request)
    url = payload.url.strip()
    
    validate_endpoint(url, field="技能包地址")

    try:
        async with async_client(timeout=httpx.Timeout(20.0, connect=8.0)) as client:
            response = await asyncio.wait_for(
                client.get(url, follow_redirects=True), timeout=20.0
            )
            response.raise_for_status()
            data = response.content
    except Exception as exc:  
        raise HTTPException(status_code=400, detail=f"下载技能包失败：{exc}") from exc

    if len(data) > MAX_PACKAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"技能包超过 {MAX_PACKAGE_BYTES // 1024 // 1024}MB，已拒绝下载。",
        )

    filename = url.rsplit("/", 1)[-1].rsplit("?", 1)[0] or "skill.zip"
    package_name = filename.rsplit(".", 1)[0] or "skill"
    return await _install_package_bytes(runtime, data, package_name, filename)


class ImportPathRequest(BaseModel):


    path: str = Field(..., min_length=1, description="要导入的文件夹的绝对路径")
    name: str = Field("", description="技能名（留空则用文件夹名）")
    domain: str = Field(
        "",
        description=(
            "技能**小分类**（技能页「通用技能」栏那排分类按钮按它分组）："
            "电商 / 金融 / 营销 / 教育 / 医疗 / 科技 / 学术 / 设计 / 法律 / 人力 / "
            "办公 / 生活 / 媒体 / 系统。留空 = 不归类。"
            "⚠️ 包内路径里读不到它 —— 批量导入第三方素材库时必须由调用方按源目录分类传进来。"
        ),
    )


@router.post("/custom/import-path")
async def import_from_path(payload: ImportPathRequest, request: Request) -> dict[str, Any]:







    runtime: AppRuntime = get_runtime(request)
    raw = payload.path.strip().strip('"')
    target = Path(raw).expanduser()
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"文件夹不存在：{raw}")
    try:
        parsed = parse_directory(target, payload.name.strip() or target.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    outcome = install_package(
        runtime,
        parsed,
        source_label=f"文件夹 {target.name}",
        domain=payload.domain.strip(),
    )
    mcp_records = await install_mcp_roots(runtime, parsed.mcp_roots)
    if mcp_records:
        outcome["mcp"] = mcp_records
        ok = sum(1 for item in mcp_records if item.get("ok"))
        outcome["message"] = f"{outcome['message']}MCP 服务接入：{ok}/{len(mcp_records)} 个成功。"
    outcome["source_path"] = str(target)
    return outcome


__all__ = [
    "HIDDEN_SKILL_NAMES",
    "VALID_PERMISSIONS",
    "_install_package_bytes",
    "router",
]

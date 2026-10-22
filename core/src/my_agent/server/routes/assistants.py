





from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from ...assistants import evolution, lifecycle, locked_builtins
from ...assistants.persona import RULES_FILE, SOUL_FILE, list_files, read_file, write_file
from ...assistants.presets import (
    DEFAULT_ASSISTANT_ID,
    RENAMED_BUILTIN_IDS,
)
from ...assistants.transfer import (
    TransferError,
    apply_buddy,
    apply_buddy_group,
    parse_buddy_package,
    parse_group_package,
)
from ...config.schemas import AssistantProfile
from ...skill.builtin import xjx
from ...skill.custom import known_skill_names
from ..deps import get_runtime
from ..runtime import AppRuntime

logger = logging.getLogger(__name__)

router = APIRouter(tags=["assistants"], prefix="/v1/assistants")











def _validate_model(runtime: AppRuntime, profile: AssistantProfile) -> None:





    if profile.model_id and not runtime.registry.has(profile.model_id):
        available = ", ".join(runtime.registry.ids()) or "(无)"
        raise HTTPException(
            status_code=422,
            detail=f"模型 {profile.model_id} 不存在。当前可用模型：{available}",
        )


def _validate_skills(runtime: AppRuntime, profile: AssistantProfile) -> None:









    from ...skill import groups

    if not profile.enabled_skills:
        return

    
    
    
    
    
    
    
    
    
    
    retired = [name for name in profile.enabled_skills if name in groups.RETIRED_COMMON_NAMES]
    if retired:
        logger.info(
            "剔除搭子「%s」可用能力里已失效的历史技能：%s",
            profile.id,
            "、".join(retired),
        )
        profile.enabled_skills = [
            name for name in profile.enabled_skills if name not in groups.RETIRED_COMMON_NAMES
        ]

    
    
    
    try:
        xjx.reject_reserved_skill_names(profile.enabled_skills)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    
    
    
    exclusive = [name for name in profile.enabled_skills if groups.is_exclusive(name)]
    if exclusive:
        raise HTTPException(
            status_code=422,
            detail=(
                f"专属技能不能写进可用能力：{'、'.join(exclusive)} —— "
                "它们按搭子归属自动生效，不需要也不能手动添加。"
            ),
        )


def _validate_voice(runtime: AppRuntime, profile: AssistantProfile) -> None:











    words = [word.strip() for word in (profile.voice.wake_words or []) if word.strip()]
    if not words:
        raise HTTPException(status_code=422, detail="唤醒词不能为空，否则这个搭子喊不醒。")

    for other in runtime.assistants.sorted():
        if other.id == profile.id:
            continue
        clash = sorted(set(words) & {w.strip() for w in (other.voice.wake_words or []) if w.strip()})
        if clash:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"唤醒词「{'、'.join(clash)}」和搭子"
                    f"「{other.nickname or other.name}」重复了，换一个 —— "
                    "两个搭子用同一个词的话，喊谁醒谁只能靠运气。"
                ),
            )
    
    
    
    known = known_skill_names(runtime)
    unknown = [name for name in profile.enabled_skills if name not in known]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                f"技能不存在：{', '.join(unknown)}。"
                "如果这是 MCP 工具，请先连接对应的 MCP 服务。"
            ),
        )


def _payload(runtime: AppRuntime, profile: AssistantProfile) -> dict[str, Any]:

    data = profile.to_dict()
    
    
    
    
    known = known_skill_names(runtime)
    
    
    
    
    
    
    
    from ...skill import groups

    sources = runtime.skills.source_map()
    
    
    
    
    
    effective = [
        name
        for name in profile.enabled_skills
        if name not in sources
        or groups.bucket_of(name, sources[name])
        in (groups.BUCKET_COMMON, groups.BUCKET_MINE)
    ]
    if len(effective) != len(profile.enabled_skills):
        data["enabled_skills"] = effective
        
        data["restricts_skills"] = bool(effective)
    
    data["unavailable_skills"] = [name for name in effective if name not in known]
    
    
    data.update(locked_builtins.lock_payload(profile.id))
    return data


def _upload_name(file: UploadFile) -> str:

    raw = (file.filename or "package").replace("\\", "/").rsplit("/", 1)[-1]
    return raw.rsplit(".", 1)[0] or "package"











@router.post("/import")
async def import_buddy(
    request: Request,
    package: UploadFile = File(...),  
) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    payload = await package.read()
    name = _upload_name(package)
    
    try:
        parsed = await asyncio.to_thread(parse_buddy_package, payload, name)
    except TransferError as exc:
        
        
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return await apply_buddy(runtime, parsed)
    except TransferError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/import-group")
async def import_buddy_group(
    request: Request,
    package: UploadFile = File(...),  
) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    payload = await package.read()
    name = _upload_name(package)
    try:
        parsed = await asyncio.to_thread(parse_group_package, payload, name)
    except TransferError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return await apply_buddy_group(runtime, parsed)
    except TransferError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("")
async def list_assistants(request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    config = runtime.assistants
    return {
        "assistants": [_payload(runtime, item) for item in config.sorted()],
        "default_assistant": config.default_assistant or DEFAULT_ASSISTANT_ID,
        
        
        
        
        
        "legacy_ids": dict(RENAMED_BUILTIN_IDS),
    }


@router.post("")
async def create_assistant(payload: AssistantProfile, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    if runtime.assistants.get(payload.id) is not None:
        raise HTTPException(status_code=409, detail=f"助手 id「{payload.id}」已存在。")

    _validate_model(runtime, payload)
    _validate_skills(runtime, payload)
    _validate_voice(runtime, payload)

    
    profile = payload.model_copy(update={"builtin": False})

    
    
    
    _validate_voice(runtime, profile)
    config = runtime.assistants.model_copy(deep=True)
    config.upsert(profile)
    runtime.save_assistants(config)

    
    
    _seed_default_soul(runtime, profile)
    
    
    _seed_default_rules(runtime, profile)
    await runtime.audit.op(
        kind="assistant",
        action="create",
        actor_id=profile.id,
        target=profile.id,
        detail=f"新建搭子「{profile.nickname or profile.name}」",
    )
    return _payload(runtime, profile)


def _seed_default_soul(runtime: AppRuntime, profile: AssistantProfile) -> None:

    name = profile.nickname.strip() or profile.name.strip()
    content = (
        f"# SOUL\n\n你是 {name}。\n"
        "这里写你的说话方式与性格：语气、在意什么、怎么接话。\n"
    )
    try:
        write_file(runtime.paths, profile.id, SOUL_FILE, content)
    except ValueError as exc:
        
        logger.warning("写入初始 SOUL 失败 %s: %s", profile.id, exc)


def _seed_default_rules(runtime: AppRuntime, profile: AssistantProfile) -> None:









    name = profile.nickname.strip() or profile.name.strip()
    try:
        if read_file(runtime.paths, profile.id, RULES_FILE).strip():
            return
        write_file(runtime.paths, profile.id, RULES_FILE, evolution.evolution_rule(name))
    except ValueError as exc:
        
        logger.warning("写入初始 RULES 失败 %s: %s", profile.id, exc)


@router.get("/{assistant_id}")
async def get_assistant(assistant_id: str, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    profile = runtime.assistants.get(assistant_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"助手「{assistant_id}」不存在")
    return _payload(runtime, profile)


@router.put("/{assistant_id}")
async def update_assistant(
    assistant_id: str, payload: AssistantProfile, request: Request
) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    existing = runtime.assistants.get(assistant_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"助手「{assistant_id}」不存在")
    if payload.id != assistant_id:
        raise HTTPException(status_code=422, detail="路径中的助手 id 与请求体不一致。")

    _validate_model(runtime, payload)
    _validate_skills(runtime, payload)
    _validate_voice(runtime, payload)

    
    
    profile = payload.model_copy(update={"builtin": existing.builtin})

    
    
    
    
    
    
    try:
        locked_builtins.ensure_mutable(
            assistant_id, changes=locked_builtins.changed_fields(existing, profile)
        )
    except locked_builtins.LockedBuiltinError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    config = runtime.assistants.model_copy(deep=True)
    config.upsert(profile)
    runtime.save_assistants(config)
    await runtime.audit.op(
        kind="assistant",
        action="update",
        actor_id=assistant_id,
        target=assistant_id,
        detail=f"修改搭子「{profile.nickname or profile.name}」的配置",
    )
    return _payload(runtime, profile)


@router.delete("/{assistant_id}")
async def delete_assistant(assistant_id: str, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    
    
    
    
    
    try:
        report = lifecycle.delete_assistant(runtime, assistant_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"助手「{assistant_id}」不存在") from None
    except locked_builtins.LockedBuiltinError as exc:
        
        
        
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await runtime.audit.op(
        kind="assistant",
        action="delete",
        actor_id=assistant_id,
        target=assistant_id,
        detail=lifecycle.describe_report(report),
    )
    return {"ok": True, **report}





class PersonaFileWrite(BaseModel):
    content: str = ""


@router.get("/{assistant_id}/persona-files")
async def list_persona_files(assistant_id: str, request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    if runtime.assistants.get(assistant_id) is None:
        raise HTTPException(status_code=404, detail=f"助手「{assistant_id}」不存在")
    return {"files": list_files(runtime.paths, assistant_id)}


@router.put("/{assistant_id}/persona-files/{name}")
async def write_persona_file(
    assistant_id: str, name: str, payload: PersonaFileWrite, request: Request
) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    if runtime.assistants.get(assistant_id) is None:
        raise HTTPException(status_code=404, detail=f"助手「{assistant_id}」不存在")
    
    
    
    
    try:
        locked_builtins.ensure_persona_writable(assistant_id, name)
    except locked_builtins.LockedBuiltinError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        write_file(runtime.paths, assistant_id, name, payload.content)
    except ValueError as exc:
        
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"files": list_files(runtime.paths, assistant_id)}







UNLOCK_CONFIRM_TEXT = "解除人格锁"


class PersonaLockPayload(BaseModel):
    action: Literal["set", "clear", "verify"]
    
    password: str = ""
    
    current: str = ""
    confirm: str = ""


@router.post("/{assistant_id}/persona-lock")
async def persona_lock(
    assistant_id: str, payload: PersonaLockPayload, request: Request
) -> dict[str, Any]:








    runtime: AppRuntime = get_runtime(request)
    if runtime.assistants.get(assistant_id) is None:
        raise HTTPException(status_code=404, detail=f"助手「{assistant_id}」不存在")

    config = runtime.assistants.model_copy(deep=True)
    target = config.get(assistant_id)
    if target is None:  
        raise HTTPException(status_code=404, detail=f"助手「{assistant_id}」不存在")

    if payload.action == "verify":
        return {"ok": target.verify_persona_password(payload.password), "locked": bool(target.persona_password_hash)}

    if payload.action == "clear":
        if payload.confirm.strip() != UNLOCK_CONFIRM_TEXT:
            raise HTTPException(
                status_code=400,
                detail=f"请先在确认框里输入「{UNLOCK_CONFIRM_TEXT}」再清除。",
            )
        target.set_persona_password("")
        runtime.save_assistants(config)
        logger.info("已清除助手的人格锁：%s", assistant_id)
        return {"ok": True, "locked": False}

    
    if target.persona_password_hash and not target.verify_persona_password(payload.current):
        raise HTTPException(status_code=403, detail="当前密码不对，无法修改。")
    if not payload.password:
        raise HTTPException(status_code=400, detail="新密码不能为空。")
    target.set_persona_password(payload.password)
    runtime.save_assistants(config)
    logger.info("已设置助手的人格锁：%s", assistant_id)
    return {"ok": True, "locked": True}

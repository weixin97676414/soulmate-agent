













































from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from ...agent.group_discussion import (
    discussion_source as _discussion_source,
)





from ...agent.group_domain import (
    ordered_members as _ordered_members,
)
from ...agent.group_domain import (
    persisting_stream as _persisting_stream,
)
from ...agent.group_domain import (
    render_history as _render_history,
)
from ...agent.group_domain import (
    resolve_thread as _resolve_thread,
)
from ...agent.group_domain import (
    restore_history as _restore_history,
)
from ...agent.group_domain import (
    say as _say,
)
from ...agent.orchestrator import AVATAR_MAX_BYTES
from ...config.schemas import ConfirmMode, GroupProfile
from ...llm.base import Message
from ...skill.custom import persona_with_instructions
from ...skill.package import slugify
from ...storage import images
from ..deps import get_runtime
from ..runtime import AppRuntime
from ..sse import format_sse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["groups"], prefix="/v1/groups")




def _slugify(text: str) -> str:






    return slugify(text, fallback="group")



_sse = format_sse


async def _reply_once(
    runtime: AppRuntime, group: GroupProfile, assistant: Any, history: list[dict[str, str]]
) -> str:
    model_id = assistant.model_id or runtime.config.models.default_model
    llm = runtime.registry.get(model_id or None)
    persona = persona_with_instructions(
        runtime, assistant.id, list(assistant.enabled_skills) or None
    )
    context = _render_history(history, group.name, assistant.name)
    
    
    messages = [Message(role="user", content=context)]
    if persona:
        messages.insert(0, Message(role="system", content=persona))
    response = await llm.chat(
        messages,
        temperature=assistant.temperature if assistant.temperature is not None else 0.7,
    )
    return (response.content or "").strip()





async def _normalize_group_avatar(runtime: AppRuntime, raw: str | None) -> str:










    text = (raw or "").strip()
    if not text:
        return ""
    
    
    if text.startswith("data:"):
        if len(text) > AVATAR_MAX_BYTES * 2:
            
            raise HTTPException(
                status_code=400,
                detail=(
                    f"这张头像太大了（约 {len(text) // 1024}KB），请换一张小一点的图。"
                    "群头像每次启动都会被读进配置，所以刻意卡得比聊天附图紧。"
                ),
            )
        return text
    try:
        _, data_url = await images.to_data_url(
            text, max_bytes=AVATAR_MAX_BYTES, workspace=runtime.workspace
        )
    except images.ImageSourceError as exc:
        
        raise HTTPException(status_code=400, detail=f"设置群头像失败：{exc}") from exc
    return data_url


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=48)
    member_assistant_ids: list[str] = Field(default_factory=list)
    speaking_order: list[str] = Field(default_factory=list)
    
    avatar: str = ""


class GroupChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


class GroupDiscussRequest(BaseModel):
    topic: str = Field("", description="讨论话题；留空表示继续上一个话题")
    
    
    attachments: list[str] = Field(default_factory=list, description="工作区文件 id（附件）")
    images: list[str] = Field(default_factory=list, description="工作区文件 id（图片）")
    
    
    
    
    
    thread_id: str = Field("", description="目标对话 id；留空则用最近一条（无则新建）")


class GroupThreadCreate(BaseModel):
    title: str = Field("", max_length=48, description="对话标题；留空用默认名")


class GroupThreadRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=48)


class GroupUpdate(BaseModel):








    name: str | None = Field(None, min_length=1, max_length=48)
    
    
    member_assistant_ids: list[str] | None = None
    speaking_order: list[str] | None = None
    
    
    
    avatar: str | None = None
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    confirm_mode: ConfirmMode | None = None
    
    
    
    
    
    
    
    
    wake_words: list[str] | None = None

    @field_validator("reasoning_effort", "confirm_mode", mode="before")
    @classmethod
    def _blank_means_default(cls, value: Any) -> Any:





        if isinstance(value, str) and not value.strip():
            return None
        return value





@router.get("")
async def list_groups(request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    return {"groups": [item.model_dump(mode="json") for item in runtime.groups.groups]}


@router.post("")
async def create_group(payload: GroupCreate, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    for assistant_id in payload.member_assistant_ids:
        if runtime.assistants.get(assistant_id) is None:
            raise HTTPException(status_code=400, detail=f"搭子「{assistant_id}」不存在")

    group = GroupProfile(
        id=f"{_slugify(payload.name)}-{uuid.uuid4().hex[:6]}",
        name=payload.name,
        member_assistant_ids=payload.member_assistant_ids,
        speaking_order=payload.speaking_order,
        
        avatar=await _normalize_group_avatar(runtime, payload.avatar),
    )
    config = runtime.groups.model_copy(deep=True)
    config.upsert(group)
    runtime.groups = runtime.config_store.save_groups(config)
    await runtime.audit.op(
        kind="group",
        action="create",
        target=group.id,
        detail=f"新建群「{group.name}」（成员：{'、'.join(group.member_assistant_ids)}）",
    )
    return group.model_dump(mode="json")


@router.patch("/{group_id}")
async def update_group(group_id: str, payload: GroupUpdate, request: Request) -> dict[str, Any]:







    runtime: AppRuntime = get_runtime(request)
    existing = runtime.groups.get(group_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")

    
    changes: dict[str, Any] = {}
    if "name" in payload.model_fields_set:
        changes["name"] = payload.name or existing.name
    if "member_assistant_ids" in payload.model_fields_set and payload.member_assistant_ids is not None:
        
        
        
        
        
        
        
        members: list[str] = []
        for assistant_id in payload.member_assistant_ids:
            if runtime.assistants.get(assistant_id) is None:
                raise HTTPException(status_code=400, detail=f"搭子「{assistant_id}」不存在")
            if assistant_id not in members:
                members.append(assistant_id)
        changes["member_assistant_ids"] = members
        
        order = [item for item in existing.speaking_order if item in members]
        changes["speaking_order"] = order + [item for item in members if item not in order]
        
        
        
        for role in ("reviewer", "advisor"):
            field = f"{role}_id"
            confirmed = (getattr(existing, field) or "").strip()
            if confirmed and confirmed not in members:
                changes[field] = ""
    if "speaking_order" in payload.model_fields_set:
        
        current_members = changes.get("member_assistant_ids") or list(
            existing.member_assistant_ids
        )
        changes["speaking_order"] = [
            item for item in (payload.speaking_order or []) if item in current_members
        ]
    if "reasoning_effort" in payload.model_fields_set:
        changes["reasoning_effort"] = payload.reasoning_effort
    if "confirm_mode" in payload.model_fields_set:
        changes["confirm_mode"] = payload.confirm_mode
    if "avatar" in payload.model_fields_set:
        
        
        changes["avatar"] = payload.avatar
    if "wake_words" in payload.model_fields_set and payload.wake_words is not None:
        
        
        
        
        
        
        
        
        
        cleaned: list[str] = []
        for word in payload.wake_words:
            text = word.strip()
            if text and text not in cleaned:
                cleaned.append(text)
        changes["wake_words"] = cleaned

    if not changes:
        return existing.model_dump(mode="json")

    if "avatar" in changes:
        
        
        changes["avatar"] = await _normalize_group_avatar(runtime, changes["avatar"])

    group = existing.model_copy(update=changes)
    config = runtime.groups.model_copy(deep=True)
    config.upsert(group)
    runtime.groups = runtime.config_store.save_groups(config)
    logger.info("群设置已更新 group=%s 变更=%s", group_id, sorted(changes))
    await runtime.audit.op(
        kind="group",
        action="update",
        target=group_id,
        detail=f"修改群设置「{group.name}」：{('、'.join(sorted(changes))) or '无字段变化'}",
    )
    return group.model_dump(mode="json")


@router.delete("/{group_id}")
async def delete_group(group_id: str, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    config = runtime.groups.model_copy(deep=True)
    if not config.remove(group_id):
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    runtime.groups = runtime.config_store.save_groups(config)
    
    
    runtime._group_history = {
        key: value for key, value in runtime._group_history.items() if key[0] != group_id
    }
    
    if runtime.db_ready:
        try:
            await runtime.group_event_repo.delete_group(group_id)
            await runtime.group_thread_repo.delete_group(group_id)
        except Exception as exc:  
            logger.warning("清理群聊记录失败 group=%s: %s", group_id, exc)
    await runtime.audit.op(
        kind="group", action="delete", target=group_id, detail="删除群（连带清掉该群的聊天记录）"
    )
    return {"ok": True}







@router.post("/{group_id}/stop")
async def stop_group_discussion(group_id: str, request: Request) -> dict[str, Any]:






    runtime: AppRuntime = get_runtime(request)
    if runtime.groups.get(group_id) is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    return await runtime.orchestrator.stop_discussion(group_id)


@router.post("/{group_id}/discuss")
async def discuss(group_id: str, payload: GroupDiscussRequest, request: Request) -> Any:

    runtime: AppRuntime = get_runtime(request)
    group = runtime.groups.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    members = _ordered_members(runtime, group)
    if not members:
        raise HTTPException(status_code=400, detail="这个群还没有成员，先拉几个搭子进来。")

    
    thread_id = await _resolve_thread(runtime, group_id, payload.thread_id)
    
    await _restore_history(runtime, group_id, thread_id)
    
    if runtime.db_ready:
        try:
            await runtime.group_thread_repo.touch(group_id, thread_id)
        except Exception as exc:  
            logger.warning("群对话时间戳更新失败 group=%s thread=%s: %s", group_id, thread_id, exc)

    
    
    from .chat import build_attachment_block, build_image_parts

    attachment_block = await build_attachment_block(runtime, payload.attachments or [])
    images = await build_image_parts(runtime, payload.images or [])

    return StreamingResponse(
        _persisting_stream(
            runtime,
            group_id,
            thread_id,
            _discussion_source(
                runtime,
                group,
                members,
                payload.topic,
                thread_id,
                attachment_block=attachment_block or "",
                images=images,
            ),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/{group_id}/messages")
async def list_group_messages(
    group_id: str, request: Request, thread_id: str = ""
) -> dict[str, Any]:








    runtime: AppRuntime = get_runtime(request)
    if runtime.groups.get(group_id) is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    if not runtime.db_ready:
        
        return {"events": [], "persistent": False, "thread_id": thread_id}
    resolved = await _resolve_thread(runtime, group_id, thread_id)
    events = await runtime.group_event_repo.list_events(group_id, resolved)
    return {"events": events, "persistent": True, "thread_id": resolved}


@router.delete("/{group_id}/messages")
async def clear_group_messages(
    group_id: str, request: Request, thread_id: str = ""
) -> dict[str, Any]:





    runtime: AppRuntime = get_runtime(request)
    if runtime.groups.get(group_id) is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    resolved = await _resolve_thread(runtime, group_id, thread_id)
    removed = 0
    if runtime.db_ready:
        removed = await runtime.group_event_repo.clear(group_id, resolved)
    
    runtime._group_history.pop((group_id, resolved), None)
    return {"ok": True, "removed": removed, "thread_id": resolved}





@router.get("/{group_id}/threads")
async def list_group_threads(group_id: str, request: Request) -> dict[str, Any]:






    runtime: AppRuntime = get_runtime(request)
    if runtime.groups.get(group_id) is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    if not runtime.db_ready:
        return {"threads": [], "persistent": False}
    threads = await runtime.group_thread_repo.list_threads(group_id)
    if not threads:
        threads = [await runtime.group_thread_repo.create(group_id)]
    return {"threads": threads, "persistent": True}


@router.post("/{group_id}/threads")
async def create_group_thread(
    group_id: str, payload: GroupThreadCreate, request: Request
) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    if runtime.groups.get(group_id) is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    if not runtime.db_ready:
        raise HTTPException(status_code=503, detail="当前是内存模式，无法新建对话")
    return await runtime.group_thread_repo.create(group_id, payload.title or None)


@router.patch("/{group_id}/threads/{thread_id}")
async def rename_group_thread(
    group_id: str, thread_id: str, payload: GroupThreadRename, request: Request
) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    if runtime.groups.get(group_id) is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    if not runtime.db_ready:
        raise HTTPException(status_code=503, detail="当前是内存模式，无法改名")
    if not await runtime.group_thread_repo.rename(group_id, thread_id, payload.title):
        raise HTTPException(status_code=404, detail=f"对话「{thread_id}」不存在")
    thread = await runtime.group_thread_repo.get(group_id, thread_id)
    if thread is None:  
        raise HTTPException(status_code=404, detail=f"对话「{thread_id}」不存在")
    return thread


@router.delete("/{group_id}/threads/{thread_id}")
async def delete_group_thread(
    group_id: str, thread_id: str, request: Request
) -> dict[str, Any]:





    runtime: AppRuntime = get_runtime(request)
    if runtime.groups.get(group_id) is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    if not runtime.db_ready:
        raise HTTPException(status_code=503, detail="当前是内存模式，无法删除对话")
    if not await runtime.group_thread_repo.delete(group_id, thread_id):
        raise HTTPException(status_code=404, detail=f"对话「{thread_id}」不存在")
    runtime._group_history.pop((group_id, thread_id), None)
    await runtime.audit.op(
        kind="group", action="delete", target=group_id, detail=f"删除群对话「{thread_id}」"
    )
    return {"ok": True}





@router.post("/{group_id}/chat")
async def group_chat(group_id: str, payload: GroupChatRequest, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    group = runtime.groups.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    if not group.member_assistant_ids:
        raise HTTPException(status_code=400, detail="这个群还没有成员，先拉几个搭子进来。")

    
    
    thread_id = await _resolve_thread(runtime, group_id, "")
    await _restore_history(runtime, group_id, thread_id)
    history = runtime._group_history.setdefault((group_id, thread_id), [])
    _say(history, role="user", name="用户", content=payload.message)

    replies: list[dict[str, str]] = []
    for member_id in group.member_assistant_ids:
        assistant = runtime.assistants.get(member_id)
        if assistant is None:
            continue
        try:
            reply = await _reply_once(runtime, group, assistant, history)
        except Exception as exc:  
            replies.append(
                {"assistant_id": member_id, "name": assistant.name, "content": "", "error": str(exc)}
            )
            continue
        if not reply:
            continue
        _say(history, role="assistant", name=assistant.name, content=reply)
        replies.append({"assistant_id": member_id, "name": assistant.name, "content": reply})

    return {"replies": replies}

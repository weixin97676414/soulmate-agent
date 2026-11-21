















from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...feishu import config as feishu_config
from ...feishu.client import FeishuAPIError, client_for
from ...feishu.config import FeishuBot
from ..deps import get_runtime
from ..runtime import AppRuntime

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feishu"], prefix="/v1/feishu")









class FeishuBotCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=48, description="机器人名称（用户起的名）")
    app_id: str = Field(..., min_length=1, max_length=128)
    app_secret: str = Field("", description="App Secret；新增强烈建议填上")
    assistant_id: str = Field(..., min_length=1, max_length=64, description="绑定哪个搭子")
    enabled: bool = True
    group_policy: Literal["mention", "all"] = "mention"
    sync_reply_to_feishu: bool = True


class FeishuBotUpdate(BaseModel):







    name: str | None = Field(None, min_length=1, max_length=48)
    app_id: str | None = Field(None, min_length=1, max_length=128)
    app_secret: str | None = None
    assistant_id: str | None = Field(None, min_length=1, max_length=64)
    enabled: bool | None = None
    group_policy: Literal["mention", "all"] | None = None
    sync_reply_to_feishu: bool | None = None


class FeishuTestPayload(BaseModel):






    bot_id: str = ""
    app_id: str = ""
    app_secret: str = ""





def _require_bot(runtime: AppRuntime, bot_id: str) -> FeishuBot:
    bot = feishu_config.load_bots(runtime.config_store).get(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail=f"飞书机器人「{bot_id}」不存在")
    return bot


def _validate_assistant(runtime: AppRuntime, assistant_id: str) -> None:

    if runtime.assistants.get(assistant_id) is None:
        raise HTTPException(
            status_code=400, detail=f"搭子「{assistant_id}」不存在（id 要用搭子清单里的）"
        )


def _validate_app_id_unique(runtime: AppRuntime, app_id: str, *, exclude: str = "") -> None:

    for item in feishu_config.load_bots(runtime.config_store).bots:
        if item.app_id == app_id and item.id != exclude:
            raise HTTPException(
                status_code=400,
                detail=f"App ID 已被「{item.name}」使用；同一个飞书应用只能接一次",
            )


def _views(runtime: AppRuntime) -> list[dict[str, Any]]:

    secrets = feishu_config.load_secrets(runtime.paths)
    return [
        feishu_config.masked(bot, has_secret=bool(secrets.get(bot.id)))
        for bot in feishu_config.load_bots(runtime.config_store).bots
    ]


async def _fetch_bot_info(app_id: str, app_secret: str) -> dict[str, str]:






    if not app_id.strip() or not app_secret.strip():
        raise HTTPException(status_code=400, detail="App ID 与 App Secret 都必须填。")

    
    
    
    try:
        return await client_for(app_id.strip(), app_secret.strip()).bot_info()
    except FeishuAPIError as exc:
        message = str(exc)
        
        status = 502 if message.startswith("连接飞书失败") else 400
        raise HTTPException(status_code=status, detail=message) from exc





@router.get("/bots")
async def list_bots(request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    return {"bots": _views(runtime)}


@router.post("/bots")
async def create_bot(payload: FeishuBotCreate, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    _validate_assistant(runtime, payload.assistant_id)
    _validate_unique_name(runtime, payload.name)
    _validate_app_id_unique(runtime, payload.app_id.strip())

    bot = FeishuBot(
        id=uuid.uuid4().hex[:12],
        name=payload.name.strip(),
        app_id=payload.app_id.strip(),
        assistant_id=payload.assistant_id.strip(),
        enabled=payload.enabled,
        group_policy=payload.group_policy,
        sync_reply_to_feishu=payload.sync_reply_to_feishu,
    )
    config = feishu_config.load_bots(runtime.config_store)
    config.upsert(bot)
    feishu_config.save_bots(runtime.config_store, config)
    feishu_config.set_secret(runtime.paths, bot.id, payload.app_secret.strip())

    await runtime.audit.op(
        kind="feishu",
        action="create",
        target=bot.id,
        detail=f"新增飞书机器人「{bot.name}」（绑定 {runtime.assistants.get(bot.assistant_id).name if runtime.assistants.get(bot.assistant_id) else bot.assistant_id}）",
    )
    await _notify(runtime, bot.id)
    return {"bot": feishu_config.masked(bot, has_secret=bool(payload.app_secret.strip()))}


@router.patch("/bots/{bot_id}")
async def update_bot(bot_id: str, payload: FeishuBotUpdate, request: Request) -> dict[str, Any]:

    runtime: AppRuntime = get_runtime(request)
    bot = _require_bot(runtime, bot_id)

    changes: dict[str, Any] = {}
    if payload.name is not None:
        _validate_unique_name(runtime, payload.name, exclude=bot_id)
        changes["name"] = payload.name.strip()
    if payload.app_id is not None:
        _validate_app_id_unique(runtime, payload.app_id.strip(), exclude=bot_id)
        changes["app_id"] = payload.app_id.strip()
    if payload.assistant_id is not None:
        _validate_assistant(runtime, payload.assistant_id)
        changes["assistant_id"] = payload.assistant_id.strip()
    if payload.enabled is not None:
        changes["enabled"] = payload.enabled
    if payload.group_policy is not None:
        changes["group_policy"] = payload.group_policy
    if payload.sync_reply_to_feishu is not None:
        changes["sync_reply_to_feishu"] = payload.sync_reply_to_feishu

    updated = bot.model_copy(update=changes) if changes else bot
    config = feishu_config.load_bots(runtime.config_store)
    config.upsert(updated)
    feishu_config.save_bots(runtime.config_store, config)

    if payload.app_secret is not None:
        feishu_config.set_secret(runtime.paths, bot_id, payload.app_secret.strip())

    await runtime.audit.op(
        kind="feishu",
        action="update",
        target=bot_id,
        detail=f"更新飞书机器人「{updated.name}」：{', '.join(changes) or '仅凭据'}",
    )
    await _notify(runtime, bot_id)
    has_secret = bool(feishu_config.get_secret(runtime.paths, bot_id))
    return {"bot": feishu_config.masked(updated, has_secret=has_secret)}


@router.delete("/bots/{bot_id}")
async def delete_bot(bot_id: str, request: Request) -> dict[str, Any]:





    runtime: AppRuntime = get_runtime(request)
    bot = _require_bot(runtime, bot_id)
    config = feishu_config.load_bots(runtime.config_store)
    config.remove(bot_id)
    feishu_config.save_bots(runtime.config_store, config)
    feishu_config.drop_secret(runtime.paths, bot_id)

    await runtime.audit.op(
        kind="feishu",
        action="delete",
        target=bot_id,
        detail=f"删除飞书机器人「{bot.name}」（已有的飞书会话与聊天记录保留）",
    )
    await _notify(runtime, bot_id)
    return {"ok": True}


@router.post("/test")
async def test_connection(payload: FeishuTestPayload, request: Request) -> dict[str, Any]:





    runtime: AppRuntime = get_runtime(request)

    app_id = payload.app_id.strip()
    app_secret = payload.app_secret.strip()
    if payload.bot_id and (not app_id or not app_secret):
        saved = feishu_config.load_bots(runtime.config_store).get(payload.bot_id)
        stored_secret = feishu_config.get_secret(runtime.paths, payload.bot_id)
        app_id = app_id or (saved.app_id if saved else "")
        app_secret = app_secret or stored_secret

    info = await _fetch_bot_info(app_id, app_secret)
    return {"ok": True, **info}


@router.get("/status")
async def status(request: Request) -> dict[str, Any]:





    runtime: AppRuntime = get_runtime(request)
    bridge = getattr(runtime, "feishu", None)
    if bridge is None:
        return {
            "bridge": "not_started",
            "bots": [
                {"id": bot.id, "state": "not_started", "error": ""}
                for bot in feishu_config.load_bots(runtime.config_store).bots
            ],
        }
    return {"bridge": "running", "bots": bridge.statuses()}





def _validate_unique_name(runtime: AppRuntime, name: str, *, exclude: str = "") -> None:

    cleaned = name.strip()
    for item in feishu_config.load_bots(runtime.config_store).bots:
        if item.name == cleaned and item.id != exclude:
            raise HTTPException(status_code=400, detail=f"已经有一个叫「{cleaned}」的机器人了")


async def _notify(runtime: AppRuntime, bot_id: str = "") -> None:






    runtime.events.publish("feishu_changed")
    handler = getattr(runtime, "feishu_handler", None)
    if handler is not None and bot_id:
        handler.forget_bot(bot_id)
    bridge = getattr(runtime, "feishu", None)
    if bridge is not None:
        bridge.reload()

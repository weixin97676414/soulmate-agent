





























from __future__ import annotations

import json
import logging
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

from . import config as feishu_config
from .client import FeishuAPIError, client_for, parse_text, strip_mentions
from .turn import TurnFailed, run_turn_silently

if TYPE_CHECKING:  
    from ..config.schemas import FeishuBot
    from ..server.runtime import AppRuntime

logger = logging.getLogger(__name__)



_SEEN_LIMIT = 2000


_FALLBACK_TITLE = "飞书会话"


class FeishuHandler:


    def __init__(self, runtime: AppRuntime) -> None:
        self._runtime = runtime
        
        self._seen: OrderedDict[str, None] = OrderedDict()
        
        self._open_ids: dict[str, str] = {}
        
        self._clients: dict[str, Any] = {}

    
    
    
    async def handle(self, bot: FeishuBot, payload: dict[str, Any]) -> None:

        try:
            await self._handle(bot, payload)
        except Exception as exc:  
            logger.exception("处理飞书消息失败（机器人 %s）：%s", bot.id, exc)

    async def _handle(self, bot: FeishuBot, payload: dict[str, Any]) -> None:
        header = payload.get("header") or {}
        event = payload.get("event") or {}
        if header.get("event_type") and header["event_type"] != "im.message.receive_v1":
            return

        message = event.get("message") or {}
        sender = event.get("sender") or {}
        event_id = str(header.get("event_id") or "")
        message_id = str(message.get("message_id") or "")

        
        if not self._remember([event_id, message_id]):
            logger.debug("飞书事件重复，已忽略：event=%s msg=%s", event_id, message_id)
            return

        
        sender_type = str(sender.get("sender_type") or "")
        if sender_type and sender_type != "user":
            return

        chat_id = str(message.get("chat_id") or "")
        chat_type = str(message.get("chat_type") or "")
        mentions = message.get("mentions") or []
        if not chat_id:
            return

        if chat_type == "group" and bot.group_policy == "mention":
            open_id = await self._bot_open_id(bot)
            if not open_id:
                
                
                logger.warning(
                    "机器人 %s 拿不到自身 open_id，群聊消息一律忽略（%s）", bot.id, chat_id
                )
                return
            if not _mentions_bot(mentions, open_id):
                
                
                logger.info(
                    "群消息没有 @ 机器人，按 group_policy=mention 忽略（chat=%s）", chat_id
                )
                return

        raw_text = parse_text(str(message.get("content") or ""))
        text = strip_mentions(raw_text, mentions if isinstance(mentions, list) else [])
        if not text:
            
            
            msg_type = str(message.get("message_type") or "")
            if msg_type not in ("image", "file"):
                logger.info("飞书消息不含可用内容（类型 %s），忽略", msg_type)
                return
            text = "（发来一个附件，请查看附件）"

        session = await self._resolve_session(bot, chat_id)
        if session is None:
            return

        
        
        file_ids = await self._collect_attachments(bot, message, session)

        
        
        self._runtime.events.publish(
            "session_message", session_id=session.id, assistant_id=bot.assistant_id
        )

        
        await self._run_and_reply(bot, chat_id, session, text, file_ids)

    
    
    
    async def _collect_attachments(
        self, bot: FeishuBot, message: dict[str, Any], session: Any
    ) -> list[str]:






        msg_type = str(message.get("message_type") or "")
        message_id = str(message.get("message_id") or "")
        if msg_type not in ("image", "file") or not message_id:
            return []

        try:
            content = json.loads(str(message.get("content") or "{}"))
        except (ValueError, TypeError):
            return []
        if not isinstance(content, dict):
            return []

        client = self._client(bot)
        if client is None:
            return []

        if msg_type == "image":
            file_key = str(content.get("image_key") or "")
            if not file_key:
                return []
            return await self._save(client, message_id, file_key, "image", "飞书图片.jpg", session)

        file_key = str(content.get("file_key") or "")
        if not file_key:
            return []
        name = str(content.get("file_name") or "飞书文件")
        return await self._save(client, message_id, file_key, "file", name, session)

    async def _save(
        self,
        client: Any,
        message_id: str,
        file_key: str,
        kind: str,
        filename: str,
        session: Any,
    ) -> list[str]:

        try:
            raw = await client.download_resource(message_id, file_key, kind=kind)
        except FeishuAPIError as exc:
            logger.warning("下载飞书%s失败（%s）：%s", "图片" if kind == "image" else "文件", file_key, exc)
            return []
        if not raw:
            return []
        try:
            record = await self._runtime.workspace.save_upload(
                filename=filename, content=raw, session_id=session.id
            )
        except Exception as exc:  
            logger.warning("飞书附件存进工作区失败（%s）：%s", filename, exc)
            return []
        logger.info("飞书附件已入库：%s（%s 字节）", record.original_name, record.size)
        return [record.id]

    
    
    
    async def _resolve_session(self, bot: FeishuBot, chat_id: str) -> Any:

        repo = getattr(self._runtime, "sessions_repo", None)
        record = None
        if repo is not None and self._runtime.db_ready:
            record = await repo.find_by_external("feishu", chat_id, bot.assistant_id)
        if record is not None:
            return await self._runtime.sessions.get(record.id)

        title = await self._chat_title(bot, chat_id)
        return await self._runtime.sessions.create(
            title=title,
            assistant_id=bot.assistant_id,
            source="feishu",
            external_id=chat_id,
        )

    async def _chat_title(self, bot: FeishuBot, chat_id: str) -> str:

        client = self._client(bot)
        if client is None:
            return _FALLBACK_TITLE
        name = await client.chat_name(chat_id)
        return f"{name}" if name else _FALLBACK_TITLE

    
    
    
    async def _run_and_reply(
        self,
        bot: FeishuBot,
        chat_id: str,
        session: Any,
        text: str,
        file_ids: list[str] | None = None,
    ) -> None:





        try:
            reply = await run_turn_silently(
                self._runtime, session, text, file_ids=file_ids
            )
        except TurnFailed as exc:
            
            await self._reply(bot, chat_id, f"（这轮没跑成：{exc}）")
            return
        except Exception as exc:  
            logger.exception("飞书会话 %s 跑一轮失败：%s", session.id, exc)
            await self._reply(
                bot, chat_id, "（处理时出错了：这轮没能完成，详情可在客户端的日志里查。）"
            )
            return

        await self._reply(bot, chat_id, reply)
        
        
        self._runtime.events.publish(
            "session_message", session_id=session.id, assistant_id=bot.assistant_id
        )

    async def _reply(self, bot: FeishuBot, chat_id: str, text: str) -> None:





        client = self._client(bot)
        if client is None:
            return
        try:
            await client.send_text(chat_id, text)
        except FeishuAPIError as exc:
            logger.warning("回发飞书失败（机器人 %s / %s）：%s", bot.id, chat_id, exc)
            await self._audit(bot, chat_id, str(exc))

    async def _audit(self, bot: FeishuBot, chat_id: str, detail: str) -> None:
        audit = getattr(self._runtime, "audit", None)
        if audit is None:
            return
        try:
            await audit.op(
                kind="feishu",
                action="send_failed",
                target=chat_id,
                detail=f"机器人「{bot.name}」回发失败：{detail[:300]}",
            )
        except Exception:  
            logger.debug("飞书发送失败审计写入失败", exc_info=True)

    
    
    
    def _client(self, bot: FeishuBot) -> Any:

        cached = self._clients.get(bot.id)
        if cached is not None:
            return cached
        secret = feishu_config.get_secret(self._runtime.paths, bot.id)
        if not secret:
            logger.warning("机器人 %s 没有 App Secret，无法回复", bot.id)
            return None
        client = client_for(bot.app_id, secret)
        self._clients[bot.id] = client
        return client

    async def _bot_open_id(self, bot: FeishuBot) -> str:

        cached = self._open_ids.get(bot.id)
        if cached:
            return cached
        client = self._client(bot)
        if client is None:
            return ""
        try:
            info = await client.bot_info()
        except FeishuAPIError as exc:
            logger.warning("机器人 %s 取 open_id 失败：%s", bot.id, exc)
            return ""
        open_id = str(info.get("open_id") or "")
        if open_id:
            self._open_ids[bot.id] = open_id
        return open_id

    
    
    
    def _remember(self, keys: list[str]) -> bool:

        cleaned = [key for key in keys if key]
        if not cleaned:
            return True
        if any(key in self._seen for key in cleaned):
            return False
        for key in cleaned:
            self._seen[key] = None
        while len(self._seen) > _SEEN_LIMIT:
            self._seen.popitem(last=False)
        return True

    def forget_bot(self, bot_id: str) -> None:

        self._clients.pop(bot_id, None)
        self._open_ids.pop(bot_id, None)


def _mentions_bot(mentions: Any, open_id: str) -> bool:

    if not isinstance(mentions, list):
        return False
    for item in mentions:
        if not isinstance(item, dict):
            continue
        identity = item.get("id") or {}
        if isinstance(identity, dict) and str(identity.get("open_id") or "") == open_id:
            return True
    return False
























from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from ..utils.http import async_client

logger = logging.getLogger(__name__)


BASE = "https://open.feishu.cn/open-apis"


TIMEOUT = 10.0


_TOKEN_MARGIN = 300



CHUNK_CHARS = 3000


CHUNK_INTERVAL = 0.25


class FeishuAPIError(RuntimeError):
    pass


class FeishuClient:


    def __init__(self, app_id: str, app_secret: str) -> None:
        self._app_id = app_id.strip()
        self._app_secret = app_secret.strip()
        self._token = ""
        self._token_expire_at = 0.0
        
        self._send_lock = asyncio.Lock()

    
    
    
    async def token(self) -> str:

        now = time.time()
        if self._token and now < self._token_expire_at - _TOKEN_MARGIN:
            return self._token
        if not self._app_id or not self._app_secret:
            raise FeishuAPIError("缺少 App ID / App Secret")

        async with async_client(timeout=TIMEOUT, trust_env=False) as client:
            try:
                resp = await client.post(
                    f"{BASE}/auth/v3/tenant_access_token/internal",
                    json={"app_id": self._app_id, "app_secret": self._app_secret},
                )
                data = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise FeishuAPIError(f"连接飞书失败：{exc}") from exc

        if data.get("code") != 0:
            raise FeishuAPIError(f"凭据无效：{data.get('msg') or '未知错误'}")
        token = str(data.get("tenant_access_token") or "")
        if not token:
            raise FeishuAPIError("飞书没有返回 access token")
        self._token = token
        
        self._token_expire_at = now + max(60, int(data.get("expire") or 7200) - 60)
        return token

    
    
    
    async def bot_info(self) -> dict[str, str]:




        token = await self.token()
        async with async_client(timeout=TIMEOUT, trust_env=False) as client:
            try:
                resp = await client.get(
                    f"{BASE}/bot/v3/info",
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise FeishuAPIError(f"查询机器人信息失败：{exc}") from exc

        if data.get("code") != 0:
            raise FeishuAPIError(
                f"凭据可用，但应用还没开通机器人能力（{data.get('msg') or '未知原因'}）"
            )
        bot = data.get("bot") or {}
        return {
            "app_name": str(bot.get("app_name") or ""),
            "open_id": str(bot.get("open_id") or ""),
        }

    async def chat_name(self, chat_id: str) -> str:

        if not chat_id:
            return ""
        try:
            token = await self.token()
        except FeishuAPIError:
            return ""
        async with async_client(timeout=TIMEOUT, trust_env=False) as client:
            try:
                resp = await client.get(
                    f"{BASE}/im/v1/chats/{chat_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = resp.json()
            except (httpx.HTTPError, ValueError):
                return ""
        if data.get("code") != 0:
            return ""
        return str((data.get("data") or {}).get("name") or "")

    
    
    
    async def download_resource(
        self, message_id: str, file_key: str, *, kind: str = "file"
    ) -> bytes:










        token = await self.token()
        async with async_client(timeout=max(TIMEOUT, 30.0), trust_env=False) as client:
            try:
                resp = await client.get(
                    f"{BASE}/im/v1/messages/{message_id}/resources/{file_key}",
                    params={"type": kind},
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError as exc:
                raise FeishuAPIError(f"下载资源失败：{exc}") from exc

        if resp.status_code != 200:
            
            detail = ""
            try:
                detail = str(resp.json().get("msg") or "")
            except ValueError:
                detail = resp.text[:120]
            raise FeishuAPIError(f"下载资源失败（HTTP {resp.status_code}）：{detail}")
        return resp.content

    
    
    
    async def send_text(self, chat_id: str, text: str) -> None:





        content = text.strip()
        if not chat_id or not content:
            return
        chunks = [
            content[index : index + CHUNK_CHARS]
            for index in range(0, len(content), CHUNK_CHARS)
        ]
        
        async with self._send_lock:
            for order, chunk in enumerate(chunks):
                await self._post_text(chat_id, chunk)
                if order < len(chunks) - 1:
                    await asyncio.sleep(CHUNK_INTERVAL)

    async def _post_text(self, chat_id: str, text: str) -> None:
        token = await self.token()
        async with async_client(timeout=TIMEOUT, trust_env=False) as client:
            try:
                resp = await client.post(
                    f"{BASE}/im/v1/messages",
                    params={"receive_id_type": "chat_id"},
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    json={
                        "receive_id": chat_id,
                        "msg_type": "text",
                        "content": _text_content(text),
                    },
                )
                data = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise FeishuAPIError(f"发送消息失败：{exc}") from exc

        if data.get("code") != 0:
            raise FeishuAPIError(f"发送消息失败：{data.get('msg') or data.get('code')}")


def _text_content(text: str) -> str:




    import json

    return json.dumps({"text": text}, ensure_ascii=False)


def client_for(app_id: str, secret: str) -> FeishuClient:

    return FeishuClient(app_id, secret)


def parse_text(content: str) -> str:




    import json

    try:
        data = json.loads(content or "{}")
    except (ValueError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("text") or "")


def strip_mentions(text: str, mentions: list[dict[str, Any]]) -> str:





    cleaned = text
    for item in mentions or []:
        key = str(item.get("key") or "")
        name = str(item.get("name") or "")
        if key and name:
            cleaned = cleaned.replace(key, f"@{name}")
    return cleaned.strip()

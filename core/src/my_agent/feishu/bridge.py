
















from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sys
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from . import config as feishu_config
from .worker import ENV_APP_ID, ENV_APP_SECRET, ENV_BOT_ID

if TYPE_CHECKING:  
    from ..config.schemas import FeishuBot
    from ..server.runtime import AppRuntime

logger = logging.getLogger(__name__)



RESTART_DELAY = 15.0



READY_GRACE = 25.0


MAX_RESTARTS = 5

EventCallback = Callable[["FeishuBot", dict[str, Any]], Awaitable[None]]


def _worker_command() -> list[str]:






    if getattr(sys, "frozen", False):
        return [sys.executable, "--feishu-worker"]
    return [sys.executable, "-m", "my_agent.feishu.worker"]


def _startup_info() -> Any:





    if os.name != "nt":
        return None
    import subprocess

    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return info


class FeishuBridge:


    def __init__(self, runtime: AppRuntime, on_event: EventCallback | None = None) -> None:
        self._runtime = runtime
        self._on_event = on_event
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._states: dict[str, dict[str, str]] = {}
        self._restarts: dict[str, int] = {}
        self._stopping = False

    def set_on_event(self, callback: EventCallback) -> None:





        self._on_event = callback

    
    
    
    async def start(self) -> None:

        self._stopping = False
        for bot in feishu_config.load_bots(self._runtime.config_store).enabled_bots():
            self._spawn(bot)

    async def stop(self) -> None:

        self._stopping = True
        tasks = list(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    def reload(self) -> None:





        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  
            return
        loop.create_task(self._reload_async())

    async def _reload_async(self) -> None:
        desired = {
            bot.id: bot
            for bot in feishu_config.load_bots(self._runtime.config_store).enabled_bots()
        }
        
        for bot_id in list(self._tasks):
            if bot_id not in desired:
                task = self._tasks.pop(bot_id)
                task.cancel()
                self._states.pop(bot_id, None)
                self._restarts.pop(bot_id, None)
        
        for bot_id, bot in desired.items():
            if bot_id not in self._tasks:
                self._spawn(bot)

    
    
    
    def statuses(self) -> list[dict[str, str]]:

        result: list[dict[str, str]] = []
        for bot in feishu_config.load_bots(self._runtime.config_store).bots:
            state = self._states.get(bot.id) or {"state": "disabled" if not bot.enabled else "connecting"}
            result.append({"id": bot.id, **state})
        return result

    def _set_state(self, bot_id: str, state: str, error: str = "") -> None:
        self._states[bot_id] = {"state": state, "error": error}

    async def _watch_first_event(self, bot_id: str) -> None:









        await asyncio.sleep(READY_GRACE)
        state = self._states.get(bot_id, {})
        current = state.get("state")
        if current == "connected":
            self._set_state(
                bot_id,
                "connected",
                "长连接已建立，但还没收到任何消息事件。"
                "若在飞书里发消息没反应，请检查飞书开放平台："
                "① 事件订阅是否选了「使用长连接接收事件」；"
                "② 是否订阅了 im.message.receive_v1；"
                "③ 权限是否已开通，且已**发布新版本**。",
            )
            logger.warning(
                "飞书机器人 %s：长连接已建立，但 %d 秒内未收到任何事件 —— 请检查事件订阅配置",
                bot_id,
                int(READY_GRACE),
            )
        elif current == "connecting":
            self._set_state(
                bot_id,
                "error",
                "子进程起来了，但没能建立长连接（具体报错见日志里的 lark 一行）",
            )

    
    
    
    def _spawn(self, bot: FeishuBot) -> None:
        secret = feishu_config.get_secret(self._runtime.paths, bot.id)
        if not secret:
            self._set_state(bot.id, "error", "还没配置 App Secret")
            return
        self._set_state(bot.id, "connecting")
        task = asyncio.create_task(
            self._supervise(bot, secret), name=f"feishu-bot-{bot.id}"
        )
        self._tasks[bot.id] = task

    async def _supervise(self, bot: FeishuBot, secret: str) -> None:

        while not self._stopping:
            try:
                await self._run_once(bot, secret)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  
                logger.warning("飞书机器人 %s 异常退出：%s", bot.id, exc)

            if self._stopping:
                return

            count = self._restarts.get(bot.id, 0) + 1
            self._restarts[bot.id] = count
            if count > MAX_RESTARTS:
                self._set_state(
                    bot.id, "error", f"连续 {MAX_RESTARTS} 次启动失败，已停止自动重试"
                )
                logger.error("飞书机器人 %s 连续启动失败，不再重试", bot.id)
                self._tasks.pop(bot.id, None)
                return
            self._set_state(bot.id, "connecting", f"第 {count} 次重连中…")
            await asyncio.sleep(RESTART_DELAY)

    async def _run_once(self, bot: FeishuBot, secret: str) -> None:

        env = {
            **os.environ,
            ENV_APP_ID: bot.app_id,
            ENV_APP_SECRET: secret,
            ENV_BOT_ID: bot.id,
            
            "PYTHONIOENCODING": "utf-8",
        }
        proc = await asyncio.create_subprocess_exec(
            *_worker_command(),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            startupinfo=_startup_info(),
        )
        logger.info("飞书机器人 %s 子进程已拉起（pid=%s）", bot.id, proc.pid)

        stderr_tail: list[str] = []

        async def drain_stderr() -> None:










            assert proc.stderr is not None
            last_hint = 0.0
            while True:
                line = await proc.stderr.readline()
                if not line:
                    return
                text = line.decode("utf-8", errors="replace").rstrip()
                stderr_tail.append(text)
                if len(stderr_tail) > 40:
                    stderr_tail.pop(0)
                lowered = text.lower()
                if "error" in lowered or "failed" in lowered:
                    now = time.monotonic()
                    if now - last_hint >= 10:
                        last_hint = now
                        logger.warning("飞书机器人 %s · 子进程：%s", bot.id, text[:300])

        stderr_task = asyncio.create_task(drain_stderr())
        try:
            await self._read_protocol(bot, proc)
        finally:
            stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stderr_task
            with contextlib.suppress(ProcessLookupError):
                if proc.returncode is None:
                    proc.kill()
            with contextlib.suppress(asyncio.TimeoutError, Exception):
                await asyncio.wait_for(proc.wait(), timeout=5)

        if stderr_tail:
            logger.warning(
                "飞书机器人 %s 子进程输出：\n%s", bot.id, "\n".join(stderr_tail[-15:])
            )
        if proc.returncode not in (0, None):
            self._set_state(bot.id, "error", f"子进程异常退出（{proc.returncode}）")

    async def _read_protocol(self, bot: FeishuBot, proc: asyncio.subprocess.Process) -> None:

        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                return
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                
                logger.debug("飞书机器人 %s 非协议输出：%s", bot.id, text[:200])
                continue

            kind = message.get("kind")
            if kind == "ready":
                
                
                
                
                
                
                
                
                self._restarts[bot.id] = 0
                self._set_state(bot.id, "connecting")
                logger.info("飞书机器人 %s 子进程已启动，正在连接", bot.id)
                
                asyncio.create_task(
                    self._watch_first_event(bot.id), name=f"feishu-watch-{bot.id}"
                )
            elif kind == "log":
                
                
                
                text = str(message.get("text") or "")
                level = str(message.get("level") or "info")
                if "connected to wss://" in text:
                    self._restarts[bot.id] = 0
                    self._set_state(bot.id, "connected")
                    logger.info("飞书机器人 %s 长连接已建立（%s）", bot.id, text[:120])
                elif level in ("error", "critical", "warning"):
                    logger.warning("飞书机器人 %s · lark：%s", bot.id, text[:300])
                    
                    if "error" in level or "critical" in level:
                        self._set_state(bot.id, "error", text[:300])
                else:
                    logger.debug("飞书机器人 %s · lark：%s", bot.id, text[:200])
            elif kind == "error":
                self._set_state(bot.id, "error", str(message.get("message") or "未知错误"))
            elif kind == "event":
                
                if self._states.get(bot.id, {}).get("state") != "connected":
                    self._set_state(bot.id, "connected")
                    logger.info("飞书机器人 %s 长连接已确认（收到事件）", bot.id)
                payload = message.get("payload")
                if isinstance(payload, dict) and self._on_event is not None:
                    try:
                        await self._on_event(bot, payload)
                    except Exception as exc:  
                        logger.exception("处理飞书消息失败（机器人 %s）：%s", bot.id, exc)

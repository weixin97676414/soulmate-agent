



















from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from ..config.schemas import McpServerConfig
from ..errors import McpToolCallError, McpUnavailableError
from ..security.paths import PathPolicy
from . import procs
from .transports import open_transport
from .types import McpServerState, McpServerStatus, McpToolInfo

logger = logging.getLogger(__name__)


DEFAULT_CONNECT_TIMEOUT = 90.0
DEFAULT_CALL_TIMEOUT = 60.0
DEFAULT_PING_TIMEOUT = 10.0

STOP_TIMEOUT = 5.0

StatusCallback = Callable[[McpServerStatus], None]

























_ENV_ALLOWLIST = frozenset(
    {
        
        "PATH",  
        "TMPDIR",
        "TERM",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        
        
        
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "COMMONPROGRAMFILES",
        "USERNAME",
        "USERDOMAIN",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        
        "HOME",
        "SHELL",
        "USER",
        "LOGNAME",
    }
)



_ENV_INHERIT_FLAG = "AGENT_MCP_INHERIT_ENV"


def build_subprocess_env(user_env: dict[str, str] | None = None) -> dict[str, str]:











    if os.environ.get(_ENV_INHERIT_FLAG, "").strip().lower() in ("1", "true", "yes", "on"):
        logger.warning(
            "检测到 %s：MCP 子进程将继承**全部**环境变量（含 AGENT_TOKEN）。"
            "仅在排查第三方 Server 问题时临时开启，用完请关掉。",
            _ENV_INHERIT_FLAG,
        )
        env = dict(os.environ)
    else:
        dropped = 0
        env = {}
        for key, value in os.environ.items():
            if key.upper() in _ENV_ALLOWLIST:
                env[key] = value
            else:
                dropped += 1
        
        
        if dropped:
            logger.debug("MCP 子进程环境变量已最小化：放行 %s 项，剔除 %s 项", len(env), dropped)

    
    
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    if user_env:
        
        
        env.update({str(k): str(v) for k, v in user_env.items()})

    return env


def sdk_available() -> bool:

    try:
        import mcp  
    except ImportError:
        return False
    return True


@dataclass
class _Command:


    kind: Literal["call", "list", "ping"]
    future: asyncio.Future[Any]
    tool: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)


class McpClient:


    def __init__(
        self,
        config: McpServerConfig,
        *,
        on_status_change: StatusCallback | None = None,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        path_policy: PathPolicy | None = None,
    ) -> None:
        self.config = config
        self.server_name = config.name
        self._on_status_change = on_status_change
        self._connect_timeout = connect_timeout
        
        self._path_policy = path_policy

        self.status = McpServerStatus.from_config(config, state=McpServerState.STOPPED)

        
        
        
        
        
        self._commands: asyncio.Queue[_Command | None] = asyncio.Queue(maxsize=64)
        self._runner: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._stopping = False
        
        self._child_pids: set[int] = set()

    
    
    
    @property
    def is_running(self) -> bool:
        return self._runner is not None and not self._runner.done()

    @property
    def is_ready(self) -> bool:
        return self.status.is_active and self.is_running

    def _set_state(
        self,
        state: McpServerState,
        *,
        message: str = "",
        tools: list[McpToolInfo] | None = None,
        last_error: str | None = None,
    ) -> None:
        self.status.state = state
        self.status.message = message
        if tools is not None:
            self.status.tools = tools
        if last_error is not None:
            self.status.last_error = last_error
        self._notify()

    def _notify(self) -> None:
        if self._on_status_change is None:
            return
        try:
            self._on_status_change(self.status)
        except Exception:  
            logger.exception("MCP 状态回调失败: %s", self.server_name)

    
    
    
    async def start(self) -> bool:

        if self.is_running:
            return self.is_ready

        if not sdk_available():
            self.status.sdk_missing = True
            self._set_state(
                McpServerState.ERROR,
                message="未安装 MCP 依赖（pip install \"my-agent-core[mcp]\"）",
                tools=[],
            )
            return False

        self.status.sdk_missing = False
        self._stopping = False
        self._ready.clear()
        
        self._drain_commands(reason="服务正在重启")

        self._set_state(McpServerState.STARTING, message="正在启动…", tools=[])
        self._runner = asyncio.create_task(self._run(), name=f"mcp-{self.server_name}")

        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._ready.wait(), timeout=self._connect_timeout)

        if self.status.state == McpServerState.READY:
            return True

        
        
        
        if not self._ready.is_set():
            self._set_state(
                McpServerState.ERROR,
                message=f"连接超时（>{self._connect_timeout:.0f}s）",
                last_error=f"连接超时（>{self._connect_timeout:.0f}s）",
                tools=[],
            )
        await self._cleanup_runner()
        return False

    async def _cleanup_runner(self) -> None:

        runner = self._runner
        self._runner = None
        if runner is None:
            return

        
        with contextlib.suppress(asyncio.QueueFull):
            self._commands.put_nowait(None)

        try:
            await asyncio.wait_for(runner, timeout=STOP_TIMEOUT)
        except TimeoutError:
            
            runner.cancel()
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(runner, timeout=STOP_TIMEOUT)
        except asyncio.CancelledError:
            
            
            
            
            
            
            
            runner.cancel()
            
            
            with contextlib.suppress(BaseException):
                await asyncio.wait_for(asyncio.shield(runner), timeout=STOP_TIMEOUT)
            await self._reap_tree()
            self._drain_commands(reason="服务已停止")
            raise
        except Exception:  
            logger.debug("MCP 任务退出时抛出异常: %s", self.server_name, exc_info=True)

        await self._reap_tree()
        self._drain_commands(reason="服务已停止")

    async def _reap_tree(self) -> None:










        if not self._child_pids:
            return
        await asyncio.to_thread(procs.kill_tree, self._child_pids, reason=self.server_name)
        self._child_pids.clear()

    async def stop(self) -> None:

        self._stopping = True
        await self._cleanup_runner()
        if self.status.state != McpServerState.DISABLED:
            self._set_state(McpServerState.STOPPED, message="已停止", tools=[])

    async def restart(self) -> bool:
        await self.stop()
        return await self.start()

    def _drain_commands(self, *, reason: str) -> None:
        while True:
            try:
                command = self._commands.get_nowait()
            except asyncio.QueueEmpty:
                return
            if command is None:
                continue
            if not command.future.done():
                command.future.set_exception(McpUnavailableError(f"{self.server_name}: {reason}"))

    
    
    
    async def _run(self) -> None:

        if not sdk_available():  
            self._set_state(McpServerState.ERROR, message="未安装 MCP 依赖")
            self._ready.set()
            return

        from contextlib import AsyncExitStack

        from mcp import ClientSession

        try:
            async with AsyncExitStack() as stack:
                
                
                
                
                before = await asyncio.to_thread(procs.snapshot_children)
                
                read, write = await open_transport(self.config, stack, self._path_policy)
                self._child_pids |= await asyncio.to_thread(procs.adopt_new_children, before)

                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()

                tools = await self._fetch_tools(session)
                
                
                self._set_state(
                    McpServerState.READY,
                    message=f"已连接，共 {len(tools)} 个工具",
                    tools=tools,
                    last_error=None,
                )
                self._ready.set()

                await self._serve(session)

        except asyncio.CancelledError:
            raise
        except Exception as exc:  
            message = self._describe_failure(exc)
            logger.error("MCP Server %s 连接失败: %s", self.server_name, message)
            self._set_state(
                McpServerState.ERROR, message=message, last_error=message, tools=[]
            )
        finally:
            
            self._ready.set()

    async def _serve(self, session: Any) -> None:
        while True:
            command = await self._commands.get()
            if command is None:  
                return
            
            
            
            if command.future.done():
                logger.debug("跳过已超时的 MCP 命令: %s", command.tool or command.kind)
                continue
            try:
                result = await self._dispatch(session, command)
                if not command.future.done():
                    command.future.set_result(result)
            except Exception as exc:  
                if not command.future.done():
                    command.future.set_exception(exc)

    async def _dispatch(self, session: Any, command: _Command) -> Any:
        if command.kind == "ping":
            await session.send_ping()
            return True
        if command.kind == "list":
            return await self._fetch_tools(session)
        result = await session.call_tool(command.tool or "", command.arguments)
        return self._render_result(command.tool or "", result)

    
    
    
    @staticmethod
    async def _fetch_tools(session: Any) -> list[McpToolInfo]:
        response = await session.list_tools()
        tools: list[McpToolInfo] = []
        for raw in getattr(response, "tools", []) or []:
            annotations = getattr(raw, "annotations", None)
            tools.append(
                McpToolInfo(
                    name=str(getattr(raw, "name", "")),
                    title=str(getattr(raw, "title", "") or ""),
                    description=str(getattr(raw, "description", "") or ""),
                    
                    input_schema=dict(
                        getattr(raw, "input_schema", None)
                        or getattr(raw, "inputSchema", None)
                        or {}
                    ),
                    read_only=_opt_bool(getattr(annotations, "read_only_hint", None)),
                    destructive=_opt_bool(getattr(annotations, "destructive_hint", None)),
                )
            )
        return tools

    @staticmethod
    def _render_result(tool: str, result: Any) -> str:

        if getattr(result, "is_error", False):
            raise McpToolCallError(_extract_error_text(tool, result))

        
        structured = getattr(result, "structured_content", None)
        if isinstance(structured, dict) and structured:
            if set(structured) == {"result"}:
                return _stringify(structured["result"])
            return _stringify(structured)

        parts: list[str] = []
        for item in getattr(result, "content", []) or []:
            text = getattr(item, "text", None)
            if text is not None:
                parts.append(str(text))
            else:
                parts.append(_stringify(item))
        return "\n".join(parts) if parts else "（工具未返回内容）"

    @staticmethod
    def _describe_failure(exc: BaseException) -> str:

        text = _flatten_exception(exc)
        lowered = text.lower()

        if isinstance(exc, FileNotFoundError) or "no such file" in lowered or "cannot find" in lowered:
            return f"找不到可执行文件「{exc}」，请确认命令已安装并在 PATH 中。"
        if "permission denied" in lowered:
            return "启动 MCP Server 被系统拒绝（权限不足）。"
        if "initialize" in lowered or "handshake" in lowered or "protocol" in lowered:
            return f"与 MCP Server 握手失败：{text[:200]}"
        return text[:300] or exc.__class__.__name__

    
    
    
    async def _submit(self, command: _Command, timeout: float) -> Any:
        if not self.is_running:
            raise McpUnavailableError(
                f"MCP Server「{self.server_name}」当前未连接（{self.status.message or self.status.state.value}）。"
            )
        await self._commands.put(command)
        try:
            return await asyncio.wait_for(command.future, timeout=timeout)
        except TimeoutError as exc:
            command.future.cancel()
            raise McpToolCallError(
                f"MCP 调用超时（>{timeout:.0f}s），服务「{self.server_name}」可能已无响应。"
            ) from exc

    async def list_tools(self) -> list[McpToolInfo]:
        return await self._submit(_Command("list", _new_future()), DEFAULT_PING_TIMEOUT)

    async def call_tool(self, tool: str, arguments: dict[str, Any] | None = None) -> str:
        command = _Command(
            "call", _new_future(), tool=tool, arguments=dict(arguments or {})
        )
        return await self._submit(command, self.config.timeout or DEFAULT_CALL_TIMEOUT)

    async def ping(self) -> bool:

        if not self.is_running:
            return False
        try:
            await self._submit(_Command("ping", _new_future()), DEFAULT_PING_TIMEOUT)
            return True
        except (McpUnavailableError, McpToolCallError):
            return False
        except Exception:  
            logger.debug("MCP ping 异常: %s", self.server_name, exc_info=True)
            return False






_ERROR_WRAPPERS = (
    re.compile(r"^Tool '.*?' failed:\s*"),
    re.compile(r"^Error executing tool .*?:\s*"),
)


def _extract_error_text(tool: str, result: Any) -> str:






    candidates: list[str] = []

    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        for key in ("error", "message", "detail", "reason", "result"):
            value = structured.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())

    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if isinstance(text, str) and text.strip():
            candidates.append(text.strip())

    
    detail = max(candidates, key=len, default="")
    if not detail:
        return f"MCP 工具 {tool} 执行失败（Server 未返回错误详情）。"

    for pattern in _ERROR_WRAPPERS:
        detail = pattern.sub("", detail)
    
    detail = detail.strip().strip("'").strip('"').strip()

    if detail.startswith(f"MCP 工具 {tool}"):
        return detail
    return f"MCP 工具 {tool} 执行失败：{detail}"


def _new_future() -> asyncio.Future[Any]:
    return asyncio.get_running_loop().create_future()


def _opt_bool(value: Any) -> bool | None:
    return None if value is None else bool(value)


def _stringify(value: Any) -> str:
    import json

    if isinstance(value, str):
        return value
    if value is None:
        return "（空）"
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def _flatten_exception(exc: BaseException) -> str:

    parts: list[str] = []
    stack: list[BaseException] = [exc]
    seen = 0
    while stack and seen < 20:
        current = stack.pop(0)
        seen += 1
        if isinstance(current, BaseExceptionGroup):  
            stack.extend(current.exceptions)
            continue
        text = str(current).strip()
        if text:
            parts.append(text)
    return " / ".join(parts) or exc.__class__.__name__


__all__ = [
    "DEFAULT_CALL_TIMEOUT",
    "DEFAULT_CONNECT_TIMEOUT",
    "McpClient",
    "sdk_available",
]

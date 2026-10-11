"""MCP 客户端：一个 Server 连接的全部生命周期。

## 为什么把连接做成「actor」

MCP 官方 SDK 的 ``stdio_client`` 内部使用 anyio 的 task group / cancel scope。
anyio 有一条硬性约束：**cancel scope 必须在创建它的那个任务里退出**。
如果我们在任务 A 里 ``connect()``、在任务 B 里 ``close()``，就会拿到
``RuntimeError: Attempted to exit cancel scope in a different task``——
这个错误信息完全看不出根因，非常难查。

因此这里采用 actor 模型：一个后台任务从连接、处理命令到断开全部包办，
外部只能通过命令队列与它交互。代价是多了一个队列，换来的是彻底绕开这个坑。

## 崩溃检测

子进程死掉时，我们的命令循环只是静静地等在队列上，不会收到任何通知。
所以探活必须**主动**做：调用 ``ping()``，超时或报错即判定服务已不可用，
由 ``McpManager`` 决定是否重启。
"""

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

# 建立连接（含 npx 现下载包）可能很慢，给足时间
DEFAULT_CONNECT_TIMEOUT = 90.0
DEFAULT_CALL_TIMEOUT = 60.0
DEFAULT_PING_TIMEOUT = 10.0
# 停止时等待优雅退出的时间，超时则强杀
STOP_TIMEOUT = 5.0

StatusCallback = Callable[[McpServerStatus], None]

# ---------------------------------------------------------------------------- #
# 子进程环境变量：白名单
# ---------------------------------------------------------------------------- #
# 传给 MCP 子进程的父进程环境变量白名单。
#
# ## 为什么不能用 ``{**os.environ, **config.env}``
#
# MCP Server 是**第三方可执行程序**（很多是 ``npx`` 现拉下来的社区包），
# 而我们把自己的本地接口令牌放在 ``AGENT_TOKEN`` 环境变量里。全量继承等于
# 把这个令牌交给每一个连进来的 Server —— 拿到它就能**绕开界面直接调用本机
# 全部接口**（读文件、执行 confirm 级技能、改配置），而这一切都不会在
# 界面上留下任何痕迹。
#
# 这跟 ``config/secrets.py`` 里"刻意不用环境变量传密钥"的设计自相矛盾：
# 密钥源头保护得很好，却在子进程这一环全漏出去了。
#
# ## 为什么是白名单而不是黑名单
#
# 黑名单要穷举"哪些不能泄漏"，而我们要挡的远不止 ``AGENT_TOKEN`` ——
# 将来新增的任何敏感变量、或者用户在 shell 里随手 ``export`` 的个人凭证，
# 都会静默流向第三方。白名单反过来：**默认不信任，只放行运行所必需的**。
#
# 真正需要给 Server 传凭证的场景（例如 GitHub MCP 需要 ``GITHUB_TOKEN``），
# 应该在 MCP 配置里显式写 ``env`` —— 那是用户的明确意图，也便于事后审计。
_ENV_ALLOWLIST = frozenset(
    {
        # ---- 跨平台必需 ----
        "PATH",  # npx/uvx/python 都靠它找到可执行文件
        "TMPDIR",
        "TERM",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        # ---- Windows 必需 ----
        # SYSTEMROOT 尤其关键：缺了它，大量程序在加载系统 DLL 阶段就失败，
        # 而且报错往往和环境变量毫无关系（表现为"无法启动"或找不到dll）。
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
        # ---- POSIX 常用 ----
        "HOME",
        "SHELL",
        "USER",
        "LOGNAME",
    }
)

# 逃生舱环境变量名。极少数 MCP Server 会依赖某个不在白名单里的变量；
# 这种情况下让用户在本机显式开启，属于知情基础上的选择（默认是关的）。
_ENV_INHERIT_FLAG = "AGENT_MCP_INHERIT_ENV"


def build_subprocess_env(user_env: dict[str, str] | None = None) -> dict[str, str]:
    """为 MCP 子进程构造一份环境变量。默认只放行白名单，可被逃生舱开关覆盖。

    Args:
        user_env: MCP 配置里用户显式填写的 env，总是**最后**覆盖上去 ——
            用户明写的优先，这是我们期望的语义。

    Windows 的环境变量名大小写不敏感；实测下 Python 的 nt 实现会把
    ``os.environ`` 的 key **统一归一成大写**，所以这里读到的已经是稳定写法。
    仍然按 ``key.upper()`` 比对、并且保留原始的 key 大小写写出，是为了让
    POSIX 侧那些刻意写成小写的变量（``TERM`` 等偶尔会被小写化）也不会漏掉。
    """
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
        # 只在确实剔除了东西时记一次 debug，避免常规路径刷日志。
        # 这个数字是排查"Server 说找不到某个变量"的第一手证据。
        if dropped:
            logger.debug("MCP 子进程环境变量已最小化：放行 %s 项，剔除 %s 项", len(env), dropped)

    # 子进程 Python 强制 UTF-8：中文参数与 stdout 不会在 GBK 终端下乱码。
    # 这两个变量本身就是我们的（不属于用户环境），放在这里而不是白名单里。
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    if user_env:
        # str() 兜一层：配置文件是 JSON，理论上都是字符串，但手改过的文件
        # 可能出现数字/bool，传 dict[str, Any] 给 SDK 会在子进程创建阶段炸掉。
        env.update({str(k): str(v) for k, v in user_env.items()})

    return env


def sdk_available() -> bool:
    """官方 mcp SDK 是否可用（它是可选依赖）。"""
    try:
        import mcp  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass
class _Command:
    """投递给 actor 任务的一条命令。"""

    kind: Literal["call", "list", "ping"]
    future: asyncio.Future[Any]
    tool: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)


class McpClient:
    """管理单个 MCP Server 的连接。"""

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
        # 只用于校验 stdio 的 cwd 是否落在允许目录内（见 transports.validate_cwd）
        self._path_policy = path_policy

        self.status = McpServerStatus.from_config(config, state=McpServerState.STOPPED)

        # **有界**队列。原先是无界的 —— 一旦 Server 卡住不再消费命令，
        # 调用方会一直往里塞，请求和它们的 Future 就无限堆积在内存里，
        # 直到整个进程被拖垮。给个上限之后 `put` 会自然形成背压：
        # 塞不进去时调用方等一等，而不是把内存耗光。
        # 上限取 64：正常情况下在途命令只有个位数，64 已经是"明显不正常"的量级。
        self._commands: asyncio.Queue[_Command | None] = asyncio.Queue(maxsize=64)
        self._runner: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._stopping = False
        # 本次启动创建的进程树根（Windows 上用来兜住 npx→node 这类孙进程）
        self._child_pids: set[int] = set()

    # ------------------------------------------------------------------ #
    # 状态
    # ------------------------------------------------------------------ #
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
        except Exception:  # noqa: BLE001 - 状态回调不能反过来影响连接
            logger.exception("MCP 状态回调失败: %s", self.server_name)

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    async def start(self) -> bool:
        """启动并等待连接就绪。返回是否成功。"""
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
        # 清掉上一次残留的命令，避免重连后执行到过期请求
        self._drain_commands(reason="服务正在重启")

        self._set_state(McpServerState.STARTING, message="正在启动…", tools=[])
        self._runner = asyncio.create_task(self._run(), name=f"mcp-{self.server_name}")

        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._ready.wait(), timeout=self._connect_timeout)

        if self.status.state == McpServerState.READY:
            return True

        # 启动失败：把任务收干净，避免留下僵尸进程。
        # 注意这里用的是 _cleanup_runner 而不是 stop()：stop 会把状态重置成
        # STOPPED，把刚刚写好的 ERROR 和失败原因一起抹掉，用户就看不到为什么连不上了。
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
        """回收 actor 任务，但**不改动状态**。"""
        runner = self._runner
        self._runner = None
        if runner is None:
            return

        # 投递停止信号，让 actor 任务在**同一个任务内**退出上下文管理器
        with contextlib.suppress(asyncio.QueueFull):
            self._commands.put_nowait(None)

        try:
            await asyncio.wait_for(runner, timeout=STOP_TIMEOUT)
        except TimeoutError:
            # runner 自己没能在时限内退出：强杀后给它最后一次机会
            runner.cancel()
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(runner, timeout=STOP_TIMEOUT)
        except asyncio.CancelledError:
            # 这是**外部**取消了当前任务（例如关停时取消健康检查循环），
            # 与上面的"runner 超时"是完全不同的两件事。
            #
            # 原先两者共用一个分支被静默吞掉，后果很隐蔽：本任务从此不再处于
            # 取消态 → 接着把 restart() 跑完、**又建起一条连接** → 而调用方
            # 还阻塞在 `await task` 上 → 关停被拖住整整一个健康周期（30s），
            # 期间新拉起的子进程也没人回收。
            runner.cancel()
            # 尽力回收，但绝不吞掉取消信号：这里 suppress 的是"等不到"这件事，
            # 不是取消本身。用 BaseException 是因为取消可能在此刻再次投递。
            with contextlib.suppress(BaseException):
                await asyncio.wait_for(asyncio.shield(runner), timeout=STOP_TIMEOUT)
            await self._reap_tree()
            self._drain_commands(reason="服务已停止")
            raise
        except Exception:  # noqa: BLE001 - 退出阶段的异常不该向上冒
            logger.debug("MCP 任务退出时抛出异常: %s", self.server_name, exc_info=True)

        await self._reap_tree()
        self._drain_commands(reason="服务已停止")

    async def _reap_tree(self) -> None:
        """强制回收本次启动的进程树。

        SDK 关掉的是它直接创建的那个进程；Windows 上 ``npx`` 还会再去开 ``node``，
        只杀直接子进程会留下孤儿 —— 它们仍占着端口与文件句柄，用户重连时会撞上
        "端口被占用"，而进程名看起来跟本应用毫无关系（是 ``node``），极难归因。

        ``to_thread``：``kill_tree`` 内部是同步的 ``subprocess.run``，
        而本方法跑在事件循环里。直接调用会把**所有**正在流式输出的会话一起卡住
        （``taskkill`` 冷启动可达数百毫秒，超时上限更是 15 秒）。
        """
        if not self._child_pids:
            return
        await asyncio.to_thread(procs.kill_tree, self._child_pids, reason=self.server_name)
        self._child_pids.clear()

    async def stop(self) -> None:
        """停止连接并回收子进程（用户主动停止 / 重连前的清理）。"""
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

    # ------------------------------------------------------------------ #
    # actor 主体
    # ------------------------------------------------------------------ #
    async def _run(self) -> None:
        """连接 → 服务命令 → 断开，全部在同一个任务内完成。"""
        if not sdk_available():  # pragma: no cover - start() 已提前拦截
            self._set_state(McpServerState.ERROR, message="未安装 MCP 依赖")
            self._ready.set()
            return

        from contextlib import AsyncExitStack

        from mcp import ClientSession

        try:
            async with AsyncExitStack() as stack:
                # 建连前后各拍一次子进程快照：差集就是**这次启动**的 Server 进程树根。
                # 用它兜住 Windows 上 npx→node 的孙进程（见 procs.py）
                # 快照在子线程里拍：两个函数内部都是同步的 subprocess.run，
                # 直接在事件循环里调用会把正在流式输出的会话一起卡住（见 _reap_tree）
                before = await asyncio.to_thread(procs.snapshot_children)
                # 三种传输共用同一套生命周期，只有"怎么建连"不同（见 transports.py）
                read, write = await open_transport(self.config, stack, self._path_policy)
                self._child_pids |= await asyncio.to_thread(procs.adopt_new_children, before)

                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()

                tools = await self._fetch_tools(session)
                # 注意：这里**不重置** status.restarts。重连次数由 McpManager 统计，
                # 在连接内部重置会让「崩溃→重连→立刻再崩」变成无限循环。
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
        except Exception as exc:  # noqa: BLE001 - 任何异常都归为连接失败
            message = self._describe_failure(exc)
            logger.error("MCP Server %s 连接失败: %s", self.server_name, message)
            self._set_state(
                McpServerState.ERROR, message=message, last_error=message, tools=[]
            )
        finally:
            # 无论成功失败都要唤醒 start()，否则它会一直等到超时
            self._ready.set()

    async def _serve(self, session: Any) -> None:
        while True:
            command = await self._commands.get()
            if command is None:  # 停止信号
                return
            # 排队期间可能已经超时（_submit 超时只取消了 future，命令本身还在队列里）。
            # 这种命令**绝不能执行**：一个已经被上报为"失败"的写操作如果照跑，
            # 用户看到的是"失败了"、实际副作用却已经发生——比直接报错糟糕得多。
            if command.future.done():
                logger.debug("跳过已超时的 MCP 命令: %s", command.tool or command.kind)
                continue
            try:
                result = await self._dispatch(session, command)
                if not command.future.done():
                    command.future.set_result(result)
            except Exception as exc:  # noqa: BLE001
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

    # ------------------------------------------------------------------ #
    # SDK 适配
    # ------------------------------------------------------------------ #
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
                    # 2.x 是 input_schema；兼容旧版的 inputSchema
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
        """把 CallToolResult 压成一段给模型看的文本。"""
        if getattr(result, "is_error", False):
            raise McpToolCallError(_extract_error_text(tool, result))

        # 优先取结构化内容：它是 Server 侧的原始返回值，比拼接文本更干净
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
        """把 SDK / anyio 的异常翻译成用户能看懂的一句话。"""
        text = _flatten_exception(exc)
        lowered = text.lower()

        if isinstance(exc, FileNotFoundError) or "no such file" in lowered or "cannot find" in lowered:
            return f"找不到可执行文件「{exc}」，请确认命令已安装并在 PATH 中。"
        if "permission denied" in lowered:
            return "启动 MCP Server 被系统拒绝（权限不足）。"
        if "initialize" in lowered or "handshake" in lowered or "protocol" in lowered:
            return f"与 MCP Server 握手失败：{text[:200]}"
        return text[:300] or exc.__class__.__name__

    # ------------------------------------------------------------------ #
    # 对外调用
    # ------------------------------------------------------------------ #
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
        """探活。返回 False 表示服务已不可用（需要重启）。"""
        if not self.is_running:
            return False
        try:
            await self._submit(_Command("ping", _new_future()), DEFAULT_PING_TIMEOUT)
            return True
        except (McpUnavailableError, McpToolCallError):
            return False
        except Exception:  # noqa: BLE001 - 探活失败一律视为不可用
            logger.debug("MCP ping 异常: %s", self.server_name, exc_info=True)
            return False


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
# SDK 会在工具错误外面套好几层壳，这里是需要剥掉的常见前缀
_ERROR_WRAPPERS = (
    re.compile(r"^Tool '.*?' failed:\s*"),
    re.compile(r"^Error executing tool .*?:\s*"),
)


def _extract_error_text(tool: str, result: Any) -> str:
    """从失败结果里挖出**真正有用**的那句话。

    MCP 的错误结果往往是层层包裹的：``Tool 'x' failed: 'Error executing tool
    x: 便签「a」不存在，现有便签：b、c'``。如果原样丢给模型，
    它会以为这是个协议错误而放弃；剥掉外壳后它就知道换个参数重试。
    """
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

    # 取最长的一条：外壳通常最短，内层的真实原因信息量更大
    detail = max(candidates, key=len, default="")
    if not detail:
        return f"MCP 工具 {tool} 执行失败（Server 未返回错误详情）。"

    for pattern in _ERROR_WRAPPERS:
        detail = pattern.sub("", detail)
    # 外层可能还留着成对的引号
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
    """anyio 会把错误包成 ExceptionGroup，这里展开成可读文本。"""
    parts: list[str] = []
    stack: list[BaseException] = [exc]
    seen = 0
    while stack and seen < 20:
        current = stack.pop(0)
        seen += 1
        if isinstance(current, BaseExceptionGroup):  # type: ignore[name-defined]
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

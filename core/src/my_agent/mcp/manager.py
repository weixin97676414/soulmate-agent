"""MCP Server 管理器：连接生命周期、技能同步、崩溃自愈。

对应开发文档 6.3 节。三件事是这个模块的核心职责：

1. **生命周期**：把配置里的 Server 连起来、断开、按需重启；
2. **技能同步**：把「当前处于 READY 的 Server 的工具」与 SkillManager 里的
   MCP 技能对齐——Server 掉线时工具必须**从模型可见列表里消失**，
   否则模型会去调用一个不存在的服务，用户看到的就是莫名其妙的失败；
3. **崩溃自愈**：主动探活，发现死亡就重连，但设上限（默认 3 次），
   避免"配置写错了导致无限重启刷屏"。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import Any

from ..config.schemas import McpConfig, McpServerConfig
from ..observability.metrics import METRICS
from ..security.paths import PathPolicy
from ..skill.manager import SkillManager
from .client import McpClient, sdk_available
from .skill import build_mcp_skill, infer_permission_level, namespaced_name
from .types import McpServerState, McpServerStatus

logger = logging.getLogger(__name__)

# 连续自动重连上限，对齐开发文档 M5 验收「最多 3 次」
MAX_AUTO_RESTARTS = 3
# 主动探活间隔
HEALTH_INTERVAL = 30.0
# 建立一次连接的等待时间
CONNECT_TIMEOUT = 90.0

PersistCallback = Callable[[McpConfig], None]
StatusCallback = Callable[[McpServerStatus], None]


class McpManager:
    def __init__(
        self,
        config: McpConfig,
        skills: SkillManager,
        *,
        persist: PersistCallback | None = None,
        on_status_change: StatusCallback | None = None,
        path_policy: PathPolicy | None = None,
    ) -> None:
        self._config = config
        self._skills = skills
        self._persist = persist
        self._on_status_change = on_status_change
        # 透传给 McpClient，只用于校验 stdio 的 cwd 落在允许目录内
        self._path_policy = path_policy

        self._clients: dict[str, McpClient] = {}
        self._health_task: asyncio.Task[None] | None = None
        self._stopping = False
        self._lock = asyncio.Lock()

        for server in config.servers:
            self._clients[server.name] = self._make_client(server)

    # ------------------------------------------------------------------ #
    # 构造与状态
    # ------------------------------------------------------------------ #
    def _make_client(self, server: McpServerConfig) -> McpClient:
        return McpClient(
            server,
            on_status_change=self._handle_status_change,
            connect_timeout=CONNECT_TIMEOUT,
            path_policy=self._path_policy,
        )

    def _handle_status_change(self, status: McpServerStatus) -> None:
        # 状态迁移是最全的观测点：连不上、崩溃、重连失败都会经过这里，
        # 而逐个在调用点埋点必然会漏掉某条路径（尤其健康检查那条）。
        METRICS.inc("mcp_status_transitions_total", server=status.name, state=status.state)
        if status.state == McpServerState.ERROR:
            # 单独再记一个"错误"计数：它才是用户关心"我的 MCP 稳不稳"时看的那条，
            # 而 transitions 里混着 starting/ready 这些正常迁移
            METRICS.inc("mcp_errors_total", server=status.name)

        if self._on_status_change is None:
            return
        try:
            self._on_status_change(status)
        except Exception:  # noqa: BLE001
            logger.exception("MCP 状态回调失败: %s", status.name)

    @property
    def config(self) -> McpConfig:
        return self._config

    @property
    def sdk_available(self) -> bool:
        return sdk_available()

    def statuses(self) -> list[McpServerStatus]:
        return [client.status for client in self._clients.values()]

    def status(self, name: str) -> McpServerStatus | None:
        client = self._clients.get(name)
        return client.status if client else None

    def client(self, name: str) -> McpClient | None:
        return self._clients.get(name)

    def _save(self) -> None:
        if self._persist is None:
            return
        try:
            self._persist(self._config)
        except Exception:  # noqa: BLE001 - 落盘失败不该让界面操作失败
            logger.exception("MCP 配置保存失败")

    def set_tool_permission(self, server_name: str, tool_name: str, level: str) -> bool:
        """把某个 MCP 工具的权限写进**配置**并落盘。

        技能页签改权限必须走这里。只改内存里的 ``SkillMeta`` 的话，下一次
        ``sync_skills``（改配置、重连、重启都会触发）会拿配置里的旧值把它覆盖回去 ——
        用户看到的是"改完生效了，过一会儿又变回去"，而且没有任何提示。
        """
        server = self._config.get(server_name)
        if server is None:
            return False
        overrides = dict(server.permission_overrides)
        overrides[tool_name] = level
        self._config.upsert(server.model_copy(update={"permission_overrides": overrides}))
        self._save()
        return True

    # ------------------------------------------------------------------ #
    # 批量启停
    # ------------------------------------------------------------------ #
    async def start_all(self) -> None:
        """连接所有「已启用且设为自动启动」的 Server。"""
        if not sdk_available():
            logger.warning("未安装 mcp 依赖，MCP 功能不可用")
            for status in self.statuses():
                status.sdk_missing = True
                status.state = McpServerState.ERROR
                status.message = '未安装 MCP 依赖（pip install "my-agent-core[mcp]"）'
                self._handle_status_change(status)
            return

        targets = [
            server
            for server in self._config.servers
            if server.enabled and server.auto_start
        ]
        if not targets:
            logger.info("没有需要自动连接的 MCP Server")
            return

        # 并发连接：多个 Server 可能都在下载依赖，串行会非常慢
        results = await asyncio.gather(
            *(self._connect_one(server.name) for server in targets),
            return_exceptions=True,
        )
        connected = sum(1 for item in results if item is True)
        logger.info("MCP 启动完成：%s/%s 个服务已连接", connected, len(targets))
        await self.sync_skills()

    async def _connect_one(self, name: str) -> bool:
        client = self._clients.get(name)
        if client is None:
            return False
        try:
            return await client.start()
        except Exception:  # noqa: BLE001 - 单个 Server 失败不影响其他
            logger.exception("MCP Server %s 启动异常", name)
            return False

    async def stop_all(self) -> None:
        # **必须先置位再取消健康检查循环。**
        # 反过来的话，`_health_loop` 的 `while not self._stopping` 会看到 False
        # 而继续循环，`await stop_health_loop()` 就迟迟不返回（它 await 的是
        # 那个任务），期间健康检查还可能把连接重新拉起来。
        self._stopping = True
        await self.stop_health_loop()
        await asyncio.gather(
            *(client.stop() for client in self._clients.values()),
            return_exceptions=True,
        )
        # 全部断开后，MCP 技能必须从工具列表里移除
        await self.sync_skills()

    # ------------------------------------------------------------------ #
    # 单个 Server 的增删改
    # ------------------------------------------------------------------ #
    async def add_server(self, server: McpServerConfig) -> McpServerStatus:
        async with self._lock:
            self._config.upsert(server)
            self._save()

            existing = self._clients.get(server.name)
            if existing is not None:
                await existing.stop()
            client = self._make_client(server)
            self._clients[server.name] = client

            if server.enabled:
                await self._connect_one(server.name)
            else:
                client.status.state = McpServerState.DISABLED
                client.status.message = "已禁用"
                self._handle_status_change(client.status)

        await self.sync_skills()
        return self._clients[server.name].status

    async def update_server(self, server: McpServerConfig) -> McpServerStatus:
        async with self._lock:
            previous = self._config.get(server.name)
            needs_restart = previous is not None and _launch_config_changed(previous, server)

            self._config.upsert(server)
            self._save()

            client = self._clients.get(server.name)
            if client is None:
                client = self._make_client(server)
                self._clients[server.name] = client
            else:
                client.config = server
                client.status.sync_from_config(server)

            if not server.enabled:
                await client.stop()
                client.status.state = McpServerState.DISABLED
                client.status.message = "已禁用"
                self._handle_status_change(client.status)
            else:
                if needs_restart:
                    # 命令行变了必须重连，否则用户会以为改了没生效
                    await client.stop()
                    await self._connect_one(server.name)
                elif not client.is_running:
                    await self._connect_one(server.name)

        await self.sync_skills()
        return self._clients[server.name].status

    async def remove_server(self, name: str) -> bool:
        async with self._lock:
            client = self._clients.pop(name, None)
            removed = self._config.remove(name)
            if client is not None:
                await client.stop()
            if removed:
                self._save()
        await self.sync_skills()
        return removed or client is not None

    async def restart_server(self, name: str) -> McpServerStatus | None:
        client = self._clients.get(name)
        if client is None:
            return None
        # 手动重启视为用户主动介入，重置自动重连计数
        client.status.restarts = 0
        await client.restart()
        await self.sync_skills()
        return client.status

    async def stop_server(self, name: str) -> McpServerStatus | None:
        client = self._clients.get(name)
        if client is None:
            return None
        await client.stop()
        await self.sync_skills()
        return client.status

    # ------------------------------------------------------------------ #
    # 技能同步
    # ------------------------------------------------------------------ #
    def _desired_tools(self) -> dict[str, tuple[McpClient, Any, str]]:
        """当前应当注册的 MCP 技能：``工具名 -> (客户端, 工具信息, 权限级别)``。"""
        desired: dict[str, tuple[McpClient, Any, str]] = {}
        for client in self._clients.values():
            if not client.is_ready:
                continue
            # 权限从 **manager 持有的配置**里读，而不是 client.config。
            #
            # 改配置走的是 ``_config.upsert(...)``，它会用 model_copy 造一个新对象
            # 放进列表；而 client 手里还握着**旧的那个**。读 client.config 的话，
            # 用户刚在设置里改过的权限根本看不到 —— 表现为"改了没用"。
            server_config = self._config.get(client.server_name) or client.config
            for tool in client.status.tools:
                name = namespaced_name(client.server_name, tool.name)
                override = server_config.permission_overrides.get(tool.name)
                level = (
                    override
                    if override in ("safe", "confirm", "admin")
                    else infer_permission_level(tool)
                )
                desired[name] = (client, tool, level)
        return desired

    async def sync_skills(self) -> int:
        """把 SkillManager 里的 MCP 技能与当前连接状态对齐。

        返回当前生效的 MCP 技能数量。
        """
        desired = self._desired_tools()
        existing = {
            meta.name: meta
            for meta in self._skills.list_metas(enabled_only=False)
            if meta.source == "mcp"
        }

        # 1) 下线：Server 断开后，它的工具必须从模型可见列表里消失
        for name in set(existing) - set(desired):
            self._skills.unregister(name)

        # 2) 上线 / 更新
        for name, (client, tool, level) in desired.items():
            meta = existing.get(name)
            if meta is not None:
                # 已存在：刷新可能变了的静态信息，保留用户改过的启用状态
                meta.description = f"[{client.server_name}] {tool.description or tool.name}"
                meta.parameters = tool.input_schema or {"type": "object", "properties": {}}
                # 权限也要跟着配置刷新。原先这里不刷权限，导致在「设置 → MCP 服务」
                # 里改了 permission_overrides 却**不生效** —— 看起来像是改了个寂寞。
                # 反过来，技能页签直接改权限的话会被这里覆盖回去，所以那条路径
                # 必须把值写进配置（见 set_tool_permission 与 routes/skills.py）。
                # 配置是权限的唯一真相来源。
                meta.permission_level = level
                continue

            skill = build_mcp_skill(client, tool, permission_level=level)
            self._skills.register(skill)
            logger.info(
                "已注册 MCP 工具 %s（来源 %s，权限 %s）", name, client.server_name, level
            )

        return len(desired)

    # ------------------------------------------------------------------ #
    # 崩溃自愈
    # ------------------------------------------------------------------ #
    def start_health_loop(self) -> None:
        if self._health_task is not None or not sdk_available():
            return
        self._stopping = False
        self._health_task = asyncio.create_task(self._health_loop(), name="mcp-health")
        logger.info("MCP 健康检查已启动（间隔 %.0fs）", HEALTH_INTERVAL)

    async def stop_health_loop(self) -> None:
        task = self._health_task
        self._health_task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _health_loop(self) -> None:
        while not self._stopping:
            try:
                await asyncio.sleep(HEALTH_INTERVAL)
                await self.health_check()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 后台任务绝不能因单次异常退出
                logger.exception("MCP 健康检查失败，将在下个周期重试")

    async def health_check(self) -> int:
        """探活并尝试恢复。返回本次重启的 Server 数量。"""
        if not sdk_available():
            return 0

        restarted = 0
        # 刻意**不**持 self._lock 遍历：下面要对 client 做 ping / restart，
        # 那是秒级的网络与进程操作，持锁会让「添加/删除 Server」的接口卡住。
        # 代价是可能与增删改并发，所以每次动手前都复核一次在册状态。
        for client in list(self._clients.values()):
            if not client.is_ready:
                continue
            if await client.ping():
                # 探活成功说明服务是健康的，把重连计数清零。
                # 不清零的话「连续 N 次」会退化成「累计 N 次」：
                # 一个稳定跑了几小时、期间偶发崩过几次且都恢复成功的 Server，
                # 第 4 次崩溃时会被误判成「请手动重启」。
                if client.status.restarts:
                    logger.info("MCP Server %s 已恢复稳定，重置重连计数", client.server_name)
                    client.status.restarts = 0
                continue
            logger.warning("MCP Server %s 无响应，尝试恢复", client.server_name)
            if await self._try_recover(client):
                restarted += 1

        if restarted:
            await self.sync_skills()
        return restarted

    def _is_registered(self, client: McpClient) -> bool:
        """该 client 是否仍是当前在册的那一个。

        健康检查不持锁，遍历期间用户可能已经删除了这个 Server
        （``remove_server`` 会把它移出字典并 stop 掉）。若不复核就对它
        ``restart()``，新拉起的子进程之后再也没人回收 —— 变成孤儿进程，
        用户关掉客户端后它还留在后台。
        """
        return self._clients.get(client.server_name) is client

    async def _try_recover(self, client: McpClient) -> bool:
        if client.status.restarts >= MAX_AUTO_RESTARTS:
            client.status.state = McpServerState.ERROR
            client.status.message = (
                f"服务已断开，且自动重连已尝试 {MAX_AUTO_RESTARTS} 次仍未成功，请手动重启。"
            )
            client.status.tools = []
            self._handle_status_change(client.status)
            return False

        client.status.restarts += 1
        client.status.state = McpServerState.RESTARTING
        client.status.message = f"连接中断，正在重连（第 {client.status.restarts} 次）…"
        self._handle_status_change(client.status)

        # 先同步一次技能：让工具立刻下线，避免模型在重连期间调用到死服务
        await self.sync_skills()

        # 动手前复核一次：期间可能已被用户删除（见 _is_registered 的说明）
        if not self._is_registered(client):
            logger.info("MCP Server %s 已从配置中移除，放弃重连", client.server_name)
            return False

        # 必须走 restart 而不是 connect：连接虽然断了，但 actor 任务还活着
        # （它只是阻塞在命令队列上），start() 会因此直接返回失败。
        try:
            ok = await client.restart()
        except Exception:  # noqa: BLE001 - 重连异常不该打断健康检查循环
            logger.exception("MCP Server %s 重连异常", client.server_name)
            ok = False

        if not ok and client.status.restarts >= MAX_AUTO_RESTARTS:
            client.status.message = (
                f"重连 {MAX_AUTO_RESTARTS} 次均失败，请检查启动命令是否正确。"
            )
            client._set_state(  # noqa: SLF001 - 复用统一的状态通知
                McpServerState.ERROR, message=client.status.message, tools=[]
            )
        return ok


def _launch_config_changed(old: McpServerConfig, new: McpServerConfig) -> bool:
    """只有影响进程启动的字段变化才需要重连。

    改个描述、改个权限覆盖就重启服务，会让用户觉得"这软件一惊一乍的"。
    """
    return (
        old.command != new.command
        or list(old.args) != list(new.args)
        or dict(old.env) != dict(new.env)
        or old.cwd != new.cwd
        # 传输方式与端点当然也属于"启动配置"：从 stdio 改成 sse 却不重连的话，
        # 界面会显示新地址、实际连的还是老进程，排查起来非常费劲
        or old.transport != new.transport
        or old.url != new.url
        or dict(old.headers) != dict(new.headers)
    )


__all__ = ["HEALTH_INTERVAL", "MAX_AUTO_RESTARTS", "McpManager"]

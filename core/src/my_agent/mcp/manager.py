











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


MAX_AUTO_RESTARTS = 3

HEALTH_INTERVAL = 30.0

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
        
        self._path_policy = path_policy

        self._clients: dict[str, McpClient] = {}
        self._health_task: asyncio.Task[None] | None = None
        self._stopping = False
        self._lock = asyncio.Lock()

        for server in config.servers:
            self._clients[server.name] = self._make_client(server)

    
    
    
    def _make_client(self, server: McpServerConfig) -> McpClient:
        return McpClient(
            server,
            on_status_change=self._handle_status_change,
            connect_timeout=CONNECT_TIMEOUT,
            path_policy=self._path_policy,
        )

    def _handle_status_change(self, status: McpServerStatus) -> None:
        
        
        METRICS.inc("mcp_status_transitions_total", server=status.name, state=status.state)
        if status.state == McpServerState.ERROR:
            
            
            METRICS.inc("mcp_errors_total", server=status.name)

        if self._on_status_change is None:
            return
        try:
            self._on_status_change(status)
        except Exception:  
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
        except Exception:  
            logger.exception("MCP 配置保存失败")

    def set_tool_permission(self, server_name: str, tool_name: str, level: str) -> bool:






        server = self._config.get(server_name)
        if server is None:
            return False
        overrides = dict(server.permission_overrides)
        overrides[tool_name] = level
        self._config.upsert(server.model_copy(update={"permission_overrides": overrides}))
        self._save()
        return True

    
    
    
    async def start_all(self) -> None:

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
        except Exception:  
            logger.exception("MCP Server %s 启动异常", name)
            return False

    async def stop_all(self) -> None:
        
        
        
        
        self._stopping = True
        await self.stop_health_loop()
        await asyncio.gather(
            *(client.stop() for client in self._clients.values()),
            return_exceptions=True,
        )
        
        await self.sync_skills()

    
    
    
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

    
    
    
    def _desired_tools(self) -> dict[str, tuple[McpClient, Any, str]]:

        desired: dict[str, tuple[McpClient, Any, str]] = {}
        for client in self._clients.values():
            if not client.is_ready:
                continue
            
            
            
            
            
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




        desired = self._desired_tools()
        existing = {
            meta.name: meta
            for meta in self._skills.list_metas(enabled_only=False)
            if meta.source == "mcp"
        }

        
        for name in set(existing) - set(desired):
            self._skills.unregister(name)

        
        for name, (client, tool, level) in desired.items():
            meta = existing.get(name)
            if meta is not None:
                
                meta.description = f"[{client.server_name}] {tool.description or tool.name}"
                meta.parameters = tool.input_schema or {"type": "object", "properties": {}}
                
                
                
                
                
                meta.permission_level = level
                continue

            skill = build_mcp_skill(client, tool, permission_level=level)
            self._skills.register(skill)
            logger.info(
                "已注册 MCP 工具 %s（来源 %s，权限 %s）", name, client.server_name, level
            )

        return len(desired)

    
    
    
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
            except Exception:  
                logger.exception("MCP 健康检查失败，将在下个周期重试")

    async def health_check(self) -> int:

        if not sdk_available():
            return 0

        restarted = 0
        
        
        
        for client in list(self._clients.values()):
            if not client.is_ready:
                continue
            if await client.ping():
                
                
                
                
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

        
        await self.sync_skills()

        
        if not self._is_registered(client):
            logger.info("MCP Server %s 已从配置中移除，放弃重连", client.server_name)
            return False

        
        
        try:
            ok = await client.restart()
        except Exception:  
            logger.exception("MCP Server %s 重连异常", client.server_name)
            ok = False

        if not ok and client.status.restarts >= MAX_AUTO_RESTARTS:
            client.status.message = (
                f"重连 {MAX_AUTO_RESTARTS} 次均失败，请检查启动命令是否正确。"
            )
            client._set_state(  
                McpServerState.ERROR, message=client.status.message, tools=[]
            )
        return ok


def _launch_config_changed(old: McpServerConfig, new: McpServerConfig) -> bool:




    return (
        old.command != new.command
        or list(old.args) != list(new.args)
        or dict(old.env) != dict(new.env)
        or old.cwd != new.cwd
        
        
        or old.transport != new.transport
        or old.url != new.url
        or dict(old.headers) != dict(new.headers)
    )


__all__ = ["HEALTH_INTERVAL", "MAX_AUTO_RESTARTS", "McpManager"]

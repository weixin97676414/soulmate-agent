
























from __future__ import annotations

import sys

from ..config.paths import AppPaths
from ..config.schemas import McpServerConfig



SQLITE_SERVER_NAME = "sqlite"


def sample_server_args(paths: AppPaths) -> list[str]:









    notes_dir = paths.workspace_dir / "mcp-notes"
    if getattr(sys, "frozen", False):
        return ["mcp-sample", "--notes-dir", str(notes_dir)]
    return ["-m", "my_agent.mcp.sample_server", "--notes-dir", str(notes_dir)]


def build_sample_server(paths: AppPaths) -> McpServerConfig:





    return McpServerConfig(
        name="sample",
        command=sys.executable,
        args=sample_server_args(paths),
        description="随应用附带的示例服务：不联网、无需额外安装，用于验证 MCP 链路是否通畅。",
        timeout=30.0,
    )


def sqlite_server_args(paths: AppPaths) -> list[str]:






    if getattr(sys, "frozen", False):
        return ["mcp-sqlite", "--db-path", str(paths.db_file)]
    return ["-m", "my_agent.mcp.sqlite_server", "--db-path", str(paths.db_file)]


def build_sqlite_server(paths: AppPaths) -> McpServerConfig:







    return McpServerConfig(
        name=SQLITE_SERVER_NAME,
        command=sys.executable,
        args=sqlite_server_args(paths),
        auto_start=True,
        description=(
            "查询应用自己的本地数据库（会话 / 消息 / 群记录 / 记账 / 提醒 / 用量 / 审计）。"
            "只读：增删改会被直接拒绝。"
        ),
        timeout=30.0,
    )


def presets(paths: AppPaths) -> list[dict[str, object]]:

    return [
        {
            "key": "sample",
            "title": "本地示例服务",
            "description": "随应用附带，免安装免联网，用于验证 MCP 是否跑通",
            "requires": "无",
            "server": build_sample_server(paths).model_dump(mode="json"),
        },
        {
            "key": "sqlite",
            "title": "数据库查询（只读）",
            "description": "用 SQL 查应用自己的数据（会话、群记录、记账、用量、审计）",
            "requires": "无（随应用附带）",
            "server": build_sqlite_server(paths).model_dump(mode="json"),
        },
    ]

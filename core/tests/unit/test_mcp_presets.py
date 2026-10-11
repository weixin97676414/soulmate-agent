"""自带 MCP：预设结构与 SQLite **只读**查询服务。

的两个决定：

1. 「SQLite 查询」要**随包分发、开箱可用** —— 原来那条命令写死 `uvx`，而 uv 不随
   我们分发（实测大多数机器都没装），所以它**开箱必报错**，用户只会当成我们的 bug；
2. 文件系统（能力已被内置技能覆盖，且技能那套受**文件访问白名单**约束）与
   Everything（纯协议演示、无实用价值）**剔除**。

⚠️ 「出厂预置」与「这一组行为」分开测：`tests/integration/test_mcp.py` 验的是
"添加/移除/停用某个服务"，它需要一个干净的 baseline，所以那边不预置。
"""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="未安装可选的 mcp SDK，MCP 相关用例跳过")

from my_agent.config.paths import AppPaths
from my_agent.mcp import sqlite_server
from my_agent.mcp.presets import (
    SQLITE_SERVER_NAME,
    build_sqlite_server,
    presets,
    sqlite_server_args,
)


@pytest.fixture
def paths(tmp_path) -> AppPaths:
    return AppPaths(tmp_path / "AgentDesktop").ensure()


@pytest.fixture
def db(tmp_path) -> Path:
    """一个装了点东西的 sqlite 库，用完把模块级路径还原。"""
    target = tmp_path / "agent.db"
    conn = sqlite3.connect(target)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO t (name) VALUES ('x')")
    conn.commit()
    conn.close()

    original = sqlite_server.DB_PATH
    sqlite_server.DB_PATH = target
    try:
        yield target
    finally:
        sqlite_server.DB_PATH = original


# --------------------------------------------------------------------------- #
# 预设结构
# --------------------------------------------------------------------------- #
def test_预设只保留自带的两个(paths):
    """剔除的三个不许回来：两个有技能替代 / 无实用价值，一个改成自带实现。"""
    keys = {item["key"] for item in presets(paths)}
    assert keys == {"sample", "sqlite"}


def test_自带SQLite的启动参数分源码态与冻结态(paths):
    """⚠️ 冻结环境里 `sys.executable` 是 agent-core.exe 本身。

    用 `-m` 起子模块会变成"把核心再拉一遍"（表现为点了没反应 / 端口被占），
    所以打包态必须走 `mcp-sqlite` 子命令。两种形态各验一次 —— 只验一半的话，
    另一半要等用户装上包才会暴露。
    """
    source_args = sqlite_server_args(paths)
    assert source_args[:2] == ["-m", "my_agent.mcp.sqlite_server"]
    assert str(paths.db_file) in source_args

    original = getattr(sys, "frozen", None)
    try:
        sys.frozen = True  # type: ignore[attr-defined]
        frozen_args = sqlite_server_args(paths)
    finally:
        if original is None:
            delattr(sys, "frozen")  # type: ignore[arg-type]
        else:
            sys.frozen = original  # type: ignore[attr-defined]
    assert frozen_args[0] == "mcp-sqlite"
    assert str(paths.db_file) in frozen_args


def test_自带SQLite默认自动启动并用我们自己的解释器(paths):
    """用户明确要求"随应用自动开启"；命令必须是**我们自己**的，不是 npx / uvx。"""
    server = build_sqlite_server(paths)
    assert server.name == SQLITE_SERVER_NAME
    assert server.auto_start is True
    assert server.command == sys.executable


async def test_出厂首次生成的配置里就带着它(tmp_path):
    """开箱即用：新装用户第一次启动，「MCP 服务」页里就该有它。

    ⚠️ 这条走真实路径（runtime.initialize → loader 首次生成 mcp.json），
    而不是直接把 presets 拿出来看 —— 后者证明不了"真的被预置进去了"。
    """
    from my_agent.server.runtime import AppRuntime

    rt = AppRuntime(AppPaths(tmp_path / "AgentDesktop").ensure())
    await rt.initialize()
    try:
        names = [item.name for item in rt.config.mcp.servers]
    finally:
        await rt.shutdown()
    assert SQLITE_SERVER_NAME in names


# --------------------------------------------------------------------------- #
# 只读保证（自己写这个服务的主要理由）
# --------------------------------------------------------------------------- #
def test_连接层就是只读的(db):
    """⚠️ 即使语句白名单被绕过，SQLite 自己也会拒绝写。

    这就是"自己写一版"换来的东西：社区那版对写操作只能"建议用户别写"，
    而它要查的恰恰是我们自己的会话表、审计日志、用量记录 —— 那些被改坏之后
    用户根本查不回来。
    """
    with closing(sqlite_server._connect()) as conn:  # noqa: SLF001 - 验的就是这一层
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("INSERT INTO t (name) VALUES ('y')")


def test_查得到的表与数据(db):
    tables = sqlite_server.list_tables()
    assert "t" in tables
    assert "1 条" in tables  # 行数也要如实报出来
    assert "name" in sqlite_server.query("SELECT name FROM t")


def test_写语句与多条语句被拦下(db):
    for bad in ("DELETE FROM t", "DROP TABLE t", "UPDATE t SET name='y'", "INSERT INTO t DEFAULT VALUES"):
        with pytest.raises(sqlite_server.ToolError):
            sqlite_server.query(bad)
    # 多条语句（`SELECT 1; DROP TABLE t` 这种）
    with pytest.raises(sqlite_server.ToolError):
        sqlite_server.query("SELECT 1; DROP TABLE t")

    # 而且数据真的没被动过 —— 上面前四条只要有一条漏了，这里就会红
    assert "x" in sqlite_server.query("SELECT name FROM t")


def test_数据库不存在时给一句人话(tmp_path):
    """新装用户还没聊过天，库当然不存在 —— 这时候不该抛底层异常。"""
    original = sqlite_server.DB_PATH
    sqlite_server.DB_PATH = tmp_path / "not-there.db"
    try:
        with pytest.raises(sqlite_server.ToolError):
            sqlite_server.list_tables()
    finally:
        sqlite_server.DB_PATH = original

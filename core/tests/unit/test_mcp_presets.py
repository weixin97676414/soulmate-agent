












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





def test_预设只保留自带的两个(paths):

    keys = {item["key"] for item in presets(paths)}
    assert keys == {"sample", "sqlite"}


def test_自带SQLite的启动参数分源码态与冻结态(paths):






    source_args = sqlite_server_args(paths)
    assert source_args[:2] == ["-m", "my_agent.mcp.sqlite_server"]
    assert str(paths.db_file) in source_args

    original = getattr(sys, "frozen", None)
    try:
        sys.frozen = True  
        frozen_args = sqlite_server_args(paths)
    finally:
        if original is None:
            delattr(sys, "frozen")  
        else:
            sys.frozen = original  
    assert frozen_args[0] == "mcp-sqlite"
    assert str(paths.db_file) in frozen_args


def test_自带SQLite默认自动启动并用我们自己的解释器(paths):

    server = build_sqlite_server(paths)
    assert server.name == SQLITE_SERVER_NAME
    assert server.auto_start is True
    assert server.command == sys.executable


async def test_出厂首次生成的配置里就带着它(tmp_path):





    from my_agent.server.runtime import AppRuntime

    rt = AppRuntime(AppPaths(tmp_path / "AgentDesktop").ensure())
    await rt.initialize()
    try:
        names = [item.name for item in rt.config.mcp.servers]
    finally:
        await rt.shutdown()
    assert SQLITE_SERVER_NAME in names





def test_连接层就是只读的(db):






    with closing(sqlite_server._connect()) as conn:  
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("INSERT INTO t (name) VALUES ('y')")


def test_查得到的表与数据(db):
    tables = sqlite_server.list_tables()
    assert "t" in tables
    assert "1 条" in tables  
    assert "name" in sqlite_server.query("SELECT name FROM t")


def test_写语句与多条语句被拦下(db):
    for bad in ("DELETE FROM t", "DROP TABLE t", "UPDATE t SET name='y'", "INSERT INTO t DEFAULT VALUES"):
        with pytest.raises(sqlite_server.ToolError):
            sqlite_server.query(bad)
    
    with pytest.raises(sqlite_server.ToolError):
        sqlite_server.query("SELECT 1; DROP TABLE t")

    
    assert "x" in sqlite_server.query("SELECT name FROM t")


def test_数据库不存在时给一句人话(tmp_path):

    original = sqlite_server.DB_PATH
    sqlite_server.DB_PATH = tmp_path / "not-there.db"
    try:
        with pytest.raises(sqlite_server.ToolError):
            sqlite_server.list_tables()
    finally:
        sqlite_server.DB_PATH = original

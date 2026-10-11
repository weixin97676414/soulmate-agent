"""测试专用的 MCP Server。

只用于覆盖「主流程之外」的场景，不随应用分发：
- ``crash`` 让进程直接退出，用来验证崩溃自愈；
- ``slow`` 用于验证调用超时；
- ``boom`` 抛出非预期异常，用于验证错误信息的可读性。

正常路径的测试一律使用随应用分发的 `my_agent/mcp/sample_server.py`，
这样「我们交付的东西」也在测试覆盖范围内。
"""

from __future__ import annotations

import os
import sys
import time

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

server = MCPServer(name="test-tools", version="1.0.0")

READ_ONLY = ToolAnnotations(read_only_hint=True)


@server.tool(description="回显文本。", annotations=READ_ONLY)
def echo(text: str) -> str:
    return f"echo: {text}"


@server.tool(description="睡眠指定秒数后返回。", annotations=READ_ONLY)
def slow(seconds: float = 1.0) -> str:
    time.sleep(seconds)
    return f"slept {seconds}s"


@server.tool(description="让进程立刻退出，用于验证崩溃自愈。", annotations=READ_ONLY)
def crash() -> str:
    # 直接 _exit，模拟被外部杀掉 / 自身崩溃的场景
    sys.stderr.flush()
    os._exit(1)
    return "unreachable"  # pragma: no cover


@server.tool(description="抛出一个非预期异常。", annotations=READ_ONLY)
def boom() -> str:
    raise ZeroDivisionError("除零了")


if __name__ == "__main__":
    server.run("stdio")

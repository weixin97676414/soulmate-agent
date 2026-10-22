










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
    
    sys.stderr.flush()
    os._exit(1)
    return "unreachable"  


@server.tool(description="抛出一个非预期异常。", annotations=READ_ONLY)
def boom() -> str:
    raise ZeroDivisionError("除零了")


if __name__ == "__main__":
    server.run("stdio")

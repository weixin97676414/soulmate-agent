"""一个极简的 MCP Server 示例（官方 Python SDK，stdio 传输）。

它有**两个用途**，都很重要：

1. **开箱即用的验证对象**。MCP 生态里主流 Server 都要靠 `npx` / `uvx` 现下载，
   用户第一次点开「MCP 服务」时很可能因为网络问题连不上，从而误以为功能是坏的。
   这个脚本随应用一起分发，免安装、免联网，双击添加就能看到工具列表；
2. **自研 Server 的模板**。把一个内部系统（知识库、审批流、工单系统）暴露成
   MCP 工具，通常只需要下面这几十行——这也是 MCP 集成最有价值的用法。

直接运行即可作为 stdio Server：

    python sample_mcp_server.py --notes-dir ./notes
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

INSTRUCTIONS = (
    "本地便签服务。可以列出、读取、写入和删除便签。"
    "写入与删除会修改磁盘文件，调用前应先向用户确认。"
)

server = MCPServer(name="sample-tools", version="1.0.0", instructions=INSTRUCTIONS)

# 显式声明注解而不是让客户端去猜：MCP 的 readOnlyHint / destructiveHint
# 是权限推断最可靠的依据，自研 Server 应当顺手标上。
READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True)


def _notes_dir() -> Path:
    raise RuntimeError("尚未初始化便签目录")


def _resolve(name: str) -> Path:
    """把便签名解析成文件路径，并挡掉目录穿越。"""
    cleaned = (name or "").strip()
    if not cleaned:
        raise ToolError("便签名不能为空")
    if any(ch in cleaned for ch in ("/", "\\", "..")):
        raise ToolError("便签名不能包含路径分隔符")

    root = _notes_dir().resolve()
    target = (root / f"{cleaned}.md").resolve()
    if target.parent != root:
        raise ToolError("便签路径越界")
    return target


@server.tool(description="列出所有便签的名称与最后修改时间。只读操作。", annotations=READ_ONLY)
def list_notes() -> str:
    root = _notes_dir()
    entries = sorted(root.glob("*.md"))
    if not entries:
        return "（还没有任何便签）"
    lines = []
    for path in entries:
        stamp = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        lines.append(f"- {path.stem}（修改于 {stamp}）")
    return "\n".join(lines)


@server.tool(description="读取指定便签的完整内容。只读操作。", annotations=READ_ONLY)
def read_note(name: str) -> str:
    path = _resolve(name)
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in _notes_dir().glob("*.md"))) or "（无）"
        # 抛 ToolError 而不是 FileNotFoundError：前者是「预期内的业务错误」，
        # SDK 会把它的原文透传给客户端；后者会被包成 "Error executing tool xxx"，
        # 把真正有用的信息（有哪些便签可用）丢掉。
        raise ToolError(f"便签「{name}」不存在。现有便签：{available}")
    return path.read_text(encoding="utf-8")


@server.tool(description="新建或覆盖一个便签。会写入磁盘文件，需要用户确认。", annotations=DESTRUCTIVE)
def write_note(name: str, content: str) -> str:
    path = _resolve(name)
    existed = path.is_file()
    path.write_text(content, encoding="utf-8")
    action = "已覆盖" if existed else "已创建"
    return f"{action}便签「{name}」，共 {len(content)} 个字符。路径：{path}"


@server.tool(description="删除一个便签。不可恢复，需要用户确认。", annotations=DESTRUCTIVE)
def delete_note(name: str) -> str:
    path = _resolve(name)
    if not path.is_file():
        raise ToolError(f"便签「{name}」不存在，无需删除。")
    path.unlink()
    return f"已删除便签「{name}」。"


@server.tool(description="原样返回输入文本。用于验证 MCP 链路是否通畅。只读操作。", annotations=READ_ONLY)
def echo(text: str) -> str:
    return f"echo: {text}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="示例 MCP Server（stdio）")
    parser.add_argument(
        "--notes-dir",
        default="./notes",
        help="便签存放目录，不存在会自动创建",
    )
    args = parser.parse_args(argv)

    notes_dir = Path(args.notes_dir).expanduser().resolve()
    notes_dir.mkdir(parents=True, exist_ok=True)

    # 通过闭包注入配置：MCP Server 是常驻进程，配置在启动时确定即可
    global _notes_dir
    _notes_dir = lambda: notes_dir  # noqa: E731

    print(f"[sample-mcp] 便签目录: {notes_dir}", file=sys.stderr)
    server.run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

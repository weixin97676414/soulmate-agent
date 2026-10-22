














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



READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True)

server = MCPServer(name="sample-tools", version="1.0.0", instructions=INSTRUCTIONS)


NOTES_DIR: Path = Path("./notes")


def _resolve(name: str) -> Path:

    cleaned = (name or "").strip()
    if not cleaned:
        raise ToolError("便签名不能为空")
    if any(ch in cleaned for ch in ("/", "\\", "..")):
        raise ToolError("便签名不能包含路径分隔符")

    root = NOTES_DIR.resolve()
    target = (root / f"{cleaned}.md").resolve()
    if target.parent != root:
        raise ToolError("便签路径越界")
    return target


@server.tool(description="列出所有便签的名称与最后修改时间。只读操作。", annotations=READ_ONLY)
def list_notes() -> str:
    root = NOTES_DIR
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
        available = ", ".join(sorted(p.stem for p in NOTES_DIR.glob("*.md"))) or "（无）"
        
        
        
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
    global NOTES_DIR

    parser = argparse.ArgumentParser(prog="mcp-sample", description="示例 MCP Server（stdio）")
    parser.add_argument(
        "--notes-dir",
        default="./notes",
        help="便签存放目录，不存在会自动创建",
    )
    args = parser.parse_args(argv)

    NOTES_DIR = Path(args.notes_dir).expanduser().resolve()
    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    
    print(f"[sample-mcp] 便签目录: {NOTES_DIR}", file=sys.stderr)
    server.run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

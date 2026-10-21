
















from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

INSTRUCTIONS = (
    "查询应用自己的本地数据库（会话、消息、群记录、记账、提醒、用量、审计等的所在处）。"
    "**只读**：只能 SELECT，增删改会在数据库层被直接拒绝。"
)

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True)




MAX_CELL = 500


MAX_ROWS = 200


DB_PATH: Path = Path("./agent.db")






_ALLOWED_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_FUNCTION,
    }
)


_ALLOWED_STARTS = frozenset({"SELECT", "WITH", "PRAGMA"})

server = MCPServer(name="app-sqlite", version="1.0.0", instructions=INSTRUCTIONS)


def _authorizer(action: int, *_args: Any) -> int:





    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def _connect() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        raise ToolError(f"数据库文件还不存在：{DB_PATH}（应用还没产生过数据）")
    
    
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True, timeout=5.0)
    conn.set_authorizer(_authorizer)
    conn.row_factory = sqlite3.Row
    return conn


@server.tool(
    description="列出数据库里有哪些表、各自有多少条记录。只读操作。",
    annotations=READ_ONLY,
)
def list_tables() -> str:
    with closing(_connect()) as conn:
        names = [
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        if not names:
            return "（数据库里还没有表）"
        lines = []
        for name in names:
            
            
            count = conn.execute(f'SELECT COUNT(*) AS n FROM "{name}"').fetchone()["n"]
            lines.append(f"- {name}（{count} 条）")
    return "\n".join(lines)


@server.tool(
    description=(
        "执行一条**只读** SQL（SELECT / WITH / PRAGMA）。"
        "增删改会被直接拒绝；一次只能执行一条语句。"
    ),
    annotations=READ_ONLY,
)
def query(sql: str) -> str:
    statement = (sql or "").strip().rstrip(";").strip()
    if not statement:
        raise ToolError("SQL 不能为空。")
    
    
    if ";" in statement:
        raise ToolError("一次只能执行一条语句（请去掉分号后面那些）。")
    head = statement.lstrip("(").split(None, 1)[0].upper()
    if head not in _ALLOWED_STARTS:
        raise ToolError(
            f"只允许查询语句（SELECT / WITH / PRAGMA），收到的是 {head or '空'}。"
            "这个工具是只读的。"
        )

    with closing(_connect()) as conn:
        try:
            cursor = conn.execute(statement)
            rows = cursor.fetchmany(MAX_ROWS)
            
            columns = [str(item[0]) for item in (cursor.description or [])]
        except sqlite3.DatabaseError as exc:
            raise ToolError(f"SQL 执行失败：{exc}") from exc

    if not rows:
        return "（查询没有返回任何行）"

    lines = [" | ".join(columns), "-" * 24]
    for row in rows:
        cells = []
        for value in row:
            text = "" if value is None else str(value)
            if len(text) > MAX_CELL:
                text = text[:MAX_CELL] + "…（已截断）"
            
            cells.append(text.replace("\n", " "))
        lines.append(" | ".join(cells))
    if len(rows) >= MAX_ROWS:
        
        lines.append(f"…（只显示前 {MAX_ROWS} 行，结果可能更多；请用 LIMIT / WHERE 收窄）")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    global DB_PATH

    parser = argparse.ArgumentParser(prog="mcp-sqlite", description="SQLite 只读查询 MCP Server")
    parser.add_argument("--db-path", default="./agent.db", help="要查询的 SQLite 数据库文件")
    args = parser.parse_args(argv)

    DB_PATH = Path(args.db_path).expanduser().resolve()

    
    print(f"[sqlite-mcp] 只读查询: {DB_PATH}", file=sys.stderr)
    server.run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""随应用分发的 SQLite **只读**查询 MCP Server（官方 Python SDK，stdio 传输）。

## 为什么自己写一个，而不是用社区的 `mcp-server-sqlite`

1. **零额外体积**：标准库 `sqlite3` 就够了。社区那个包要用 `uvx` 现下载，而 `uv`
   不随我们分发（实测大多数机器都没装）—— 那个预设因此**开箱必报错**；
2. **能真的保证只读**：社区包的写能力只能靠"文档建议用户别写"。而让 AI 拿着写权限
   去改我们自己的会话表、审计日志、用量记录，是**不可接受**的默认值 ——
   那些表坏掉之后用户根本查不回来。这里用 `mode=ro` 打开，写操作在 SQLite 层就被拒；
3. **查询有双层护栏**：SQL 文本先按语句类型白名单筛一遍，连接上再挂 `authorizer`
   挡一道。两层的失效原因不同，同时漏掉的概率远小于任一层单独漏掉。

⚠️ 与 `sample_server.py` 同一套路：打包成 exe 之后没有独立的 Python 解释器，
所以由 `agent-core.exe mcp-sqlite` 这个子命令在同一份二进制里启动它
（见 ``my_agent/__main__.py`` 与 ``presets.sqlite_server_args``）。
"""

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

#: 单个字段最多返回多少字符。超了截断并**写明已截断**。
#: 宁可给一个诚实的截断结果，也不要把几万字灌进对话 —— 它会吃掉上下文，
#: 而用户其实只想看其中一行。
MAX_CELL = 500

#: 一次最多返回多少行。防手滑用的，不是能力上限（要更多请自己加 LIMIT）。
MAX_ROWS = 200

#: 数据库文件路径，由 main() 在启动时确定
DB_PATH: Path = Path("./agent.db")

#: 允许的 SQLite authorizer 动作码 —— 只有"读"三件套。
#:
#: ⚠️ 必须放行 `SQLITE_FUNCTION`：`count()` / `sum()` / `max()` 这类聚合都走它，
#: 挡了的话最常用的统计查询会直接报错（而它明明只是读）。
#: 写（INSERT / UPDATE / DELETE / DDL）与 ATTACH 等一律不在表里，即被拒绝。
_ALLOWED_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_FUNCTION,
    }
)

#: 只放行的语句开头。`WITH` 是给 CTE 用的（`WITH x AS (...) SELECT ...` 是纯读）。
_ALLOWED_STARTS = frozenset({"SELECT", "WITH", "PRAGMA"})

server = MCPServer(name="app-sqlite", version="1.0.0", instructions=INSTRUCTIONS)


def _authorizer(action: int, *_args: Any) -> int:
    """第二道防线：把非读操作全部拒掉。

    ⚠️ 与 `mode=ro` 是**互补**关系，不是重复：
    `mode=ro` 依赖连接串拼对，这里是逐动作的逻辑判断 —— 两者的失效原因不同。
    """
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def _connect() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        raise ToolError(f"数据库文件还不存在：{DB_PATH}（应用还没产生过数据）")
    # ⚠️ `mode=ro` = 只读打开。就算上面的 authorizer 被绕过，SQLite 自己也会
    # 拒绝任何写操作。`uri=True` 才能用这种查询串。
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
            # ⚠️ 表名来自 sqlite_master（不是用户输入），但这里仍然加双引号 ——
            # 万一将来有人把用户输入接到这段上，不至于当场变成注入点。
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
    # ⚠️ 挡多条语句（`...; DROP TABLE ...`）：authorizer 也能挡，但在这里先拦掉
    # 报错更清楚（"一次只能执行一条"比"not authorized"可读得多）。
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
            # ⚠️ 必须在连接关掉**之前**取列名：Cursor 活不过 Connection。
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
            # 换行会把表格撑散，压成空格
            cells.append(text.replace("\n", " "))
        lines.append(" | ".join(cells))
    if len(rows) >= MAX_ROWS:
        # 如实说明"被截了" —— 不吭声的话用户会以为"就这么多"，然后据此得出错误结论
        lines.append(f"…（只显示前 {MAX_ROWS} 行，结果可能更多；请用 LIMIT / WHERE 收窄）")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    global DB_PATH

    parser = argparse.ArgumentParser(prog="mcp-sqlite", description="SQLite 只读查询 MCP Server")
    parser.add_argument("--db-path", default="./agent.db", help="要查询的 SQLite 数据库文件")
    args = parser.parse_args(argv)

    DB_PATH = Path(args.db_path).expanduser().resolve()

    # stdout 是 MCP 的协议通道，任何调试输出都必须走 stderr，否则会污染握手
    print(f"[sqlite-mcp] 只读查询: {DB_PATH}", file=sys.stderr)
    server.run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

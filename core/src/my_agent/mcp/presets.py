"""MCP 配置的默认值与「快速添加」预设。

预设分两类，这个区分对首次体验很关键：

- **免下载的本地服务**：随应用一起提供，双击就能连上看到效果 —— 不需要 Node、
  不需要网络、不需要 uv。用户第一次点开「MCP 服务」页签时应该立刻看到"能用"，
  而不是先被 npx / uvx 的安装失败劝退；
- ~~社区常用 Server~~：⚠️ 2026-10-06 **全部剔除**（见下）。

## 为什么把 npx / uvx 那三个预设都拿掉了

它们都要靠 `npx` / `uvx` 现下载，而 **uv 不随我们分发**（实测大多数机器都没装），
「SQLite 查询」因此**开箱必报错** —— 用户看到的是一个红点，只会当成我们的 bug。

逐个说：

- **文件系统**：能力已被内置技能覆盖（`skill/builtin/file_tools.py`），而且技能那套
  受**文件访问白名单**（``PathPolicy``）约束 —— 比 MCP 那版更符合本项目的安全模型；
- **Everything（测试用）**：纯协议演示，对用户没有实用价值；至于"验证 MCP 通路能不能
  连上"这件事，「本地示例服务」本来就能承担；
- **SQLite 查询**：**能力保留了，但换成自带的实现**（见 ``sqlite_server.py``）——
  零额外体积（标准库 `sqlite3`）、开箱即用，而且**能真的保证只读**
  （社区那版只能靠"文档建议用户别写"，而它查的正是我们自己的会话表与审计日志）。
"""

from __future__ import annotations

import sys

from ..config.paths import AppPaths
from ..config.schemas import McpServerConfig

#: 自带 SQLite 服务的名字。刻意沿用旧的 ``sqlite``：老配置里若已有同名条目，
#: 用户升级后会被这里的新命令覆盖，而不是多出一个连不上的僵尸服务。
SQLITE_SERVER_NAME = "sqlite"


def sample_server_args(paths: AppPaths) -> list[str]:
    """示例服务的启动参数。

    **开发与打包要走两条不同的路**：源码环境下用 ``python -m`` 直接跑模块；
    打包后没有 Python 解释器，改由 ``agent-core.exe mcp-sample`` 这个子命令
    在同一份二进制里启动（见 ``my_agent/__main__.py`` 的分发逻辑）。

    如果不做这个区分，冻结环境里 ``sys.executable`` 就是 agent-core.exe 本身，
    启动示例服务会变成把 Agent 核心再拉一遍——表现为"点了没反应/端口被占"。
    """
    notes_dir = paths.workspace_dir / "mcp-notes"
    if getattr(sys, "frozen", False):
        return ["mcp-sample", "--notes-dir", str(notes_dir)]
    return ["-m", "my_agent.mcp.sample_server", "--notes-dir", str(notes_dir)]


def build_sample_server(paths: AppPaths) -> McpServerConfig:
    """构建「本地示例服务」配置。

    示例服务随应用分发（在包内），因此**永远可用**，不需要探测文件是否存在——
    早先放在 `examples/` 目录时打包后探测不到，界面上就会少一个预设项。
    """
    return McpServerConfig(
        name="sample",
        command=sys.executable,
        args=sample_server_args(paths),
        description="随应用附带的示例服务：不联网、无需额外安装，用于验证 MCP 链路是否通畅。",
        timeout=30.0,
    )


def sqlite_server_args(paths: AppPaths) -> list[str]:
    """自带 SQLite 服务的启动参数。

    与 :func:`sample_server_args` 同一套路：源码环境走 ``python -m``，
    冻结环境走 ``agent-core.exe mcp-sqlite`` 子命令 —— 打包后没有独立解释器，
    ``sys.executable`` 就是 agent-core.exe 本身。
    """
    if getattr(sys, "frozen", False):
        return ["mcp-sqlite", "--db-path", str(paths.db_file)]
    return ["-m", "my_agent.mcp.sqlite_server", "--db-path", str(paths.db_file)]


def build_sqlite_server(paths: AppPaths) -> McpServerConfig:
    """构建「数据库查询（只读）」配置 —— 随应用分发，因此永远可用。

    ``auto_start`` 显式写 True（``McpServerConfig`` 的默认值也是 True，见
    ``config/schemas.py``）：产品要求它"随应用自动开启"。
    写出来是为了让**这是刻意的**这件事留在代码里 —— 默认值将来若被改动，
    这里不会跟着悄悄变。
    """
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
    """返回「快速添加」列表。每项含 ``requires`` 字段，供界面提示依赖。"""
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

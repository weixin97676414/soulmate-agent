"""``utils/http.py`` 的回归测试。

锁住的是一个**真实发生过的性能事故**：Windows 上每创建一个 SSL 上下文约 500ms，
而 ``httpx.AsyncClient()`` 默认每次都新建一个。于是

- 「保存模型」重建全部适配器 → 几个模型就付几次（实测 3 个模型 = 1457ms）；
- 内置天气查询、自定义 HTTP 技能、技能包下载、助手集市 → 每调用一次付一次；

而且它是**同步**的，会把整个事件循环一起堵住，表现为"毫不相干的本地接口
（例如 MCP 列表）突然要转很久"。

修复是所有构造点统一走 ``utils/http.async_client()``，共享一个进程级
SSL 上下文（实测 3 个客户端 1457ms → 0.7ms）。

这里用两条测试守住它：
1. 上下文确实只建一次（同一对象）；
2. **生产代码里不允许再出现裸的 ``httpx.AsyncClient(``**（静态扫描源码树）。
"""

from __future__ import annotations

import re
from pathlib import Path

from my_agent.utils.http import async_client, shared_ssl_context

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "my_agent"

# 唯一允许直接构造 httpx 客户端的地方（它自己就是那个"统一入口"）
ALLOWED = {"utils/http.py"}

# 去掉注释与文档字符串后再扫，避免文档里的示例代码被误判成真实调用。
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_STRING_LITERAL = re.compile(r'"""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\'', re.S)
_LINE_COMMENT = re.compile(r"#.*$", re.M)


def _strip_non_code(source: str) -> str:
    """去掉文档字符串与注释，只留下会真正执行的代码。"""
    without_docstrings = _STRING_LITERAL.sub("", source)
    without_blocks = _BLOCK_COMMENT.sub("", without_docstrings)
    return _LINE_COMMENT.sub("", without_blocks)


def test_shared_ssl_context_is_built_once() -> None:
    """同一进程内必须是同一个对象 —— 这正是"只付一次 500ms"的关键。"""
    assert shared_ssl_context() is shared_ssl_context()


def test_creating_many_clients_is_cheap() -> None:
    """连续建 5 个客户端必须很快。

    这是一条**行为断言**，直接对准用户能感知的那个属性（建客户端很便宜），
    而不是去读 httpx 的内部属性。

    裸建 5 个客户端在本机实测约 2.5 秒（每个约 500ms）；
    共享上下文之后 5 个合计不到 1ms。阈值取 1 秒 —— 与失败态（≥2.5s）
    之间还有 2.5 倍余量，不会因为 CI 机器慢而误报。
    """
    import asyncio
    import time

    shared_ssl_context()  # 预热：允许第一次付出构建成本

    started = time.perf_counter()
    clients = [async_client(timeout=1.0) for _ in range(5)]
    elapsed = time.perf_counter() - started
    for client in clients:
        asyncio.run(client.aclose())

    assert elapsed < 1.0, (
        f"建 5 个 httpx 客户端花了 {elapsed * 1000:.0f} ms —— "
        "说明没有复用共享 SSL 上下文（每次新建约 500ms）"
    )


def test_no_bare_httpx_client_in_production_code() -> None:
    """生产代码里不允许直接写 ``httpx.AsyncClient(``。

    绕开工厂 = 每次网络调用都把证书库重新加载一遍（Windows 约 500ms）。
    这个错误**不会报错、只是慢**，所以只能靠静态检查守住。
    """
    offenders: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        relative = path.relative_to(SRC_ROOT).as_posix()
        if relative in ALLOWED:
            continue
        # ⚠️ `resources/` 下装的是**第三方技能包**（含它们自带的 Python 脚本），
        # 那些不是我们的代码、也不经过我们的网络工厂 —— 扫进来只会误报。
        # 与 `pyproject.toml` 里 ruff 的 `extend-exclude` 是同一个口径
        # （加出厂技能时发现的）。
        if relative.startswith("resources/"):
            continue
        code = _strip_non_code(path.read_text(encoding="utf-8"))
        if "httpx.AsyncClient(" in code:
            offenders.append(relative)

    assert not offenders, (
        "以下文件绕开了 utils/http.async_client()，会在每次网络调用时"
        f"重新构建 SSL 上下文（Windows 约 500ms）：{offenders}"
    )

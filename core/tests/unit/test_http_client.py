


















from __future__ import annotations

import re
from pathlib import Path

from my_agent.utils.http import async_client, shared_ssl_context

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "my_agent"


ALLOWED = {"utils/http.py"}


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_STRING_LITERAL = re.compile(r'"""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\'', re.S)
_LINE_COMMENT = re.compile(r"#.*$", re.M)


def _strip_non_code(source: str) -> str:

    without_docstrings = _STRING_LITERAL.sub("", source)
    without_blocks = _BLOCK_COMMENT.sub("", without_docstrings)
    return _LINE_COMMENT.sub("", without_blocks)


def test_shared_ssl_context_is_built_once() -> None:

    assert shared_ssl_context() is shared_ssl_context()


def test_creating_many_clients_is_cheap() -> None:









    import asyncio
    import time

    shared_ssl_context()  

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





    offenders: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        relative = path.relative_to(SRC_ROOT).as_posix()
        if relative in ALLOWED:
            continue
        
        
        
        
        if relative.startswith("resources/"):
            continue
        code = _strip_non_code(path.read_text(encoding="utf-8"))
        if "httpx.AsyncClient(" in code:
            offenders.append(relative)

    assert not offenders, (
        "以下文件绕开了 utils/http.async_client()，会在每次网络调用时"
        f"重新构建 SSL 上下文（Windows 约 500ms）：{offenders}"
    )

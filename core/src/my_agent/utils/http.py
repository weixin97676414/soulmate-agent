"""HTTP 客户端的统一入口。

## 为什么需要这个文件（一次真实的性能事故）

Windows 上**每创建一个 SSL 上下文约 500 ms**（要加载系统证书库），而
``httpx.AsyncClient()`` 默认**每次都新建一个**。本机实测（0.1.10）：

| 操作 | 耗时 |
|---|---|
| ``ssl.create_default_context()`` | 31 ms |
| ``httpx.AsyncClient()`` × 1 | 517 ms |
| ``httpx.AsyncClient()`` × 3 | 1457 ms |
| ``httpx.AsyncClient(verify=<共享上下文>)`` × 3 | **0.7 ms** |

这 ~500ms / 次的开销原本散落在**每一处网络调用**上：

- 「保存模型」→ ``reload_models`` 重建**全部**适配器 → 几个模型就付几次，
  而且它**同步阻塞整个事件循环** → 连 MCP 列表这种纯内存接口都会被拖慢；
- 「测试连通性」/「同步模型」→ 每次一个；
- 内置的**天气查询**、**自定义 HTTP 技能**、技能包下载、助手集市 → 每调用一次付一次。

修复方式：**进程级共享一个 SSL 上下文**，并让所有构造点都走本模块的
``async_client()``。

## 用法

```python
from ...utils.http import async_client

async with async_client(timeout=10.0) as client:
    response = await client.get(url)
```

**不要**再直接写 ``httpx.AsyncClient(...)``：那样等于每次调用都把证书库
重新加载一遍。如果需要自定义信任配置，请给 ``shared_ssl_context()`` 传参数
而不是绕开它。
"""

from __future__ import annotations

import logging
import ssl
from functools import lru_cache
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def shared_ssl_context() -> ssl.SSLContext:
    """取（并缓存）进程级共享的 SSL 上下文。

    第一次调用付出那 ~0.5s 的代价，之后零成本。用 ``lru_cache`` 而不是模块级
    变量，是为了让"只建一次"由标准库保证，而不是靠 `if x is None` 的约定
    （后者在多线程首次并发调用时会重复构建）。
    """
    context = ssl.create_default_context()
    # 显式加载系统信任根：某些 Windows 环境下 ``create_default_context()``
    # 只带上 OpenSSL 自带的默认路径，缺了系统证书库里的企业根证书。
    context.load_default_certs()
    logger.debug("已构建共享 SSL 上下文（进程内只做一次）")
    return context


def async_client(**kwargs: Any) -> httpx.AsyncClient:
    """构造 ``httpx.AsyncClient`` 的统一入口，自动复用共享 TLS 上下文。

    只共享**证书信任配置**，不共享连接池 —— 各调用点的 base_url / 超时 /
    代理设置依然彼此独立。
    """
    kwargs.setdefault("verify", shared_ssl_context())
    return httpx.AsyncClient(**kwargs)

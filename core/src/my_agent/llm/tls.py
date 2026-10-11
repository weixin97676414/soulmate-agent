"""进程级共享的 TLS 配置。

## 为什么需要这个文件

Windows 上**每创建一个 SSL 上下文约 500 ms**（要加载系统证书库 / CA 包），
而 ``httpx.AsyncClient()`` 默认**每次都新建一个**。实测（本机 0.1.10）：

| 操作 | 耗时 |
|---|---|
| ``ssl.create_default_context()`` | 31 ms |
| ``httpx.AsyncClient()`` × 1 | 517 ms |
| ``httpx.AsyncClient()`` × 3 | 1457 ms |
| ``httpx.AsyncClient(verify=<共享上下文>) × 3`` | **0.7 ms** |

这个开销原本落在两条**用户天天走**的路径上：

- 「保存模型」→ ``reload_models`` 会**重建全部**适配器 → 有几个模型就付几次；
- 「测试连通性」/「同步模型」→ 每次都要建一个。

而且它是**同步**的，会把整个事件循环一起堵住 —— 于是一个本该毫秒级的本地接口
（例如 MCP 列表）也会被拖成"转很久"。所以共享一个上下文不只是省时间，
它消掉的是一类"毫不相干的接口突然变慢"的故障。

**注意**：只共享**上下文**，不共享连接池。每个适配器的 ``httpx.AsyncClient``
仍然是独立的（各自的 base_url / 超时 / 代理设置都不同），只是复用同一份
证书信任配置。
"""

from __future__ import annotations

import logging
import ssl
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def shared_ssl_context() -> ssl.SSLContext:
    """取（并缓存）进程级共享的 SSL 上下文。

    第一次调用会付出那 ~0.5s 的代价，之后是零成本。用 ``lru_cache`` 而不是模块级
    变量，是为了让"只建一次"这件事由标准库保证，而不是靠 `if x is None` 的约定。
    """
    context = ssl.create_default_context()
    # 显式加载系统信任根：某些 Windows 环境下 ``create_default_context()``
    # 只带上了 OpenSSL 自带的默认路径，缺了系统证书库里的企业根证书。
    context.load_default_certs()
    logger.debug("已构建共享 SSL 上下文（进程内只做一次）")
    return context

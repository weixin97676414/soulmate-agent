





































from __future__ import annotations

import logging
import ssl
from functools import lru_cache
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def shared_ssl_context() -> ssl.SSLContext:






    context = ssl.create_default_context()
    
    
    context.load_default_certs()
    logger.debug("已构建共享 SSL 上下文（进程内只做一次）")
    return context


def async_client(**kwargs: Any) -> httpx.AsyncClient:





    kwargs.setdefault("verify", shared_ssl_context())
    return httpx.AsyncClient(**kwargs)

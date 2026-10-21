


























from __future__ import annotations

import ipaddress
import logging
from urllib.parse import urlparse

from ..errors import ConfigError

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = ("http", "https")


_BLOCKED_HOSTS = frozenset(
    {
        "169.254.169.254",  
        "169.254.170.2",  
        "100.100.100.200",  
        
        
        
        "fd00:ec2::254",
        "metadata.google.internal",
        "metadata",
        "metadata.goog",
    }
)


def validate_endpoint(url: str, *, field: str = "base_url") -> str:





    raw = (url or "").strip()
    if not raw:
        raise ConfigError(f"{field} 不能为空")

    parsed = urlparse(raw)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ConfigError(
            f"{field} 只支持 http/https，当前是「{parsed.scheme or '空'}」：{raw}"
        )

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ConfigError(f"{field} 缺少主机名：{raw}")

    if host in _BLOCKED_HOSTS:
        logger.warning("已拦截指向云元数据服务的端点：%s", raw)
        raise ConfigError(
            f"出于安全考虑，不允许把 {field} 指向云元数据服务（{host}）。"
            "请填写真实的模型服务地址。"
        )

    
    
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return raw

    
    
    
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped

    if address.is_link_local:
        logger.warning("已拦截指向链路本地地址的端点：%s", raw)
        raise ConfigError(
            f"出于安全考虑，不允许把 {field} 指向链路本地地址（{host}）。"
        )
    if address.is_multicast or address.is_unspecified:
        raise ConfigError(f"{field} 指向了一个无效地址：{host}")

    return raw

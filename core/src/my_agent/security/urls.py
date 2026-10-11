"""对外部端点 URL 的校验（SSRF 收口）。

## 背景

模型配置里的 ``base_url`` 来自**请求体**（"添加服务商"、连通性测试、模型发现），
而服务端会按它发起 HTTP 请求并把结果（模型列表、错误信息）返回给调用方 ——
这是一个典型的 SSRF 形态。

## 为什么不干脆禁止内网

因为**本机模型是一等功能**：Ollama 默认就在 ``http://127.0.0.1:11434``，
LM Studio、vLLM 同理。一刀切拦掉私有网段，用户第一个下午就会遇到
"我本地明明跑着 Ollama，为什么填不进去"。

所以这里采取的是**精准拦截**：只挡掉那些"被访问到就等于失陷"的目标，
其余交给上游的鉴权与回环来源校验。

## 真正的灾难目标

云厂商的元数据服务（``169.254.169.254`` 等）会给**任何**能访问到它的进程
签发临时凭证。一旦被诱导访问并把响应回显出来，等于直接把云账号交出去。
它同时也是唯一一类"访问本身即造成损失"的内网地址，所以值得单独拦。

附带挡掉非 http(s) 协议：``file://`` 能让服务端读本地文件，
``gopher://`` / ``dict://`` 常被用来构造更复杂的探测链。
"""

from __future__ import annotations

import ipaddress
import logging
from urllib.parse import urlparse

from ..errors import ConfigError

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = ("http", "https")

# 云元数据服务。命中即拒绝，且**不做例外** —— 没有任何正当的模型端点在这里。
_BLOCKED_HOSTS = frozenset(
    {
        "169.254.169.254",  # AWS / GCP / Azure / 阿里云 / 腾讯云 通用
        "169.254.170.2",  # AWS ECS 任务角色
        "100.100.100.200",  # 阿里云
        # ⚠️ 元数据服务的 **IPv6** 地址。它是 ULA（fd00::/8）而**不是** link-local，
        # 所以下面的 `is_link_local` 判断抓不到它 —— 漏掉这一条等于留了一扇后门：
        # 只要把地址写成 IPv6 形式就能读到机器的临时凭证。
        "fd00:ec2::254",
        "metadata.google.internal",
        "metadata",
        "metadata.goog",
    }
)


def validate_endpoint(url: str, *, field: str = "base_url") -> str:
    """校验一个用户提供的端点地址。不合法时抛 ``ConfigError``。

    返回原值（便于链式使用），不做规范化 —— 规范化会掩盖用户填错的部分，
    而这里的目标是"拒绝危险输入"，不是"猜测用户想填什么"。
    """
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

    # 同义写法（例如 169.254.169.254 的十进制/八进制变体）解析后仍是同一个 IP，
    # 所以对能解析成 IP 的主机再做一次 link-local 判断
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return raw

    # IPv4 映射形式的 IPv6（``::ffff:169.254.169.254``）要**按它里面的 IPv4 判断**：
    # 不展开的话，这个"看起来是 IPv6"的写法能绕过上面全部检查，
    # 而内核照样把它路由到 169.254.169.254。
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

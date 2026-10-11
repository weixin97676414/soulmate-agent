"""密钥的注入与剥离。

## 分工

密钥的**保管**由 Electron 主进程负责：它用 `safeStorage`（Windows 上就是 DPAPI，
按当前用户加密）把密钥写进 `secrets.bin`。Python 侧既不加密也不落盘，只做两件事：

1. **启动时注入**：Electron 把解密后的密钥写进一个临时文件，把路径通过
   ``AGENT_SECRETS_FILE`` 传给本进程；本进程读取后**立刻删除该文件**，
   再把密钥叠加到内存里的配置上（``apply_secrets``）；
2. **保存时剥离**：任何写配置文件的路径都把密钥字段清空（``strip_secrets``），
   这样磁盘上永远只有空字符串。

## 为什么用「临时文件 + 环境变量」而不是直接塞进环境变量

环境变量会被子进程继承——而本进程会 spawn MCP Server（``env={**os.environ, ...}``），
密钥会直接漏给第三方进程。传路径就没这个问题：文件读完即删，且只有本进程知道路径。

## 为什么注入要发生在很早的阶段

``AppRuntime`` 构造时会用配置里的 Key 建 LLM 注册表、建 MCP 管理器（后者持有
配置对象的引用）。注入必须排在这些动作之前，否则加载到的是空 Key。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ENV_SECRETS_FILE = "AGENT_SECRETS_FILE"


@dataclass
class Secrets:
    """从 Electron 侧拿到的密钥集合。"""

    # 模型 id -> API Key
    models: dict[str, str] = field(default_factory=dict)
    # MCP 服务名 -> 该服务的环境变量（可能含访问令牌）
    mcp: dict[str, dict[str, str]] = field(default_factory=dict)
    # 外部集成的凭据：能力名 -> 凭据字段（例如 {"calendar": {"password": "..."}}）。
    #
    # 为什么单独一段而不是塞进 mcp：``mcp`` 的键会被注入到第三方 MCP 进程的
    # 环境变量里（见 apply_secrets），把日历密码放进去等于**顺手泄漏给第三方**。
    integrations: dict[str, dict[str, str]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.models and not self.mcp and not self.integrations

    def to_dict(self) -> dict[str, Any]:
        return {
            "models": dict(self.models),
            "mcp": {k: dict(v) for k, v in self.mcp.items()},
            "integrations": {k: dict(v) for k, v in self.integrations.items()},
        }


def parse_secrets(raw: Any) -> Secrets:
    """把外部传入的 JSON 结构收敛成 ``Secrets``，脏数据一律忽略。

    这个函数的输入来自另一个进程，不能假设它一定合法——宁可少注入几个 Key，
    也不能因为格式问题让整个应用起不来。
    """
    if not isinstance(raw, dict):
        return Secrets()

    models: dict[str, str] = {}
    raw_models = raw.get("models")
    if isinstance(raw_models, dict):
        for key, value in raw_models.items():
            if isinstance(key, str) and isinstance(value, str) and value:
                models[key] = value

    mcp: dict[str, dict[str, str]] = {}
    raw_mcp = raw.get("mcp")
    if isinstance(raw_mcp, dict):
        for server, env in raw_mcp.items():
            if not isinstance(server, str) or not isinstance(env, dict):
                continue
            cleaned = {
                str(k): str(v) for k, v in env.items() if isinstance(v, (str, int, float, bool))
            }
            if cleaned:
                mcp[server] = cleaned

    integrations: dict[str, dict[str, str]] = {}
    raw_integrations = raw.get("integrations")
    if isinstance(raw_integrations, dict):
        for name, fields in raw_integrations.items():
            if not isinstance(name, str) or not isinstance(fields, dict):
                continue
            cleaned_integration = {
                str(k): str(v) for k, v in fields.items() if isinstance(v, (str, int, float, bool))
            }
            if cleaned_integration:
                integrations[name] = cleaned_integration

    return Secrets(models=models, mcp=mcp, integrations=integrations)


def read_secrets_file(path: str | Path | None) -> Secrets | None:
    """读取密钥文件，**读取后立即删除**。

    **返回 None 表示「密钥不由外部托管」**（没传路径），调用方据此决定要不要
    在保存配置时剥离密钥字段。这个区分很关键：独立运行后端（开发调试、CLI）
    时没有 safeStorage 可用，此时若照样剥离，用户的 Key 会在下次保存时静默消失。

    删除是刻意放在这里而不是调用方：文件的存在窗口越短越好，
    哪怕是异常路径也要保证它不会留在磁盘上被后续进程读到。
    """
    if not path:
        return None

    file_path = Path(path)
    raw: Any = {}
    try:
        if file_path.is_file():
            raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # ValueError 必须显式列进来：文件里出现非法 UTF-8 字节时
        # ``read_text`` 抛的是 ``UnicodeDecodeError``，它是 ValueError 的子类、
        # **不是** OSError。漏掉它的后果不是"密钥读不到"，而是**进程直接起不来** ——
        # 一个损坏的临时文件就能让整个应用打不开，用户完全无从下手。
        # （JSONDecodeError 同样是 ValueError 子类，一并覆盖。）
        logger.warning("密钥文件读取失败，将按未提供处理: %s", exc)
    finally:
        # 无论成功失败都要删掉；失败也不该阻断启动
        try:
            file_path.unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover - 极端情况
            logger.warning("密钥文件删除失败: %s", exc)

    secrets = parse_secrets(raw)
    logger.info(
        "已注入 %s 个模型密钥、%s 个 MCP 服务密钥", len(secrets.models), len(secrets.mcp)
    )
    return secrets


def apply_secrets(config: Any, secrets: Secrets) -> None:
    """把密钥叠加到配置对象上（仅内存，不落盘）。"""
    if secrets.is_empty():
        return

    for spec in getattr(config.models, "models", []):
        key = secrets.models.get(spec.id)
        if key:
            spec.api_key = key

    for server in getattr(config.mcp, "servers", []):
        extra = secrets.mcp.get(server.name)
        if extra:
            server.env.update(extra)

    # 外部集成：目前只有日历（CalDAV 密码）。
    # 只往**我们自己的配置对象**上叠加，绝不进任何子进程的环境变量。
    calendar_secrets = secrets.integrations.get("calendar") or {}
    if calendar_secrets.get("password"):
        settings = getattr(config, "settings", None)
        if settings is not None and getattr(settings, "calendar", None) is not None:
            settings.calendar.caldav_password = calendar_secrets["password"]


def is_secret_key(name: str) -> bool:
    """按名字判断一个环境变量是不是密钥。

    只剥离**看起来是密钥**的那些，而不是把整个 env 清空：
    像 ``LOG_LEVEL=debug`` 这种普通配置留在 mcp.json 里更透明，
    也让"secrets.bin 丢了"不至于把 MCP 的整份配置一起带走。
    """
    lowered = (name or "").lower()
    return any(
        token in lowered
        for token in ("key", "token", "secret", "password", "passwd", "credential", "auth")
    )


def strip_secrets(config: Any) -> dict[str, Any]:
    """产出**用于落盘**的配置副本：所有密钥字段清空。

    调用方仍需传入内存中的完整配置（``apply_secrets`` 已经注入过），
    这里只负责生成"可以安全写进磁盘"的那一份。
    """
    models_dump = config.models.model_dump(mode="json")
    for spec in models_dump.get("models", []):
        spec["api_key"] = ""

    mcp_dump = config.mcp.model_dump(mode="json")
    for server in mcp_dump.get("servers", []):
        env = server.get("env") or {}
        server["env"] = {k: v for k, v in env.items() if not is_secret_key(k)}

    settings_dump = config.settings.model_dump(mode="json")
    calendar_dump = settings_dump.get("calendar") or {}
    # 日历密码与模型 Key 同规则：内存里有、磁盘上永远没有
    calendar_dump["caldav_password"] = ""
    settings_dump["calendar"] = calendar_dump

    return {"models": models_dump, "mcp": mcp_dump, "settings": settings_dump}


__all__ = [
    "ENV_SECRETS_FILE",
    "Secrets",
    "apply_secrets",
    "is_secret_key",
    "parse_secrets",
    "read_secrets_file",
    "strip_secrets",
]

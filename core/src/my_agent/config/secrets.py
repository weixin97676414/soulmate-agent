























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


    
    models: dict[str, str] = field(default_factory=dict)
    
    mcp: dict[str, dict[str, str]] = field(default_factory=dict)
    
    
    
    
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









    if not path:
        return None

    file_path = Path(path)
    raw: Any = {}
    try:
        if file_path.is_file():
            raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        
        
        
        
        
        logger.warning("密钥文件读取失败，将按未提供处理: %s", exc)
    finally:
        
        try:
            file_path.unlink(missing_ok=True)
        except OSError as exc:  
            logger.warning("密钥文件删除失败: %s", exc)

    secrets = parse_secrets(raw)
    logger.info(
        "已注入 %s 个模型密钥、%s 个 MCP 服务密钥", len(secrets.models), len(secrets.mcp)
    )
    return secrets


def apply_secrets(config: Any, secrets: Secrets) -> None:

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

    
    
    calendar_secrets = secrets.integrations.get("calendar") or {}
    if calendar_secrets.get("password"):
        settings = getattr(config, "settings", None)
        if settings is not None and getattr(settings, "calendar", None) is not None:
            settings.calendar.caldav_password = calendar_secrets["password"]


def is_secret_key(name: str) -> bool:






    lowered = (name or "").lower()
    return any(
        token in lowered
        for token in ("key", "token", "secret", "password", "passwd", "credential", "auth")
    )


def strip_secrets(config: Any) -> dict[str, Any]:





    models_dump = config.models.model_dump(mode="json")
    for spec in models_dump.get("models", []):
        spec["api_key"] = ""

    mcp_dump = config.mcp.model_dump(mode="json")
    for server in mcp_dump.get("servers", []):
        env = server.get("env") or {}
        server["env"] = {k: v for k, v in env.items() if not is_secret_key(k)}

    settings_dump = config.settings.model_dump(mode="json")
    calendar_dump = settings_dump.get("calendar") or {}
    
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

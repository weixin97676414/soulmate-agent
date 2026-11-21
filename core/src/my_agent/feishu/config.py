



















from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..config import keystore
from ..config.schemas import FeishuBot, FeishuConfig

if TYPE_CHECKING:  
    from ..config.loader import ConfigStore
    from ..config.paths import AppPaths

logger = logging.getLogger(__name__)

__all__ = [
    "FeishuBot",
    "FeishuConfig",
    "drop_secret",
    "get_secret",
    "load_bots",
    "load_secrets",
    "mask_secret",
    "masked",
    "save_bots",
    "save_secrets",
    "set_secret",
]





def load_bots(store: ConfigStore) -> FeishuConfig:




    return store.load_feishu()


def save_bots(store: ConfigStore, config: FeishuConfig) -> FeishuConfig:
    return store.save_feishu(config)





def load_secrets(paths: AppPaths) -> dict[str, str]:

    path: Path = paths.feishu_secrets_file
    if not path.exists():
        return {}
    try:
        raw = path.read_bytes()
    except OSError as exc:
        logger.warning("读取飞书凭据失败：%s", exc)
        return {}

    if keystore.is_available():
        data = keystore.load_keys(raw)
        if data:
            return {str(k): str(v) for k, v in data.items() if isinstance(v, str) and v}
        
        logger.warning("飞书凭据解密失败（换了 Windows 账户或机器？），尝试按明文读取")

    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("飞书凭据既不是有效密文也不是合法 JSON，按空处理")
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items() if isinstance(v, str) and v}


def save_secrets(paths: AppPaths, secrets: dict[str, str]) -> None:

    path: Path = paths.feishu_secrets_file
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = {k: v for k, v in secrets.items() if v}

    if keystore.is_available():
        blob = keystore.dump_keys(cleaned)
        if blob is not None:
            path.write_bytes(blob)
            return
        logger.warning("飞书凭据加密失败，退回明文存储（与 keystore 降级口径一致）")
    else:
        logger.warning("当前环境没有 DPAPI，飞书凭据将以明文落盘")

    path.write_text(json.dumps(cleaned, ensure_ascii=False), encoding="utf-8")


def get_secret(paths: AppPaths, bot_id: str) -> str:
    return load_secrets(paths).get(bot_id, "")


def set_secret(paths: AppPaths, bot_id: str, secret: str) -> None:





    secrets = load_secrets(paths)
    if secret:
        secrets[bot_id] = secret
    else:
        secrets.pop(bot_id, None)
    save_secrets(paths, secrets)


def drop_secret(paths: AppPaths, bot_id: str) -> None:

    secrets = load_secrets(paths)
    if bot_id in secrets:
        secrets.pop(bot_id)
        save_secrets(paths, secrets)





def masked(bot: FeishuBot, *, has_secret: bool) -> dict[str, Any]:

    return {**bot.model_dump(mode="json"), "has_secret": has_secret}


def mask_secret(secret: str) -> str:




    if not secret:
        return ""
    if len(secret) <= 6:
        return "*" * len(secret)
    return f"{secret[:3]}{'*' * 6}{secret[-3:]}"

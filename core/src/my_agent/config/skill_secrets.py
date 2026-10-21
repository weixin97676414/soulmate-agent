























from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)



ENV_SKILL_SECRETS_FILE = "AGENT_SKILL_SECRETS_FILE"




_MAX_NAME_LEN = 64
_ALLOWED_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)


def is_valid_name(name: str) -> bool:

    if not name or len(name) > _MAX_NAME_LEN:
        return False
    return all(ch in _ALLOWED_CHARS for ch in name)


@dataclass
class SkillSecrets:


    keys: dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.keys

    def get(self, name: str) -> str | None:
        return self.keys.get(name)

    def names(self) -> list[str]:

        return sorted(self.keys)

    def to_dict(self) -> dict[str, Any]:
        return {"keys": dict(self.keys)}


def parse_skill_secrets(raw: Any) -> SkillSecrets:






    if not isinstance(raw, dict):
        return SkillSecrets()

    
    
    
    source = raw.get("keys")
    if not isinstance(source, dict):
        source = raw

    keys: dict[str, str] = {}
    dropped: list[str] = []
    for name, value in source.items():
        if not isinstance(name, str) or not isinstance(value, str) or not value:
            continue
        if not is_valid_name(name):
            dropped.append(name[:32])
            continue
        keys[name] = value
    if dropped:
        
        logger.warning("忽略了 %s 个名字不合法的技能密钥：%s", len(dropped), dropped)
    return SkillSecrets(keys=keys)


def read_skill_secrets_file(path: str | Path | None) -> SkillSecrets | None:








    if not path:
        return None

    file_path = Path(path)
    raw: Any = {}
    try:
        if file_path.is_file():
            raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        
        
        
        logger.warning("技能密钥文件读取失败，将按未提供处理: %s", exc)
    finally:
        try:
            file_path.unlink(missing_ok=True)
        except OSError as exc:  
            logger.warning("技能密钥文件删除失败: %s", exc)

    secrets = parse_skill_secrets(raw)
    logger.info("已注入 %s 个用户给技能的密钥（只记个数，不记内容）", len(secrets.keys))
    return secrets


__all__ = [
    "ENV_SKILL_SECRETS_FILE",
    "SkillSecrets",
    "is_valid_name",
    "parse_skill_secrets",
    "read_skill_secrets_file",
]

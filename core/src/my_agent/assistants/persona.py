





























from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _atomic_write_text(target: Path, content: str) -> None:











    tmp = target.with_name(f".{target.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)


SOUL_FILE = "SOUL.md"
IDENTITY_FILE = "IDENTITY.md"
RULES_FILE = "RULES.md"
MEMORY_FILE = "MEMORY.md"
USER_FILE = "USER.md"





EVOLUTION_LOG_FILE = "进化日志.md"
ALLOWED_FILES: tuple[str, ...] = (
    SOUL_FILE,
    IDENTITY_FILE,
    RULES_FILE,
    MEMORY_FILE,
    USER_FILE,
    EVOLUTION_LOG_FILE,
)



MAX_FILE_BYTES = 32_000

DEFAULT_SOUL_HINT = (
    "# SOUL\n\n"
    "这里写这个助手的人格：它怎么看自己、怎么说话、在意什么。\n"
)



DEFAULT_IDENTITY_HINT = (
    "# IDENTITY · 助手身份\n\n"
    "这里写这个助手的身份：名字、定位、自我介绍。\n"
)



DEFAULT_RULES_HINT = (
    "# RULES · 工作逻辑与规则\n\n"
    "这里写这个助手的工作方式与规矩：先做什么后做什么、什么必须确认、\n"
    "回答要什么风格。助手也可以按你的要求修改（每次修改都会先让你确认）。\n"
)

DEFAULT_MEMORY_HINT = (
    "# MEMORY\n\n"
    "这里写这个助手记得的事：你的偏好、习惯、约定。\n"
    "助手也可以自己往这里补充（每次补充都会先让你确认）。\n"
)




DEFAULT_USER_HINT = (
    "# USER · 关于用户\n\n"
    "这里写关于用户本人的档案：怎么称呼、职业、长期偏好。\n"
    "助手也可以按你的要求往里补充（每次补充都会先让你确认）。\n"
)





DEFAULT_EVOLUTION_LOG_HINT = (
    "# 进化日志\n\n"
    "搭子每周自我进化那一轮自己写这里：改了什么、为什么改、下轮要验证什么。\n"
    "由它自动追加，你也可以直接编辑。\n"
)


def assistant_dir(paths: Any, assistant_id: str) -> Path:

    return Path(paths.data_dir) / "assistants" / assistant_id


def _resolve(paths: Any, assistant_id: str, name: str) -> Path:
    if name not in ALLOWED_FILES:
        raise ValueError(f"不支持的文件名：{name}")
    return assistant_dir(paths, assistant_id) / name


def read_file(paths: Any, assistant_id: str, name: str) -> str:

    target = _resolve(paths, assistant_id, name)
    try:
        return target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        logger.warning("读取助手文件失败 %s/%s：%s", assistant_id, name, exc)
        return ""


def write_file(paths: Any, assistant_id: str, name: str, content: str) -> None:


















    from . import locked_builtins

    locked_builtins.ensure_persona_writable(assistant_id, name)

    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError(
            f"{name} 最多 {MAX_FILE_BYTES // 1000} KB，当前内容超出。"
            "它会被放进每次对话的提示词里，写太长会挤掉真正的对话。"
        )
    target = _resolve(paths, assistant_id, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(target, content)


def list_files(paths: Any, assistant_id: str) -> list[dict[str, Any]]:

    items: list[dict[str, Any]] = []
    hints = {
        SOUL_FILE: DEFAULT_SOUL_HINT,
        IDENTITY_FILE: DEFAULT_IDENTITY_HINT,
        RULES_FILE: DEFAULT_RULES_HINT,
        MEMORY_FILE: DEFAULT_MEMORY_HINT,
        USER_FILE: DEFAULT_USER_HINT,
        EVOLUTION_LOG_FILE: DEFAULT_EVOLUTION_LOG_HINT,
    }
    for name in ALLOWED_FILES:
        target = _resolve(paths, assistant_id, name)
        exists = target.is_file()
        items.append(
            {
                "name": name,
                "exists": exists,
                "size": target.stat().st_size if exists else 0,
                "content": read_file(paths, assistant_id, name),
                "hint": hints[name],
            }
        )
    return items


def build_persona_section(
    paths: Any, assistant_id: str, *, nickname: str = ""
) -> str:


















    if not assistant_id:
        return ""

    parts: list[str] = []
    soul = read_file(paths, assistant_id, SOUL_FILE).strip()
    identity = read_file(paths, assistant_id, IDENTITY_FILE).strip()
    rules = read_file(paths, assistant_id, RULES_FILE).strip()
    memory = read_file(paths, assistant_id, MEMORY_FILE).strip()
    user = read_file(paths, assistant_id, USER_FILE).strip()

    if nickname.strip():
        parts.append("## 你的名字\n" f"你叫「{nickname.strip()}」，用户会这样称呼你。")
    if identity:
        parts.append("## 你的身份（IDENTITY）\n" + identity)
    if soul:
        parts.append("## 你的人格（SOUL）\n" + soul)
    if user:
        parts.append("## 关于用户（USER）\n" + user)
    if memory:
        parts.append("## 你记得的事（MEMORY）\n" + memory)
    if rules:
        parts.append("## 你的工作逻辑与规则（RULES）\n" + rules)

    if not parts:
        return ""
    return "\n\n".join(parts)


__all__ = [
    "ALLOWED_FILES",
    "DEFAULT_EVOLUTION_LOG_HINT",
    "DEFAULT_IDENTITY_HINT",
    "DEFAULT_RULES_HINT",
    "DEFAULT_USER_HINT",
    "EVOLUTION_LOG_FILE",
    "IDENTITY_FILE",
    "MAX_FILE_BYTES",
    "MEMORY_FILE",
    "RULES_FILE",
    "SOUL_FILE",
    "USER_FILE",
    "assistant_dir",
    "build_persona_section",
    "list_files",
    "read_file",
    "write_file",
]

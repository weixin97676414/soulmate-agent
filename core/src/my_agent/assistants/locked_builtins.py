































from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from . import persona
from .presets import BUILTIN_IDENTITIES, BUILTIN_RULES, BUILTIN_SOULS, BUILTIN_USERS





LOCKED_ASSISTANT_IDS: frozenset[str] = frozenset(
    {"BuddyManager", "soulmate", "LoveBuddy", "RelationBuddy", "FortuneTellingBuddy"}
)


def is_locked_assistant(assistant_id: str | None) -> bool:











    return bool(assistant_id) and assistant_id in LOCKED_ASSISTANT_IDS









LOCKED_FIELD_LABELS: dict[str, str] = {
    "name": "名称",
    "description": "简介",
}




LOCKED_PERSONA_FILES: frozenset[str] = frozenset()







FACTORY_TEXTS: dict[str, dict[str, str]] = {
    persona.SOUL_FILE: BUILTIN_SOULS,
    persona.IDENTITY_FILE: BUILTIN_IDENTITIES,
    persona.RULES_FILE: BUILTIN_RULES,
    persona.USER_FILE: BUILTIN_USERS,
}


class LockedBuiltinError(ValueError):
    pass














def is_locked(assistant_id: str | None) -> bool:

    return bool(assistant_id) and assistant_id in LOCKED_ASSISTANT_IDS


def factory_text(assistant_id: str, filename: str) -> str | None:

    table = FACTORY_TEXTS.get(filename)
    if table is None:
        return None
    return table.get(assistant_id)


def locked_field_message(field: str) -> str:

    label = LOCKED_FIELD_LABELS.get(field, field)
    return (
        f"内置搭子的{label}是固定的，不能修改 —— 改了它就不再是原来那个人了。"
        "昵称、头像与记忆（MEMORY.md）仍可自由设置。"
    )


def locked_persona_message(filename: str) -> str:
    return (
        f"内置搭子的 {filename} 是固定的，不能修改；"
        "人格（SOUL.md / IDENTITY.md）、记忆（MEMORY.md）与"
        "关于用户的认识（USER.md）仍可自由编辑。"
    )


def locked_delete_message(assistant_id: str, name: str = "") -> str:
    label = name or assistant_id
    return (
        f"「{label}」是内置搭子，不能删除。"
        "它是产品的一部分（用户、群聊、定时任务都可能正在用它），"
        "删掉之后没有任何办法恢复成原样。"
    )


def ensure_deletable(assistant_id: str, name: str = "") -> None:

    if is_locked(assistant_id):
        raise LockedBuiltinError(locked_delete_message(assistant_id, name))


def ensure_mutable(
    assistant_id: str,
    *,
    changes: Iterable[str] = (),
    name: str = "",
) -> None:

    if not is_locked(assistant_id):
        return
    bad = [field for field in changes if field in LOCKED_FIELD_LABELS]
    if bad:
        raise LockedBuiltinError(locked_field_message(bad[0]))


def ensure_persona_writable(assistant_id: str, filename: str) -> None:

    if is_locked(assistant_id) and filename in LOCKED_PERSONA_FILES:
        raise LockedBuiltinError(locked_persona_message(filename))


def lock_payload(assistant_id: str) -> dict[str, Any]:






    if not is_locked(assistant_id):
        return {"locked": False, "locked_fields": [], "locked_reason": ""}
    return {
        "locked": True,
        "locked_fields": sorted(LOCKED_FIELD_LABELS),
        "locked_reason": (
            "这是内置搭子：名称与简介由产品固定，不能修改或删除；"
            "可用能力可以像普通搭子一样勾选技能，昵称、头像与人格文件"
            "（SOUL / IDENTITY / RULES / MEMORY / USER）均可自由设置。"
        ),
    }


def changed_fields(before: Any, after: Any) -> list[str]:





    changed: list[str] = []
    for field in LOCKED_FIELD_LABELS:
        old = getattr(before, field, None)
        new = getattr(after, field, None)
        if field == "enabled_skills":
            
            
            
            if set(old or []) != set(new or []):
                changed.append(field)
        elif (old or "") != (new or ""):
            changed.append(field)
    return changed


def restore_factory_fields(profile: Any) -> Any:











    from .presets import BUILTIN_ASSISTANTS

    if not is_locked(getattr(profile, "id", "")):
        return profile
    for proto in BUILTIN_ASSISTANTS:
        if proto.id != profile.id:
            continue
        return profile.model_copy(
            update={
                "name": proto.name,
                "description": proto.description,
            }
        )
    return profile


__all__ = [
    "FACTORY_TEXTS",
    "LOCKED_ASSISTANT_IDS",
    "LOCKED_FIELD_LABELS",
    "LOCKED_PERSONA_FILES",
    "LockedBuiltinError",
    "changed_fields",
    "ensure_deletable",
    "ensure_mutable",
    "ensure_persona_writable",
    "factory_text",
    "is_locked",
    "locked_delete_message",
    "locked_field_message",
    "lock_payload",
    "locked_persona_message",
    "restore_factory_fields",
]

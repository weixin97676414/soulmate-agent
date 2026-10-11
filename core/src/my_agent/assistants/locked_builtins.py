"""四位内置搭子的硬锁：简介 / 规则 / 名称 / 可用能力都改不了、也删不掉。

## 为什么"写死"是三层，而不是一个开关

产品约定是"任何途径都不可改、不可删"。只做一层一定漏：

1. **默认值层**（``assistants/presets.py`` + ``config/loader.py``）：
   出厂正文写进去之后还会**回写** —— 用户（或模型）改了文件，下次启动就还原。
   只播种一次是没用的：改一次就永久生效了。
2. **裁决层**（本模块）：HTTP 路由、"搭子总管"技能、群解散连带删除，
   三条路径都要过 ``ensure_mutable`` / ``ensure_deletable``。
   **漏掉任何一条，就有一条路能改能删** —— 而这三条路平时各走各的，不会互相提醒。
3. **呈现层**（桌面端）：字段置灰 + 写明原因。少了这层，用户点半天没反应，
   只会以为客户端坏了。

## 只按 id 精确命中

不按名字、也不按 ``builtin=True``。用户可以自己建一个叫「Soulmate」的搭子 ——
那是他的东西，不该被锁住。同理，老版本里存在过的同名内置（比如被改名前的
``office``）也不在名单里，那是迁移该管的事。

## 只锁"内容"（2026-09-28 二次修正）

**昵称与头像照旧可改**（用户明确要求），``MEMORY.md`` / ``USER.md`` 也照旧可写 ——
那是搭子的记忆，锁了就等于把搭子变成一块石头。

⚠️ 锁的**人格文件只有 RULES.md**（用户同日更正："可是现在 soul.md 和
IDENTITY.md 也被固定了，这是不对的"）。SOUL / IDENTITY 在**一次性对齐**到
《搭子人格包》之后完全解锁（见 ``config/loader.py`` 的对齐迁移）——
它们是搭子的"性格与身份"，用户要能改；RULES 是"工作规矩"，保持出厂。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from . import persona
from .presets import BUILTIN_IDENTITIES, BUILTIN_RULES, BUILTIN_SOULS, BUILTIN_USERS

# 四位内置搭子（id 与 presets.BUILTIN_ASSISTANTS 一致）。
# ⚠️ 改这里必须同时看 presets：写死的正文以那边的出厂表为准。
LOCKED_ASSISTANT_IDS: frozenset[str] = frozenset(
    {"BuddyManager", "soulmate", "LoveBuddy", "RelationBuddy"}
)


def is_locked_assistant(assistant_id: str | None) -> bool:
    """这个搭子是不是四位内置搭子之一。

    内置搭子的技能是**固定**的：可用能力 = 全部内置技能 ∪ 自己的专属技能
    （产品约定："内置搭子依然保持禁止用户和 ai 添加技能，保持出厂设置"）。
    它档案里的 ``enabled_skills`` 同时在 ``LOCKED_FIELD_LABELS`` 里被锁住，
    装配时会被**忽略**（见 ``skill/groups.py::allowed_skill_names``）。

    ⚠️ 只按 id 精确命中 —— 用户自己建一个叫「Soulmate」的搭子不该被锁住。
    """
    return bool(assistant_id) and assistant_id in LOCKED_ASSISTANT_IDS

# 被锁住的字段 → 给用户看的中文名。路由层按这个报"改不了的到底是哪一项"，
# 而不是笼统一句"内置搭子不可修改"（用户会以为是整个搭子不能动）。
LOCKED_FIELD_LABELS: dict[str, str] = {
    "name": "名称",
    "description": "简介",
    "enabled_skills": "可用能力",
}

# 被锁住的人格文件：**只有 RULES.md**（修正：）。
# SOUL / IDENTITY 对齐一次后解锁 —— 锁死"它是谁"就等于用户改不了搭子的性格；
# MEMORY.md / USER.md 本来就不在锁内（记忆必须继续可写）。
LOCKED_PERSONA_FILES: frozenset[str] = frozenset({persona.RULES_FILE})

# 出厂正文来源：文件名 → 表。供 loader 回写与"被改回原样"的判断共用一份。
#
# ⚠️ USER.md 也在表里，但它**不在** ``LOCKED_PERSONA_FILES`` —— 持续回写只查锁内
# 文件，所以这张表里放 USER 不会让 USER 被反复覆盖；它只服务两处：
# ``loader._seed_builtin_souls``（缺失才播种）与一次性人格包对齐（同样只补缺）。
# USER 是报告维护的活文档，覆盖它等于抹掉已积累的报告数据。
FACTORY_TEXTS: dict[str, dict[str, str]] = {
    persona.SOUL_FILE: BUILTIN_SOULS,
    persona.IDENTITY_FILE: BUILTIN_IDENTITIES,
    persona.RULES_FILE: BUILTIN_RULES,
    persona.USER_FILE: BUILTIN_USERS,
}


class LockedBuiltinError(ValueError):
    """内置搭子的写操作被拒绝。

    **刻意用异常而不是返回 bool**：调用点（HTTP 路由 / 技能 / 生命周期）
    必须显式处理它，否则会静默地"什么都没做就当成功了"——
    那正是最难发现的一类 bug（界面上显示已保存，实际没变）。

    **继承 ``ValueError`` 是刻意的**：这条链路上本来就有好几处
    ``except ValueError``（人格文件写入、搭子总管技能的执行外壳）。
    继承它，那些先写好的兜底会**自动**把拒绝原因如实转成用户看得懂的一句话，
    而不是变成一个 500 或者"技能执行失败（未知错误）"。
    顺带也说明了一件事：这里的失败原因**本来就是给用户看的输入问题**，
    不是"服务器坏了"。
    """


def is_locked(assistant_id: str | None) -> bool:
    """这个 id 是不是写死的四位内置搭子。"""
    return bool(assistant_id) and assistant_id in LOCKED_ASSISTANT_IDS


def factory_text(assistant_id: str, filename: str) -> str | None:
    """该内置搭子的出厂正文；没写过这个文件就返回 ``None``。"""
    table = FACTORY_TEXTS.get(filename)
    if table is None:
        return None
    return table.get(assistant_id)


def locked_field_message(field: str) -> str:
    """单个字段被锁时给用户看的一句话。"""
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
    """删除前的裁决。三条删除路径都必须调用。"""
    if is_locked(assistant_id):
        raise LockedBuiltinError(locked_delete_message(assistant_id, name))


def ensure_mutable(
    assistant_id: str,
    *,
    changes: Iterable[str] = (),
    name: str = "",
) -> None:
    """修改前的裁决。``changes`` 是"这次想改的字段名"（见 ``LOCKED_FIELD_LABELS``）。"""
    if not is_locked(assistant_id):
        return
    bad = [field for field in changes if field in LOCKED_FIELD_LABELS]
    if bad:
        raise LockedBuiltinError(locked_field_message(bad[0]))


def ensure_persona_writable(assistant_id: str, filename: str) -> None:
    """人格文件写入前的裁决。"""
    if is_locked(assistant_id) and filename in LOCKED_PERSONA_FILES:
        raise LockedBuiltinError(locked_persona_message(filename))


def lock_payload(assistant_id: str) -> dict[str, Any]:
    """给界面用的"这个搭子被锁了什么"（不在名单里就给一份空壳）。

    为什么由**核心**下发、而不是让界面自己写死一份 id 名单：名单只存在于这一处。
    界面另存一份的话，加一个内置搭子就要改两个仓库的两处代码，
    而漏改的那一处不会报错 —— 只是那个搭子突然可以随便改了。
    """
    if not is_locked(assistant_id):
        return {"locked": False, "locked_fields": [], "locked_reason": ""}
    return {
        "locked": True,
        "locked_fields": sorted(LOCKED_FIELD_LABELS),
        "locked_reason": (
            "这是内置搭子：名称、简介、可用能力与人格规则（RULES.md）由产品固定，"
            "不能修改或删除；昵称、头像与人格（SOUL / IDENTITY）仍可自由设置。"
        ),
    }


def changed_fields(before: Any, after: Any) -> list[str]:
    """对比两份档案里"被锁字段"的差异，返回有变化的字段名（可能多个）。

    只比被锁的那几项：昵称、头像、温度这些本来就允许改，把它们也算进来会让
    拒绝文案说成"连昵称也不能动"，而明明只有名称被锁。
    """
    changed: list[str] = []
    for field in LOCKED_FIELD_LABELS:
        old = getattr(before, field, None)
        new = getattr(after, field, None)
        if field == "enabled_skills":
            # 只看集合内容：顺序不算改动，[] 与 None 等价
            # （历史上空列表表示过"不限制"，现在是"没额外勾选" —— 但两者都是"同一个值的两种写法"，
            #  这里判断的是"用户改没改这一项"，与语义无关）
            if set(old or []) != set(new or []):
                changed.append(field)
        elif (old or "") != (new or ""):
            changed.append(field)
    return changed


def restore_factory_fields(profile: Any) -> Any:
    """把内置搭子被写死的字段强行掰回出厂值（返回新的 profile）。

    用户在老版本里改过名字/简介的机器，升级后靠这个回到出厂态 ——
    只回写"被锁的字段"，昵称与头像原样保留。
    """
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
                "enabled_skills": list(proto.enabled_skills),
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

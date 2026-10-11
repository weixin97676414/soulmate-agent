"""内置搭子预设：新增的「搭子总管」与**默认搭子的迁移**。

产品要求：

> 新增搭子：Buddy Manager（搭子总管），定位是用户的总管家……该搭子要默认置顶，
> 且为打开客户端的默认搭子（之前是 Relation Buddy）。

这里最容易出错、也最不容易被发现的地方是**迁移**：``assistants.json`` 是持久化的，
光改 ``DEFAULT_ASSISTANT_ID`` 这个常量，对已经跑过一次的老机器**完全没有影响** ——
用户装上新版打开，默认搭子还是原来那个，然后他会说"你根本没改"。所以迁移那几条
边界（只动出厂值、不动用户自己挑过的、目标搭子必须先真的存在）都要有用例钉住。
"""

from __future__ import annotations

import json
from typing import Any

from my_agent.assistants.presets import (
    BUILTIN_ASSISTANTS,
    BUILTIN_SOULS,
    DEFAULT_ASSISTANT_ID,
    LEGACY_DEFAULT_ASSISTANT_IDS,
    builtin_config,
)
from my_agent.config.loader import ConfigStore
from my_agent.config.paths import AppPaths


def _store(paths, **kwargs):
    """测试用：带**内置搭子数据源**的 `ConfigStore`。

    ⚠️ 生产路径里这一步由组合根 `AppRuntime` 做（审计 M-20：`config` 不许 import
    `assistants`，内置搭子的数据由上层注入）。测试直接构造 `ConfigStore` 而不注入，
    就只剩"读文件 + 校验" —— 内置搭子既不会播种也不会迁移，断言它们存在的用例会红。
    走这个 helper 才与生产同口径。

    （两个 import 放在函数里：有的测试文件是在**函数内** import `ConfigStore` 的，
    写成模块级会去动它们的 import 块 —— 上一版就是这么把括号插坏的。）
    """
    from my_agent.assistants.bootstrap import BuiltinAssistants

    return ConfigStore(paths, builtin=BuiltinAssistants(), **kwargs)


def preset(assistant_id: str) -> Any:
    return next(item for item in BUILTIN_ASSISTANTS if item.id == assistant_id)


def write_assistants(paths: AppPaths, payload: dict[str, Any]) -> None:
    paths.assistants_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def legacy_row() -> dict[str, Any]:
    """一条最小可用的老配置行（模拟用户机器上早就存在的那份）。"""
    old = preset(LEGACY_DEFAULT_ASSISTANT_IDS[0])
    return old.model_dump(mode="json")


# --------------------------------------------------------------------------- #
# 预设本身
# --------------------------------------------------------------------------- #
def test_buddy_manager_exists_and_is_pinned():
    """置顶靠 ``sort_order`` 最小实现（列表按 ``(sort_order, name)`` 排）。"""
    manager = preset("BuddyManager")

    assert manager.builtin is True
    assert manager.emoji, "没有图标的话搭子栏里是个空白方块"
    others = [item.sort_order for item in BUILTIN_ASSISTANTS if item.id != "BuddyManager"]
    assert manager.sort_order < min(others), "总管必须排在所有内置搭子前面"
    assert builtin_config().sorted()[0].id == "BuddyManager"


def test_buddy_manager_has_a_soul():
    """出厂 SOUL 缺了的话它一开口就是"我是一个AI助手"那股味儿。"""
    assert "BuddyManager" in BUILTIN_SOULS
    assert BUILTIN_SOULS["BuddyManager"].strip()


async def test_buddy_manager_gets_everything_it_needs(tmp_path):
    """搭子总管的能力由**四分类**算出来，不再靠白名单罗列。

    ⚠️ 这条口径变过两次，当前以第二次为准：

    1. 2026-09-28：用户要求「Buddy Manager 要开启全部技能」→ 白名单留空
       （当时的语义是"空 = 不限制"）；
    2. **2026-10-06**：「内置搭子 = 专属技能 + 内置技能，且**不能再添加任何技能**」
       → "空 = 全开"作废。它的实际能力由 `skill/groups.py` 算：
       **全部内置技能 ∪ 自己归属的专属技能**，档案里那份白名单被**忽略**。

    所以现在验两件事：① 白名单必须是空的（用户与 AI 都改不了它）；
    ② 算出来的可用集合必须真实、且包含它该有的东西（见 `test_skill_groups.py`）。
    """
    from my_agent.server.runtime import AppRuntime

    runtime = AppRuntime(AppPaths(tmp_path / "probe").ensure())
    await runtime.initialize()
    try:
        available = set(runtime.skills.all_names())
        allowed = runtime.skills.allowed_names(
            assistant_id="BuddyManager", enabled_skills=None
        )
    finally:
        await runtime.shutdown()

    assert preset("BuddyManager").enabled_skills == [], "内置搭子不可添加技能，白名单必须为空"
    assert available, "技能注册表是空的话，后面这些断言都是空话"
    # 算出来的名字必须**有据可查**：要么在注册表里，要么在 `groups` 的指导型名单里。
    #
    # ⚠️ 放宽了这一条（这是**真信号**，不是测试过时）：`allowed` 现在还会
    # 包含「指导型技能」—— 它们按设计**不注册进工具注册表**（没有动作，注册了只会让
    # 模型看到一个"调了也没意义"的工具），所以永远不可能出现在 `all_names()` 里。
    # 但"注册表里没有"≠"算错了"：那批名字来自 `groups` 的两份名单，是有据可查的。
    # 保留这条断言的价值在于：**两边都不在**的名字就是真 bug（拼错、名单与数据脱节）。
    from my_agent.skill import groups

    known_instructions = set(groups.INSTRUCTION_EXCLUSIVE_OWNERS) | set(
        groups.ALWAYS_ON_INSTRUCTION_NAMES
    )
    stray = sorted(allowed - available - known_instructions)
    assert not stray, f"可用集合里有来路不明的技能：{stray}"
    # 内置技能恒有
    assert {"calc", "kb_search", "self_growth"} <= allowed
    # 它自己的专属：团队管理 + 电脑操作那两批
    assert any(name.startswith("team_") for name in allowed), "团队管理那批应当在"
    assert any(name.startswith("computer_") for name in allowed), "电脑操作那批应当在"
    # ：转过来的 8 个指导型专属 + 2 个指导型常驻也必须有
    assert set(groups.INSTRUCTION_EXCLUSIVE_OWNERS) <= allowed
    assert set(groups.ALWAYS_ON_INSTRUCTION_NAMES) <= allowed
    # 通用技能**不给** —— 内置搭子不能添加技能，这是产品要求的
    assert "weather_query" not in allowed


def test_default_assistant_id_matches_a_preset():
    """常量与预设表必须对得上。

    载入时那条迁移会**无条件**去预设表里找 ``DEFAULT_ASSISTANT_ID``；找不到就
    跳过（只打一条 warning）。也就是说这两个东西脱节时，表现出来是"迁移什么都没
    做"，安安静静 —— 所以要用例钉住它们。
    """
    assert preset(DEFAULT_ASSISTANT_ID).id == DEFAULT_ASSISTANT_ID


# --------------------------------------------------------------------------- #
# 默认搭子的迁移
# --------------------------------------------------------------------------- #
def test_old_default_is_migrated_and_manager_is_seeded(tmp_path):
    """老机器（默认位还是出厂值）：默认换成总管，并且总管真的进了清单。"""
    paths = AppPaths(tmp_path / "data").ensure()
    write_assistants(paths, {"default_assistant": "RelationBuddy", "assistants": [legacy_row()]})

    config = _store(paths).load().assistants

    assert config.default_assistant == "BuddyManager"
    assert config.get("BuddyManager") is not None, "默认位指向了一个不存在的搭子"
    # 落盘了才算数：不写回去的话下次启动又要重算一遍，而且用户可能中途退出
    on_disk = json.loads(paths.assistants_file.read_text(encoding="utf-8"))
    assert on_disk["default_assistant"] == "BuddyManager"


def test_migration_is_stable_across_restarts(tmp_path):
    """迁移只发生一次：第二次载入不再改动（否则用户改回去也会被反复覆盖）。"""
    paths = AppPaths(tmp_path / "data").ensure()
    write_assistants(paths, {"default_assistant": "RelationBuddy", "assistants": [legacy_row()]})

    _store(paths).load()
    second = _store(paths).load().assistants

    assert second.default_assistant == "BuddyManager"
    assert len([item for item in second.assistants if item.id == "BuddyManager"]) == 1


def test_user_chosen_default_is_left_alone(tmp_path):
    """用户自己挑过默认搭子 → 一律不动，也不给他塞新搭子。

    "不动默认位"是既定规矩（与 ``RENAMED_BUILTINS`` 的"只覆盖还是出厂值的那部分"
    同源）；"不塞新搭子"同样是刻意的 —— 不然用户删掉的总管下次启动又回来了，
    而"用户删内置搭子"是明确意图。
    """
    paths = AppPaths(tmp_path / "data").ensure()
    write_assistants(paths, {"default_assistant": "soulmate", "assistants": [legacy_row()]})

    config = _store(paths).load().assistants

    assert config.default_assistant == "soulmate"
    assert config.get("BuddyManager") is None


def test_existing_manager_is_not_duplicated(tmp_path):
    """已经有总管了（用户改过它的名字/头像）：迁移不许把它重置回出厂值。"""
    paths = AppPaths(tmp_path / "data").ensure()
    mine = preset("BuddyManager").model_dump(mode="json")
    mine["nickname"] = "我给总管起的名字"
    write_assistants(
        paths,
        {
            "default_assistant": "RelationBuddy",
            "assistants": [legacy_row(), mine],
        },
    )

    config = _store(paths).load().assistants

    assert config.default_assistant == "BuddyManager"
    assert config.get("BuddyManager").nickname == "我给总管起的名字"


def test_fresh_install_defaults_to_manager(tmp_path):
    """全新安装（还没有 ``assistants.json``）：默认搭子就该是总管。

    这条是"用户第一次打开客户端会看到谁"，与老机器迁移是两回事 ——
    前者走首次播种分支，后者走迁移分支，两条都要对。
    """
    paths = AppPaths(tmp_path / "data").ensure()

    config = _store(paths).load().assistants

    assert config.default_assistant == "BuddyManager"
    assert config.get("BuddyManager") is not None


# ⚠️ 已知的**既有**问题（本次没有动，记在这里免得下次又被当成新 bug 查一遍）：
# ``loader._read_json`` 对坏掉的 json 是直接抛 ``JSONDecodeError`` 的，也就是说
# 任何一份配置文件被写坏（断电、手改错了），客户端启动就会整个失败。
# 这与本次的迁移无关（迁移之前就会抛），修它要动所有配置的读取策略，属另一件事。


def test_manager_deleted_by_hand_stays_deleted(tmp_path):
    """手改配置文件把总管抹掉之后，它**不会**被偷偷补回来（第 95 批改名）。

    ⚠️ 这条原先叫 ``test_manager_is_reported_as_missing_when_user_deleted_it``，
    assert 的是"能把总管列进「恢复默认搭子」的清单"。2026-10-10 用户拍板：
    四位内置搭子在界面上**没有删除途径**（右键菜单里根本不画删除项、接口 409），
    所以"一键找回"连同设置页一起删掉了，判定"谁缺失"的那份清单也就不需要了。

    留下来的是原来那半条**更重要的意图**：配置文件被手改 / 被别的工具写坏时，
    系统不能把用户明确不要的东西偷偷恢复 —— 那比丢配置更让人恼火。
    同口径的端到端断言见
    ``tests/integration/test_p4_assistants.py::test_removed_builtin_is_not_resurrected_on_reload``。
    """
    paths = AppPaths(tmp_path / "data").ensure()
    write_assistants(paths, {"default_assistant": "soulmate", "assistants": [legacy_row()]})

    config = _store(paths).load().assistants

    assert config.get("BuddyManager") is None

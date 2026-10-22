












from __future__ import annotations

import json
from typing import Any

from my_agent.assistants.presets import (
    BUILTIN_ASSISTANTS,
    BUILTIN_IDENTITIES,
    BUILTIN_SOULS,
    DEFAULT_ASSISTANT_ID,
    LEGACY_DEFAULT_ASSISTANT_IDS,
    builtin_config,
)
from my_agent.config.loader import ConfigStore
from my_agent.config.paths import AppPaths


def _store(paths, **kwargs):










    from my_agent.assistants.bootstrap import BuiltinAssistants

    return ConfigStore(paths, builtin=BuiltinAssistants(), **kwargs)


def preset(assistant_id: str) -> Any:
    return next(item for item in BUILTIN_ASSISTANTS if item.id == assistant_id)


def write_assistants(paths: AppPaths, payload: dict[str, Any]) -> None:
    paths.assistants_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def legacy_row() -> dict[str, Any]:

    old = preset(LEGACY_DEFAULT_ASSISTANT_IDS[0])
    return old.model_dump(mode="json")





def test_buddy_manager_exists_and_is_pinned():

    manager = preset("BuddyManager")

    assert manager.builtin is True
    assert manager.emoji, "没有图标的话搭子栏里是个空白方块"
    others = [item.sort_order for item in BUILTIN_ASSISTANTS if item.id != "BuddyManager"]
    assert manager.sort_order < min(others), "总管必须排在所有内置搭子前面"
    assert builtin_config().sorted()[0].id == "BuddyManager"


def test_fortune_telling_buddy_is_the_fifth_builtin():








    from my_agent.assistants.presets import (
        ADDED_BUILTIN_IDS,
        BUILTIN_IDENTITIES,
        BUILTIN_RULES,
        BUILTIN_USERS,
    )

    fortune = preset("FortuneTellingBuddy")
    assert fortune.builtin is True
    assert fortune.name == "Fortune telling Buddy"
    assert fortune.sort_order == 11
    assert fortune.sort_order > preset("RelationBuddy").sort_order
    
    assert fortune.description.strip()
    assert not fortune.description.strip().startswith("#")

    for table in (BUILTIN_SOULS, BUILTIN_IDENTITIES, BUILTIN_RULES, BUILTIN_USERS):
        assert table.get("FortuneTellingBuddy", "").strip(), table is BUILTIN_SOULS

    assert "FortuneTellingBuddy" in ADDED_BUILTIN_IDS


def test_fortune_telling_buddy_has_no_wrong_skill_names():





    from my_agent.assistants.presets import BUILTIN_RULES

    rules = BUILTIN_RULES["FortuneTellingBuddy"]
    assert "XJX-Astro-cn" in rules and "XJX-Astro-global" in rules
    assert "XJX-Meihua-cn" in rules and "XJX-Meihua-global" in rules
    assert "XJX-Tarot-cn" in rules and "XJX-Tarot-global" in rules
    
    assert "占星（XJX-Bazi" not in rules
    assert "梅花（XJX-Bazi" not in rules


def test_buddy_manager_has_a_soul():

    assert "BuddyManager" in BUILTIN_SOULS
    assert BUILTIN_SOULS["BuddyManager"].strip()


def test_buddy_manager_positioning_is_the_new_one():










    manager = preset("BuddyManager")
    first_line = manager.description.split("\n")[0]

    assert first_line == "我是你的**首席事务助理**兼**策略顾问**"
    
    assert manager.description.split("\n")[1:] == [
        "新建、优化、协调其他搭子，并快速组建和调整团队",
        "也能根据你的想法策划出切实可行的落地方案",
    ]

    
    for text in (
        BUILTIN_SOULS["BuddyManager"],
        BUILTIN_IDENTITIES["BuddyManager"],
        manager.system_prompt,
    ):
        assert "首席事务助理兼策略顾问" in text
        assert "搭子总管" not in text
        assert "私人军师" not in text


async def test_buddy_manager_gets_everything_it_needs(tmp_path):













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
    
    
    
    
    
    
    
    from my_agent.skill import groups

    known_instructions = set(groups.INSTRUCTION_EXCLUSIVE_OWNERS) | set(
        groups.ALWAYS_ON_INSTRUCTION_NAMES
    )
    stray = sorted(allowed - available - known_instructions)
    assert not stray, f"可用集合里有来路不明的技能：{stray}"
    
    assert {"calc", "kb_search", "self_growth"} <= allowed
    
    assert any(name.startswith("team_") for name in allowed), "团队管理那批应当在"
    assert any(name.startswith("computer_") for name in allowed), "电脑操作那批应当在"
    
    assert set(groups.INSTRUCTION_EXCLUSIVE_OWNERS) <= allowed
    assert set(groups.ALWAYS_ON_INSTRUCTION_NAMES) <= allowed
    
    assert "weather_query" not in allowed


def test_default_assistant_id_matches_a_preset():






    assert preset(DEFAULT_ASSISTANT_ID).id == DEFAULT_ASSISTANT_ID





def test_old_default_is_migrated_and_manager_is_seeded(tmp_path):

    paths = AppPaths(tmp_path / "data").ensure()
    write_assistants(paths, {"default_assistant": "RelationBuddy", "assistants": [legacy_row()]})

    config = _store(paths).load().assistants

    assert config.default_assistant == "BuddyManager"
    assert config.get("BuddyManager") is not None, "默认位指向了一个不存在的搭子"
    
    on_disk = json.loads(paths.assistants_file.read_text(encoding="utf-8"))
    assert on_disk["default_assistant"] == "BuddyManager"


def test_migration_is_stable_across_restarts(tmp_path):

    paths = AppPaths(tmp_path / "data").ensure()
    write_assistants(paths, {"default_assistant": "RelationBuddy", "assistants": [legacy_row()]})

    _store(paths).load()
    second = _store(paths).load().assistants

    assert second.default_assistant == "BuddyManager"
    assert len([item for item in second.assistants if item.id == "BuddyManager"]) == 1


def test_user_chosen_default_is_left_alone(tmp_path):






    paths = AppPaths(tmp_path / "data").ensure()
    write_assistants(paths, {"default_assistant": "soulmate", "assistants": [legacy_row()]})

    config = _store(paths).load().assistants

    assert config.default_assistant == "soulmate"
    assert config.get("BuddyManager") is None


def test_existing_manager_is_not_duplicated(tmp_path):

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





    paths = AppPaths(tmp_path / "data").ensure()

    config = _store(paths).load().assistants

    assert config.default_assistant == "BuddyManager"
    assert config.get("BuddyManager") is not None








def test_manager_deleted_by_hand_stays_deleted(tmp_path):












    paths = AppPaths(tmp_path / "data").ensure()
    write_assistants(paths, {"default_assistant": "soulmate", "assistants": [legacy_row()]})

    config = _store(paths).load().assistants

    assert config.get("BuddyManager") is None

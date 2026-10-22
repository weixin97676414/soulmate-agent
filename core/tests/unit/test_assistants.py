

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from my_agent.agent.session import Session
from my_agent.assistants.persona import SOUL_FILE, assistant_dir
from my_agent.assistants.presets import (
    BUILTIN_ASSISTANTS,
    BUILTIN_SOULS,
    DEFAULT_ASSISTANT_ID,
    RENAMED_BUILTIN_IDS,
    RENAMED_BUILTINS,
    builtin_config,
)
from my_agent.config.loader import ConfigStore
from my_agent.config.paths import AppPaths
from my_agent.config.schemas import AssistantProfile, AssistantsConfig


def _store(paths, **kwargs):










    from my_agent.assistants.bootstrap import BuiltinAssistants

    return ConfigStore(paths, builtin=BuiltinAssistants(), **kwargs)





def test_builtin_assistants_are_complete():




    ids = [item.id for item in BUILTIN_ASSISTANTS]
    
    
    assert ids == [
        "RelationBuddy",
        "soulmate",
        "LoveBuddy",
        
        "BuddyManager",
        
        "FortuneTellingBuddy",
    ]
    assert all(item.builtin for item in BUILTIN_ASSISTANTS)
    
    
    


def test_removed_builtin_ids_match_reality():





    from my_agent.assistants.presets import REMOVED_BUILTIN_IDS

    ids = {item.id for item in BUILTIN_ASSISTANTS}
    assert not ids & set(REMOVED_BUILTIN_IDS)


def test_renamed_builtins_keep_ids():

    by_id = {item.id: item for item in BUILTIN_ASSISTANTS}
    assert by_id["RelationBuddy"].name == "Relation Buddy"
    assert by_id["LoveBuddy"].name == "Love Buddy"
    
    
    
    
    
    assert by_id["RelationBuddy"].description.startswith("我是你的职场人际关系运营助手")
    assert "我是你的 Relation Buddy" not in by_id["RelationBuddy"].description
    assert by_id["LoveBuddy"].description.startswith("我是你的婚恋情感搭子")


def test_companion_assistants_have_no_skill_restriction():







    companions = {"soulmate", "LoveBuddy"}
    for profile in BUILTIN_ASSISTANTS:
        if profile.id in companions:
            assert profile.enabled_skills == []
            
            assert profile.to_dict()["restricts_skills"] is False


def test_builtin_skill_whitelists_reference_real_skills():





    try:
        from my_agent.skill.builtin import discover_builtin_skills
    except ImportError:  
        pytest.skip("技能发现不可用")

    known = {cls.meta.name for cls in discover_builtin_skills()}
    for profile in BUILTIN_ASSISTANTS:
        unknown = [name for name in profile.enabled_skills if name not in known]
        assert not unknown, f"{profile.id} 引用了不存在的技能：{unknown}"


def test_builtin_skill_whitelists_exclude_mcp():

    for profile in BUILTIN_ASSISTANTS:
        assert not [name for name in profile.enabled_skills if "__" in name]


def test_builtin_config_returns_independent_copies():





    first = builtin_config()
    first.assistants[0].name = "被改过了"
    first.assistants[0].enabled_skills.append("calc")

    second = builtin_config()
    assert second.assistants[0].name != "被改过了"
    assert "calc" not in second.assistants[0].enabled_skills





def test_assistant_id_rejects_illegal_chars():





    with pytest.raises(ValidationError):
        AssistantProfile(id="bad id!", name="x")


def test_assistants_config_upsert_replaces_in_place():
    config = AssistantsConfig()
    config.upsert(AssistantProfile(id="a", name="A"))
    config.upsert(AssistantProfile(id="a", name="A2"))
    assert len(config.assistants) == 1
    assert config.get("a").name == "A2"


def test_sorted_puts_lower_order_first():
    config = AssistantsConfig()
    config.upsert(AssistantProfile(id="z", name="Z", sort_order=99))
    config.upsert(AssistantProfile(id="a", name="A", sort_order=1))
    assert [item.id for item in config.sorted()] == ["a", "z"]


def test_default_assistant_id_exists_in_presets():
    assert any(item.id == DEFAULT_ASSISTANT_ID for item in BUILTIN_ASSISTANTS)





def test_apply_assistant_sets_persona_and_skills():
    session = Session(id="s1")
    profile = AssistantProfile(
        id="analyst",
        name="分析师",
        system_prompt="你是数据分析师",
        enabled_skills=["excel_read", "chart_generate"],
        model_id="deepseek-chat",
    )

    session.apply_assistant(profile)
    assert session.assistant_id == "analyst"
    assert session.system_prompt == "你是数据分析师"
    assert session.enabled_skills == {"excel_read", "chart_generate"}
    assert session.model_id == "deepseek-chat"


def test_空技能清单表示没额外勾选():







    session = Session(id="s1")
    session.apply_assistant(AssistantProfile(id="RelationBuddy", name="办公", enabled_skills=[]))
    assert session.enabled_skills is None


def test_apply_assistant_keeps_history():






    session = Session(id="s1")
    session.memory.add_user("之前的对话")
    session.memory.add_assistant("之前的回复")

    session.apply_assistant(AssistantProfile(id="writer", name="写作", system_prompt="你是写作助手"))

    assert len(session.history()) == 2
    assert session.history()[0]["content"] == "之前的对话"


def test_apply_assistant_without_model_keeps_current_choice():

    session = Session(id="s1", model_id="qwen-max")
    session.apply_assistant(AssistantProfile(id="RelationBuddy", name="办公"))
    assert session.model_id == "qwen-max"


def test_apply_assistant_updates_in_place_after_prompt_change():

    session = Session(id="s1")
    session.apply_assistant(AssistantProfile(id="a", name="A", system_prompt="提示词 A"))
    session.memory.ensure_system("提示词 A")

    session.apply_assistant(AssistantProfile(id="b", name="B", system_prompt="提示词 B"))
    session.memory.ensure_system(session.system_prompt)

    systems = [m for m in session.memory.messages if m.role == "system"]
    assert len(systems) == 1
    assert systems[0].content == "提示词 B"





def _write_legacy_assistants(paths: Any) -> AssistantsConfig:








    config = builtin_config()
    legacy_ids = {new: old for old, new in RENAMED_BUILTIN_IDS.items()}
    legacy_profiles: list[AssistantProfile] = []
    for item in config.assistants:
        legacy_id = legacy_ids.get(item.id, "")
        old = RENAMED_BUILTINS.get(legacy_id)
        if not legacy_id or not old:
            legacy_profiles.append(item)
            continue
        profile = item.model_copy(deep=True)
        profile.id = legacy_id
        profile.name = old["name"]
        profile.description = old["description"]
        legacy_profiles.append(profile)
        target = assistant_dir(paths, legacy_id) / SOUL_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(old["soul"], encoding="utf-8")
    config.assistants = legacy_profiles
    
    
    
    
    config.default_assistant = legacy_ids["RelationBuddy"]
    paths.assistants_file.write_text(
        json.dumps(config.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )
    return config


def test_first_load_writes_builtin_souls(tmp_path):







    from my_agent.assistants.persona import build_persona_section

    paths = AppPaths(tmp_path / "data").ensure()

    _store(paths).load()

    soul = assistant_dir(paths, "RelationBuddy") / SOUL_FILE
    assert soul.is_file(), "首启没写出厂 SOUL.md"
    
    
    
    assert soul.read_text(encoding="utf-8") == BUILTIN_SOULS["RelationBuddy"]
    
    assert build_persona_section(paths, "RelationBuddy", nickname="").strip()


def test_renamed_builtins_are_migrated(tmp_path):




    paths = AppPaths(tmp_path / "data").ensure()
    _write_legacy_assistants(paths)

    loaded = _store(paths).load()

    assert loaded.assistants.get("RelationBuddy").name == "Relation Buddy"
    assert loaded.assistants.get("LoveBuddy").name == "Love Buddy"
    
    
    assert loaded.assistants.get("RelationBuddy").description.startswith(
        "我是你的职场人际关系运营助手"
    )

    
    
    
    soul = (assistant_dir(paths, "RelationBuddy") / SOUL_FILE).read_text(encoding="utf-8")
    assert soul == BUILTIN_SOULS["RelationBuddy"]
    assert "WorkBuddy" not in soul

    
    raw = json.loads(paths.assistants_file.read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in raw["assistants"]}
    assert by_id["RelationBuddy"]["name"] == "Relation Buddy"
    
    assert by_id["LoveBuddy"]["description"].startswith("我是你的婚恋情感搭子")
    assert not any(item["id"] in RENAMED_BUILTIN_IDS for item in raw["assistants"])

    
    
    
    
    
    
    
    assert raw["default_assistant"] == "BuddyManager"
    assert not assistant_dir(paths, "office").exists()
    assert assistant_dir(paths, "LoveBuddy").is_dir()
    
    
    


def test_locked_builtins_reset_user_edits(tmp_path):














    paths = AppPaths(tmp_path / "data").ensure()
    config = _write_legacy_assistants(paths)

    profile = config.get("office")  
    assert profile is not None
    profile.name = "我自己的办公搭子"
    profile.description = "我自己写的简介"
    paths.assistants_file.write_text(
        json.dumps(config.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )
    my_soul = "# SOUL\n\n我自己写的人设，一个字都别动。\n"
    assistant_dir(paths, "office").mkdir(parents=True, exist_ok=True)
    target = assistant_dir(paths, "office") / SOUL_FILE
    target.write_text(my_soul, encoding="utf-8")

    loaded = _store(paths).load()

    
    assert loaded.assistants.get("RelationBuddy") is not None
    assert loaded.assistants.get("RelationBuddy").name == "Relation Buddy"
    
    
    assert loaded.assistants.get("RelationBuddy").description == (
        builtin_config().get("RelationBuddy").description
    )
    
    moved = assistant_dir(paths, "RelationBuddy") / SOUL_FILE
    assert "我自己写的人设" not in moved.read_text(encoding="utf-8")
    
    assert loaded.assistants.get("LoveBuddy").name == "Love Buddy"


def test_builtin_temperatures_are_migrated(tmp_path):





    paths = AppPaths(tmp_path / "data").ensure()
    config = builtin_config()
    by_id = {item.id: item for item in config.assistants}
    by_id["LoveBuddy"].temperature = 0.85  
    by_id["soulmate"].temperature = 0.9  
    paths.assistants_file.write_text(
        json.dumps(config.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )

    loaded = _store(paths).load()

    assert loaded.assistants.get("LoveBuddy").temperature == 0.5
    assert loaded.assistants.get("RelationBuddy").temperature == 0.4
    assert loaded.assistants.get("soulmate").temperature == 0.9


def test_locked_builtins_skip_user_assistants(tmp_path):






    paths = AppPaths(tmp_path / "data").ensure()
    config = builtin_config()
    config.upsert(
        AssistantProfile(id="office", name="WorkBuddy", description="我自己建的，同名")
    )
    paths.assistants_file.write_text(
        json.dumps(config.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )

    loaded = _store(paths).load()

    assert loaded.assistants.get("office").name == "WorkBuddy"
    assert loaded.assistants.get("office").description == "我自己建的，同名"

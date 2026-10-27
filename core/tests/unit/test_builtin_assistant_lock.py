






























from __future__ import annotations

import json

import pytest

from my_agent.assistants import lifecycle, persona
from my_agent.assistants.locked_builtins import (
    LOCKED_ASSISTANT_IDS,
    LockedBuiltinError,
    changed_fields,
    ensure_deletable,
    ensure_mutable,
    ensure_persona_writable,
    is_locked,
    lock_payload,
)
from my_agent.assistants.persona import IDENTITY_FILE, RULES_FILE, SOUL_FILE, write_file
from my_agent.assistants.presets import (
    BUILTIN_IDENTITIES,
    BUILTIN_RULES,
    BUILTIN_SOULS,
    BUILTIN_USERS,
    PERSONA_TEXT_MIGRATIONS,
    builtin_config,
)
from my_agent.config.loader import ConfigStore
from my_agent.config.paths import AppPaths
from my_agent.config.schemas import AssistantProfile
from my_agent.errors import SkillExecutionError
from my_agent.server.runtime import AppRuntime
from my_agent.skill.builtin import xjx


def _store(paths, **kwargs):










    from my_agent.assistants.bootstrap import BuiltinAssistants

    return ConfigStore(paths, builtin=BuiltinAssistants(), **kwargs)



LOCKED_IDS = (
    "BuddyManager",
    "soulmate",
    "LoveBuddy",
    "RelationBuddy",
    "FortuneTellingBuddy",
)

USER_ID = "my-own-buddy"


@pytest.fixture
def runtime(tmp_path):
    paths = AppPaths(tmp_path / "data").ensure()
    return AppRuntime(paths=paths)


def _profile(assistant_id: str) -> AssistantProfile:
    profile = builtin_config().get(assistant_id)
    assert profile is not None, f"内置搭子 {assistant_id} 不见了"
    return profile





def test_exactly_the_locked_ids_are_locked() -> None:





    assert LOCKED_ASSISTANT_IDS == set(LOCKED_IDS)
    assert all(is_locked(item) for item in LOCKED_IDS)
    assert not is_locked(USER_ID)


def test_changed_fields_reports_every_locked_field() -> None:











    before = _profile("soulmate")
    after = before.model_copy(update={"name": "改名", "description": "改简介"})

    assert sorted(changed_fields(before, after)) == ["description", "name"]


def test_changed_fields_ignores_enabled_skills_now() -> None:

    before = _profile("soulmate")
    after = before.model_copy(update={"enabled_skills": ["weather_query"]})

    assert changed_fields(before, after) == []


def test_changed_fields_ignores_allowed_fields() -> None:

    before = _profile("soulmate")
    after = before.model_copy(
        update={
            "nickname": "宝宝",
            "emoji": "🌙",
            "avatar": "avatar.png",
            "temperature": 0.9,
            "model_id": "local-qwen3",
        }
    )

    assert changed_fields(before, after) == []


def test_ensure_mutable_allows_editable_fields_for_locked_id() -> None:

    ensure_mutable("soulmate", changes=())  


def test_ensure_mutable_rejects_locked_field_with_readable_message() -> None:
    with pytest.raises(LockedBuiltinError) as exc:
        ensure_mutable("soulmate", changes=["name"])

    message = str(exc.value)
    
    assert "名称" in message
    assert "昵称" in message


def test_ensure_mutable_ignores_user_assistants() -> None:
    ensure_mutable(USER_ID, changes=["name", "description", "enabled_skills"])





def test_ensure_deletable_rejects_builtins() -> None:
    for assistant_id in LOCKED_IDS:
        with pytest.raises(LockedBuiltinError) as exc:
            ensure_deletable(assistant_id, "显示名")
        assert "内置搭子" in str(exc.value)


def test_lifecycle_refuses_and_keeps_the_assistant(runtime) -> None:

    for assistant_id in LOCKED_IDS:
        with pytest.raises(LockedBuiltinError):
            lifecycle.delete_assistant(runtime, assistant_id)

    left = {item.id for item in runtime.assistants.sorted()}
    assert set(LOCKED_IDS) <= left


async def test_orchestrator_delete_raises_a_user_facing_error(runtime) -> None:





    assert issubclass(LockedBuiltinError, ValueError)

    with pytest.raises(ValueError):
        await runtime.orchestrator.delete_assistant(assistant_id="soulmate")





def test_all_persona_files_are_writable_for_builtins() -> None:





    
    for name in (SOUL_FILE, IDENTITY_FILE, RULES_FILE, "MEMORY.md", "USER.md"):
        ensure_persona_writable("LoveBuddy", name)
    
    for name in (SOUL_FILE, IDENTITY_FILE, RULES_FILE):
        ensure_persona_writable(USER_ID, name)


def test_write_file_is_the_backstop(runtime) -> None:





    write_file(runtime.paths, "soulmate", RULES_FILE, "# 我自己写的规则\n")
    assert "我自己写的规则" in persona.read_file(runtime.paths, "soulmate", RULES_FILE)

    
    write_file(runtime.paths, "soulmate", SOUL_FILE, "# 我自己写的人设\n")
    assert "我自己写的人设" in persona.read_file(runtime.paths, "soulmate", SOUL_FILE)

    
    write_file(runtime.paths, "soulmate", "MEMORY.md", "# MEMORY\n\n用户喜欢喝美式。\n")
    assert "美式" in persona.read_file(runtime.paths, "soulmate", "MEMORY.md")


async def test_team_update_assistant_can_append_rules_but_not_description(runtime) -> None:





    before_rules = persona.read_file(runtime.paths, "soulmate", RULES_FILE)
    await runtime.orchestrator.append_assistant_setup(
        assistant_id="soulmate", rules_append="不许说脏话。"
    )
    assert "不许说脏话" in persona.read_file(runtime.paths, "soulmate", RULES_FILE)
    assert len(persona.read_file(runtime.paths, "soulmate", RULES_FILE)) > len(before_rules)

    with pytest.raises((LockedBuiltinError, SkillExecutionError)) as exc:
        await runtime.orchestrator.append_assistant_setup(
            assistant_id="soulmate", description_append="顺带也懂点法律。"
        )
    assert "内置搭子" in str(exc.value)


async def test_team_update_assistant_refuses_to_append_description(runtime) -> None:

    before = runtime.assistants.get("soulmate").description

    with pytest.raises((LockedBuiltinError, SkillExecutionError)):
        await runtime.orchestrator.append_assistant_setup(
            assistant_id="soulmate", description_append="顺带也懂点法律。"
        )

    assert runtime.assistants.get("soulmate").description == before





def _hand_edit(paths: AppPaths) -> None:

    raw = json.loads(paths.assistants_file.read_text(encoding="utf-8"))
    for item in raw["assistants"]:
        if item["id"] in LOCKED_IDS:
            item["name"] = f"我改的{item['id']}"
            item["description"] = "我自己写的简介"
            item["enabled_skills"] = ["calc"]
    paths.assistants_file.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    directory = persona.assistant_dir(paths, "soulmate")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / SOUL_FILE).write_text("# 我自己写的人设\n", encoding="utf-8")
    (directory / IDENTITY_FILE).write_text("# 我自己写的身份\n", encoding="utf-8")
    (directory / RULES_FILE).write_text("# 我自己写的规则\n", encoding="utf-8")


def test_loader_restores_locked_fields_on_start(tmp_path) -> None:




    paths = AppPaths(tmp_path / "data").ensure()
    _store(paths).load()  
    _hand_edit(paths)

    loaded = _store(paths).load().assistants

    for assistant_id in LOCKED_IDS:
        profile = loaded.get(assistant_id)
        factory = _profile(assistant_id)
        assert profile.name == factory.name, assistant_id
        assert profile.description == factory.description, assistant_id
        
        
        
        assert profile.enabled_skills == ["calc"], assistant_id


def test_added_builtin_is_seeded_once_into_old_config(tmp_path) -> None:








    paths = AppPaths(tmp_path / "data").ensure()
    _store(paths).load()

    
    raw = json.loads(paths.assistants_file.read_text(encoding="utf-8"))
    raw["assistants"] = [item for item in raw["assistants"] if item["id"] != "FortuneTellingBuddy"]
    paths.assistants_file.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    (paths.data_dir / ".added-builtins").unlink(missing_ok=True)

    loaded = _store(paths).load().assistants
    assert loaded.get("FortuneTellingBuddy") is not None
    assert loaded.get("FortuneTellingBuddy").builtin is True
    
    directory = persona.assistant_dir(paths, "FortuneTellingBuddy")
    assert (directory / SOUL_FILE).read_text(encoding="utf-8").strip()

    
    raw = json.loads(paths.assistants_file.read_text(encoding="utf-8"))
    raw["assistants"] = [item for item in raw["assistants"] if item["id"] != "FortuneTellingBuddy"]
    paths.assistants_file.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    again = _store(paths).load().assistants
    assert again.get("FortuneTellingBuddy") is None


def test_loader_keeps_user_selected_skills_across_restart(tmp_path) -> None:





    paths = AppPaths(tmp_path / "data").ensure()
    store = _store(paths)
    store.load()

    picked = ["weather_query", "humanizer"]
    raw = json.loads(paths.assistants_file.read_text(encoding="utf-8"))
    for item in raw["assistants"]:
        if item["id"] in LOCKED_IDS:
            item["enabled_skills"] = list(picked)
    paths.assistants_file.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    loaded = _store(paths).load().assistants
    for assistant_id in LOCKED_IDS:
        assert loaded.get(assistant_id).enabled_skills == picked, assistant_id


def test_loader_keeps_hand_edited_persona_files(tmp_path) -> None:




    paths = AppPaths(tmp_path / "data").ensure()
    _store(paths).load()
    _hand_edit(paths)

    _store(paths).load()

    directory = persona.assistant_dir(paths, "soulmate")
    
    assert (directory / RULES_FILE).read_text(encoding="utf-8") == "# 我自己写的规则\n"
    assert (directory / SOUL_FILE).read_text(encoding="utf-8") == "# 我自己写的人设\n"
    assert (directory / IDENTITY_FILE).read_text(encoding="utf-8") == "# 我自己写的身份\n"


def test_persona_pack_alignment_is_one_time(tmp_path) -> None:








    paths = AppPaths(tmp_path / "data").ensure()
    _store(paths).load()

    directory = persona.assistant_dir(paths, "soulmate")
    assert (directory / SOUL_FILE).read_text(encoding="utf-8") == BUILTIN_SOULS["soulmate"]
    assert (directory / IDENTITY_FILE).read_text(encoding="utf-8") == BUILTIN_IDENTITIES["soulmate"]
    assert (directory / RULES_FILE).read_text(encoding="utf-8") == BUILTIN_RULES["soulmate"]
    
    assert (directory / "USER.md").read_text(encoding="utf-8") == BUILTIN_USERS["soulmate"]

    
    (directory / SOUL_FILE).write_text("# 用户自己改的人设\n", encoding="utf-8")
    (directory / RULES_FILE).write_text("# 我自己写的规则\n", encoding="utf-8")
    _store(paths).load()

    
    assert (directory / SOUL_FILE).read_text(encoding="utf-8") == "# 用户自己改的人设\n"
    assert (directory / RULES_FILE).read_text(encoding="utf-8") == "# 我自己写的规则\n"


def test_persona_pack_version_bump_realigns_once(tmp_path) -> None:






    paths = AppPaths(tmp_path / "data").ensure()
    _store(paths).load()

    directory = persona.assistant_dir(paths, "soulmate")
    marker = paths.data_dir / ".persona-pack-aligned"
    assert marker.read_text(encoding="utf-8").strip() == "4"

    
    marker.write_text("1\n", encoding="utf-8")
    (directory / SOUL_FILE).write_text("# 用户在旧版本里改的人设\n", encoding="utf-8")

    _store(paths).load()

    
    assert (directory / SOUL_FILE).read_text(encoding="utf-8") == BUILTIN_SOULS["soulmate"]
    assert marker.read_text(encoding="utf-8").strip() == "4"

    
    (directory / SOUL_FILE).write_text("# 再次手改\n", encoding="utf-8")
    _store(paths).load()
    assert (directory / SOUL_FILE).read_text(encoding="utf-8") == "# 再次手改\n"


def test_persona_text_migration_replaces_only_factory_text(tmp_path) -> None:









    paths = AppPaths(tmp_path / "data").ensure()
    _store(paths).load()

    directory = persona.assistant_dir(paths, "BuddyManager")
    old = PERSONA_TEXT_MIGRATIONS["BuddyManager"]
    (directory / SOUL_FILE).write_text(old[SOUL_FILE], encoding="utf-8")
    (directory / IDENTITY_FILE).write_text(old[IDENTITY_FILE], encoding="utf-8")

    _store(paths).load()

    assert (directory / SOUL_FILE).read_text(encoding="utf-8") == BUILTIN_SOULS["BuddyManager"]
    assert (directory / IDENTITY_FILE).read_text(encoding="utf-8") == BUILTIN_IDENTITIES["BuddyManager"]
    
    assert "私人军师" not in (directory / SOUL_FILE).read_text(encoding="utf-8")
    assert "私人军师" not in (directory / IDENTITY_FILE).read_text(encoding="utf-8")


def test_persona_text_migration_leaves_user_edits_alone(tmp_path) -> None:

    paths = AppPaths(tmp_path / "data").ensure()
    _store(paths).load()

    directory = persona.assistant_dir(paths, "BuddyManager")
    (directory / SOUL_FILE).write_text("# 我自己写的人设\n", encoding="utf-8")
    (directory / IDENTITY_FILE).write_text("# 我自己写的身份\n", encoding="utf-8")

    _store(paths).load()

    assert (directory / SOUL_FILE).read_text(encoding="utf-8") == "# 我自己写的人设\n"
    assert (directory / IDENTITY_FILE).read_text(encoding="utf-8") == "# 我自己写的身份\n"


def test_persona_text_migration_snapshot_is_really_old() -> None:





    for assistant_id, files in PERSONA_TEXT_MIGRATIONS.items():
        for file_name, old_text in files.items():
            fresh = (
                BUILTIN_SOULS.get(assistant_id)
                if file_name == SOUL_FILE
                else BUILTIN_IDENTITIES.get(assistant_id)
            )
            assert fresh, f"{assistant_id} 的 {file_name} 没有对应出厂正文"
            assert old_text != fresh, f"{assistant_id} 的迁移表记的是新正文，迁移永远不会触发"
            assert "首席事务助理" not in old_text, (
                f"{assistant_id} 的 {file_name} 旧文案里已经出现新说法，迁移表记错了版本"
            )


def test_user_template_inserts_gender_line_once(tmp_path) -> None:





    paths = AppPaths(tmp_path / "data").ensure()
    _store(paths).load()  
    for assistant_id in ("soulmate", "LoveBuddy", "RelationBuddy", "BuddyManager"):
        assert "用户性别" in persona.read_file(paths, assistant_id, "USER.md"), assistant_id

    
    user_file = persona.assistant_dir(paths, "soulmate") / "USER.md"
    user_file.write_text(
        "# USER · 关于用户\n\n用户称呼：老王\n\n爱喝美式。\n", encoding="utf-8"
    )
    (paths.data_dir / ".persona-pack-aligned").write_text("1\n", encoding="utf-8")

    _store(paths).load()

    patched = user_file.read_text(encoding="utf-8")
    assert "用户性别：" in patched
    
    lines = patched.split("\n")
    assert lines[2] == "用户称呼：老王"
    assert lines[3] == "用户性别："
    assert "爱喝美式。" in patched

    
    user_file.write_text("# 用户自己写的档案\n", encoding="utf-8")
    (paths.data_dir / ".persona-pack-aligned").write_text("1\n", encoding="utf-8")
    _store(paths).load()
    appended = user_file.read_text(encoding="utf-8")
    assert appended.startswith("# 用户自己写的档案\n")
    assert "用户性别：" in appended


def test_loader_keeps_editable_fields_and_memory(tmp_path) -> None:





    paths = AppPaths(tmp_path / "data").ensure()
    store = _store(paths)
    config = store.load().assistants

    profile = config.get("soulmate")
    config.upsert(profile.model_copy(update={"nickname": "宝宝", "temperature": 0.9}))
    store.save_assistants(config)
    persona.write_file(paths, "soulmate", "MEMORY.md", "# MEMORY\n\n用户喜欢喝美式。\n")

    loaded = _store(paths).load().assistants.get("soulmate")

    assert loaded.nickname == "宝宝"
    assert loaded.temperature == 0.9
    assert "美式" in persona.read_file(paths, "soulmate", "MEMORY.md")


def test_loader_never_touches_user_assistants(tmp_path) -> None:

    paths = AppPaths(tmp_path / "data").ensure()
    store = _store(paths)
    config = store.load().assistants
    config.upsert(
        AssistantProfile(id=USER_ID, name="我的搭子", description="我自己写的", enabled_skills=["calc"])
    )
    store.save_assistants(config)

    loaded = _store(paths).load().assistants.get(USER_ID)

    assert loaded.name == "我的搭子"
    assert loaded.description == "我自己写的"
    assert loaded.enabled_skills == ["calc"]





def test_lock_payload_tells_the_ui_what_to_grey_out() -> None:





    payload = lock_payload("soulmate")

    assert payload["locked"] is True
    
    
    assert sorted(payload["locked_fields"]) == ["description", "name"]
    
    
    assert "昵称、头像与人格" in payload["locked_reason"]
    assert "SOUL / IDENTITY" in payload["locked_reason"]
    
    assert "可用能力" in payload["locked_reason"]

    assert lock_payload(USER_ID) == {"locked": False, "locked_fields": [], "locked_reason": ""}





def test_reserved_skill_names_are_rejected() -> None:






    for name in ("Soulmate专用", "人际关系运营"):
        with pytest.raises(ValueError) as exc:
            xjx.reject_reserved_skill_names([name])
        assert name in str(exc.value)

    
    xjx.reject_reserved_skill_names(["calc", "kb_search", ""])


def test_rejection_messages_are_shared_by_all_four() -> None:





    names, deletes = set(), set()
    for assistant_id in LOCKED_IDS:
        with pytest.raises(LockedBuiltinError) as field_exc:
            ensure_mutable(assistant_id, changes=["name"])
        with pytest.raises(LockedBuiltinError) as delete_exc:
            ensure_deletable(assistant_id, "显示名")
        names.add(str(field_exc.value))
        deletes.add(str(delete_exc.value))

    assert len(names) == 1, f"四位内置搭子的改名文案不一致：{names}"
    assert len(deletes) == 1, f"四位内置搭子的删除文案不一致：{deletes}"
    assert "内置搭子" in names.pop()
    assert "内置搭子" in deletes.pop()

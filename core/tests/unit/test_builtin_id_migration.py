













from __future__ import annotations

import json

import pytest

from my_agent.assistants.persona import SOUL_FILE, assistant_dir
from my_agent.assistants.presets import BUILTIN_SOULS, RENAMED_BUILTIN_IDS, builtin_config
from my_agent.config.loader import ConfigStore
from my_agent.config.paths import AppPaths
from my_agent.config.schemas import (
    AssistantProfile,
    GroupProfile,
    GroupsConfig,
    ScheduledTaskSpec,
)
from my_agent.storage.db import SCHEMA_V11, Database


def _store(paths, **kwargs):










    from my_agent.assistants.bootstrap import BuiltinAssistants

    return ConfigStore(paths, builtin=BuiltinAssistants(), **kwargs)


def _write_legacy(paths: AppPaths) -> None:

    config = builtin_config()
    legacy_ids = {new: old for old, new in RENAMED_BUILTIN_IDS.items()}
    for item in config.assistants:
        legacy_id = legacy_ids.get(item.id)
        if legacy_id:
            item.id = legacy_id
    
    
    
    config.default_assistant = legacy_ids["RelationBuddy"]
    paths.assistants_file.write_text(
        json.dumps(config.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )
    for legacy_id in legacy_ids.values():
        target = assistant_dir(paths, legacy_id) / SOUL_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# SOUL\n\n我是老版本的 {legacy_id}。\n", encoding="utf-8")


def test_config_migration_is_idempotent(tmp_path):

    paths = AppPaths(tmp_path / "data").ensure()
    _write_legacy(paths)

    first = _store(paths).load()
    ids_first = sorted(item.id for item in first.assistants.assistants)
    assert "office" not in ids_first and "lovebuddy" not in ids_first
    assert "RelationBuddy" in ids_first and "LoveBuddy" in ids_first
    
    
    assert first.assistants.default_assistant == "BuddyManager"

    raw_after_first = paths.assistants_file.read_text(encoding="utf-8")
    second = _store(paths).load()
    assert sorted(item.id for item in second.assistants.assistants) == ids_first
    assert paths.assistants_file.read_text(encoding="utf-8") == raw_after_first, (
        "第二次加载不该再改动文件（迁移必须幂等）"
    )


def test_persona_dir_moves_with_the_id(tmp_path):







    paths = AppPaths(tmp_path / "data").ensure()
    _write_legacy(paths)

    _store(paths).load()

    moved = assistant_dir(paths, "RelationBuddy") / SOUL_FILE
    assert "老版本的 office" not in moved.read_text(encoding="utf-8")
    assert moved.read_text(encoding="utf-8") == BUILTIN_SOULS["RelationBuddy"]
    assert not assistant_dir(paths, "office").exists()


def test_groups_members_are_migrated(tmp_path):

    paths = AppPaths(tmp_path / "data").ensure()
    _write_legacy(paths)
    store = _store(paths)
    store.save_groups(
        GroupsConfig(
            groups=[
                GroupProfile(
                    id="legacy-group",
                    name="老群",
                    member_assistant_ids=["office", "lovebuddy"],
                    speaking_order=["lovebuddy", "office"],
                )
            ]
        )
    )

    group = store.load_groups().get("legacy-group")

    assert group is not None
    assert group.member_assistant_ids == ["RelationBuddy", "LoveBuddy"]
    assert group.speaking_order == ["LoveBuddy", "RelationBuddy"]
    
    raw = json.loads(paths.groups_file.read_text(encoding="utf-8"))
    assert raw["groups"][0]["member_assistant_ids"] == ["RelationBuddy", "LoveBuddy"]


def test_scheduled_tasks_are_migrated(tmp_path):

    paths = AppPaths(tmp_path / "data").ensure()
    _write_legacy(paths)
    store = _store(paths)
    settings = store.load().settings
    settings.agent.scheduled_tasks = [
        ScheduledTaskSpec(id="t1", name="老任务", prompt="做点事", assistant_id="office")
    ]
    paths.settings_file.write_text(
        json.dumps(settings.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )

    reloaded = _store(paths).load()

    assert [item.assistant_id for item in reloaded.settings.agent.scheduled_tasks] == [
        "RelationBuddy"
    ]
    raw = json.loads(paths.settings_file.read_text(encoding="utf-8"))
    assert raw["agent"]["scheduled_tasks"][0]["assistant_id"] == "RelationBuddy"


def test_user_made_assistant_with_legacy_id_is_untouched(tmp_path):

    paths = AppPaths(tmp_path / "data").ensure()
    _write_legacy(paths)
    config = _store(paths).load().assistants
    config.assistants = [item for item in config.assistants if item.id != "office"]
    config.upsert(AssistantProfile(id="office", name="我自己建的", builtin=False))
    paths.assistants_file.write_text(
        json.dumps(config.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )

    reloaded = _store(paths).load()

    mine = reloaded.assistants.get("office")
    assert mine is not None, "自建搭子不该被改 id"
    assert mine.name == "我自己建的"


@pytest.mark.asyncio
async def test_schema_v11_rewrites_session_owner(tmp_path):

    db = Database(tmp_path / "data.db")
    await db.connect()
    try:
        await db.execute(
            "INSERT INTO sessions (id, title, assistant_id, created_at, updated_at)"
            " VALUES ('s1', '老会话', 'office', 0, 0),"
            " ('s2', '新会话', 'RelationBuddy', 0, 0),"
            " ('s3', '别人的', 'my-own-assistant', 0, 0)"
        )
        
        
        for statement in [item for item in SCHEMA_V11.split(";") if item.strip()]:
            await db.execute(statement)
        rows = await db.fetch_all("SELECT id, assistant_id FROM sessions ORDER BY id")
    finally:
        await db.close()

    assert {row["id"]: row["assistant_id"] for row in rows} == {
        "s1": "RelationBuddy",
        "s2": "RelationBuddy",
        "s3": "my-own-assistant",
    }

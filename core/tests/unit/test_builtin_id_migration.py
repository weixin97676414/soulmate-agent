"""内置搭子改 id（office → RelationBuddy、lovebuddy → LoveBuddy）的迁移。

产品要求是「id 改成不带空格的搭子名」。id 是**主键** —— 会话归属、
群成员、人格文件目录、定时任务、长期记忆库名全挂在它上面，所以这次不是"改个字符串"，
而是一次**数据迁移**。这组用例守的就是"老数据一个都不能丢"：

1. 配置里连着跑**两段**迁移（先改名、再改 id），人格目录一起搬走；
2. 幂等：跑第二次什么都不改；
3. `groups.json` 的成员与发言顺序、`settings.json` 里的定时任务都要跟着迁
   —— 这两处最容易漏（既不在 assistants.json 里，也不在数据库里）；
4. 用户自建的搭子碰都不碰；
5. 数据库 V11 把会话归属改成新值，且非破坏。
"""

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


def _write_legacy(paths: AppPaths) -> None:
    """造一份"上个版本留下来的"配置：id / 名字 / 简介 / SOUL 全是旧值。"""
    config = builtin_config()
    legacy_ids = {new: old for old, new in RENAMED_BUILTIN_IDS.items()}
    for item in config.assistants:
        legacy_id = legacy_ids.get(item.id)
        if legacy_id:
            item.id = legacy_id
    # ⚠️ 默认位要显式写成**当时的出厂值**（``office`` → 迁移后是 ``RelationBuddy``）：
    # ``builtin_config()`` 现在的默认是 ``BuddyManager``，照着搬的话这段"默认位跟着
    # id 迁移走"的链路会被绕开 —— 用例就成了假绿。
    config.default_assistant = legacy_ids["RelationBuddy"]
    paths.assistants_file.write_text(
        json.dumps(config.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )
    for legacy_id in legacy_ids.values():
        target = assistant_dir(paths, legacy_id) / SOUL_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# SOUL\n\n我是老版本的 {legacy_id}。\n", encoding="utf-8")


def test_config_migration_is_idempotent(tmp_path):
    """配置层面：旧 id 全换新值、默认搭子跟着换，且跑两次结果一致。"""
    paths = AppPaths(tmp_path / "data").ensure()
    _write_legacy(paths)

    first = _store(paths).load()
    ids_first = sorted(item.id for item in first.assistants.assistants)
    assert "office" not in ids_first and "lovebuddy" not in ids_first
    assert "RelationBuddy" in ids_first and "LoveBuddy" in ids_first
    # 默认位连着走两段迁移：office → RelationBuddy（id 迁移）→ BuddyManager
    # （产品要求默认落到搭子总管，且只覆盖"仍是旧出厂值"的那种）
    assert first.assistants.default_assistant == "BuddyManager"

    raw_after_first = paths.assistants_file.read_text(encoding="utf-8")
    second = _store(paths).load()
    assert sorted(item.id for item in second.assistants.assistants) == ids_first
    assert paths.assistants_file.read_text(encoding="utf-8") == raw_after_first, (
        "第二次加载不该再改动文件（迁移必须幂等）"
    )


def test_persona_dir_moves_with_the_id(tmp_path):
    """人格目录要跟着 id 搬走（不搬的话内置搭子的人设会全空）。

    ⚠️ 断言**改过**：这里原先断言"内容一个字节都不能变"，
    但 ``RelationBuddy`` 属于四位写死的内置搭子，目录搬完紧接着就会被
    ``loader._enforce_locked_builtins`` 回写成出厂正文 ——
    所以现在能断言的是"搬过去了，而且内容等于出厂正文"。
    """
    paths = AppPaths(tmp_path / "data").ensure()
    _write_legacy(paths)

    _store(paths).load()

    moved = assistant_dir(paths, "RelationBuddy") / SOUL_FILE
    assert "老版本的 office" not in moved.read_text(encoding="utf-8")
    assert moved.read_text(encoding="utf-8") == BUILTIN_SOULS["RelationBuddy"]
    assert not assistant_dir(paths, "office").exists()


def test_groups_members_are_migrated(tmp_path):
    """群成员与发言顺序：**升级用户最容易踩的一处**（不迁的话群指向不存在的搭子）。"""
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
    # 也要落盘，否则重启后又变回旧 id
    raw = json.loads(paths.groups_file.read_text(encoding="utf-8"))
    assert raw["groups"][0]["member_assistant_ids"] == ["RelationBuddy", "LoveBuddy"]


def test_scheduled_tasks_are_migrated(tmp_path):
    """定时任务里的 assistant_id（在 settings.json 里，最容易被漏）。"""
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
    """用户自己建的搭子（`builtin=False`）即使 id 是 office 也不能被"迁移"掉。"""
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
    """数据库 V11：会话归属里的旧 id 换成新值，不认得的值一个都不动。"""
    db = Database(tmp_path / "data.db")
    await db.connect()
    try:
        await db.execute(
            "INSERT INTO sessions (id, title, assistant_id, created_at, updated_at)"
            " VALUES ('s1', '老会话', 'office', 0, 0),"
            " ('s2', '新会话', 'RelationBuddy', 0, 0),"
            " ('s3', '别人的', 'my-own-assistant', 0, 0)"
        )
        # 直接执行 V11 的语句：库建出来时已经是 V11 了，所以这里验的是**语句本身**
        # 对不对（列名写错这类错误只在真库上才暴露，而用户的库一辈子只升一次级）
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

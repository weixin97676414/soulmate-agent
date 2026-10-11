"""助手（Agent 预设）的单元测试。"""

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


# --------------------------------------------------------------------------- #
# 内置预设
# --------------------------------------------------------------------------- #
def test_builtin_assistants_are_complete():
    """内置助手清单（含 Soulmate 系列两个伴侣）。

    次序按**定义顺序**（界面上的展示次序由 sort_order 决定，与之不同）。
    """
    ids = [item.id for item in BUILTIN_ASSISTANTS]
    # 数据分析师（analyst）/ 文档写作助手（writer）/ PlayBuddy（life）/
    # SoulBuddy（soulbuddy）已按产品决策移除
    assert ids == [
        "RelationBuddy",
        "soulmate",
        "LoveBuddy",
        # 产品要求新增的入口搭子（自己不干活，只安排别的搭子）
        "BuddyManager",
    ]
    assert all(item.builtin for item in BUILTIN_ASSISTANTS)
    # 这里曾经还断言 ``system_prompt`` 非空。那个字段已不参与提示词组装
    # （见 agent/engine.py 的 _system_prompt），非不非空都不影响行为 ——
    # 所以不再断言，免得反过来暗示它还有用。


def test_removed_builtin_ids_match_reality():
    """REMOVED_BUILTIN_IDS 必须与预设表实际状态一致。

    这个常量负责启动时清理旧配置里的幽灵条目，写漏了清理就会失效；
    写多了会把还存在的助手误删。两边对得上，这条链路才是完整的。
    """
    from my_agent.assistants.presets import REMOVED_BUILTIN_IDS

    ids = {item.id for item in BUILTIN_ASSISTANTS}
    assert not ids & set(REMOVED_BUILTIN_IDS)


def test_renamed_builtins_keep_ids():
    """改名只动 name，不动 id —— id 是会话归属与人格文件目录的键。"""
    by_id = {item.id: item for item in BUILTIN_ASSISTANTS}
    assert by_id["RelationBuddy"].name == "Relation Buddy"
    assert by_id["LoveBuddy"].name == "Love Buddy"
    # 中文说明**进简介**（产品定的口径）。⚠️ 断言改过：
    # 简介正文现在逐字取自《搭子人格包》的 简介.md（见 presets._pack_intro），
    # 不再是代码里手写的那两句旧文案。
    # ⚠️ 又改过一次：Relation Buddy 的简介换成了新的三行
    # （"职场人际关系运营助手 / 日常社交问题 / 深度剖析心理运作模式"）。
    assert by_id["RelationBuddy"].description.startswith("我是你的职场人际关系运营助手")
    assert "我是你的 Relation Buddy" not in by_id["RelationBuddy"].description
    assert by_id["LoveBuddy"].description.startswith("我是你的婚恋情感搭子")


def test_companion_assistants_have_no_skill_restriction():
    """两个伴侣助手的技能白名单是空的。

    ⚠️ 空列表的含义 2026-10-06 **反转过**：以前是"不限制（全开）"，
    现在是"**没有额外勾选任何技能**"。但两种含义下这里要钉住的东西都一样 ——
    **它必须为空**：内置搭子的白名单被 `locked_builtins` 锁着，
    非空就意味着有人绕过了那把锁。
    """
    companions = {"soulmate", "LoveBuddy"}
    for profile in BUILTIN_ASSISTANTS:
        if profile.id in companions:
            assert profile.enabled_skills == []
            # 派生字段的含义同样变了：现在它只说明"额外勾没勾"（False = 一个都没额外勾）
            assert profile.to_dict()["restricts_skills"] is False


def test_builtin_skill_whitelists_reference_real_skills():
    """预设里写的技能名必须是真实存在的。

    写错一个名字不会让程序报错，只会让助手悄悄少一个工具——
    这种问题在界面上很难被发现，所以用测试钉死。
    """
    try:
        from my_agent.skill.builtin import discover_builtin_skills
    except ImportError:  # pragma: no cover
        pytest.skip("技能发现不可用")

    known = {cls.meta.name for cls in discover_builtin_skills()}
    for profile in BUILTIN_ASSISTANTS:
        unknown = [name for name in profile.enabled_skills if name not in known]
        assert not unknown, f"{profile.id} 引用了不存在的技能：{unknown}"


def test_builtin_skill_whitelists_exclude_mcp():
    """预设里不能写 MCP 工具名：它们随连接状态增删，写死了会指向空气。"""
    for profile in BUILTIN_ASSISTANTS:
        assert not [name for name in profile.enabled_skills if "__" in name]


def test_builtin_config_returns_independent_copies():
    """每次返回的必须是副本。

    否则用户改了助手的提示词，会连模块级的模板一起改掉——
    同进程内的其他测试/请求就会看到被污染的定义。
    """
    first = builtin_config()
    first.assistants[0].name = "被改过了"
    first.assistants[0].enabled_skills.append("calc")

    second = builtin_config()
    assert second.assistants[0].name != "被改过了"
    assert "calc" not in second.assistants[0].enabled_skills


# --------------------------------------------------------------------------- #
# 配置校验
# --------------------------------------------------------------------------- #
def test_assistant_id_rejects_illegal_chars():
    """非法 id 必须在**校验期**就被拒，而不是留到落盘或用于 URL 拼接时。

    这里断言具体的 ``ValidationError`` 而不是 ``Exception``：后者会把
    "抛了个 TypeError"（比如校验器自身写错）也当成通过，测试就失去意义了。
    """
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


# --------------------------------------------------------------------------- #
# apply_assistant
# --------------------------------------------------------------------------- #
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
    """空列表 = "一个都没额外勾"，**不是**"不限制"（这条口径 2026-10-06 反转过）。

    ⚠️ 这里测的只是 `Session` 里存下来的**原始值**：真正"能用什么"由
    `SkillManager.allowed_names` 在装配时展开（内置技能 ∪ 自己的专属 ∪ 勾选的通用/我的，
    见 skill/groups.py）。之所以还要钉住这个 None，是因为"没勾"与"勾了"在持久化层
    必须分得开 —— 以前两者都是"全开"，现在不是了。
    """
    session = Session(id="s1")
    session.apply_assistant(AssistantProfile(id="RelationBuddy", name="办公", enabled_skills=[]))
    assert session.enabled_skills is None


def test_apply_assistant_keeps_history():
    """切换助手**不能**清空历史。

    清空是不可逆的破坏；而且技术上也不需要——每轮 run_stream 都会用
    ensure_system() 就地替换 system 消息，列表里永远只有一条 system，
    不存在两套人设共存的问题。
    """
    session = Session(id="s1")
    session.memory.add_user("之前的对话")
    session.memory.add_assistant("之前的回复")

    session.apply_assistant(AssistantProfile(id="writer", name="写作", system_prompt="你是写作助手"))

    assert len(session.history()) == 2
    assert session.history()[0]["content"] == "之前的对话"


def test_apply_assistant_without_model_keeps_current_choice():
    """助手没指定模型时，不该把用户手选的模型抹掉。"""
    session = Session(id="s1", model_id="qwen-max")
    session.apply_assistant(AssistantProfile(id="RelationBuddy", name="办公"))
    assert session.model_id == "qwen-max"


def test_apply_assistant_updates_in_place_after_prompt_change():
    """连续切两次助手，system 消息应被替换而不是叠加。"""
    session = Session(id="s1")
    session.apply_assistant(AssistantProfile(id="a", name="A", system_prompt="提示词 A"))
    session.memory.ensure_system("提示词 A")

    session.apply_assistant(AssistantProfile(id="b", name="B", system_prompt="提示词 B"))
    session.memory.ensure_system(session.system_prompt)

    systems = [m for m in session.memory.messages if m.role == "system"]
    assert len(systems) == 1
    assert systems[0].content == "提示词 B"


# --------------------------------------------------------------------------- #
# 出厂改名迁移（RENAMED_BUILTINS + ConfigStore.load）
# --------------------------------------------------------------------------- #
def _write_legacy_assistants(paths: Any) -> AssistantsConfig:
    """造一份"上个版本留下来的"配置：**id、名字、简介、SOUL 全是旧值**。

    ⚠️ 这里必须连 **id 一起写成旧的**（``office`` / ``lovebuddy``）：老用户磁盘上
    就是那样，而 ``RENAMED_BUILTINS``（改名迁移表）也是按旧 id 查的。
    于是这次 ``load()`` 会连着跑两段迁移 —— 先改名、再改 id 并把人格目录搬过去，
    正是升级用户真实会走的那条路（以前这个辅助函数只写了旧名字、id 还是新的，
    等于绕开了迁移，用例是"假绿"的）。
    """
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
    # ⚠️ 默认搭子也要写成**当时的出厂值**（RelationBuddy，再往前是 ``office``）。
    # ``builtin_config()`` 现在的默认是 ``BuddyManager``，不显式改回去的话
    # ``default_assistant in legacy_ids`` 永远不成立，这段"默认位跟着 id 迁移走"
    # 的链路就被绕开了 —— 用例会变成假绿。
    config.default_assistant = legacy_ids["RelationBuddy"]
    paths.assistants_file.write_text(
        json.dumps(config.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )
    return config


def test_first_load_writes_builtin_souls(tmp_path):
    """**全新安装的首启**就要把出厂 SOUL.md 写出来。

    这条是回归用例：加载配置时"首次播种"分支曾提前 ``return``，把播种 SOUL
    这一步漏掉了。在提示词兜底退役之后，内置搭子的人设**只**来自 SOUL.md ——
    漏播的后果是首启那一次会话一条 system 都没有，用户会看到"搭子不知道自己是谁"，
    而且**要等到第二次启动才自愈**。
    """
    from my_agent.assistants.persona import build_persona_section

    paths = AppPaths(tmp_path / "data").ensure()

    _store(paths).load()

    soul = assistant_dir(paths, "RelationBuddy") / SOUL_FILE
    assert soul.is_file(), "首启没写出厂 SOUL.md"
    # ⚠️ 断言改过：出厂 SOUL 逐字取自《搭子人格包》后，
    # RelationBuddy 的正文是"你的风格"那段（不含"Relation Buddy"字样），
    # 所以这里钉的是"等于出厂正文"，而不是"含搭子名"。
    assert soul.read_text(encoding="utf-8") == BUILTIN_SOULS["RelationBuddy"]
    # 人格装配必须非空 —— 空人格会让引擎干脆不发 system 消息
    assert build_persona_section(paths, "RelationBuddy", nickname="").strip()


def test_renamed_builtins_are_migrated(tmp_path):
    """老配置里"仍是出厂旧值"的名字 / 简介 / SOUL 都要换成新值。

    光改代码里的预设对老用户没用 —— 配置是持久化的，他们磁盘上仍是旧名。
    """
    paths = AppPaths(tmp_path / "data").ensure()
    _write_legacy_assistants(paths)

    loaded = _store(paths).load()

    assert loaded.assistants.get("RelationBuddy").name == "Relation Buddy"
    assert loaded.assistants.get("LoveBuddy").name == "Love Buddy"
    # ⚠️ 简介断言改过：出厂简介换成《搭子人格包》的 简介.md 正文。
    # 又改过一次：Relation Buddy 的简介换成新的三行。
    assert loaded.assistants.get("RelationBuddy").description.startswith(
        "我是你的职场人际关系运营助手"
    )

    # SOUL.md 里的自称才是模型真正看到的那份人设，必须一起换。
    # ⚠️ 断言改过（同上）：出厂 SOUL 现在逐字等于人格包原文（"你的风格"那段，
    # 不含搭子名），所以钉"等于出厂正文 + 旧自称绝不能还在"。
    soul = (assistant_dir(paths, "RelationBuddy") / SOUL_FILE).read_text(encoding="utf-8")
    assert soul == BUILTIN_SOULS["RelationBuddy"]
    assert "WorkBuddy" not in soul

    # 迁移结果要落盘：否则每次启动都白算一遍，而且界面上永远是旧名
    raw = json.loads(paths.assistants_file.read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in raw["assistants"]}
    assert by_id["RelationBuddy"]["name"] == "Relation Buddy"
    # 简介出厂值已换成《搭子人格包》正文
    assert by_id["LoveBuddy"]["description"].startswith("我是你的婚恋情感搭子")
    assert not any(item["id"] in RENAMED_BUILTIN_IDS for item in raw["assistants"])

    # id 迁移 + 人格目录搬家（产品要求 id = 名字去空格）
    #
    # ⚠️ 默认位到这里应该是 **BuddyManager**，而不是迁移后的 ``RelationBuddy``：
    # 这段磁盘数据是"默认位还是 RelationBuddy"的老机器，会连着走两段迁移 ——
    # ① office → RelationBuddy（id 迁移，默认位一起换）
    # ② RelationBuddy → BuddyManager（产品要求默认落到搭子总管）
    # 第二段只在"默认位仍是旧出厂值"时才动，所以这条断言同时钉住了那个条件。
    assert raw["default_assistant"] == "BuddyManager"
    assert not assistant_dir(paths, "office").exists()
    assert assistant_dir(paths, "LoveBuddy").is_dir()
    # ⚠️ 这里**不能**断言 `not assistant_dir(paths, "lovebuddy").exists()`：
    # Windows / macOS 的文件系统大小写不敏感，那个路径会解析到同一个目录上
    # （写这条断言只有 Linux 会绿，是本项目"只在一边绿"的经典坑）。


def test_locked_builtins_reset_user_edits(tmp_path):
    """⚠️ 这条测试的**结论在 2026-09-28 反过来了**，旧名字留在注释里是为了别再改回去。

    它原先叫 ``test_renamed_builtins_never_touch_user_edits``，断言"用户自己改过的
    名字 / 简介 / SOUL 一个字都不能动"。产品约定：

        「四位内置搭子（Buddy Manager / Soulmate / Love Buddy / Relation Buddy）
          的简介、规则、名称、可用能力全部写死，任何途径不可改、不可删」

    而 ``RelationBuddy`` 同时又是 id 迁移的落点，于是"迁移保用户编辑"这条老规矩
    在这四个 id 上**必须让路** —— 两条规矩都成立，只是服务的对象不同：
    其它内置搭子属于用户，这四个属于产品。

    仍然成立的那半条见 ``test_locked_builtins_skip_user_assistants``。
    """
    paths = AppPaths(tmp_path / "data").ensure()
    config = _write_legacy_assistants(paths)

    profile = config.get("office")  # 旧 id（用户磁盘上的样子）
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

    # id 迁移照做（老数据得搬到新目录），但写死的三样被掰回出厂值
    assert loaded.assistants.get("RelationBuddy") is not None
    assert loaded.assistants.get("RelationBuddy").name == "Relation Buddy"
    # ⚠️ 简介出厂值换成《搭子人格包》正文后，这里改为与
    # 出厂表对比，而不是抄一份字面量 —— 表改了测试不该跟着假红
    assert loaded.assistants.get("RelationBuddy").description == (
        builtin_config().get("RelationBuddy").description
    )
    # SOUL 也被换回出厂正文 —— 留着用户那份等于"改掉内置搭子的人设"还有一条路
    moved = assistant_dir(paths, "RelationBuddy") / SOUL_FILE
    assert "我自己写的人设" not in moved.read_text(encoding="utf-8")
    # 同一个文件里没被改过的另一个搭子，照常迁移
    assert loaded.assistants.get("LoveBuddy").name == "Love Buddy"


def test_builtin_temperatures_are_migrated(tmp_path):
    """温度出厂值调整只迁"仍是旧出厂值"的：自调过的不动。

    温度是用户可调字段（不在硬锁范围），所以不能像简介那样一律掰回 ——
    这里沿用改名迁移的同一条规矩：逐字等于旧出厂值才替换。
    """
    paths = AppPaths(tmp_path / "data").ensure()
    config = builtin_config()
    by_id = {item.id: item for item in config.assistants}
    by_id["LoveBuddy"].temperature = 0.85  # 旧出厂值 → 应迁到 0.5
    by_id["soulmate"].temperature = 0.9  # 用户自调 → 不动
    paths.assistants_file.write_text(
        json.dumps(config.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )

    loaded = _store(paths).load()

    assert loaded.assistants.get("LoveBuddy").temperature == 0.5
    assert loaded.assistants.get("RelationBuddy").temperature == 0.4
    assert loaded.assistants.get("soulmate").temperature == 0.9


def test_locked_builtins_skip_user_assistants(tmp_path):
    """用户自己建的搭子照旧一个字都不动 —— 被锁的只有那四个**出厂 id**。

    ⚠️ 这里用旧出厂 id ``office`` 而不是 ``RelationBuddy``：后者已经在写死名单里，
    它已经不可能是"用户自建的搭子"了。断言的核心没变 ——
    ``builtin=False`` 的条目既不被改名迁移、也不被 id 迁移、更不被写死回写碰到。
    """
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

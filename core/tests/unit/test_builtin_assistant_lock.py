"""四位内置搭子的硬锁（``assistants/locked_builtins.py``）。

## 产品约定（，原文）

    「四位内置搭子（Buddy Manager / Soulmate / Love Buddy / Relation Buddy）
      的简介、规则、名称、可用能力全部写死，任何途径不可改、不可删」

## 为什么"任何途径"这四个字决定了测试的样子

"某条路径拒绝"和"任何途径都拒绝"是两种不同的东西，测试也得分开写：

- **裁决层**（本文件上半部分）：直接调那几个 ``ensure_*``，钉住判断本身。
- **唯一汇合点**（中段）：删除只有一个入口（``lifecycle``），
  所以"群解散连带删除""搭子总管技能删除""设置页按钮"三条路一次全覆盖。
- **兜底**（下半段）：``persona.write_file`` 是**唯一**的写盘函数 ——
  即使将来有人加了一个新的写入口忘了加裁决，也绕不过去。
- **启动回写**（末段）：接口与技能都挡不住"直接改文件"，所以每次启动要掰回去。
  ⚠️ 范围（修正：）：人格文件里**只有 RULES.md** 继续锁定；
  SOUL / IDENTITY 在《搭子人格包》**一次性对齐**之后解锁 —— 用户改了要算数，
  回写再把它们掰回去就违背了"这是不对的"那句更正。

⚠️ 单独测某一个接口是不够的：那只能证明"这条路是堵的"，
不能证明"没有别的路"。这也是这批改动里唯一值得写这么多断言的地方。
"""

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
    builtin_config,
)
from my_agent.config.loader import ConfigStore
from my_agent.config.paths import AppPaths
from my_agent.config.schemas import AssistantProfile
from my_agent.errors import SkillExecutionError
from my_agent.server.runtime import AppRuntime
from my_agent.skill.builtin import xjx


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

FOUR = ("BuddyManager", "soulmate", "LoveBuddy", "RelationBuddy")
# 一个"用户自己建的搭子"：锁对它必须**完全不生效**
USER_ID = "my-own-buddy"


@pytest.fixture
def runtime(tmp_path):
    paths = AppPaths(tmp_path / "data").ensure()
    return AppRuntime(paths=paths)


def _profile(assistant_id: str) -> AssistantProfile:
    profile = builtin_config().get(assistant_id)
    assert profile is not None, f"内置搭子 {assistant_id} 不见了"
    return profile


# --------------------------------------------------------------------------- #
# 名单与字段
# --------------------------------------------------------------------------- #
def test_exactly_four_ids_are_locked() -> None:
    """名单里一个不多、一个不少。

    多一个 → 某个用户/自建搭子被莫名锁住；少一个 → 那个内置搭子可以随便改。
    两种都不会报错，只会安静地做错事，所以钉在这里。
    """
    assert LOCKED_ASSISTANT_IDS == set(FOUR)
    assert all(is_locked(item) for item in FOUR)
    assert not is_locked(USER_ID)


def test_changed_fields_reports_every_locked_field() -> None:
    """三个写死字段被同时改了，**三个都要报出来**。

    ⚠️ 只报第一个的话，用户按提示改回第一项、再保存，又被第二项顶回来 ——
    像打地鼠。这类"一次只报一个"的体验问题在硬锁上尤其明显，
    因为用户根本没有"多试几次"的耐心：他以为这功能坏了。
    """
    before = _profile("soulmate")
    after = before.model_copy(
        update={"name": "改名", "description": "改简介", "enabled_skills": ["calc"]}
    )

    assert sorted(changed_fields(before, after)) == ["description", "enabled_skills", "name"]


def test_changed_fields_ignores_allowed_fields() -> None:
    """昵称 / 头像 / 温度 / 模型：用户正当要改的东西，不算"改动"。"""
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
    """锁的是字段，不是"整个搭子"：一个字段都没碰就别拦。"""
    ensure_mutable("soulmate", changes=())  # 不该抛


def test_ensure_mutable_rejects_locked_field_with_readable_message() -> None:
    with pytest.raises(LockedBuiltinError) as exc:
        ensure_mutable("soulmate", changes=["name"])

    message = str(exc.value)
    # 得说清"哪一项被锁"和"哪些还能改"——否则用户只会反复点保存
    assert "名称" in message
    assert "昵称" in message


def test_ensure_mutable_ignores_user_assistants() -> None:
    ensure_mutable(USER_ID, changes=["name", "description", "enabled_skills"])


# --------------------------------------------------------------------------- #
# 删除：唯一的汇合点
# --------------------------------------------------------------------------- #
def test_ensure_deletable_rejects_builtins() -> None:
    for assistant_id in FOUR:
        with pytest.raises(LockedBuiltinError) as exc:
            ensure_deletable(assistant_id, "显示名")
        assert "内置搭子" in str(exc.value)


def test_lifecycle_refuses_and_keeps_the_assistant(runtime) -> None:
    """生命周期层拒绝之后，配置必须**一点没变**（别留下删一半的残局）。"""
    for assistant_id in FOUR:
        with pytest.raises(LockedBuiltinError):
            lifecycle.delete_assistant(runtime, assistant_id)

    left = {item.id for item in runtime.assistants.sorted()}
    assert set(FOUR) <= left


async def test_orchestrator_delete_raises_a_user_facing_error(runtime) -> None:
    """搭子总管技能那条路：抛出的异常必须是 ``ValueError`` 的子类。

    技能外壳只认 ``ValueError``；不是它的话会变成一个 500 / "未知错误"，
    用户拿到的提示里没有"为什么不能删"。
    """
    assert issubclass(LockedBuiltinError, ValueError)

    with pytest.raises(ValueError):
        await runtime.orchestrator.delete_assistant(assistant_id="soulmate")


# --------------------------------------------------------------------------- #
# 人格文件：写死 + 兜底
# --------------------------------------------------------------------------- #
def test_persona_files_are_locked_but_memory_is_not() -> None:
    """⚠️ 只有 RULES 写不动；SOUL / IDENTITY / MEMORY / USER 必须都能写。

    ⚠️ 范围改过（修正：）：原先 SOUL/IDENTITY 也在锁内，
    用户更正"这是不对的"——它们对齐一次后必须能改，否则用户改不了搭子的性格与身份。
    锁死记忆/性格等于把搭子变成一块不会成长的石头。
    """
    with pytest.raises(LockedBuiltinError):
        ensure_persona_writable("LoveBuddy", RULES_FILE)

    # 解锁的四份：内置搭子照样能写
    for name in (SOUL_FILE, IDENTITY_FILE, "MEMORY.md", "USER.md"):
        ensure_persona_writable("LoveBuddy", name)
    # 自建搭子的全都能写
    for name in (SOUL_FILE, IDENTITY_FILE, RULES_FILE):
        ensure_persona_writable(USER_ID, name)


def test_write_file_is_the_backstop(runtime) -> None:
    """``persona.write_file`` 是唯一的写盘函数，任何路径都绕不过它。

    特意测这一层：将来有人加了新的写入口却忘了加裁决，
    只要他走的是这个函数，就还是被拦住 —— 这比"记得在每个入口加判断"可靠得多。
    """
    with pytest.raises(LockedBuiltinError):
        write_file(runtime.paths, "soulmate", RULES_FILE, "# 我自己写的规则\n")

    # SOUL 已解锁：写得进去，且内容落盘
    write_file(runtime.paths, "soulmate", SOUL_FILE, "# 我自己写的人设\n")
    assert "我自己写的人设" in persona.read_file(runtime.paths, "soulmate", SOUL_FILE)

    # 记忆照写
    write_file(runtime.paths, "soulmate", "MEMORY.md", "# MEMORY\n\n用户喜欢喝美式。\n")
    assert "美式" in persona.read_file(runtime.paths, "soulmate", "MEMORY.md")


async def test_team_update_assistant_refuses_to_append(runtime) -> None:
    """搭子总管技能的"补充设定"：追加也算改，而且要在**动手写之前**就拒绝。

    写一份判一份的话，被锁的搭子上会留下"第一份写进去了、第二份才报错"的半截状态。
    """
    before = persona.read_file(runtime.paths, "soulmate", SOUL_FILE)

    with pytest.raises((LockedBuiltinError, SkillExecutionError)) as exc:
        await runtime.orchestrator.append_assistant_setup(
            assistant_id="soulmate",
            tone_append="以后说话简短点。",
            rules_append="不许说脏话。",
        )

    assert "内置搭子" in str(exc.value)
    assert persona.read_file(runtime.paths, "soulmate", SOUL_FILE) == before


async def test_team_update_assistant_refuses_to_append_description(runtime) -> None:
    """简介也是被锁的一项 —— 追加不是"绕过写死"的后门。"""
    before = runtime.assistants.get("soulmate").description

    with pytest.raises((LockedBuiltinError, SkillExecutionError)):
        await runtime.orchestrator.append_assistant_setup(
            assistant_id="soulmate", description_append="顺带也懂点法律。"
        )

    assert runtime.assistants.get("soulmate").description == before


# --------------------------------------------------------------------------- #
# 启动回写：挡住"直接改文件"
# --------------------------------------------------------------------------- #
def _hand_edit(paths: AppPaths) -> None:
    """把配置和人格文件都按"用户手改"的样子写坏一遍。"""
    raw = json.loads(paths.assistants_file.read_text(encoding="utf-8"))
    for item in raw["assistants"]:
        if item["id"] in FOUR:
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
    """手改过的写死字段，下次启动必须被掰回去。

    接口拦得住模型，拦不住"直接编辑 json" —— 这条是那半边。
    """
    paths = AppPaths(tmp_path / "data").ensure()
    _store(paths).load()  # 先落一次盘
    _hand_edit(paths)

    loaded = _store(paths).load().assistants

    for assistant_id in FOUR:
        profile = loaded.get(assistant_id)
        factory = _profile(assistant_id)
        assert profile.name == factory.name, assistant_id
        assert profile.description == factory.description, assistant_id
        assert profile.enabled_skills == factory.enabled_skills, assistant_id


def test_loader_restores_persona_files_on_start(tmp_path) -> None:
    """⚠️ 范围改过（修正：）：只有 RULES 被掰回去。

    SOUL / IDENTITY 已经在首次加载时**一次性对齐**到《搭子人格包》并解锁 ——
    之后用户手改它们必须算数（marker 挡住再次对齐），只有 RULES 继续锁定。
    """
    paths = AppPaths(tmp_path / "data").ensure()
    _store(paths).load()
    _hand_edit(paths)

    _store(paths).load()

    directory = persona.assistant_dir(paths, "soulmate")
    # RULES 还在锁内：手改被掰回出厂
    rules = directory / RULES_FILE
    assert rules.read_text(encoding="utf-8") == BUILTIN_RULES["soulmate"]
    # SOUL / IDENTITY 已解锁：手改原样保留 —— 这正是"这是不对的"那句更正要的效果
    assert (directory / SOUL_FILE).read_text(encoding="utf-8") == "# 我自己写的人设\n"
    assert (directory / IDENTITY_FILE).read_text(encoding="utf-8") == "# 我自己写的身份\n"


def test_persona_pack_alignment_is_one_time(tmp_path) -> None:
    """首次加载把人格文件对齐到《搭子人格包》原文；此后用户的手改必须算数。

    这条同时钉住两件事：
    ① 对齐**发生**（机器上被写坏的旧文件被矫成正文 —— 用户点名要删的那几句
      只在旧文件里，对齐即消失）；
    ② 对齐**只发生一次**（marker 机制）—— 没有它的话，用户每次改完 SOUL
      一重启就被覆盖回出厂，等于没解锁。
    """
    paths = AppPaths(tmp_path / "data").ensure()
    _store(paths).load()

    directory = persona.assistant_dir(paths, "soulmate")
    assert (directory / SOUL_FILE).read_text(encoding="utf-8") == BUILTIN_SOULS["soulmate"]
    assert (directory / IDENTITY_FILE).read_text(encoding="utf-8") == BUILTIN_IDENTITIES["soulmate"]
    assert (directory / RULES_FILE).read_text(encoding="utf-8") == BUILTIN_RULES["soulmate"]
    # USER 模板播种了（缺失才写）；它是活文档，之后不参与任何覆盖
    assert (directory / "USER.md").read_text(encoding="utf-8") == BUILTIN_USERS["soulmate"]

    # 用户手改 SOUL + 手改 RULES，再启动一次
    (directory / SOUL_FILE).write_text("# 用户自己改的人设\n", encoding="utf-8")
    (directory / RULES_FILE).write_text("# 我自己写的规则\n", encoding="utf-8")
    _store(paths).load()

    # SOUL 的手改保留（解锁生效）；RULES 的手改被掰回（仍在锁内）
    assert (directory / SOUL_FILE).read_text(encoding="utf-8") == "# 用户自己改的人设\n"
    assert (directory / RULES_FILE).read_text(encoding="utf-8") == BUILTIN_RULES["soulmate"]


def test_persona_pack_version_bump_realigns_once(tmp_path) -> None:
    """marker **版本化**：模板升级（版本号 +1）时重对齐一次，之后手改重新算数。

    这条是 43 批"性别行"需求的守护：0.1.50 的机器上 marker 已经写过，直接改
    资源模板永远不生效。marker 里写版本号、版本不一致就重对齐一次 ——
    重对齐会覆盖用户在旧版本期间的手改（模板变更的既定代价），但**只发生一次**。
    """
    paths = AppPaths(tmp_path / "data").ensure()
    _store(paths).load()

    directory = persona.assistant_dir(paths, "soulmate")
    marker = paths.data_dir / ".persona-pack-aligned"
    assert marker.read_text(encoding="utf-8").strip() == "3"

    # 模拟"装过 0.1.50（marker 版本 1）"的机器：旧 marker + 用户改过的 SOUL
    marker.write_text("1\n", encoding="utf-8")
    (directory / SOUL_FILE).write_text("# 用户在旧版本里改的人设\n", encoding="utf-8")

    _store(paths).load()

    # 版本不一致 → 重对齐一次：SOUL 回到新原文（含性别行），marker 升到 3
    assert (directory / SOUL_FILE).read_text(encoding="utf-8") == BUILTIN_SOULS["soulmate"]
    assert marker.read_text(encoding="utf-8").strip() == "3"

    # 之后的手改照常算数
    (directory / SOUL_FILE).write_text("# 再次手改\n", encoding="utf-8")
    _store(paths).load()
    assert (directory / SOUL_FILE).read_text(encoding="utf-8") == "# 再次手改\n"


def test_user_template_inserts_gender_line_once(tmp_path) -> None:
    """USER 是活文档：已有文件只补缺失的"用户性别"行，其余内容一字不动。

    四位内置搭子都有 USER 模板（产品要求"用户称呼"下加"用户性别："）；
    已有档案不能整份覆盖 —— 那会把 AI 已记录的称呼/偏好抹掉，所以走**插行**。
    """
    paths = AppPaths(tmp_path / "data").ensure()
    _store(paths).load()  # 四位都播种了含"用户性别"行的模板
    for assistant_id in ("soulmate", "LoveBuddy", "RelationBuddy", "BuddyManager"):
        assert "用户性别" in persona.read_file(paths, assistant_id, "USER.md"), assistant_id

    # 造一份"AI 已写过、但没有用户性别行"的旧档案，并把 marker 退回旧版本触发重对齐
    user_file = persona.assistant_dir(paths, "soulmate") / "USER.md"
    user_file.write_text(
        "# USER · 关于用户\n\n用户称呼：老王\n\n爱喝美式。\n", encoding="utf-8"
    )
    (paths.data_dir / ".persona-pack-aligned").write_text("1\n", encoding="utf-8")

    _store(paths).load()

    patched = user_file.read_text(encoding="utf-8")
    assert "用户性别：" in patched
    # 插在"用户称呼"行之后，其余内容原样保留
    lines = patched.split("\n")
    assert lines[2] == "用户称呼：老王"
    assert lines[3] == "用户性别："
    assert "爱喝美式。" in patched

    # 没有锚点行的档案：兜底**追加**在末尾（不挤占原文任何一行）
    user_file.write_text("# 用户自己写的档案\n", encoding="utf-8")
    (paths.data_dir / ".persona-pack-aligned").write_text("1\n", encoding="utf-8")
    _store(paths).load()
    appended = user_file.read_text(encoding="utf-8")
    assert appended.startswith("# 用户自己写的档案\n")
    assert "用户性别：" in appended


def test_loader_keeps_editable_fields_and_memory(tmp_path) -> None:
    """回写只动写死的那几样：昵称、头像、记忆不受影响。

    这一条是**反向**断言，别删：没有它的话，"回写"很容易被后来的人顺手扩成
    "把整份 profile 覆盖成出厂值"，于是用户给搭子起的昵称每重启一次就丢一次。
    """
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
    """用户自建的搭子：名字、简介、能力一个字都不能动。"""
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


# --------------------------------------------------------------------------- #
# 界面拿得到的"为什么"
# --------------------------------------------------------------------------- #
def test_lock_payload_tells_the_ui_what_to_grey_out() -> None:
    """名单只存在于核心这一处：界面不另存一份，问接口要。

    界面自己写死一份的话，将来加一个内置搭子要改两个仓库，
    而漏改的那处不会报错 —— 只是那个搭子突然可以随便改了。
    """
    payload = lock_payload("soulmate")

    assert payload["locked"] is True
    assert sorted(payload["locked_fields"]) == ["description", "enabled_skills", "name"]
    # 文案要点名"哪些还能改"——SOUL/IDENTITY 解锁后（修正：），
    # "还能改什么"的清单里必须有人格，否则用户以为连性格都改不了
    assert "昵称、头像与人格" in payload["locked_reason"]
    assert "SOUL / IDENTITY" in payload["locked_reason"]

    assert lock_payload(USER_ID) == {"locked": False, "locked_fields": [], "locked_reason": ""}


# --------------------------------------------------------------------------- #
# 专属技能名不能写进技能清单
# --------------------------------------------------------------------------- #
def test_reserved_skill_names_are_rejected() -> None:
    """心鉴学专属技能是"线路 + 归属"算出来的，写进白名单**还会把搭子弄残**。

    非空 ``enabled_skills`` = "只开放这几项"，于是模型写下这几个名字之后，
    那个搭子的工具清单会被收窄成"什么都没有"——用户看到的是"搭子突然什么都不会了"，
    而原因藏在一份他根本没编辑过的技能清单里。所以必须明确报错，不能静默剔除。
    """
    for name in ("Soulmate专用", "人际关系运营"):
        with pytest.raises(ValueError) as exc:
            xjx.reject_reserved_skill_names([name])
        assert name in str(exc.value)

    # 普通技能名原样放行
    xjx.reject_reserved_skill_names(["calc", "kb_search", ""])


def test_rejection_messages_are_shared_by_all_four() -> None:
    """四位用同一套文案，别各写各的 —— 用户看到的口径必须一致。

    文案里必须同时出现"内置搭子"（是什么）和"昵称"（还能改什么）。
    只说"不允许"会让人以为是权限问题，跑去别的地方找开关。
    """
    names, deletes = set(), set()
    for assistant_id in FOUR:
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

"""P4 集成测试：助手（Agent 预设）。

验收要点（对应客户端计划 P4）：
- 切换助手后人格文档与默认模型随之切换；
- 助手的技能白名单真的限制了模型能看到的工具；
- 助手专属的权限策略生效。
"""

from __future__ import annotations

import json

import pytest

from my_agent.assistants import evolution
from my_agent.assistants.persona import RULES_FILE, SOUL_FILE, assistant_dir
from my_agent.assistants.presets import builtin_config
from my_agent.config.loader import ConfigStore

from .conftest import (
    FakeLLM,
    install_fake_model,
    make_client,
    read_sse,
    register_confirm_skill,
    tool_call,
)


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


@pytest.fixture
async def http(base_url):
    async with make_client(base_url) as client:
        yield client


def _factory_fields(assistant_id: str) -> dict:
    """取内置搭子的**出厂**名称 / 简介 / 能力。

    ⚠️ 别在测试里手抄这几个字面量：产品改一次文案，测试就会以"409 != 200"
    的形式失败，而真正的原因（"我没改啊"）根本看不出来。
    这里要表达的是"**原样回传不算改**"，所以基准必须来自出厂值本身。
    """
    profile = next(item for item in builtin_config().assistants if item.id == assistant_id)
    return {
        "id": profile.id,
        "name": profile.name,
        "description": profile.description,
        "enabled_skills": list(profile.enabled_skills),
    }


def assistant_payload(**overrides):
    payload = {
        "id": "custom",
        "name": "自定义助手",
        "emoji": "🧪",
        "description": "测试用",
        "system_prompt": "你是测试助手",
        "model_id": "",
        "temperature": 0.5,
        "max_iterations": 3,
        "enabled_skills": [],
        "confirm_mode": None,
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- #
# 列表与内置预设
# --------------------------------------------------------------------------- #
async def test_list_returns_builtins(runtime, http):
    body = (await http.get("/v1/assistants")).json()
    ids = [item["id"] for item in body["assistants"]]
    # 接口按 **sort_order** 返回：搭子总管 0（置顶）→ Soulmate 系列 1/3 → 办公类 10
    # 数据分析师 / 文档写作助手 / PlayBuddy / SoulBuddy 已按产品决策移除
    assert ids == [
        "BuddyManager",
        "soulmate",
        "LoveBuddy",
        "RelationBuddy",
    ]
    assert body["default_assistant"] == "BuddyManager"
    assert all(item["builtin"] for item in body["assistants"])
    # ⚠️ `restricts_skills` 的含义 变过：它以前表示"限没限范围"
    # （False = 全开，那时**有**"全开"这种搭子），现在只表示"额外勾了几个通用/我的技能"。
    # 这条断言仍要钉住"白名单是空的"，因为内置搭子根本不允许添加技能。
    love = next(item for item in body["assistants"] if item["id"] == "LoveBuddy")
    assert love["restricts_skills"] is False
    assert love["enabled_skills"] == []
    assert love["unavailable_skills"] == []

    # 搭子总管同理：它的能力由"内置 ∪ 自己的专属"算出来（团队管理 + 电脑操作那批），
    # 档案里的白名单永远是空的、且被 locked_builtins 锁着。
    manager = next(item for item in body["assistants"] if item["id"] == "BuddyManager")
    assert manager["restricts_skills"] is False
    assert manager["enabled_skills"] == []
    assert manager["unavailable_skills"] == []


async def test_builtins_cannot_be_deleted(runtime, http):
    """⚠️ 四位内置搭子"任何途径不可改、不可删"。

    这条**推翻了**原来 ``test_builtins_are_seeded_once_and_not_resurrected`` 的前提 ——
    那个用例要先删掉内置搭子，现在删不掉了，所以要测的变成了"删不掉"本身：
    409（不是 403：这不是"你没权限"，是"这个东西不允许被删"）+ 一句看得懂的原因。
    """
    for assistant_id in ("LoveBuddy", "soulmate", "RelationBuddy", "BuddyManager"):
        resp = await http.delete(f"/v1/assistants/{assistant_id}")
        assert resp.status_code == 409, assistant_id
        assert "内置搭子" in resp.json()["detail"]

    ids = [item["id"] for item in (await http.get("/v1/assistants")).json()["assistants"]]
    assert {"LoveBuddy", "soulmate", "RelationBuddy", "BuddyManager"} <= set(ids)


async def test_removed_builtin_is_not_resurrected_on_reload(runtime, http):
    """被人为从配置文件里抹掉的内置搭子，启动时**不会**被偷偷补回来。

    这是原用例保留下来的那半条意图。⚠️ 为什么不再走 HTTP 删除：删不掉了（见上一条）。
    但"文件被手改 / 被别的工具写坏"这条路径依然存在，而"用户明确不要的东西被系统
    偷偷恢复"比丢配置更让人恼火 —— 这条规矩得继续有效。
    """
    path = runtime.paths.assistants_file
    data = json.loads(path.read_text(encoding="utf-8"))
    data["assistants"] = [item for item in data["assistants"] if item["id"] != "LoveBuddy"]
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    # 直接验证「再次加载配置」的行为，不另起一个 runtime——
    # 同一份 SQLite 上开两个连接容易引入无关的竞争，干扰这条用例的意图
    reloaded = _store(runtime.paths).load().assistants
    assert reloaded.get("LoveBuddy") is None
    assert reloaded.get("soulmate") is not None


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
async def test_create_update_delete(runtime, http):
    created = await http.post("/v1/assistants", json=assistant_payload())
    assert created.status_code == 200, created.text
    assert created.json()["builtin"] is False

    duplicate = await http.post("/v1/assistants", json=assistant_payload())
    assert duplicate.status_code == 409

    updated = await http.put(
        "/v1/assistants/custom", json=assistant_payload(name="改名了", temperature=0.9)
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "改名了"

    assert (await http.delete("/v1/assistants/custom")).status_code == 200
    assert (await http.get("/v1/assistants/custom")).status_code == 404


async def test_new_assistant_gets_the_evolution_rule(runtime, http):
    """新建搭子的 RULES.md 里要带一段「全员进化」系统规则（产品要求）。

    内置搭子的进化任务由系统预置；**自建搭子没有**，只能靠这段规则让它在对话里主动问用户。
    少写这一段，自建搭子永远不会提这件事，而界面上完全看不出缺了什么。
    """
    created = await http.post("/v1/assistants", json=assistant_payload(name="小明"))
    assert created.status_code == 200, created.text

    rules = (assistant_dir(runtime.paths, "custom") / RULES_FILE).read_text(encoding="utf-8")
    assert evolution.SECTION_TITLE in rules
    # 任务名要填进正文里（「全员进化中 小明」），模型照着建才不会建出别的名字
    assert evolution.task_name("小明") in rules
    # 初始 SOUL 照旧（这条路径本来就有的行为，别被这次改动带坏）
    soul = (assistant_dir(runtime.paths, "custom") / SOUL_FILE).read_text(encoding="utf-8")
    assert "小明" in soul


async def test_editing_builtin_nickname_keeps_builtin_flag(runtime, http):
    """改内置助手的**昵称**不该把它洗成自定义。

    否则「恢复默认助手」会把这个被改过的助手又加一份进来，出现两个同名助手。
    ⚠️ 这里刻意只动昵称：名称 / 简介 / 可用能力已经写死，
    传它们会直接 409 —— 见下面的 ``test_locked_builtin_fields_are_rejected``。
    """
    payload = {
        **assistant_payload(),
        **_factory_fields("LoveBuddy"),
        "nickname": "我改过的称呼",
        "builtin": False,
    }
    saved = await http.put("/v1/assistants/LoveBuddy", json=payload)
    assert saved.status_code == 200
    assert saved.json()["builtin"] is True


async def test_locked_builtin_fields_are_rejected(runtime, http):
    """名称 / 简介 / 可用能力改不动；昵称仍然可改。

    ⚠️ 判的必须是"**改的那几项**"，不是"是不是内置搭子"：
    设置页保存时整份回传，一律拒绝的话用户连换个昵称都做不到，
    而提示还会说成"名称不能改" —— 错怪了用户。
    """
    base = {
        **assistant_payload(),
        **_factory_fields("soulmate"),
        "nickname": "宝宝",
    }

    for field, value in (
        ("name", "我自己起的名字"),
        ("description", "我自己写的简介"),
        ("enabled_skills", ["calc"]),
    ):
        resp = await http.put("/v1/assistants/soulmate", json={**base, field: value})
        assert resp.status_code == 409, field
        assert "内置搭子" in resp.json()["detail"]

    # 昵称照改不误；字段值没变的整份回传也不该被拒
    resp = await http.put("/v1/assistants/soulmate", json=base)
    assert resp.status_code == 200
    assert resp.json()["nickname"] == "宝宝"
    # 界面靠这两个字段把输入框置灰并写明原因
    assert resp.json()["locked"] is True
    assert "name" in resp.json()["locked_fields"]


async def test_locked_builtin_persona_files_are_rejected(runtime, http):
    """⚠️ 只有 RULES 写不动（修正：）；其余照常可写。

    原先 SOUL / IDENTITY 也在锁内，用户更正"这是不对的"——
    它们在《搭子人格包》一次性对齐之后必须能改，否则用户改不了搭子的性格与身份；
    锁死记忆/性格等于把搭子变成一块不会成长的石头。
    """
    blocked = await http.put(
        "/v1/assistants/soulmate/persona-files/RULES.md",
        json={"content": "# 我自己写的规则\n"},
    )
    assert blocked.status_code == 409

    for name in ("SOUL.md", "IDENTITY.md", "MEMORY.md", "USER.md"):
        ok = await http.put(
            f"/v1/assistants/soulmate/persona-files/{name}",
            json={"content": f"# {name}\n\n我自己写的内容。\n"},
        )
        assert ok.status_code == 200, name


async def test_deleting_default_reassigns_it(runtime, http):
    """删掉默认助手后必须把默认值挪到别的助手上，不能留一个悬空 id。

    ⚠️ 默认那位现在是内置的 BuddyManager，删不动了；
    所以这里把默认位挪到一个自建搭子上再删 —— 要测的兜底逻辑没变。
    """
    created = await http.post("/v1/assistants", json=assistant_payload(id="temp"))
    assert created.status_code == 200
    temp_id = created.json()["id"]

    config = runtime.assistants
    config.default_assistant = temp_id
    runtime.save_assistants(config)

    await http.delete(f"/v1/assistants/{temp_id}")

    body = (await http.get("/v1/assistants")).json()
    ids = [item["id"] for item in body["assistants"]]
    assert body["default_assistant"] in ids


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #
async def test_unknown_model_is_rejected(runtime, http):
    """不校验的话，用户会在第一次对话时报"模型不存在"，很难联想到是助手配置。"""
    resp = await http.post("/v1/assistants", json=assistant_payload(model_id="no-such-model"))
    assert resp.status_code == 422
    assert "no-such-model" in resp.text


async def test_unknown_skill_is_rejected(runtime, http):
    resp = await http.post(
        "/v1/assistants", json=assistant_payload(enabled_skills=["not_a_skill"])
    )
    assert resp.status_code == 422
    assert "not_a_skill" in resp.text


async def test_mcp_skill_name_is_accepted_when_connected(runtime, http):
    """MCP 工具名应该被接受（它们随连接状态出现），不写死成"不存在"。"""
    from my_agent.mcp.presets import build_sample_server

    sample = build_sample_server(runtime.paths)
    assert sample is not None
    await http.post("/v1/mcp/servers", json=sample.model_dump(mode="json"))

    resp = await http.post(
        "/v1/assistants", json=assistant_payload(enabled_skills=["sample__read_note"])
    )
    assert resp.status_code == 200, resp.text


# --------------------------------------------------------------------------- #
# 对话集成
# --------------------------------------------------------------------------- #
async def test_assistant_persona_reaches_system(runtime, http):
    """P4 验收核心项：请求带 assistant_id 时，它的**人格文档**要进 system。

    这条在"兜底提示词退役"之后变得更关键：system 里除人格文档之外不再有任何
    别的内容（见 agent/engine.py 的 _system_prompt），所以"人格没进去"就等于
    "模型完全不知道自己在扮谁"。

    这里直接写人格文件，而不是依赖出厂播种：要验的正是"文档 → system"这条链路
    （配置里的 system_prompt 已不参与组装）。

    ⚠️ 用**自建**搭子，不用内置的：内置搭子的 SOUL 是写死的，
    写它会 409 —— 那样证的是"锁生效了"，不是"文档进 system"。
    """
    llm = FakeLLM(["好的"])
    install_fake_model(runtime, llm)

    created = await http.post(
        "/v1/assistants", json=assistant_payload(id="probe", name="人设探针")
    )
    assert created.status_code == 200, created.text

    written = await http.put(
        "/v1/assistants/probe/persona-files/SOUL.md",
        json={"content": "# SOUL\n\n你是 LoveBuddy，验证用标记 MARK-PERSONA。"},
    )
    assert written.status_code == 200, written.text

    await read_sse(http, {"message": "我们吵架了", "model_id": "fake", "assistant_id": "probe"})

    system = llm.calls[0][0]
    assert system.role == "system"
    assert "MARK-PERSONA" in system.content


async def test_assistant_skill_whitelist_limits_tools(runtime, http):
    """给助手限定技能白名单后，模型只看到白名单里的工具。"""
    llm = FakeLLM(["好的"])
    install_fake_model(runtime, llm)

    resp = await http.post(
        "/v1/assistants",
        json=assistant_payload(
            id="limited", name="受限助手", enabled_skills=["weather_query", "calc"]
        ),
    )
    assert resp.status_code == 200, resp.text

    await read_sse(
        http, {"message": "今天天气", "model_id": "fake", "assistant_id": "limited"}
    )

    tools = {spec.name for spec in llm.tools_seen[0]}
    # 白名单内的在，白名单外的不在
    assert {"weather_query", "calc"} <= tools
    assert "excel_read" not in tools


async def test_内置搭子只带内置技能与自己的专属(runtime, http):
    """内置搭子（RelationBuddy）= 全部内置技能 ∪ 自己的专属技能。

    ⚠️ 这条**推翻了**原来的 `test_assistant_without_restriction_exposes_everything`
    （"没限制 = 暴露全部工具"）。产品约定：
    "以后没有默认加载全部技能的搭子了"、"内置搭子 = 专属技能 + 内置技能，
    **且不能再添加任何技能**"。
    """
    llm = FakeLLM(["好的"])
    install_fake_model(runtime, llm)

    await read_sse(http, {"message": "你好", "model_id": "fake", "assistant_id": "RelationBuddy"})

    tools = {spec.name for spec in llm.tools_seen[0]}
    # 内置技能：每个搭子恒有（与勾没勾技能无关）
    assert {"calc", "system_time", "kb_search", "read_tool_output"} <= tools
    # 通用技能：不在 —— 内置搭子不能再添加技能
    # ⚠️ 举反例别用 reminder_create / browser_read 这些：它们 已经
    # 从通用技能转成内置技能了（见 skill/groups.py 的第二版划分）。
    assert "excel_read" not in tools
    assert "weather_query" not in tools
    assert "doc_to_pdf" not in tools
    # 本轮转成内置技能的那批：**应当在**。
    #
    # ⚠️ 这批以前不在（那时它们是通用技能，内置搭子拿不到），所以这条断言同时钉住
    # 一个**预期内的能力扩张**：内置搭子从这天起获得了浏览器操作、日程、提醒、
    # 屏幕截图等能力。哪天有人把这批又挪回通用技能，这里会立刻红。
    assert {"reminder_create", "browser_read", "calendar_create"} <= tools
    assert "system_screenshot" in tools
    # 别人的专属技能：也不在
    assert "team_create_group" not in tools
    assert "computer_type_text" not in tools
    # 心鉴学的配套工具跟着归属走：RelationBuddy 是它的归属搭子之一，应当在
    assert "xjx_place_lookup" in tools


async def test_explicit_model_beats_assistant_model(runtime, http):
    """工具条上手选的模型优先级最高，不能被助手的默认模型盖掉。

    优先级：助手默认模型 < 用户手选的模型。
    """
    llm = FakeLLM(["好的"])
    install_fake_model(runtime, llm)

    buddy = runtime.assistants.get("LoveBuddy")
    buddy.model_id = "local-qwen3"  # 助手指定了另一个模型
    runtime.save_assistants(runtime.assistants)

    events = await read_sse(
        http, {"message": "你好", "model_id": "fake", "assistant_id": "LoveBuddy"}
    )
    meta = next(data for name, data in events if name == "meta")
    assert meta["model_id"] == "fake"


async def test_assistant_model_applies_when_nothing_explicit(runtime, http):
    """没手选模型时，助手的默认模型要生效。

    注意：不传 model_id 且助手也没指定时，会落到 settings 里的默认模型
    （测试环境是 deepseek-chat，会真的发请求）。所以这条用例必须让助手
    明确指定一个注册过的模型，才测得到"助手模型生效"这件事本身。
    """
    llm = FakeLLM(["好的"])
    install_fake_model(runtime, llm)

    buddy = runtime.assistants.get("LoveBuddy")
    buddy.model_id = "fake"
    runtime.save_assistants(runtime.assistants)

    events = await read_sse(http, {"message": "你好", "assistant_id": "LoveBuddy"})
    meta = next(data for name, data in events if name == "meta")
    assert meta["model_id"] == "fake"
    assert llm.calls, "助手指定的模型必须被真正调用到"


async def test_unknown_assistant_id_returns_404(runtime, http):
    resp = await http.post(
        "/v1/chat", json={"message": "你好", "model_id": "fake", "assistant_id": "nope"}
    )
    assert resp.status_code == 404


async def test_session_remembers_assistant(runtime, http):
    """会话记住自己用的助手：第二句话不传 assistant_id 也保持一致。

    ⚠️ 用自建搭子（``probe``），理由同 ``test_assistant_persona_reaches_system``：
    内置搭子的人设文件写不动，拿它当样本证不了这条链路。
    """
    llm = FakeLLM(["第一句回复", "第二句回复"])
    install_fake_model(runtime, llm)

    created = await http.post(
        "/v1/assistants", json=assistant_payload(id="probe", name="会话探针")
    )
    assert created.status_code == 200, created.text

    await http.put(
        "/v1/assistants/probe/persona-files/SOUL.md",
        json={"content": "# SOUL\n\n你是 Soulmate，验证用标记 MARK-SOULMATE。"},
    )

    events = await read_sse(
        http, {"message": "第一句", "model_id": "fake", "assistant_id": "probe"}
    )
    session_id = next(data for name, data in events if name == "meta")["session_id"]

    await read_sse(http, {"message": "第二句", "session_id": session_id, "model_id": "fake"})

    # 第二轮依然用的是同一个人设（人格文档随会话记的 assistant_id 走）
    assert "MARK-SOULMATE" in llm.calls[1][0].content
    sessions = (await http.get("/v1/sessions")).json()["sessions"]
    stored = next(item for item in sessions if item["id"] == session_id)
    assert stored["assistant_id"] == "probe"


async def test_switching_assistant_keeps_history(runtime, http):
    """切换助手不能把已有对话清空——那是不可逆的破坏。

    ⚠️ 用两个自建搭子做 A/B：内置搭子的人设文件写不动，
    拿它们证不了"人设跟着切换走"。
    """
    llm = FakeLLM(["办公搭子的回复", "伴侣搭子的回复"])
    install_fake_model(runtime, llm)

    for assistant_id, marker in (("probe-a", "MARK-OFFICE"), ("probe-b", "MARK-LOVEBUDDY")):
        created = await http.post(
            "/v1/assistants", json=assistant_payload(id=assistant_id, name=assistant_id)
        )
        assert created.status_code == 200, created.text
        await http.put(
            f"/v1/assistants/{assistant_id}/persona-files/SOUL.md",
            json={"content": f"# SOUL\n\n你是 {assistant_id}，验证用标记 {marker}。"},
        )

    events = await read_sse(
        http, {"message": "第一句", "model_id": "fake", "assistant_id": "probe-a"}
    )
    session_id = next(data for name, data in events if name == "meta")["session_id"]
    assert "MARK-OFFICE" in llm.calls[0][0].content

    # 中途换成另一个搭子
    await read_sse(
        http,
        {
            "message": "第二句",
            "session_id": session_id,
            "model_id": "fake",
            "assistant_id": "probe-b",
        },
    )

    messages = (await http.get(f"/v1/sessions/{session_id}/messages")).json()["messages"]
    contents = [item["content"] for item in messages]
    assert "第一句" in contents
    assert "办公搭子的回复" in contents
    # 人设已换成伴侣搭子，但历史还在
    assert "MARK-LOVEBUDDY" in llm.calls[1][0].content


async def test_assistant_confirm_mode_is_applied(runtime, http):
    """助手专属的权限策略必须生效，且不能污染其他会话。"""
    # ⚠️ 技能名必须落在**该搭子的可用集合**里，否则模型压根看不到它、执行也会被
    # "不在当前会话启用的技能范围内"拦下 —— 那测到的就不是权限策略了。
    # 用 `file_write`（属内置技能、每个搭子恒有）而不是自造的 `write_file`。
    register_confirm_skill(runtime, "file_write")
    runtime.assistants.get("RelationBuddy").confirm_mode = "deny"
    runtime.save_assistants(runtime.assistants)

    install_fake_model(
        runtime,
        FakeLLM(
            [
                _tool_response("file_write", {"path": "x.txt"}),
                "已被拒绝。",
            ]
        ),
    )

    events = await read_sse(
        http, {"message": "写个文件", "model_id": "fake", "assistant_id": "RelationBuddy"}
    )
    result = next(data for name, data in events if name == "tool_result")
    # "被拒绝"是与"执行失败"不同的状态，界面上要能区分（前者是策略，后者是故障）
    assert result["status"] == "denied"
    assert "一律拒绝" in result["result"]

    # 全局策略没被改坏：guard 是共享的，按会话改它会串味到别的会话
    assert runtime.skills.guard.confirm_mode == runtime.config.settings.security.confirm_mode


async def test_confirm_mode_change_applies_to_running_task(runtime, http):
    """任务跑到一半改搭子的权限策略，**后续工具调用立刻按新策略走**。

    用户反馈："搭子在进行任务中，更换权限确认后要即时生效，而不是等下一次任务"。
    策略过去是在任务开始时被快照进 SkillContext 的，所以要复现这个时序：
    先用一个 safe 技能在同一次任务里把策略改成「自动批准」，紧接着的那个
    confirm 技能就必须被放行 —— 否则就说明它还在用任务开始时的旧策略。
    """
    from my_agent.skill.base import BaseSkill
    from my_agent.skill.decorator import skill as skill_decorator

    # 同上：技能名要在该搭子的可用集合里（用内置技能 `file_write`）
    register_confirm_skill(runtime, "file_write")

    # ⚠️ 这个"翻转策略"的技能必须**落在该搭子的可用集合里**，否则模型调不到它、
    # 策略也就不会被改 —— 于是这条用例测不到它想测的东西。
    # 所以借用一个内置技能的名字（`calc`）来注册这个假实现：
    # 内置技能是每个搭子恒有的（见 skill/groups.py）。
    @skill_decorator(
        name="calc",
        display_name="切换权限策略",
        description="把搭子的权限策略改成自动批准（测试用）",
        permission_level="safe",
    )
    class _FlipSkill(BaseSkill):
        async def run(self, ctx, **params):
            runtime.assistants.get("RelationBuddy").confirm_mode = "auto_approve"
            runtime.save_assistants(runtime.assistants)
            return "已切换"

    runtime.skills.register(_FlipSkill)

    runtime.assistants.get("RelationBuddy").confirm_mode = "deny"
    runtime.save_assistants(runtime.assistants)

    install_fake_model(
        runtime,
        FakeLLM(
            [
                _tool_response("calc", {}),
                _tool_response("file_write", {"path": "x.txt"}),
                "好的",
            ]
        ),
    )

    events = await read_sse(
        http, {"message": "先改策略再写文件", "model_id": "fake", "assistant_id": "RelationBuddy"}
    )
    results = {data["name"]: data for name, data in events if name == "tool_result"}

    assert results["calc"]["status"] != "denied"
    # 关键断言：策略是同一次任务里改的，第二次工具调用必须按**新**策略走
    assert results["file_write"]["status"] != "denied", results["file_write"]
    assert "写入成功" in results["file_write"]["result"]


def _tool_response(name: str, arguments: dict):
    from my_agent.llm.base import LLMResponse

    return LLMResponse(
        tool_calls=[tool_call(name, arguments, call_id=f"call_{name}")],
        finish_reason="tool_calls",
    )

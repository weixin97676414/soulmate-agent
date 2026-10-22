







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










    from my_agent.assistants.bootstrap import BuiltinAssistants

    return ConfigStore(paths, builtin=BuiltinAssistants(), **kwargs)


@pytest.fixture
async def http(base_url):
    async with make_client(base_url) as client:
        yield client


def _factory_fields(assistant_id: str) -> dict:






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





async def test_list_returns_builtins(runtime, http):
    body = (await http.get("/v1/assistants")).json()
    ids = [item["id"] for item in body["assistants"]]
    
    
    
    assert ids == [
        "BuddyManager",
        "soulmate",
        "LoveBuddy",
        "RelationBuddy",
        "FortuneTellingBuddy",
    ]
    assert body["default_assistant"] == "BuddyManager"
    assert all(item["builtin"] for item in body["assistants"])
    
    
    
    love = next(item for item in body["assistants"] if item["id"] == "LoveBuddy")
    assert love["restricts_skills"] is False
    assert love["enabled_skills"] == []
    assert love["unavailable_skills"] == []

    
    
    manager = next(item for item in body["assistants"] if item["id"] == "BuddyManager")
    assert manager["restricts_skills"] is False
    assert manager["enabled_skills"] == []
    assert manager["unavailable_skills"] == []


async def test_builtins_cannot_be_deleted(runtime, http):






    for assistant_id in ("LoveBuddy", "soulmate", "RelationBuddy", "BuddyManager"):
        resp = await http.delete(f"/v1/assistants/{assistant_id}")
        assert resp.status_code == 409, assistant_id
        assert "内置搭子" in resp.json()["detail"]

    ids = [item["id"] for item in (await http.get("/v1/assistants")).json()["assistants"]]
    assert {"LoveBuddy", "soulmate", "RelationBuddy", "BuddyManager"} <= set(ids)


async def test_removed_builtin_is_not_resurrected_on_reload(runtime, http):






    path = runtime.paths.assistants_file
    data = json.loads(path.read_text(encoding="utf-8"))
    data["assistants"] = [item for item in data["assistants"] if item["id"] != "LoveBuddy"]
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    
    
    reloaded = _store(runtime.paths).load().assistants
    assert reloaded.get("LoveBuddy") is None
    assert reloaded.get("soulmate") is not None





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





    created = await http.post("/v1/assistants", json=assistant_payload(name="小明"))
    assert created.status_code == 200, created.text

    rules = (assistant_dir(runtime.paths, "custom") / RULES_FILE).read_text(encoding="utf-8")
    assert evolution.SECTION_TITLE in rules
    
    assert evolution.task_name("小明") in rules
    
    soul = (assistant_dir(runtime.paths, "custom") / SOUL_FILE).read_text(encoding="utf-8")
    assert "小明" in soul


async def test_editing_builtin_nickname_keeps_builtin_flag(runtime, http):






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










    base = {
        **assistant_payload(),
        **_factory_fields("soulmate"),
        "nickname": "宝宝",
    }

    for field, value in (
        ("name", "我自己起的名字"),
        ("description", "我自己写的简介"),
    ):
        resp = await http.put("/v1/assistants/soulmate", json={**base, field: value})
        assert resp.status_code == 409, field
        assert "内置搭子" in resp.json()["detail"]

    
    picked = ["weather_query"]
    resp = await http.put("/v1/assistants/soulmate", json={**base, "enabled_skills": picked})
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled_skills"] == picked
    
    assert "name" in resp.json()["locked_fields"]
    assert "enabled_skills" not in resp.json()["locked_fields"]

    
    resp = await http.put("/v1/assistants/soulmate", json=base)
    assert resp.status_code == 200
    assert resp.json()["nickname"] == "宝宝"
    
    assert resp.json()["locked"] is True
    assert "name" in resp.json()["locked_fields"]


async def test_locked_builtin_persona_files_are_rejected(runtime, http):






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





async def test_unknown_model_is_rejected(runtime, http):

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

    from my_agent.mcp.presets import build_sample_server

    sample = build_sample_server(runtime.paths)
    assert sample is not None
    await http.post("/v1/mcp/servers", json=sample.model_dump(mode="json"))

    resp = await http.post(
        "/v1/assistants", json=assistant_payload(enabled_skills=["sample__read_note"])
    )
    assert resp.status_code == 200, resp.text





async def test_assistant_persona_reaches_system(runtime, http):












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
    
    assert {"weather_query", "calc"} <= tools
    assert "excel_read" not in tools


async def test_内置搭子只带内置技能与自己的专属(runtime, http):







    llm = FakeLLM(["好的"])
    install_fake_model(runtime, llm)

    await read_sse(http, {"message": "你好", "model_id": "fake", "assistant_id": "RelationBuddy"})

    tools = {spec.name for spec in llm.tools_seen[0]}
    
    assert {"calc", "system_time", "kb_search", "read_tool_output"} <= tools
    
    
    
    assert "excel_read" not in tools
    assert "weather_query" not in tools
    assert "doc_to_pdf" not in tools
    
    
    
    
    
    assert {"reminder_create", "browser_read", "calendar_create"} <= tools
    assert "system_screenshot" in tools
    
    assert "team_create_group" not in tools
    assert "computer_type_text" not in tools
    
    assert "xjx_place_lookup" in tools


async def test_explicit_model_beats_assistant_model(runtime, http):




    llm = FakeLLM(["好的"])
    install_fake_model(runtime, llm)

    buddy = runtime.assistants.get("LoveBuddy")
    buddy.model_id = "local-qwen3"  
    runtime.save_assistants(runtime.assistants)

    events = await read_sse(
        http, {"message": "你好", "model_id": "fake", "assistant_id": "LoveBuddy"}
    )
    meta = next(data for name, data in events if name == "meta")
    assert meta["model_id"] == "fake"


async def test_assistant_model_applies_when_nothing_explicit(runtime, http):






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

    
    assert "MARK-SOULMATE" in llm.calls[1][0].content
    sessions = (await http.get("/v1/sessions")).json()["sessions"]
    stored = next(item for item in sessions if item["id"] == session_id)
    assert stored["assistant_id"] == "probe"


async def test_switching_assistant_keeps_history(runtime, http):





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
    
    assert "MARK-LOVEBUDDY" in llm.calls[1][0].content


async def test_assistant_confirm_mode_is_applied(runtime, http):

    
    
    
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
    
    assert result["status"] == "denied"
    assert "一律拒绝" in result["result"]

    
    assert runtime.skills.guard.confirm_mode == runtime.config.settings.security.confirm_mode


async def test_confirm_mode_change_applies_to_running_task(runtime, http):







    from my_agent.skill.base import BaseSkill
    from my_agent.skill.decorator import skill as skill_decorator

    
    register_confirm_skill(runtime, "file_write")

    
    
    
    
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
    
    assert results["file_write"]["status"] != "denied", results["file_write"]
    assert "写入成功" in results["file_write"]["result"]


def _tool_response(name: str, arguments: dict):
    from my_agent.llm.base import LLMResponse

    return LLMResponse(
        tool_calls=[tool_call(name, arguments, call_id=f"call_{name}")],
        finish_reason="tool_calls",
    )

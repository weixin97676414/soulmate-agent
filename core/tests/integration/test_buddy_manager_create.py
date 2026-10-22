



















from __future__ import annotations

import pytest

from my_agent.assistants import library as library_mod
from my_agent.assistants.persona import IDENTITY_FILE, RULES_FILE, SOUL_FILE, assistant_dir
from my_agent.assistants.transfer import TransferError
from my_agent.llm.base import LLMResponse

from .conftest import (
    FakeLLM,
    install_fake_model,
    make_client,
    read_sse,
    read_sse_auto_approve,
    tool_call,
)


def _store(paths, **kwargs):










    from my_agent.assistants.bootstrap import BuiltinAssistants
    from my_agent.config.loader import ConfigStore

    return ConfigStore(paths, builtin=BuiltinAssistants(), **kwargs)


@pytest.fixture
async def http(base_url):
    async with make_client(base_url) as client:
        yield client


def _call(name: str, arguments: dict | None = None) -> LLMResponse:

    return LLMResponse(
        content="",
        tool_calls=[tool_call(name, arguments)],
        finish_reason="tool_calls",
    )


async def test_buddy_manager_can_see_the_create_buddy_skill(runtime, http):






    llm = FakeLLM(["好的"])
    install_fake_model(runtime, llm)

    await read_sse(http, {"message": "你好", "model_id": "fake", "assistant_id": "BuddyManager"})

    tools = {spec.name for spec in llm.tools_seen[0]}
    
    assert {"team_list_assistants", "team_create_assistant", "team_update_assistant"} <= tools
    
    assert {"buddy_library_list", "buddy_import"} <= tools
    
    assert "excel_read" not in tools


async def test_buddy_manager_really_creates_a_buddy(runtime, http, monkeypatch):










    def _offline(url: str) -> bytes:
        raise TransferError("测试环境不联网")

    monkeypatch.setattr(library_mod, "_fetch", _offline)

    install_fake_model(
        runtime,
        FakeLLM(
            [
                
                _call("buddy_library_list"),
                
                _call(
                    "team_create_assistant",
                    {
                        "name": "资料整理助手",
                        "description": "整理资料、归档与检索",
                        "identity": "负责把用户散落的资料整理成可检索的档案。",
                        "abilities": "1. 归档；2. 按关键词检索；3. 定期清理重复项。",
                        "rules": "先问清存放位置再动手；拿不准时先列方案给用户选。",
                        "tone": "像交付清单一样简洁，每条给依据，不寒暄。",
                        "emoji": "📚",
                    },
                ),
                "官网没有合适的，我已经自己建了一个。",
            ]
        ),
    )

    events = await read_sse_auto_approve(
        http,
        {
            "message": "帮我建一个整理资料的搭子",
            "model_id": "fake",
            "assistant_id": "BuddyManager",
        },
    )

    results = [data for name, data in events if name == "tool_result"]
    assert results, f"一次工具都没执行成功（事件：{[name for name, _ in events]}）"

    
    listed = " ".join(str(item.get("result", "")) for item in results)
    assert "读取官网搭子库失败" in listed, "第一轮那次官网查询没有留下痕迹"

    
    profile = next(
        (item for item in runtime.assistants.sorted() if item.name == "资料整理助手"),
        None,
    )
    assert profile is not None, "技能回报建好了，但搭子清单里没有它"
    assert profile.builtin is False, "AI 建的搭子不该被当成内置（否则会被写死回厂值）"
    assert profile.description == "整理资料、归档与检索"

    
    folder = assistant_dir(runtime.paths, profile.id)
    identity = (folder / IDENTITY_FILE).read_text(encoding="utf-8")
    rules = (folder / RULES_FILE).read_text(encoding="utf-8")
    soul = (folder / SOUL_FILE).read_text(encoding="utf-8")
    assert "整理成可检索的档案" in identity, "IDENTITY.md 没写进去"
    assert "先问清存放位置" in rules, "RULES.md 没写进去"
    assert "不寒暄" in soul, "SOUL.md 没写进去"

    
    payload = (await http.get("/v1/assistants")).json()
    assert profile.id in {item["id"] for item in payload["assistants"]}

    

    reloaded = _store(runtime.paths).load().assistants
    assert reloaded.get(profile.id) is not None, "assistants.json 里没有它，重启就会丢"

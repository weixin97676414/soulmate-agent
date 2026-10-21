















from __future__ import annotations

from typing import Any

from my_agent.config.loader import ConfigStore
from my_agent.llm.base import LLMResponse
from my_agent.server.runtime import AppRuntime

from .conftest import FakeLLM, event_collector, install_fake_model, read_sse, tool_call, wait_for


def _store(paths, **kwargs):










    from my_agent.assistants.bootstrap import BuiltinAssistants

    return ConfigStore(paths, builtin=BuiltinAssistants(), **kwargs)



PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"profile-update-e2e-payload"


def _tool_response(name: str, arguments: dict[str, Any], call_id: str = "call_1") -> LLMResponse:
    return LLMResponse(
        tool_calls=[tool_call(name, arguments, call_id=call_id)],
        finish_reason="tool_calls",
    )


def _from_disk(runtime: AppRuntime, assistant_id: str):

    return _store(runtime.paths).load().assistants.get(assistant_id)


async def test_ai_renames_itself_and_it_lands_on_disk(runtime, client):





    install_fake_model(
        runtime,
        FakeLLM(
            [
                _tool_response("update_assistant_profile", {"nickname": "小管家"}),
                "好，以后我就叫小管家。",
            ]
        ),
    )

    events = await read_sse(
        client,
        {"message": "你以后叫小管家", "model_id": "fake", "assistant_id": "BuddyManager"},
    )

    result = next(data for name, data in events if name == "tool_result")
    assert result["status"] == "ok", result
    assert "小管家" in result["result"]

    saved = _from_disk(runtime, "BuddyManager")
    assert saved is not None
    assert saved.nickname == "小管家"


async def test_renamed_assistant_is_visible_through_the_api(runtime, client):

    install_fake_model(
        runtime,
        FakeLLM(
            [
                _tool_response("update_assistant_profile", {"nickname": "新名字"}),
                "改好了。",
            ]
        ),
    )
    await read_sse(
        client,
        {"message": "改个名", "model_id": "fake", "assistant_id": "BuddyManager"},
    )

    body = (await client.get("/v1/assistants")).json()
    done = next(item for item in body["assistants"] if item["id"] == "BuddyManager")
    assert done["nickname"] == "新名字"


async def test_profile_update_pushes_the_change_event(runtime, client):

    install_fake_model(
        runtime,
        FakeLLM(
            [
                _tool_response("update_assistant_profile", {"emoji": "🛠️"}),
                "换了个图标。",
            ]
        ),
    )

    async with event_collector(client) as events:
        await read_sse(
            client,
            {"message": "换个图标", "model_id": "fake", "assistant_id": "BuddyManager"},
        )
        assert await wait_for(
            lambda: any(name == "assistants_changed" for name, _ in events), timeout=5
        )

    payload = next(data for name, data in events if name == "assistants_changed")
    assert payload["assistant_id"] == "BuddyManager"


async def test_ai_sets_its_own_avatar_from_a_local_file(runtime, client, tmp_path):

    image = tmp_path / "avatar.png"
    image.write_bytes(PNG_BYTES)

    install_fake_model(
        runtime,
        FakeLLM(
            [
                _tool_response("update_assistant_profile", {"avatar_source": str(image)}),
                "头像换好了。",
            ]
        ),
    )
    events = await read_sse(
        client,
        {"message": "把你的头像换成这张", "model_id": "fake", "assistant_id": "BuddyManager"},
    )
    result = next(data for name, data in events if name == "tool_result")
    assert result["status"] == "ok", result

    saved = _from_disk(runtime, "BuddyManager")
    
    assert saved.avatar.startswith("data:image/png;base64,")
    assert str(image) not in saved.avatar


async def test_a_broken_avatar_source_is_reported_not_swallowed(runtime, client, tmp_path):





    missing = str(tmp_path / "nope.png")
    install_fake_model(
        runtime,
        FakeLLM(
            [
                _tool_response("update_assistant_profile", {"avatar_source": missing}),
                "这张图我读不到。",
            ]
        ),
    )
    events = await read_sse(
        client,
        {"message": "换成这张", "model_id": "fake", "assistant_id": "BuddyManager"},
    )
    result = next(data for name, data in events if name == "tool_result")
    assert result["status"] == "error", result
    assert "找不到" in result["result"]
    
    assert "base64" not in result["result"]

    saved = _from_disk(runtime, "BuddyManager")
    assert saved.avatar == ""


async def test_no_field_given_is_refused_with_a_reason(runtime, client):




    install_fake_model(
        runtime,
        FakeLLM(
            [
                _tool_response("update_assistant_profile", {}),
                "我没改什么。",
            ]
        ),
    )
    events = await read_sse(
        client,
        {"message": "改点什么", "model_id": "fake", "assistant_id": "BuddyManager"},
    )
    result = next(data for name, data in events if name == "tool_result")
    assert result["status"] == "error", result
    assert "至少要给一个" in result["result"]


async def test_unknown_target_reports_a_readable_reason(runtime, client):

    install_fake_model(
        runtime,
        FakeLLM(
            [
                _tool_response(
                    "update_assistant_profile",
                    {"assistant_id": "no-such-buddy", "nickname": "X"},
                ),
                "没有这个搭子。",
            ]
        ),
    )
    events = await read_sse(
        client,
        {"message": "给那个搭子改名", "model_id": "fake", "assistant_id": "BuddyManager"},
    )
    result = next(data for name, data in events if name == "tool_result")
    assert result["status"] == "error", result
    assert "不存在" in result["result"]


async def test_manager_is_usable_out_of_the_box(runtime, client):





    install_fake_model(runtime, FakeLLM(["你要我安排点什么？"]))
    events = await read_sse(
        client, {"message": "你好", "model_id": "fake", "assistant_id": "BuddyManager"}
    )
    session_id = next(data for name, data in events if name == "meta")["session_id"]

    sessions = (await client.get("/v1/sessions")).json()["sessions"]
    stored = next(item for item in sessions if item["id"] == session_id)
    assert stored["assistant_id"] == "BuddyManager"


async def test_default_assistant_is_the_manager_and_pinned(runtime, client):

    body = (await client.get("/v1/assistants")).json()
    assert body["default_assistant"] == "BuddyManager"
    
    assert body["assistants"][0]["id"] == "BuddyManager"

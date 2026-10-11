"""「AI 改自己的档案」端到端：对话入口 → 技能 → 落盘 → 界面能刷新到。

实测反馈问题原话："让 AI 自己修改昵称时，只会修改 md，而不能修改搭子
中的昵称配置，这导致了昵称设置后，对话中搭子仍然显示的搭子名。"

单元测试（``tests/unit/test_profile_tools.py``）已经守住了
``orchestrator.update_assistant_profile`` 与 ``storage.images`` 各自的行为，
这一组守的是**从对话入口一路通到磁盘**的那条链：模型发出的工具调用 → 技能 →
写 ``assistants.json`` → 推出 ``assistants_changed``。中间任何一环断了（技能没随
搭子白名单暴露、``ctx`` 里拿不到当前搭子、写完忘了落盘、忘了推事件），用户看到的
就还是那句"改了没生效"——而这恰恰是这一整轮要修的东西。

**断言一律读磁盘**（``_store(paths).load()``），不读 ``runtime.assistants``：
后者是内存对象，哪怕"忘了落盘"它也已经变了，会把正是要验的那一步放过去。
"""

from __future__ import annotations

from typing import Any

from my_agent.config.loader import ConfigStore
from my_agent.llm.base import LLMResponse
from my_agent.server.runtime import AppRuntime

from .conftest import FakeLLM, event_collector, install_fake_model, read_sse, tool_call, wait_for


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

# 只要魔数正确就够了：技能与 ``storage.images`` 只嗅格式、**不解码**（核心不引图像库），
# 所以一段假字节完全够用，还免了往仓库里塞二进制。
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"profile-update-e2e-payload"


def _tool_response(name: str, arguments: dict[str, Any], call_id: str = "call_1") -> LLMResponse:
    return LLMResponse(
        tool_calls=[tool_call(name, arguments, call_id=call_id)],
        finish_reason="tool_calls",
    )


def _from_disk(runtime: AppRuntime, assistant_id: str):
    """重新从磁盘读一遍配置 —— 验的是"真的写进去了"。"""
    return _store(runtime.paths).load().assistants.get(assistant_id)


async def test_ai_renames_itself_and_it_lands_on_disk(runtime, client):
    """用户报的那个 bug 本身：改昵称必须落到 ``assistants.json``。

    注意助手 id 传空（模型在参数里没给）—— 这正是用户说"你自己以后叫 XX"时的形态，
    技能必须能自己认出"我自己是谁"，而不是反过来要模型猜。
    """
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
    """落盘之后，界面读的那张列表要跟着变 —— 这是"不需要重开应用"的依据。"""
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
    """必须推 ``assistants_changed``：界面靠它刷新，而不是靠用户切来切去。"""
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
    """三种头像来源里的"本机路径"这条，从对话一路走到磁盘。"""
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
    # 契约是 data URL 而不是文件路径：渲染层那张 <img> 发不出带鉴权的请求
    assert saved.avatar.startswith("data:image/png;base64,")
    assert str(image) not in saved.avatar


async def test_a_broken_avatar_source_is_reported_not_swallowed(runtime, client, tmp_path):
    """取不到图时必须**明说原因**，并且绝不改坏已有档案。

    用户口径："最不能接受静默降级"。所以这里既断言报错是"找不到"，也断言
    文件其实没被动过 —— 一条失败的改动不该留下半个状态。
    """
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
    # base64 绝不该出现在回填文本里（会把日志撑爆，也是无意义的噪声）
    assert "base64" not in result["result"]

    saved = _from_disk(runtime, "BuddyManager")
    assert saved.avatar == ""


async def test_no_field_given_is_refused_with_a_reason(runtime, client):
    """四个字段一个都没给：明确报错，而不是静默"成功"。

    静默成功最糟 —— 模型会照着"已更新"去回话，用户看到的是"AI 说改了、实际没改"。
    """
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
    """改一个不存在的搭子：报错要指路，不能是一句无从下手的失败。"""
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
    """搭子总管必须**开箱可用**：它是默认搭子，第一句话就得能发出去。

    这条是前面几条的前提 —— 如果它根本没被播种进来、或它的技能白名单里写错了一个
    不存在的技能名，用户第一次打开客户端就会撞上。
    """
    install_fake_model(runtime, FakeLLM(["你要我安排点什么？"]))
    events = await read_sse(
        client, {"message": "你好", "model_id": "fake", "assistant_id": "BuddyManager"}
    )
    session_id = next(data for name, data in events if name == "meta")["session_id"]

    sessions = (await client.get("/v1/sessions")).json()["sessions"]
    stored = next(item for item in sessions if item["id"] == session_id)
    assert stored["assistant_id"] == "BuddyManager"


async def test_default_assistant_is_the_manager_and_pinned(runtime, client):
    """默认落点从 Relation Buddy 换成搭子总管（产品约定），且置顶。"""
    body = (await client.get("/v1/assistants")).json()
    assert body["default_assistant"] == "BuddyManager"
    # 列表按 (sort_order, name) 排，总管必须是第一个
    assert body["assistants"][0]["id"] == "BuddyManager"

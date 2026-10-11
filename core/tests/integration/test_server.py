"""HTTP 服务层集成测试。

**为什么起真实 uvicorn 而不是 httpx.ASGITransport**：
ASGITransport 会把整个响应体缓冲完再交给调用方，于是
「SSE 事件流」永远读不到内容，直到服务端把流关闭为止。
结果就是确认回传（需要边读流边发新请求）必然死锁到超时。
起一个真实监听端口的服务，才能真实验证流式与并发行为。

覆盖 P0 验收要求：SSE 流式对话、工具调用事件、权限确认往返、
鉴权、会话隔离、停止、设置读写。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from my_agent.config.loader import ConfigStore
from my_agent.config.paths import AppPaths
from my_agent.llm.base import LLMResponse

# 夹具与工具函数统一放在 tests/integration/conftest.py，供本模块与 P2 测试共用
from .conftest import (  # noqa: F401 - FakeLLM/tool_call 供各用例使用
    TOKEN,
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

# --------------------------------------------------------------------------- #
# 基础接口与鉴权
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_health(client):
    body = (await client.get("/v1/health")).json()
    assert body["status"] == "ok"
    assert body["skills"] >= 2  # calc + system_time


@pytest.mark.asyncio
async def test_missing_token_is_rejected(base_url):
    async with make_client(base_url, token=None) as c:
        assert (await c.get("/v1/health")).status_code == 401


@pytest.mark.asyncio
async def test_wrong_token_is_rejected(base_url):
    async with make_client(base_url, token="nope") as c:
        assert (await c.get("/v1/health")).status_code == 401


@pytest.mark.asyncio
async def test_skills_endpoint(client):
    body = (await client.get("/v1/skills")).json()
    names = {s["name"] for s in body["skills"]}
    assert {"calc", "system_time"} <= names
    calc = next(s for s in body["skills"] if s["name"] == "calc")
    assert calc["category"] == "system"
    assert calc["permission_level"] == "safe"
    assert calc["parameters"]["properties"]["expression"]


@pytest.mark.asyncio
async def test_disabled_skill_is_excluded_from_tool_list(client):
    """禁用后仍能在设置里看到（enabled=false），但不再提供给模型。

    ⚠️ 用一个**通用技能**（`weather_query`）而不是 `calc`：2026-10-06 的四分类里
    `calc` 属「内置技能」，它连开关都不给（PATCH 会被 409 拒），
    拿它测"禁用"测的就不再是这条链路了。
    """
    resp = await client.patch("/v1/skills/weather_query", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    all_skills = (await client.get("/v1/skills")).json()["skills"]
    target = next(s for s in all_skills if s["name"] == "weather_query")
    assert target["enabled"] is False

    exposed = (await client.get("/v1/skills?enabled_only=true")).json()["skills"]
    assert all(s["name"] != "weather_query" for s in exposed)


@pytest.mark.asyncio
async def test_skill_permission_override(client):
    # ⚠️ 同上：`calc` 是内置技能（权限被锁），改不了；用通用技能才测得到这条链路
    resp = await client.patch("/v1/skills/weather_query", json={"permission_level": "confirm"})
    assert resp.json()["permission_level"] == "confirm"
    bad = await client.patch("/v1/skills/weather_query", json={"permission_level": "whatever"})
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_paths_endpoint(client):
    body = (await client.get("/v1/paths")).json()
    assert body["workspace"] and body["artifacts"]


# --------------------------------------------------------------------------- #
# 对话流
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_plain_streaming_reply(runtime, client):
    install_fake_model(runtime, FakeLLM(["你好，我是助手。"]))
    events = await read_sse(client, {"message": "你好", "model_id": "fake"})

    types = [e[0] for e in events]
    assert types[0] == "meta"
    assert "done" in types
    assert "trace" in types  # 右侧抽屉的数据来源

    text = "".join(d["text"] for t, d in events if t == "delta")
    assert text == "你好，我是助手。"
    assert events[0][1]["session_id"]
    assert events[0][1]["task_id"]


@pytest.mark.asyncio
async def test_tool_call_events_are_streamed(runtime, client):
    from my_agent.skill.builtin.system import CalculatorSkill

    runtime.skills.register(CalculatorSkill)
    install_fake_model(
        runtime,
        FakeLLM(
            [
                LLMResponse(
                    tool_calls=[tool_call("calc", {"expression": "12*8"})],
                    finish_reason="tool_calls",
                ),
                "结果是 96",
            ]
        ),
    )
    events = await read_sse(client, {"message": "12*8 等于多少", "model_id": "fake"})
    types = [e[0] for e in events]

    assert "tool_call" in types
    assert "tool_result" in types

    call = next(d for t, d in events if t == "tool_call")
    assert call["name"] == "calc"
    assert call["display_name"] == "精确计算"
    assert call["params"] == {"expression": "12*8"}

    result = next(d for t, d in events if t == "tool_result")
    assert result["status"] == "ok"
    assert "96" in result["result"]
    assert result["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_trace_event_contains_spans(runtime, client):
    from my_agent.skill.builtin.system import CalculatorSkill

    runtime.skills.register(CalculatorSkill)
    install_fake_model(
        runtime,
        FakeLLM(
            [
                LLMResponse(
                    tool_calls=[tool_call("calc", {"expression": "1+1"})],
                    finish_reason="tool_calls",
                ),
                "等于 2",
            ]
        ),
    )
    events = await read_sse(client, {"message": "算一下", "model_id": "fake"})
    trace = next(d for t, d in events if t == "trace")

    names = [s["name"] for s in trace["spans"]]
    assert "step:1" in names
    assert "skill:calc" in names
    assert trace["total_tokens"] > 0
    # Span 必须带耗时，前端时间线要用
    assert all("duration_ms" in s for s in trace["spans"])


# --------------------------------------------------------------------------- #
# 权限确认往返
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_permission_request_and_approve_round_trip(runtime, client):
    """完整验证：SSE 下发确认请求 -> 独立 HTTP 回传 -> Agent 继续执行。"""
    register_confirm_skill(runtime)
    install_fake_model(
        runtime,
        FakeLLM(
            [
                LLMResponse(
                    tool_calls=[tool_call("write_file", {"path": "a.txt"})],
                    finish_reason="tool_calls",
                ),
                "已经写好了",
            ]
        ),
    )

    seen: list[dict] = []
    async with client.stream(
        "POST", "/v1/chat", json={"message": "写文件", "model_id": "fake"}
    ) as resp:
        current = None
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
            elif line.startswith("data: ") and current:
                data = json.loads(line[6:])
                if current == "permission_request":
                    seen.append(data)
                    approved = await client.post(
                        "/v1/confirm", json={"request_id": data["request_id"], "approved": True}
                    )
                    assert approved.json()["ok"] is True
                elif current == "tool_result":
                    seen.append({"result": data})
                elif current == "done":
                    break

    request = next(s for s in seen if "skill_name" in s)
    assert request["skill_name"] == "write_file"
    assert request["display_name"] == "写入文件"
    assert request["permission_level"] == "confirm"

    results = [s["result"] for s in seen if "result" in s]
    assert results, "批准后应当有工具执行结果"
    assert results[0]["status"] == "ok"


@pytest.mark.asyncio
async def test_permission_request_denied_marks_result(runtime, client):
    register_confirm_skill(runtime, name="delete_file")
    install_fake_model(
        runtime,
        FakeLLM(
            [
                LLMResponse(
                    tool_calls=[tool_call("delete_file", {"path": "a.txt"})],
                    finish_reason="tool_calls",
                ),
                "好的，已取消。",
            ]
        ),
    )

    denied: dict = {}
    async with client.stream(
        "POST", "/v1/chat", json={"message": "删文件", "model_id": "fake"}
    ) as resp:
        current = None
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
            elif line.startswith("data: ") and current:
                data = json.loads(line[6:])
                if current == "permission_request":
                    await client.post(
                        "/v1/confirm", json={"request_id": data["request_id"], "approved": False}
                    )
                elif current == "tool_result":
                    denied = data
                elif current == "done":
                    break

    assert denied.get("status") == "denied"
    assert "权限拒绝" in denied.get("result", "")


@pytest.mark.asyncio
async def test_没人响应的确认在任务被停止时作废(runtime, client):
    """没人点确认、直到任务被停掉时，那条操作必须作废（不能执行）。

    ## ⚠️ 这条用例守的东西反过来了

    它以前叫 ``test_unanswered_confirm_falls_back_to_deny``，守的是
    "超时后按拒绝，不能让 Agent 永久挂住"。产品要求确认弹窗
    **永不超时**之后，那个语义就不存在了 —— 于是这里改走**现在唯一会发生的
    收尾路径**：任务被停止（``reject_pending``）。

    为什么可以接受"永久挂着"：**"被静默拒绝"才是更糟的结果**。用户走开两分钟
    回来，看到的是"操作被拒绝了"，还得重做一遍，而屏幕上没有任何东西告诉他
    "是你没及时点"。挂着至少是诚实的 —— 而且关会话 / 点停止 / 重启都能收尾。
    """
    register_confirm_skill(runtime, name="slow_write")
    install_fake_model(
        runtime,
        FakeLLM(
            [
                LLMResponse(
                    tool_calls=[tool_call("slow_write", {"path": "a.txt"})],
                    finish_reason="tool_calls",
                ),
                "已放弃该操作",
            ]
        ),
    )

    # 并发地跑：一边消费事件流，一边在确认挂起之后"用户走开"（停掉任务）
    stream = asyncio.create_task(read_sse(client, {"message": "写文件", "model_id": "fake"}))
    for _ in range(60):  # 最多等 3 秒，让确认请求真的推出来
        await asyncio.sleep(0.05)
        if runtime.pending_confirms:
            break
    assert runtime.pending_confirms, "这一步应该已经挂起了一个确认"
    runtime.reject_pending()

    events = await stream
    result = next(d for t, d in events if t == "tool_result")
    assert result["status"] == "denied"


# --------------------------------------------------------------------------- #
# 会话
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_session_is_reused_and_history_returned(runtime, client):
    install_fake_model(runtime, FakeLLM(["第一次", "第二次"]))
    first = await read_sse(client, {"message": "你好", "model_id": "fake"})
    session_id = first[0][1]["session_id"]

    await read_sse(client, {"message": "再来一次", "session_id": session_id, "model_id": "fake"})

    history = (await client.get(f"/v1/sessions/{session_id}/messages")).json()["messages"]
    roles = [m["role"] for m in history]
    assert roles.count("user") == 2
    assert roles.count("assistant") == 2


@pytest.mark.asyncio
async def test_sessions_are_isolated(runtime, client):
    """不同会话的记忆必须互相隔离。"""
    install_fake_model(runtime, FakeLLM(["A", "B"]))
    a = await read_sse(client, {"message": "会话A的第一句", "model_id": "fake"})
    b = await read_sse(client, {"message": "会话B的第一句", "model_id": "fake"})

    sid_a = a[0][1]["session_id"]
    sid_b = b[0][1]["session_id"]
    assert sid_a != sid_b

    history_a = (await client.get(f"/v1/sessions/{sid_a}/messages")).json()["messages"]
    assert len(history_a) == 2
    assert history_a[0]["content"] == "会话A的第一句"


@pytest.mark.asyncio
async def test_session_title_is_auto_generated(runtime, client):
    install_fake_model(runtime, FakeLLM(["好"]))
    events = await read_sse(client, {"message": "帮我分析一下这个季度的销售数据", "model_id": "fake"})
    session_id = events[0][1]["session_id"]
    sessions = (await client.get("/v1/sessions")).json()["sessions"]
    target = next(s for s in sessions if s["id"] == session_id)
    assert "分析" in target["title"]


@pytest.mark.asyncio
async def test_sessions_crud(runtime, client):
    created = (await client.post("/v1/sessions", json={"title": "手工会话"})).json()
    sid = created["id"]
    assert created["title"] == "手工会话"

    patched = (await client.patch(f"/v1/sessions/{sid}", json={"title": "改名了"})).json()
    assert patched["title"] == "改名了"

    assert (await client.delete(f"/v1/sessions/{sid}")).json()["ok"] is True
    assert (await client.get(f"/v1/sessions/{sid}/messages")).status_code == 404


@pytest.mark.asyncio
async def test_batch_delete(runtime, client):
    a = (await client.post("/v1/sessions", json={"title": "a"})).json()["id"]
    b = (await client.post("/v1/sessions", json={"title": "b"})).json()["id"]
    resp = await client.post("/v1/sessions/batch-delete", json={"ids": [a, b]})
    assert resp.json()["deleted"] == 2
    assert (await client.get("/v1/sessions")).json()["sessions"] == []


# --------------------------------------------------------------------------- #
# 其他
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stop_returns_ok(client):
    resp = await client.post("/v1/stop", json={"session_id": "whatever"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_stop_actually_cancels_running_task(runtime, client):
    """停止必须真正取消 Agent 任务，而不是只回一个 ok。"""

    class SlowLLM(FakeLLM):
        # 覆盖父类实现时**必须**连带接受采样参数：Agent 会无条件传
        # top_p / frequency_penalty / presence_penalty，只写 temperature
        # 会让这里抛 TypeError —— 而表现是"停止任务返回 cancelled=0"，
        # 看起来像取消功能坏了，跟签名一点关系都没有。
        async def stream(
            self, messages, tools=None, *, temperature=0.7, max_tokens=None, **_sampling
        ):
            from my_agent.llm.base import StreamChunk

            for _ in range(500):
                await asyncio.sleep(0.05)
                yield StreamChunk(delta="…")

    install_fake_model(runtime, SlowLLM([]))

    got_meta = asyncio.Event()
    async with client.stream(
        "POST", "/v1/chat", json={"message": "慢慢说", "model_id": "fake"}
    ) as resp:
        current = None
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
            elif line.startswith("data: ") and current == "meta":
                task_id = json.loads(line[6:])["task_id"]
                got_meta.set()
                stop = await client.post("/v1/stop", json={"task_id": task_id})
                assert stop.json()["cancelled"] == 1
                break

    assert got_meta.is_set()
    assert runtime.tasks == {}  # 任务已注销，没有泄漏


@pytest.mark.asyncio
async def test_stop_with_stale_task_id_leaves_other_confirms_alone(runtime, client):
    """``/v1/stop`` 传一个查不到的 ``task_id`` 时，绝不能把**别的会话**挂起的确认一起作废。

    ⚠️ 这条分支的常态不是"出错了"，而是"任务已经正常跑完、被 unregister 掉了"
    （见 ``routes/chat.py`` 里 ``stop`` 的处理与 ``finally`` 里的 ``unregister_task``）：
    用户重复点一下「停止」、或前端重放一个旧 task_id 都会走到这里。
    当时的实现是 ``reject_pending(owner.session_id if owner else None)`` —— 而
    ``reject_pending(None)`` 的语义是**作废全部**（那是整体关闭用的），于是别的
    会话里正等用户点的确认框 / 计划卡 / 密钥输入框会一起消失，且没有任何日志解释。
    """
    from my_agent.security.confirm import ConfirmRequest

    async def emit(_request) -> None:
        return None

    request = ConfirmRequest(
        request_id="r-stale-stop",
        skill_name="write_file",
        display_name="写入文件",
        description="测试用",
        permission_level="confirm",
        params={"path": "a.txt"},
        prompt="是否继续？",
    )
    pending = asyncio.create_task(
        runtime.request_confirm(request, emit, owner="another-session")
    )
    await asyncio.sleep(0)
    assert "r-stale-stop" in runtime.pending_confirms

    resp = await client.post("/v1/stop", json={"task_id": "no-such-task"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "cancelled": 0}
    # 别的会话的确认必须仍然挂着（这正是本用例要守的东西）
    assert "r-stale-stop" in runtime.pending_confirms
    assert not pending.done()

    runtime.reject_pending("another-session")
    assert await pending is False


@pytest.mark.asyncio
async def test_unknown_model_returns_error(runtime, client):
    # 这条验证的是"模型配置错了"（有模型，但 id 对不上）→ llm_error；
    # "一个模型都没有"是另一种状态，现在会得到 400 的引导提示（空清单是新装常态）
    install_fake_model(runtime, FakeLLM(["回复"]))
    resp = await client.post("/v1/chat", json={"message": "hi", "model_id": "no-such-model"})
    assert resp.status_code == 502
    assert resp.json()["code"] == "llm_error"


@pytest.mark.asyncio
async def test_chat_with_no_models_returns_guidance(runtime, client):
    """一个模型都没配时发消息，得到的是**引导**，不是配置错误的措辞。

    出厂清单已改为空（新装用户从接入向导开始配），这条钉住新装首启的体验：
    用户在引导页/对话区发第一条消息，必须被明确告知"去哪里配"。
    """
    resp = await client.post("/v1/chat", json={"message": "hi"})
    assert resp.status_code == 400
    assert "还没有配置任何模型" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_clear_session_messages(runtime, client):
    install_fake_model(runtime, FakeLLM(["回复"]))
    events = await read_sse(client, {"message": "你好", "model_id": "fake"})
    session_id = events[0][1]["session_id"]

    await client.delete(f"/v1/sessions/{session_id}/messages")

    body = (await client.get(f"/v1/sessions/{session_id}/messages")).json()
    assert body["messages"] == []
    sessions = (await client.get("/v1/sessions")).json()
    target = next(s for s in sessions["sessions"] if s["id"] == session_id)
    assert target["message_count"] == 0


@pytest.mark.asyncio
async def test_sessions_report_persistence_mode(client):
    body = (await client.get("/v1/sessions")).json()
    assert body["persistent"] is True
    assert (await client.get("/v1/health")).json()["persistent"] is True


# --------------------------------------------------------------------------- #
# 工作区文件
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_file_upload_list_download_delete(client):
    upload = await client.post(
        "/v1/files/upload",
        files={"file": ("销售数据.csv", b"month,amount\n1,100\n", "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    record = upload.json()
    assert record["original_name"] == "销售数据.csv"
    assert record["size"] == len(b"month,amount\n1,100\n")

    listed = (await client.get("/v1/files")).json()
    assert [item["id"] for item in listed["files"]] == [record["id"]]
    assert listed["stats"]["uploads"] == 1

    download = await client.get(f"/v1/files/{record['id']}")
    assert download.status_code == 200
    assert download.content == b"month,amount\n1,100\n"

    assert (await client.delete(f"/v1/files/{record['id']}")).json()["ok"] is True
    assert (await client.get(f"/v1/files/{record['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_file_upload_blocks_dangerous_suffix(client):
    resp = await client.post(
        "/v1/files/upload", files={"file": ("payload.exe", b"MZ", "application/octet-stream")}
    )
    assert resp.status_code == 400
    assert "安全" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_file_kind_must_be_valid(client):
    assert (await client.get("/v1/files?kind=bogus")).status_code == 422
    assert (await client.get("/v1/files/limits/info")).json()["max_upload_mb"] == 50


@pytest.mark.asyncio
async def test_attachment_path_is_injected_into_context(runtime, client):
    """附件必须把**真实绝对路径**送进模型，否则模型会去猜文件名。"""
    upload = await client.post(
        "/v1/files/upload", files={"file": ("sales.csv", b"a,b\n1,2\n", "text/csv")}
    )
    file_id = upload.json()["id"]

    llm = FakeLLM(["收到，我来分析。"])
    install_fake_model(runtime, llm)
    await read_sse(
        client,
        {"message": "分析这个表", "model_id": "fake", "attachments": [file_id]},
    )

    # 第一次模型调用的最后一条 user 消息应包含附件路径
    first_call = llm.calls[0]
    user_messages = [m for m in first_call if m.role == "user"]
    assert user_messages
    content = user_messages[-1].content
    assert "[附件]" in content
    assert "sales.csv" in content
    assert str(runtime.paths.workspace_dir) in content.replace("\\\\", "\\")
    assert content.rstrip().endswith("分析这个表")


@pytest.mark.asyncio
async def test_missing_attachment_does_not_break_chat(runtime, client):
    install_fake_model(runtime, FakeLLM(["好的"]))
    events = await read_sse(
        client,
        {"message": "看看这个", "model_id": "fake", "attachments": ["notexist.csv"]},
    )
    assert events[-1][0] in ("trace", "done")


@pytest.mark.asyncio
async def test_attachment_wrapper_is_parseable_by_frontend(runtime, client):
    """前端要靠这对标记把附件块从用户气泡里剥掉，约定不能变。"""
    from my_agent.server.routes.chat import ATTACHMENT_CLOSE, ATTACHMENT_OPEN

    upload = await client.post("/v1/files/upload", files={"file": ("a.txt", b"x", "text/plain")})
    llm = FakeLLM(["好"])
    install_fake_model(runtime, llm)
    await read_sse(
        client,
        {"message": "内容", "model_id": "fake", "attachments": [upload.json()["id"]]},
    )
    content = [m for m in llm.calls[0] if m.role == "user"][-1].content
    # ⚠️ 模型看到的这份 user 消息**带时间前缀**（"现在：2026-…"，见 memory/short_term.py
    # 的时间维度），所以标记不再落在第 0 个字符上。要守的约定没变：这一对标记必须
    # 完整、且包住附件信息 —— 前端剥附件读的是**历史接口**（那边没有前缀），
    # 所以两边的解析都不受影响。
    assert ATTACHMENT_OPEN in content
    assert ATTACHMENT_CLOSE in content
    inside = content.split(ATTACHMENT_OPEN, 1)[1].split(ATTACHMENT_CLOSE, 1)[0]
    assert "a.txt" in inside


# --------------------------------------------------------------------------- #
# 审计
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_skill_execution_is_audited(runtime, client):
    from my_agent.skill.builtin.system import CalculatorSkill

    runtime.skills.register(CalculatorSkill)
    install_fake_model(
        runtime,
        FakeLLM(
            [
                LLMResponse(
                    tool_calls=[tool_call("calc", {"expression": "6*7"})],
                    finish_reason="tool_calls",
                ),
                "结果是 42",
            ]
        ),
    )
    await read_sse(client, {"message": "6*7 等于多少", "model_id": "fake"})

    entries = (await client.get("/v1/audit")).json()["entries"]
    assert entries, "技能执行必须留下审计记录"
    record = entries[0]
    assert record["skill_name"] == "calc"
    assert record["status"] == "ok"
    assert record["params"] == {"expression": "6*7"}
    assert record["session_id"]


@pytest.mark.asyncio
async def test_denied_skill_is_audited(runtime, client):
    register_confirm_skill(runtime, name="audited_write")
    install_fake_model(
        runtime,
        FakeLLM(
            [
                LLMResponse(
                    tool_calls=[tool_call("audited_write", {"path": "x.txt"})],
                    finish_reason="tool_calls",
                ),
                "已取消",
            ]
        ),
    )

    async with client.stream(
        "POST", "/v1/chat", json={"message": "写文件", "model_id": "fake"}
    ) as resp:
        current = None
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
            elif line.startswith("data: ") and current == "permission_request":
                data = json.loads(line[6:])
                await client.post(
                    "/v1/confirm", json={"request_id": data["request_id"], "approved": False}
                )
            elif current == "done":
                break

    entries = (await client.get("/v1/audit?status=denied")).json()["entries"]
    assert entries
    assert entries[0]["skill_name"] == "audited_write"
    assert entries[0]["permission_level"] == "confirm"


@pytest.mark.asyncio
async def test_audit_stats_and_clear(client):
    stats = (await client.get("/v1/audit/stats")).json()
    assert stats["available"] is True
    assert "total" in stats
    cleared = (await client.delete("/v1/audit")).json()
    assert cleared["ok"] is True
    assert (await client.get("/v1/audit")).json()["entries"] == []


@pytest.mark.asyncio
async def test_usage_summary_reports_availability_and_prices(client):
    """用量总览：可用时如实报告，且**没配单价时不许把费用说成 0**。

    ⚠️ 这条是抽 `services/usage.py` 时补的回归钉（审计 L-01）：`/v1/usage`
    此前**一条直接用例都没有**，而这次搬的正是"取数 + 可用性判定 + 单价判定" ——
    搬错了没有任何东西会红。所以先把口径钉住，再谈搬家。
    """
    summary = (await client.get("/v1/usage/summary?days=7")).json()
    assert summary["available"] is True
    assert summary["window_days"] == 7
    # 测试环境没配单价 ⇒ 必须如实说"没配"（界面据此显示「未配置价格」而不是 ¥0.00）
    assert summary["prices_configured"] is False
    assert summary["currency"]
    # 可用时要给出真实结构，而不是那套"没有数据"的空壳
    assert summary["today"] is not None
    assert isinstance(summary["by_day"], list)

    # 单会话用量也走同一个服务
    session = (await client.get("/v1/usage/session/does-not-exist")).json()
    assert session["available"] is True


@pytest.mark.asyncio
async def test_settings_round_trip(client):
    settings = (await client.get("/v1/settings")).json()
    settings["agent"]["max_iterations"] = 7
    # 「压缩 / 规划 / 自检用哪个模型」也要能存能读（产品要求的那条设置项）。
    # 它是个**松散引用**（模型 id），所以后端不校验存在性 —— 校验的那部分
    # 由 llm/factory.py::resolve_utility_llm 在运行期兜底。
    settings["agent"]["utility_model_id"] = "cheap-model"
    saved = (await client.put("/v1/settings", json=settings)).json()
    assert saved["agent"]["max_iterations"] == 7
    assert saved["agent"]["utility_model_id"] == "cheap-model"
    fresh = (await client.get("/v1/settings")).json()
    assert fresh["agent"]["max_iterations"] == 7
    assert fresh["agent"]["utility_model_id"] == "cheap-model"


@pytest.mark.asyncio
async def test_settings_validation_rejects_bad_values(client):
    settings = (await client.get("/v1/settings")).json()
    # 这里要的是一个**确实越界**的值。原先用 999，是因为当时 max_iterations 的
    # 上限是 50；后来实测反馈"没执行几个就提示已达到最大执行轮数"，默认值调到 500、
    # 上限放宽到 10 万 —— 999 因此变成合法值。改成明显越界的 20 万，
    # 这条测试要守的是"越界会被拒"，不是"999 会被拒"。
    settings["agent"]["max_iterations"] = 200_000
    resp = await client.put("/v1/settings", json=settings)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_models_api_returns_plain_api_key(client):
    # 出厂清单现在是**空**的（不再硬塞默认模型）—— 先按正常用户路径加一个
    await client.put(
        "/v1/models",
        json={
            "default_model": "deepseek-chat",
            "models": [
                {
                    "id": "deepseek-chat",
                    "name": "DeepSeek Chat",
                    "provider": "deepseek",
                    "base_url": "https://api.deepseek.com/v1",
                    "model_name": "deepseek-chat",
                    "api_key": "sk-abcdef123456",
                    "token_limit": 65536,
                }
            ],
        },
    )

    body = (await client.get("/v1/models")).json()
    assert body["models"], "刚添加的模型应出现在清单里"
    # ⚠️ 这里**曾经断言的是"带星号"**（密钥以脱敏预览下发）。
    #
    # 那套设计反复导致"密钥被清空"：前端拿到预览后，只要在某一刻把空值当成新值
    # 提交（回填竞态、has_api_key 恰好为 false……），真 Key 就被覆盖成空串。
    # 用户的要求是**明文常显** —— 字段里永远是真字符，就不存在"要不要判断
    # 用户改没改"这个环节。所以现在断言反过来：接口必须回传完整明文。
    for m in body["models"]:
        assert "has_api_key" in m
    target = next(m for m in body["models"] if m["id"] == "deepseek-chat")
    assert target["api_key"] == "sk-abcdef123456", "模型列表必须回传完整明文密钥"
    assert target["has_api_key"] is True
    assert body["presets"], "应提供服务商预设"
    assert body["effective_default"]


@pytest.mark.asyncio
async def test_api_key_survives_read_edit_save_round_trip(runtime, client, tmp_path):
    """设置界面「读取 -> 编辑 -> 整体保存」不能把真实 Key 弄丢。

    这条测试历史上叫 `test_masked_api_key_is_preserved_on_save`，
    守的是"别把真 Key 覆盖成星号"。现在不再有星号（明文常显），
    但**要守的东西没变，而且更强**：这一趟来回之后 Key 必须一模一样。
    """

    # 先添加一个带 Key 的模型（出厂清单为空，正常用户的路径就是先添加）
    await client.put(
        "/v1/models",
        json={
            "default_model": "deepseek-chat",
            "models": [
                {
                    "id": "deepseek-chat",
                    "name": "DeepSeek Chat",
                    "provider": "deepseek",
                    "base_url": "https://api.deepseek.com/v1",
                    "model_name": "deepseek-chat",
                    "api_key": "sk-realsecret1234567890",
                    "token_limit": 65536,
                }
            ],
        },
    )

    # 模拟前端：读回来、原样提交（明文常显之后，提交的就是真值本身）
    readback = (await client.get("/v1/models")).json()["models"]
    target = next(m for m in readback if m["id"] == "deepseek-chat")
    assert target["api_key"] == "sk-realsecret1234567890"
    assert target["has_api_key"] is True

    await client.put("/v1/models", json={"default_model": "deepseek-chat", "models": readback})

    reloaded = _store(AppPaths(tmp_path / "data")).load()
    assert reloaded.models.get("deepseek-chat").api_key == "sk-realsecret1234567890"


@pytest.mark.asyncio
async def test_submitting_empty_key_never_wipes_it(runtime, client, tmp_path):
    """**用户反复反馈的那条**：任何一次空值提交都不得清掉密钥。

    用户的原话是"不知道操作了什么，密钥又被清空了，模型无法使用"。
    历史上"空值"确实等价于"删除"，而前端提交空值的时刻有一堆不可控来源
    （回填竞态、密钥库条目缺失、列表正在刷新……）。现在把这条语义删掉了，
    删除只能靠显式的 ``clear_api_key``。

    这条测试直接模拟最坏情况：前端把 ``api_key`` 提交成空串、且不带任何标记。
    """
    await client.put(
        "/v1/models",
        json={
            "default_model": "deepseek-chat",
            "models": [
                {
                    "id": "deepseek-chat",
                    "name": "DeepSeek Chat",
                    "provider": "deepseek",
                    "base_url": "https://api.deepseek.com/v1",
                    "model_name": "deepseek-chat",
                    "api_key": "sk-realsecret1234567890",
                    "token_limit": 65536,
                }
            ],
        },
    )

    readback = (await client.get("/v1/models")).json()["models"]
    for spec in readback:
        # 最坏情况：值被清空，且**没有**带 api_key_unchanged 标记
        spec["api_key"] = ""

    resp = await client.put(
        "/v1/models", json={"default_model": "deepseek-chat", "models": readback}
    )
    assert resp.status_code == 200, resp.text

    after = next(
        m for m in resp.json()["models"] if m["id"] == "deepseek-chat"
    )
    assert after["has_api_key"] is True, "空值提交不得清掉密钥"
    assert after["api_key"] == "sk-realsecret1234567890", "密钥必须原样保留"


@pytest.mark.asyncio
async def test_models_save_persists(runtime, client, tmp_path):
    body = (await client.get("/v1/models")).json()
    models = body["models"]
    models.append(
        {
            "id": "my-model",
            "name": "我的模型",
            "provider": "openai",
            "adapter": "openai_compat",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-abcdefghijklmn",
            "model_name": "gpt-4o-mini",
            "token_limit": 32768,
            "supports_tools": True,
            "supports_stream": True,
            "timeout": 60,
            "temperature": 0.7,
            "max_tokens": None,
            "enabled": True,
            "is_default": False,
        }
    )
    resp = await client.put("/v1/models", json={"default_model": "my-model", "models": models})
    assert resp.status_code == 200
    assert resp.json()["effective_default"] == "my-model"

    # 落盘后重新加载，验证持久化生效

    reloaded = _store(AppPaths(tmp_path / "data")).load()
    assert reloaded.models.get("my-model") is not None
    assert reloaded.models.default_model == "my-model"

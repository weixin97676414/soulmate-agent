











from __future__ import annotations

import asyncio
import json

import pytest

from my_agent.config.loader import ConfigStore
from my_agent.config.paths import AppPaths
from my_agent.llm.base import LLMResponse


from .conftest import (  
    TOKEN,
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






@pytest.mark.asyncio
async def test_health(client):
    body = (await client.get("/v1/health")).json()
    assert body["status"] == "ok"
    assert body["skills"] >= 2  


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
    
    resp = await client.patch("/v1/skills/weather_query", json={"permission_level": "confirm"})
    assert resp.json()["permission_level"] == "confirm"
    bad = await client.patch("/v1/skills/weather_query", json={"permission_level": "whatever"})
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_paths_endpoint(client):
    body = (await client.get("/v1/paths")).json()
    assert body["workspace"] and body["artifacts"]







@pytest.mark.asyncio
async def test_plain_streaming_reply(runtime, client):
    install_fake_model(runtime, FakeLLM(["你好，我是助手。"]))
    events = await read_sse(client, {"message": "你好", "model_id": "fake"})

    types = [e[0] for e in events]
    assert types[0] == "meta"
    assert "done" in types
    assert "trace" in types  

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
    
    assert all("duration_ms" in s for s in trace["spans"])







@pytest.mark.asyncio
async def test_permission_request_and_approve_round_trip(runtime, client):

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

    
    stream = asyncio.create_task(read_sse(client, {"message": "写文件", "model_id": "fake"}))
    for _ in range(60):  
        await asyncio.sleep(0.05)
        if runtime.pending_confirms:
            break
    assert runtime.pending_confirms, "这一步应该已经挂起了一个确认"
    runtime.reject_pending()

    events = await stream
    result = next(d for t, d in events if t == "tool_result")
    assert result["status"] == "denied"







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







@pytest.mark.asyncio
async def test_stop_returns_ok(client):
    resp = await client.post("/v1/stop", json={"session_id": "whatever"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_stop_actually_cancels_running_task(runtime, client):


    class SlowLLM(FakeLLM):
        
        
        
        
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
    assert runtime.tasks == {}  


@pytest.mark.asyncio
async def test_stop_with_stale_task_id_leaves_other_confirms_alone(runtime, client):









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
    
    assert "r-stale-stop" in runtime.pending_confirms
    assert not pending.done()

    runtime.reject_pending("another-session")
    assert await pending is False


@pytest.mark.asyncio
async def test_unknown_model_returns_error(runtime, client):
    
    
    install_fake_model(runtime, FakeLLM(["回复"]))
    resp = await client.post("/v1/chat", json={"message": "hi", "model_id": "no-such-model"})
    assert resp.status_code == 502
    assert resp.json()["code"] == "llm_error"


@pytest.mark.asyncio
async def test_chat_with_no_models_returns_guidance(runtime, client):





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

    from my_agent.server.routes.chat import ATTACHMENT_CLOSE, ATTACHMENT_OPEN

    upload = await client.post("/v1/files/upload", files={"file": ("a.txt", b"x", "text/plain")})
    llm = FakeLLM(["好"])
    install_fake_model(runtime, llm)
    await read_sse(
        client,
        {"message": "内容", "model_id": "fake", "attachments": [upload.json()["id"]]},
    )
    content = [m for m in llm.calls[0] if m.role == "user"][-1].content
    
    
    
    
    assert ATTACHMENT_OPEN in content
    assert ATTACHMENT_CLOSE in content
    inside = content.split(ATTACHMENT_OPEN, 1)[1].split(ATTACHMENT_CLOSE, 1)[0]
    assert "a.txt" in inside







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






    summary = (await client.get("/v1/usage/summary?days=7")).json()
    assert summary["available"] is True
    assert summary["window_days"] == 7
    
    assert summary["prices_configured"] is False
    assert summary["currency"]
    
    assert summary["today"] is not None
    assert isinstance(summary["by_day"], list)

    
    session = (await client.get("/v1/usage/session/does-not-exist")).json()
    assert session["available"] is True


@pytest.mark.asyncio
async def test_settings_round_trip(client):
    settings = (await client.get("/v1/settings")).json()
    settings["agent"]["max_iterations"] = 7
    
    
    
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
    
    
    
    
    settings["agent"]["max_iterations"] = 200_000
    resp = await client.put("/v1/settings", json=settings)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_models_api_returns_plain_api_key(client):
    
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
    
    
    
    
    
    
    for m in body["models"]:
        assert "has_api_key" in m
    target = next(m for m in body["models"] if m["id"] == "deepseek-chat")
    assert target["api_key"] == "sk-abcdef123456", "模型列表必须回传完整明文密钥"
    assert target["has_api_key"] is True
    assert body["presets"], "应提供服务商预设"
    assert body["effective_default"]


@pytest.mark.asyncio
async def test_api_key_survives_read_edit_save_round_trip(runtime, client, tmp_path):







    
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
    target = next(m for m in readback if m["id"] == "deepseek-chat")
    assert target["api_key"] == "sk-realsecret1234567890"
    assert target["has_api_key"] is True

    await client.put("/v1/models", json={"default_model": "deepseek-chat", "models": readback})

    reloaded = _store(AppPaths(tmp_path / "data")).load()
    assert reloaded.models.get("deepseek-chat").api_key == "sk-realsecret1234567890"


@pytest.mark.asyncio
async def test_submitting_empty_key_never_wipes_it(runtime, client, tmp_path):









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

    

    reloaded = _store(AppPaths(tmp_path / "data")).load()
    assert reloaded.models.get("my-model") is not None
    assert reloaded.models.default_model == "my-model"

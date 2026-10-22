









from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from my_agent.config.paths import AppPaths
from my_agent.config.schemas import McpServerConfig
from my_agent.mcp.manager import MAX_AUTO_RESTARTS
from my_agent.mcp.presets import build_sample_server
from my_agent.mcp.types import McpServerState
from my_agent.server.runtime import AppRuntime
from my_agent.skill.base import SkillContext

from .conftest import (
    FakeLLM,
    event_collector,
    install_fake_model,
    make_client,
    read_sse,
    read_sse_auto_approve,
    tool_call,
    wait_for,
)

FIXTURE_SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "test_mcp_server.py"


CONNECT_WAIT = 60.0


@pytest.fixture
def paths(tmp_path) -> AppPaths:
    p = AppPaths(tmp_path / "AgentDesktop").ensure()
    
    
    
    
    
    
    
    
    p.mcp_file.write_text('{"servers": []}', encoding="utf-8")
    return p


async def build_runtime(paths: AppPaths) -> AppRuntime:
    runtime = AppRuntime(paths)
    await runtime.initialize()
    return runtime


@pytest.fixture
async def runtime(paths):
    rt = await build_runtime(paths)
    
    
    
    
    
    
    rt.config.settings.security.confirm_timeout_seconds = 5.0
    
    
    
    
    rt.config.settings.security.confirm_mode = "interactive"
    rt.skills.guard.set_confirm_mode("interactive")
    try:
        yield rt
    finally:
        await rt.shutdown()


@pytest.fixture
def sample_config(paths):
    config = build_sample_server(paths)
    
    config.command = sys.executable
    return config


def fixture_config(name: str = "probe") -> McpServerConfig:
    return McpServerConfig(
        name=name,
        command=sys.executable,
        args=[str(FIXTURE_SERVER)],
        timeout=10.0,
    )


async def wait_state(runtime: AppRuntime, name: str, state: McpServerState, timeout=CONNECT_WAIT):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        status = runtime.mcp.status(name)
        if status is not None and status.state == state:
            return status
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"等待 {name} 进入 {state.value} 超时，当前状态："
        f"{runtime.mcp.status(name).state.value if runtime.mcp.status(name) else 'None'}"
        f"（{runtime.mcp.status(name).message if runtime.mcp.status(name) else ''}）"
    )


def mcp_skill_names(runtime: AppRuntime) -> set[str]:
    return {
        meta.name
        for meta in runtime.skills.list_metas(enabled_only=False)
        if meta.source == "mcp"
    }





async def test_add_server_registers_tools(runtime, sample_config):
    status = await runtime.mcp.add_server(sample_config)

    assert status.state == McpServerState.READY, status.message
    assert status.tool_count == 5

    names = mcp_skill_names(runtime)
    assert names == {
        "sample__list_notes",
        "sample__read_note",
        "sample__write_note",
        "sample__delete_note",
        "sample__echo",
    }
    
    exposed = {spec.name for spec in runtime.skills.to_tool_specs()}
    assert "sample__read_note" in exposed


async def test_tool_metadata_is_preserved(runtime, sample_config):
    await runtime.mcp.add_server(sample_config)
    meta = next(
        m for m in runtime.skills.list_metas() if m.name == "sample__read_note"
    )
    
    assert meta.description.startswith("[sample]")
    assert meta.category == "mcp"
    assert meta.source == "mcp"
    
    assert "name" in meta.parameters["properties"]


async def test_permission_inferred_from_annotations(runtime, sample_config):

    await runtime.mcp.add_server(sample_config)
    levels = {
        meta.name: meta.permission_level
        for meta in runtime.skills.list_metas(enabled_only=False)
        if meta.source == "mcp"
    }
    assert levels["sample__read_note"] == "safe"
    assert levels["sample__list_notes"] == "safe"
    assert levels["sample__write_note"] == "confirm"
    assert levels["sample__delete_note"] == "confirm"





def approved_ctx(runtime: AppRuntime) -> SkillContext:






    async def approve(_request) -> bool:
        return True

    return SkillContext(paths=runtime.paths, confirm=approve)


async def test_call_tool_through_skill_manager(runtime, sample_config):
    await runtime.mcp.add_server(sample_config)
    ctx = approved_ctx(runtime)

    result = await runtime.skills.execute("sample__echo", {"text": "你好"}, ctx)
    assert "你好" in result

    
    await runtime.skills.execute(
        "sample__write_note", {"name": "周报", "content": "本周完成 MCP 集成"}, ctx
    )
    listed = await runtime.skills.execute("sample__list_notes", {}, ctx)
    assert "周报" in listed

    content = await runtime.skills.execute("sample__read_note", {"name": "周报"}, ctx)
    assert "MCP 集成" in content


async def test_confirm_tool_is_denied_without_channel(runtime, sample_config):

    await runtime.mcp.add_server(sample_config)
    ctx = SkillContext(paths=runtime.paths)

    from my_agent.errors import SkillPermissionError

    with pytest.raises(SkillPermissionError):
        await runtime.skills.execute(
            "sample__write_note", {"name": "不该被创建", "content": "x"}, ctx
        )
    
    notes = list((runtime.paths.workspace_dir / "mcp-notes").glob("*.md"))
    assert notes == []


async def test_tool_error_message_reaches_model(runtime, sample_config):




    await runtime.mcp.add_server(sample_config)
    ctx = SkillContext(paths=runtime.paths)

    from my_agent.errors import SkillExecutionError

    with pytest.raises(SkillExecutionError) as exc:
        await runtime.skills.execute("sample__read_note", {"name": "不存在"}, ctx)

    message = str(exc.value)
    assert "不存在" in message
    
    assert message.count("执行失败") <= 1
    assert message.count("执行出错") <= 1





async def test_remove_server_unregisters_tools(runtime, sample_config):
    await runtime.mcp.add_server(sample_config)
    assert mcp_skill_names(runtime)

    assert await runtime.mcp.remove_server("sample") is True

    
    assert mcp_skill_names(runtime) == set()
    assert runtime.mcp.status("sample") is None


async def test_stop_server_unregisters_tools(runtime, sample_config):
    await runtime.mcp.add_server(sample_config)
    assert mcp_skill_names(runtime)

    await runtime.mcp.stop_server("sample")

    assert runtime.mcp.status("sample").state == McpServerState.STOPPED
    assert mcp_skill_names(runtime) == set()


async def test_disabled_server_is_not_connected(runtime, sample_config):
    sample_config.enabled = False
    status = await runtime.mcp.add_server(sample_config)

    assert status.state == McpServerState.DISABLED
    assert mcp_skill_names(runtime) == set()


async def test_duplicate_add_replaces_existing(runtime, sample_config):

    await runtime.mcp.add_server(sample_config)
    again = await runtime.mcp.add_server(sample_config)

    assert again.state == McpServerState.READY
    assert len(runtime.mcp.statuses()) == 1


async def test_restart_reconnects(runtime, sample_config):
    await runtime.mcp.add_server(sample_config)
    first = mcp_skill_names(runtime)

    status = await runtime.mcp.restart_server("sample")

    assert status.state == McpServerState.READY
    assert mcp_skill_names(runtime) == first


async def test_user_overrides_survive_reconnect(runtime, sample_config):

    await runtime.mcp.add_server(sample_config)
    runtime.skills.set_permission("sample__write_note", "safe")

    await runtime.mcp.restart_server("sample")

    meta = next(m for m in runtime.skills.list_metas() if m.name == "sample__write_note")
    assert meta.permission_level == "safe"


async def test_permission_override_from_config(runtime, sample_config):
    sample_config.permission_overrides = {"read_note": "admin"}
    await runtime.mcp.add_server(sample_config)

    meta = next(m for m in runtime.skills.list_metas() if m.name == "sample__read_note")
    assert meta.permission_level == "admin"





async def test_crash_is_detected_and_recovered(runtime):
    await runtime.mcp.add_server(fixture_config())
    assert runtime.mcp.status("probe").state == McpServerState.READY

    client = runtime.mcp.client("probe")
    assert client is not None

    
    with pytest.raises(Exception):  
        await client.call_tool("crash")

    assert await client.ping() is False, "进程已退出，探活必须能发现"

    restarted = await runtime.mcp.health_check()
    assert restarted == 1
    assert runtime.mcp.status("probe").state == McpServerState.READY
    
    assert "probe__echo" in mcp_skill_names(runtime)


async def test_restart_limit_is_enforced(runtime):

    broken = McpServerConfig(
        name="broken",
        command=sys.executable,
        args=["-c", "import sys; sys.exit(1)"],
        timeout=5.0,
    )

    await runtime.mcp.add_server(broken)
    status = runtime.mcp.status("broken")
    
    assert status.state == McpServerState.ERROR
    assert status.last_error

    client = runtime.mcp.client("broken")
    assert client is not None

    
    client.status.restarts = MAX_AUTO_RESTARTS
    assert await runtime.mcp._try_recover(client) is False  
    assert "手动重启" in client.status.message
    
    assert client.status.restarts == MAX_AUTO_RESTARTS


async def test_bad_command_gives_readable_error(runtime):
    bad = McpServerConfig(
        name="ghost",
        command="definitely-not-a-real-binary-xyz",
        args=[],
        timeout=5.0,
    )
    status = await runtime.mcp.add_server(bad)

    assert status.state == McpServerState.ERROR
    assert status.last_error
    
    assert "找不到可执行文件" in (status.last_error or "") or "不存在" in (
        status.last_error or ""
    )


async def test_unexpected_exception_is_contained(runtime):

    await runtime.mcp.add_server(fixture_config())
    client = runtime.mcp.client("probe")
    assert client is not None

    from my_agent.errors import McpToolCallError

    with pytest.raises(McpToolCallError):
        await client.call_tool("boom")

    
    assert await client.ping() is True
    assert "ok" in await client.call_tool("echo", {"text": "ok"})





async def test_config_is_persisted(paths, sample_config):
    runtime = await build_runtime(paths)
    try:
        await runtime.mcp.add_server(sample_config)
    finally:
        await runtime.shutdown()

    raw = json.loads(paths.mcp_file.read_text(encoding="utf-8"))
    assert raw["servers"][0]["name"] == "sample"
    assert raw["servers"][0]["command"] == sys.executable

    
    second = await build_runtime(paths)
    try:
        assert [s.name for s in second.mcp.statuses()] == ["sample"]
    finally:
        await second.shutdown()


async def test_auto_start_connects_on_boot(paths, sample_config):

    runtime = await build_runtime(paths)
    try:
        await runtime.mcp.add_server(sample_config)
    finally:
        await runtime.shutdown()

    second = await build_runtime(paths)
    try:
        assert second.mcp.status("sample").state == McpServerState.READY
        assert "sample__echo" in mcp_skill_names(second)
    finally:
        await second.shutdown()





@pytest.fixture
async def http(base_url):
    async with make_client(base_url) as client:
        yield client


async def test_http_list_servers_includes_presets(runtime, http):
    body = (await http.get("/v1/mcp/servers")).json()
    assert body["sdk_available"] is True
    assert body["servers"] == []
    keys = {item["key"] for item in body["presets"]}
    
    
    
    
    
    assert keys == {"sample", "sqlite"}


async def test_http_add_and_list_server(runtime, http, sample_config):
    created = await http.post("/v1/mcp/servers", json=sample_config.model_dump(mode="json"))
    assert created.status_code == 200, created.text
    assert created.json()["state"] == "ready"

    listed = (await http.get("/v1/mcp/servers")).json()
    assert listed["tool_total"] == 5

    
    skills = (await http.get("/v1/skills")).json()["skills"]
    mcp_skills = [s for s in skills if s["source"] == "mcp"]
    assert len(mcp_skills) == 5

    
    duplicate = await http.post(
        "/v1/mcp/servers", json=sample_config.model_dump(mode="json")
    )
    assert duplicate.status_code == 409

    assert (await http.delete("/v1/mcp/servers/sample")).json()["ok"] is True
    assert (await http.get("/v1/skills")).json()["skills"]
    remaining = [
        s for s in (await http.get("/v1/skills")).json()["skills"] if s["source"] == "mcp"
    ]
    assert remaining == []


async def test_http_tools_preview(runtime, http, sample_config):
    await http.post("/v1/mcp/servers", json=sample_config.model_dump(mode="json"))
    body = (await http.get("/v1/mcp/servers/sample/tools")).json()
    names = {tool["name"] for tool in body["tools"]}
    assert {"read_note", "write_note", "echo"} <= names
    assert next(t for t in body["tools"] if t["name"] == "read_note")["read_only"] is True


async def test_http_permission_override(runtime, http, sample_config):
    await http.post("/v1/mcp/servers", json=sample_config.model_dump(mode="json"))

    resp = await http.patch(
        "/v1/mcp/servers/sample/permission",
        json={"tool": "write_note", "permission_level": "admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["overrides"]["write_note"] == "admin"

    meta = next(
        m
        for m in runtime.skills.list_metas(enabled_only=False)
        if m.name == "sample__write_note"
    )
    assert meta.permission_level == "admin"

    bad = await http.patch(
        "/v1/mcp/servers/sample/permission",
        json={"tool": "write_note", "permission_level": "whatever"},
    )
    assert bad.status_code == 422


async def test_env_survives_status_round_trip(runtime, http, sample_config):





    sample_config.env = {"MY_TOKEN": "s3cret"}
    sample_config.auto_start = False

    await http.post("/v1/mcp/servers", json=sample_config.model_dump(mode="json"))

    listed = (await http.get("/v1/mcp/servers")).json()["servers"][0]
    assert listed["env"] == {"MY_TOKEN": "s3cret"}
    assert listed["cwd"] is None

    
    saved = await http.put("/v1/mcp/servers/sample", json={**listed, "enabled": False})
    assert saved.status_code == 200, saved.text

    after = (await http.get("/v1/mcp/servers")).json()["servers"][0]
    assert after["env"] == {"MY_TOKEN": "s3cret"}
    assert after["enabled"] is False
    
    assert "state" not in json.loads(runtime.paths.mcp_file.read_text(encoding="utf-8"))["servers"][0]


async def test_http_404_for_unknown_server(runtime, http):
    assert (await http.get("/v1/mcp/servers/nope")).status_code == 404
    assert (await http.post("/v1/mcp/servers/nope/restart")).status_code == 404
    assert (await http.delete("/v1/mcp/servers/nope")).status_code == 404


async def test_http_status_event_is_pushed(runtime, http, sample_config):

    async with event_collector(http) as events:
        await http.post("/v1/mcp/servers", json=sample_config.model_dump(mode="json"))
        assert await wait_for(lambda: any(e[0] == "mcp_status" for e in events))

    statuses = [data["server"] for name, data in events if name == "mcp_status"]
    assert any(item["state"] == "ready" for item in statuses)
    assert any(item["state"] == "starting" for item in statuses)





async def test_agent_calls_mcp_tool_end_to_end(runtime, http, sample_config):





    await http.post("/v1/mcp/servers", json=sample_config.model_dump(mode="json"))
    created = await http.post(
        "/v1/assistants",
        json={
            "id": "mcp-probe",
            "name": "MCP 探针",
            "emoji": "🔌",
            "description": "验证 MCP 工具端到端",
            "system_prompt": "你是测试助手",
            "model_id": "",
            "temperature": 0.5,
            "max_iterations": 3,
            "enabled_skills": ["sample__write_note", "sample__read_note"],
            "confirm_mode": None,
        },
    )
    assert created.status_code == 200, created.text

    install_fake_model(
        runtime,
        FakeLLM(
            [
                
                _tool_response(
                    "sample__write_note",
                    {"name": "待办", "content": "1. 验证 MCP 端到端"},
                ),
                
                _tool_response("sample__read_note", {"name": "待办"}),
                "已经通过 MCP 便签服务记录并读回了内容。",
            ]
        ),
    )

    events = await read_sse_auto_approve(
        http, {"message": "帮我记个待办", "model_id": "fake", "assistant_id": "mcp-probe"}
    )
    types = [name for name, _ in events]

    
    assert "permission_request" in types
    assert types.count("tool_call") == 2

    results = [data for name, data in events if name == "tool_result"]
    assert all(item["status"] == "ok" for item in results), results
    assert "sample__write_note" in results[0]["name"]
    assert "验证 MCP 端到端" in results[1]["result"]

    final = "".join(data["text"] for name, data in events if name == "delta")
    assert "MCP" in final

    
    notes = list((runtime.paths.workspace_dir / "mcp-notes").glob("*.md"))
    assert any("验证 MCP 端到端" in item.read_text(encoding="utf-8") for item in notes)


async def test_agent_sees_mcp_tools_disappear_after_disconnect(runtime, http, sample_config):

    await http.post("/v1/mcp/servers", json=sample_config.model_dump(mode="json"))
    
    created = await http.post(
        "/v1/assistants",
        json={
            "id": "mcp-see",
            "name": "MCP 可见性探针",
            "emoji": "🔌",
            "description": "验证 MCP 工具的可见性",
            "system_prompt": "你是测试助手",
            "model_id": "",
            "temperature": 0.5,
            "max_iterations": 3,
            "enabled_skills": ["sample__echo"],
            "confirm_mode": None,
        },
    )
    assert created.status_code == 200, created.text

    llm = FakeLLM(["好的"])
    install_fake_model(runtime, llm)
    await read_sse(
        http, {"message": "看看有哪些工具", "model_id": "fake", "assistant_id": "mcp-see"}
    )
    
    
    first_tools = {spec.name for spec in llm.tools_seen[0]}
    assert "sample__echo" in first_tools

    await http.delete("/v1/mcp/servers/sample")

    llm2 = FakeLLM(["好的"])
    install_fake_model(runtime, llm2)
    await read_sse(http, {"message": "再看看", "model_id": "fake", "assistant_id": "mcp-see"})
    second_tools = {spec.name for spec in llm2.tools_seen[0]}
    assert "sample__echo" not in second_tools
    
    assert "calc" in second_tools


def _tool_response(name: str, arguments: dict):
    from my_agent.llm.base import LLMResponse

    
    
    return LLMResponse(
        tool_calls=[tool_call(name, arguments, call_id=f"call_{name}")],
        finish_reason="tool_calls",
    )

"""MCP 集成测试：真实子进程、真实 stdio 协议。

覆盖开发文档 M5 验收与客户端计划 P3 验收的全部条目：
工具自动出现在工具列表、调用成功、命名空间防冲突、崩溃自动重连、
以及「断连后工具从模型可见列表消失」。

正常路径用**随应用分发的示例 Server**（`my_agent/mcp/sample_server.py`，
它就在包内，打包后也能跑），异常路径用 `tests/fixtures/test_mcp_server.py`。
"""

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

# 拉起 Python 子进程 + 完成 MCP 握手需要一两秒，给足余量
CONNECT_WAIT = 60.0


@pytest.fixture
def paths(tmp_path) -> AppPaths:
    p = AppPaths(tmp_path / "AgentDesktop").ensure()
    # ⚠️ 先放一份**空的** mcp.json：出厂首次生成会预置自带的 SQLite 只读查询服务
    # （见 `config/loader.py` 的 `_load_mcp`），而这一组用例验的是"添加 / 移除 /
    # 停用某个服务"的行为，需要一个**已知的干净 baseline** —— 否则它们会带着一个
    # 额外的已连接服务跑，工具集与计数全对不上。
    #
    # 文件先存在 → loader 走"读取"分支，不会预置。
    # 「出厂确实预置了 sqlite」由 `tests/unit/test_mcp_presets.py` 专门验，
    # 两件事分开测：混在一起的话，任一边改动都会让另一边莫名报红。
    p.mcp_file.write_text('{"servers": []}', encoding="utf-8")
    return p


async def build_runtime(paths: AppPaths) -> AppRuntime:
    runtime = AppRuntime(paths)
    await runtime.initialize()
    return runtime


@pytest.fixture
async def runtime(paths):
    rt = await build_runtime(paths)
    # ⚠️ 出厂首次生成的 mcp.json 里**预置了自带的 SQLite 只读查询服务**
    # （见 `loader._load_mcp`，它 `auto_start=True`）。这一组用例验的是"添加 /
    # 移除 / 停用某个服务"，需要从**已知的干净 baseline** 开始 ——
    # 那一行保证由上面的 `paths` fixture 完成（它预先放一份空配置，让 loader
    # 走"读取"分支而不是"首次生成"分支）。
    # 确认超时压到 5 秒：用例失败时不至于白等两分钟
    rt.config.settings.security.confirm_timeout_seconds = 5.0
    # 显式钉住「每次确认」：这一组里有专门验「confirm 级 MCP 工具必须弹确认 /
    # 没有确认通道就拒绝」的用例。**不要**改成"跟着出厂默认走"——
    # 默认值是会变的（近期已经翻过一次：自动批准 → 每次确认），而一旦它恰好不是
    # 这一档，那两条用例就会静默地什么都不验直接变绿（理由同 conftest.py）。
    rt.config.settings.security.confirm_mode = "interactive"
    rt.skills.guard.set_confirm_mode("interactive")
    try:
        yield rt
    finally:
        await rt.shutdown()


@pytest.fixture
def sample_config(paths):
    config = build_sample_server(paths)
    # 用当前解释器启动，避免依赖 PATH 里的 python
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


# --------------------------------------------------------------------------- #
# 连接与工具注册
# --------------------------------------------------------------------------- #
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
    # 工具必须真的进入模型可见列表，否则等于没接
    exposed = {spec.name for spec in runtime.skills.to_tool_specs()}
    assert "sample__read_note" in exposed


async def test_tool_metadata_is_preserved(runtime, sample_config):
    await runtime.mcp.add_server(sample_config)
    meta = next(
        m for m in runtime.skills.list_metas() if m.name == "sample__read_note"
    )
    # 描述要带来源前缀，模型在多工具场景下更容易选对
    assert meta.description.startswith("[sample]")
    assert meta.category == "mcp"
    assert meta.source == "mcp"
    # 参数 Schema 来自 Server 的 inputSchema
    assert "name" in meta.parameters["properties"]


async def test_permission_inferred_from_annotations(runtime, sample_config):
    """示例 Server 显式声明了 readOnlyHint / destructiveHint，应被优先采用。"""
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


# --------------------------------------------------------------------------- #
# 调用
# --------------------------------------------------------------------------- #
def approved_ctx(runtime: AppRuntime) -> SkillContext:
    """带「总是批准」确认通道的上下文。

    MCP 里被推断为 confirm 的工具（如 write_note）没有确认通道时会被**正确拒绝**，
    这里显式装上通道，好让调用链路本身可测；确认机制自身由其它用例覆盖。
    """

    async def approve(_request) -> bool:
        return True

    return SkillContext(paths=runtime.paths, confirm=approve)


async def test_call_tool_through_skill_manager(runtime, sample_config):
    await runtime.mcp.add_server(sample_config)
    ctx = approved_ctx(runtime)

    result = await runtime.skills.execute("sample__echo", {"text": "你好"}, ctx)
    assert "你好" in result

    # 先写再读，验证副作用类工具真的落到了磁盘
    await runtime.skills.execute(
        "sample__write_note", {"name": "周报", "content": "本周完成 MCP 集成"}, ctx
    )
    listed = await runtime.skills.execute("sample__list_notes", {}, ctx)
    assert "周报" in listed

    content = await runtime.skills.execute("sample__read_note", {"name": "周报"}, ctx)
    assert "MCP 集成" in content


async def test_confirm_tool_is_denied_without_channel(runtime, sample_config):
    """没有确认通道时必须拒绝执行，绝不能"因为不知道就放行"。"""
    await runtime.mcp.add_server(sample_config)
    ctx = SkillContext(paths=runtime.paths)

    from my_agent.errors import SkillPermissionError

    with pytest.raises(SkillPermissionError):
        await runtime.skills.execute(
            "sample__write_note", {"name": "不该被创建", "content": "x"}, ctx
        )
    # 拒绝之后磁盘上不应该有痕迹
    notes = list((runtime.paths.workspace_dir / "mcp-notes").glob("*.md"))
    assert notes == []


async def test_tool_error_message_reaches_model(runtime, sample_config):
    """Server 抛 ToolError 时，原文必须透传给模型，而不是被吞成通用错误。

    否则模型只知道"失败了"，无法自我修正（比如换个便签名重试）。
    """
    await runtime.mcp.add_server(sample_config)
    ctx = SkillContext(paths=runtime.paths)

    from my_agent.errors import SkillExecutionError

    with pytest.raises(SkillExecutionError) as exc:
        await runtime.skills.execute("sample__read_note", {"name": "不存在"}, ctx)

    message = str(exc.value)
    assert "不存在" in message
    # 不能出现层层叠加的错误前缀，那样反而把真正的信息淹没了
    assert message.count("执行失败") <= 1
    assert message.count("执行出错") <= 1


# --------------------------------------------------------------------------- #
# 生命周期
# --------------------------------------------------------------------------- #
async def test_remove_server_unregisters_tools(runtime, sample_config):
    await runtime.mcp.add_server(sample_config)
    assert mcp_skill_names(runtime)

    assert await runtime.mcp.remove_server("sample") is True

    # 工具必须从模型可见列表里消失，否则模型会去调用一个不存在的服务
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
    """同名服务重复添加应视为替换，而不是留下两条记录。"""
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
    """用户把某个工具改成 safe 后，服务重连不能把它改回 confirm。"""
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


# --------------------------------------------------------------------------- #
# 崩溃与自愈
# --------------------------------------------------------------------------- #
async def test_crash_is_detected_and_recovered(runtime):
    await runtime.mcp.add_server(fixture_config())
    assert runtime.mcp.status("probe").state == McpServerState.READY

    client = runtime.mcp.client("probe")
    assert client is not None

    # 让子进程直接退出
    with pytest.raises(Exception):  # noqa: B017 - 传输中断，具体类型由 SDK 决定
        await client.call_tool("crash")

    assert await client.ping() is False, "进程已退出，探活必须能发现"

    restarted = await runtime.mcp.health_check()
    assert restarted == 1
    assert runtime.mcp.status("probe").state == McpServerState.READY
    # 工具在恢复后重新上线
    assert "probe__echo" in mcp_skill_names(runtime)


async def test_restart_limit_is_enforced(runtime):
    """连续失败达到上限后必须停止重试，避免"配置写错 → 无限重启"刷屏。"""
    broken = McpServerConfig(
        name="broken",
        command=sys.executable,
        args=["-c", "import sys; sys.exit(1)"],
        timeout=5.0,
    )

    await runtime.mcp.add_server(broken)
    status = runtime.mcp.status("broken")
    # 启动即失败，错误原因必须落到状态里供界面展示
    assert status.state == McpServerState.ERROR
    assert status.last_error

    client = runtime.mcp.client("broken")
    assert client is not None

    # 直接驱动恢复逻辑：用光自动重连额度后，必须放弃并提示用户手动处理
    client.status.restarts = MAX_AUTO_RESTARTS
    assert await runtime.mcp._try_recover(client) is False  # noqa: SLF001
    assert "手动重启" in client.status.message
    # 额度用尽后不再继续加计数
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
    # 错误信息必须能指导用户，而不是甩一串 anyio 的堆栈
    assert "找不到可执行文件" in (status.last_error or "") or "不存在" in (
        status.last_error or ""
    )


async def test_unexpected_exception_is_contained(runtime):
    """工具内部抛非预期异常时，不能让整个连接崩掉。"""
    await runtime.mcp.add_server(fixture_config())
    client = runtime.mcp.client("probe")
    assert client is not None

    from my_agent.errors import McpToolCallError

    with pytest.raises(McpToolCallError):
        await client.call_tool("boom")

    # 连接仍可用
    assert await client.ping() is True
    assert "ok" in await client.call_tool("echo", {"text": "ok"})


# --------------------------------------------------------------------------- #
# 配置持久化
# --------------------------------------------------------------------------- #
async def test_config_is_persisted(paths, sample_config):
    runtime = await build_runtime(paths)
    try:
        await runtime.mcp.add_server(sample_config)
    finally:
        await runtime.shutdown()

    raw = json.loads(paths.mcp_file.read_text(encoding="utf-8"))
    assert raw["servers"][0]["name"] == "sample"
    assert raw["servers"][0]["command"] == sys.executable

    # 重启后配置仍在（但不会自动连接，除非 auto_start）
    second = await build_runtime(paths)
    try:
        assert [s.name for s in second.mcp.statuses()] == ["sample"]
    finally:
        await second.shutdown()


async def test_auto_start_connects_on_boot(paths, sample_config):
    """auto_start 的服务应在客户端启动时自动连上。"""
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


# --------------------------------------------------------------------------- #
# HTTP 接口
# --------------------------------------------------------------------------- #
@pytest.fixture
async def http(base_url):
    async with make_client(base_url) as client:
        yield client


async def test_http_list_servers_includes_presets(runtime, http):
    body = (await http.get("/v1/mcp/servers")).json()
    assert body["sdk_available"] is True
    assert body["servers"] == []
    keys = {item["key"] for item in body["presets"]}
    # 这两个都免安装免联网：示例服务是首次体验的兜底，SQLite 查询是开箱可用的实用能力。
    #
    # ⚠️ 起 filesystem / everything 已剔除（前者能力被内置技能覆盖、
    # 后者纯演示），sqlite 也换成了自带的实现 —— 三个 npx / uvx 预设一个不剩。
    # 用 `==` 而不是 `<=`：以后谁再加回一个需要联网下载的预设，这里就该红一次。
    assert keys == {"sample", "sqlite"}


async def test_http_add_and_list_server(runtime, http, sample_config):
    created = await http.post("/v1/mcp/servers", json=sample_config.model_dump(mode="json"))
    assert created.status_code == 200, created.text
    assert created.json()["state"] == "ready"

    listed = (await http.get("/v1/mcp/servers")).json()
    assert listed["tool_total"] == 5

    # 工具出现在技能清单里，并标注来源
    skills = (await http.get("/v1/skills")).json()["skills"]
    mcp_skills = [s for s in skills if s["source"] == "mcp"]
    assert len(mcp_skills) == 5

    # 重复添加应被拒绝，避免悄悄覆盖掉正在运行的服务
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
    """界面上「读取 → 改开关 → 整体保存」不能把用户填的环境变量清空。

    状态接口如果不返回 env，界面就无从保留它，用户点一下开关配置就没了——
    这类"静默丢数据"比直接报错更难被发现。
    """
    sample_config.env = {"MY_TOKEN": "s3cret"}
    sample_config.auto_start = False

    await http.post("/v1/mcp/servers", json=sample_config.model_dump(mode="json"))

    listed = (await http.get("/v1/mcp/servers")).json()["servers"][0]
    assert listed["env"] == {"MY_TOKEN": "s3cret"}
    assert listed["cwd"] is None

    # 模拟界面：把状态原样提交回去，只改 enabled
    saved = await http.put("/v1/mcp/servers/sample", json={**listed, "enabled": False})
    assert saved.status_code == 200, saved.text

    after = (await http.get("/v1/mcp/servers")).json()["servers"][0]
    assert after["env"] == {"MY_TOKEN": "s3cret"}
    assert after["enabled"] is False
    # 状态字段不该污染配置文件
    assert "state" not in json.loads(runtime.paths.mcp_file.read_text(encoding="utf-8"))["servers"][0]


async def test_http_404_for_unknown_server(runtime, http):
    assert (await http.get("/v1/mcp/servers/nope")).status_code == 404
    assert (await http.post("/v1/mcp/servers/nope/restart")).status_code == 404
    assert (await http.delete("/v1/mcp/servers/nope")).status_code == 404


async def test_http_status_event_is_pushed(runtime, http, sample_config):
    """服务状态变化必须实时推给客户端，界面上的连接灯才能立刻变。"""
    async with event_collector(http) as events:
        await http.post("/v1/mcp/servers", json=sample_config.model_dump(mode="json"))
        assert await wait_for(lambda: any(e[0] == "mcp_status" for e in events))

    statuses = [data["server"] for name, data in events if name == "mcp_status"]
    assert any(item["state"] == "ready" for item in statuses)
    assert any(item["state"] == "starting" for item in statuses)


# --------------------------------------------------------------------------- #
# 端到端：模型通过 MCP 工具完成任务
# --------------------------------------------------------------------------- #
async def test_agent_calls_mcp_tool_end_to_end(runtime, http, sample_config):
    """P3 验收核心项：让 Agent 通过 MCP 工具读写文件成功。

    ⚠️ 2026-10-06 四分类后 MCP 工具归「通用技能」—— 搭子要**勾选**才能用它，
    所以先建一个勾了它们的搭子（内置搭子不能加技能，见 skill/groups.py）。
    """
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
                # 第一轮：模型决定调用 MCP 工具写便签（confirm 级，需要批准）
                _tool_response(
                    "sample__write_note",
                    {"name": "待办", "content": "1. 验证 MCP 端到端"},
                ),
                # 第二轮：模型读回来确认
                _tool_response("sample__read_note", {"name": "待办"}),
                "已经通过 MCP 便签服务记录并读回了内容。",
            ]
        ),
    )

    events = await read_sse_auto_approve(
        http, {"message": "帮我记个待办", "model_id": "fake", "assistant_id": "mcp-probe"}
    )
    types = [name for name, _ in events]

    # 写便签是 confirm 级，必须先弹确认再执行
    assert "permission_request" in types
    assert types.count("tool_call") == 2

    results = [data for name, data in events if name == "tool_result"]
    assert all(item["status"] == "ok" for item in results), results
    assert "sample__write_note" in results[0]["name"]
    assert "验证 MCP 端到端" in results[1]["result"]

    final = "".join(data["text"] for name, data in events if name == "delta")
    assert "MCP" in final

    # 文件真的落到了磁盘上
    notes = list((runtime.paths.workspace_dir / "mcp-notes").glob("*.md"))
    assert any("验证 MCP 端到端" in item.read_text(encoding="utf-8") for item in notes)


async def test_agent_sees_mcp_tools_disappear_after_disconnect(runtime, http, sample_config):
    """断连后工具必须从模型可见列表消失（P3 验收项）。"""
    await http.post("/v1/mcp/servers", json=sample_config.model_dump(mode="json"))
    # ⚠️ 同上：MCP 工具归「通用技能」，要勾选才对某个搭子可见
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
    # 必须看「模型实际收到了哪些工具」，而不是 SkillManager 里注册了什么——
    # 后者不代表模型真的能看到
    first_tools = {spec.name for spec in llm.tools_seen[0]}
    assert "sample__echo" in first_tools

    await http.delete("/v1/mcp/servers/sample")

    llm2 = FakeLLM(["好的"])
    install_fake_model(runtime, llm2)
    await read_sse(http, {"message": "再看看", "model_id": "fake", "assistant_id": "mcp-see"})
    second_tools = {spec.name for spec in llm2.tools_seen[0]}
    assert "sample__echo" not in second_tools
    # 内置技能不受影响
    assert "calc" in second_tools


def _tool_response(name: str, arguments: dict):
    from my_agent.llm.base import LLMResponse

    # call_id 用工具名派生：多轮里如果都用 call_1，回填给模型的 tool 消息
    # 会和上一条助手消息配不上对，协议层面是错的
    return LLMResponse(
        tool_calls=[tool_call(name, arguments, call_id=f"call_{name}")],
        finish_reason="tool_calls",
    )

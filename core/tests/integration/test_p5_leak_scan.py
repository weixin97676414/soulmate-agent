"""P5 验收：敏感信息零泄露扫描。

对应开发文档 M7 与客户端计划 P5 的验收项——「敏感信息（API Key、手机号）
在日志/响应中零泄露（扫描验证）」。

**为什么要用"扫描"而不是"看代码"**：脱敏是横切关注点，任何一条新加的日志、
新写的一个字段都可能绕开它。靠 review 保证不了，必须让机器每次跑一遍真实的
对话流程，然后拿哨兵值去全文搜。
"""

from __future__ import annotations

import json

import pytest

from my_agent.config.paths import AppPaths
from my_agent.config.secrets import ENV_SECRETS_FILE
from my_agent.observability.logger import setup_logging
from my_agent.server.runtime import AppRuntime
from my_agent.skill.base import BaseSkill
from my_agent.skill.decorator import skill as skill_decorator

from .conftest import (
    FakeLLM,
    install_fake_model,
    make_client,
    read_sse,
    serve_runtime,
    tool_call,
)

# 哨兵值：刻意做成"绝不可能自然出现"的字符串，扫描时不会误报
CANARY_KEY = "sk-CANARY1234567890abcdef"
CANARY_PHONE = "13800138000"


def register_echo_skill(runtime: AppRuntime) -> None:
    """注册一个把参数原样带回的技能，用来把哨兵值灌进审计与 Trace。"""

    @skill_decorator(
        name="echo_params",
        display_name="回显参数",
        description="原样返回收到的参数（测试用）",
        params_model=None,
        permission_level="safe",
    )
    class _EchoSkill(BaseSkill):
        async def run(self, ctx, **params):
            return {"received": params}

    runtime.skills.register(_EchoSkill)


def scan_for(text: str, log_dir) -> list[str]:
    """在日志目录里找哨兵值，返回命中的文件路径。"""
    hits: list[str] = []
    if not log_dir.exists():
        return hits
    for path in log_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if text in content:
            hits.append(str(path))
    return hits


@pytest.fixture
async def leak_env(tmp_path, monkeypatch):
    """自带 HTTP 服务的运行时。

    不能复用 conftest 的 `http` 夹具：那个绑定的是它自己的 runtime 实例，
    而这里必须让请求打在同一份"装了哨兵技能"的运行时上，
    否则扫描的是另一个进程状态，等于空检查。
    """
    monkeypatch.delenv(ENV_SECRETS_FILE, raising=False)
    paths = AppPaths(tmp_path / "data").ensure()
    setup_logging(level="DEBUG", logs_dir=paths.logs_dir)

    runtime = AppRuntime(paths)
    await runtime.initialize()
    register_echo_skill(runtime)
    try:
        async with serve_runtime(runtime) as url:
            async with make_client(url) as client:
                yield runtime, client
    finally:
        await runtime.shutdown()


async def test_pii_in_tool_params_stays_out_of_logs_and_audit(leak_env):
    """工具参数里的敏感信息不得进入日志与审计库。

    **注意这里刻意不断言 tool_call / tool_result 事件**：用户在点「允许执行」之前
    必须看到真实的参数，把参数脱敏掉等于让确认弹窗失去意义。
    这条链路是"用户自己的数据回显给用户自己"，不是泄露；
    真正的风险在于它被**持久化**（审计库）或被**写进日志**（日志常被拿去做支持）。
    """
    runtime, http = leak_env
    install_fake_model(
        runtime,
        FakeLLM([LLMResponseWithTool(CANARY_KEY, CANARY_PHONE), "已经处理完了。"]),
    )

    events = await read_sse(http, {"message": "把这两项记一下", "model_id": "fake"})

    # ---- 1) 审计库：必须已脱敏 ---- //
    rows = await runtime.db.fetch_all("SELECT * FROM audit_log")
    audit_dump = json.dumps(rows, ensure_ascii=False, default=str)
    assert CANARY_KEY not in audit_dump, "密钥出现在了审计库中"
    assert CANARY_PHONE not in audit_dump, "手机号出现在了审计库中"
    assert rows, "审计表为空说明根本没走到被检查的链路"

    # ---- 2) Trace 事件：必须已脱敏 ---- //
    trace = next(data for name, data in events if name == "trace")
    trace_dump = json.dumps(trace, ensure_ascii=False, default=str)
    assert CANARY_KEY not in trace_dump, "密钥出现在了执行链路里"
    assert CANARY_PHONE not in trace_dump, "手机号出现在了执行链路里"

    # ---- 3) 日志文件 ---- //
    for canary in (CANARY_KEY, CANARY_PHONE):
        hits = scan_for(canary, runtime.paths.logs_dir)
        assert not hits, f"{canary[:12]}… 出现在日志文件里：{hits}"


async def test_provider_echoed_credentials_are_redacted(leak_env):
    """厂商把请求原样回显时，错误信息里的凭据必须被脱敏。

    这是真实存在的一类响应：某些网关/反向代理在 401 时会把整个请求（含
    Authorization 头）回显出来。而 LLM 的错误信息会一路走到界面上，
    不脱敏就等于把 Key 直接印给用户看。
    """
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    captured: list[str] = []

    class EchoHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server 的约定
            auth = self.headers.get("Authorization", "")
            captured.append(auth)
            body = json.dumps({"error": f"invalid credentials: {auth}"}).encode()
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # 静音，避免污染测试输出
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    runtime, http = leak_env
    try:
        response = await http.post(
            "/v1/models/test",
            json={
                "spec": {
                    "id": "echo",
                    "name": "Echo",
                    "adapter": "openai_compat",
                    "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                    "api_key": CANARY_KEY,
                    "model_name": "echo",
                }
            },
        )
        payload = json.dumps(response.json(), ensure_ascii=False)

        assert captured, "回显服务没有被调用到，用例失去意义"
        assert CANARY_KEY in captured[0], "回显服务确实收到了明文 Key"

        assert CANARY_KEY not in payload, "厂商回显的 Key 没有被脱敏就返回给了客户端"
        assert "<API_KEY>" in payload or "<TOKEN>" in payload
    finally:
        server.shutdown()
        server.server_close()


async def test_managed_mode_keeps_secrets_out_of_entire_data_dir(tmp_path, monkeypatch):
    """开启密钥托管时，整个数据目录（含配置与数据库）都不该出现明文 Key。"""
    paths = AppPaths(tmp_path / "managed").ensure()
    # 模型清单默认为空（出厂不再硬塞模型），先种一个接收密钥的条目
    (paths.models_file).write_text(
        json.dumps(
            {
                "default_model": "deepseek-chat",
                "models": [
                    {
                        "id": "deepseek-chat",
                        "provider": "deepseek",
                        "base_url": "https://api.deepseek.com/v1",
                        "model_name": "deepseek-chat",
                        "token_limit": 65536,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    secrets_file = tmp_path / "secrets.json"
    secrets_file.write_text(json.dumps({"models": {"deepseek-chat": CANARY_KEY}}), "utf-8")
    monkeypatch.setenv(ENV_SECRETS_FILE, str(secrets_file))
    setup_logging(level="DEBUG", logs_dir=paths.logs_dir)

    runtime = AppRuntime(paths)
    await runtime.initialize()
    try:
        assert runtime.config.models.get("deepseek-chat").api_key == CANARY_KEY
        # 触发一次落盘，确认写出去的配置里没有 Key
        runtime.config_store.save_models(runtime.config.models)
    finally:
        await runtime.shutdown()

    offenders: list[str] = []
    for path in paths.root.rglob("*"):
        if not path.is_file():
            continue
        try:
            if CANARY_KEY in path.read_text(encoding="utf-8", errors="replace"):
                offenders.append(str(path.relative_to(paths.root)))
        except OSError:
            continue

    assert not offenders, f"密钥明文出现在数据目录中：{offenders}"


def LLMResponseWithTool(secret: str, phone: str):
    """构造一次携带哨兵参数的工具调用。"""
    from my_agent.llm.base import LLMResponse

    return LLMResponse(
        tool_calls=[
            tool_call(
                "echo_params",
                {"api_key": secret, "phone": phone},
                call_id="call_canary",
            )
        ],
        finish_reason="tool_calls",
    )


async def test_sensitive_values_are_redacted_by_the_util():
    """底层脱敏工具的直接验证——上层扫描失败时能快速定位是工具本身的问题。"""
    from my_agent.security.redact import redact, redact_obj

    assert CANARY_KEY not in redact(CANARY_KEY)
    assert CANARY_PHONE not in redact(CANARY_PHONE)
    assert "<API_KEY>" in redact(f"key is {CANARY_KEY} ok")
    assert "<手机号>" in redact(f"电话 {CANARY_PHONE}")

    payload = redact_obj({"nested": [{"token": "sk-live-abcdefghijklmn"}]})
    assert "sk-live" not in json.dumps(payload, ensure_ascii=False)

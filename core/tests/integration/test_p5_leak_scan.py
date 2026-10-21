









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


CANARY_KEY = "sk-CANARY1234567890abcdef"
CANARY_PHONE = "13800138000"


def register_echo_skill(runtime: AppRuntime) -> None:


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







    runtime, http = leak_env
    install_fake_model(
        runtime,
        FakeLLM([LLMResponseWithTool(CANARY_KEY, CANARY_PHONE), "已经处理完了。"]),
    )

    events = await read_sse(http, {"message": "把这两项记一下", "model_id": "fake"})

    
    rows = await runtime.db.fetch_all("SELECT * FROM audit_log")
    audit_dump = json.dumps(rows, ensure_ascii=False, default=str)
    assert CANARY_KEY not in audit_dump, "密钥出现在了审计库中"
    assert CANARY_PHONE not in audit_dump, "手机号出现在了审计库中"
    assert rows, "审计表为空说明根本没走到被检查的链路"

    
    trace = next(data for name, data in events if name == "trace")
    trace_dump = json.dumps(trace, ensure_ascii=False, default=str)
    assert CANARY_KEY not in trace_dump, "密钥出现在了执行链路里"
    assert CANARY_PHONE not in trace_dump, "手机号出现在了执行链路里"

    
    for canary in (CANARY_KEY, CANARY_PHONE):
        hits = scan_for(canary, runtime.paths.logs_dir)
        assert not hits, f"{canary[:12]}… 出现在日志文件里：{hits}"


async def test_provider_echoed_credentials_are_redacted(leak_env):






    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    captured: list[str] = []

    class EchoHandler(BaseHTTPRequestHandler):
        def do_GET(self):  
            auth = self.headers.get("Authorization", "")
            captured.append(auth)
            body = json.dumps({"error": f"invalid credentials: {auth}"}).encode()
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  
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

    paths = AppPaths(tmp_path / "managed").ensure()
    
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

    from my_agent.security.redact import redact, redact_obj

    assert CANARY_KEY not in redact(CANARY_KEY)
    assert CANARY_PHONE not in redact(CANARY_PHONE)
    assert "<API_KEY>" in redact(f"key is {CANARY_KEY} ok")
    assert "<手机号>" in redact(f"电话 {CANARY_PHONE}")

    payload = redact_obj({"nested": [{"token": "sk-live-abcdefghijklmn"}]})
    assert "sk-live" not in json.dumps(payload, ensure_ascii=False)

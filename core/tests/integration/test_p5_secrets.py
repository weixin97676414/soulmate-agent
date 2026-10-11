"""P5 集成测试：密钥由外部托管时的完整链路。

验收要点：密钥能注入到运行时、**不会落盘**、且保存配置的动作不会把
内存里的 Key 一起弄丢（后者表现为"刚填完 Key 就认证失败"，极难排查）。
"""

from __future__ import annotations

import json

import httpx
import pytest

from my_agent.config.paths import AppPaths
from my_agent.config.secrets import ENV_SECRETS_FILE
from my_agent.server.app import create_app
from my_agent.server.runtime import AppRuntime

from .conftest import TOKEN


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
    from my_agent.config.loader import ConfigStore

    return ConfigStore(paths, builtin=BuiltinAssistants(), **kwargs)


def write_secrets(path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def seed_deepseek(paths) -> None:
    """种一个 deepseek-chat 条目，供"密钥注入到模型"类用例使用。

    模型清单默认**为空**（新装用户从接入向导开始配，出厂不再硬塞模型），
    所以依赖"已存在一个模型"的用例必须自己把模型写进配置文件。
    """
    paths.models_file.write_text(
        json.dumps(
            {
                "default_model": "deepseek-chat",
                "models": [
                    {
                        "id": "deepseek-chat",
                        "name": "DeepSeek Chat",
                        "provider": "deepseek",
                        "base_url": "https://api.deepseek.com/v1",
                        "model_name": "deepseek-chat",
                        "token_limit": 65536,
                        "supports_tools": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
async def managed_runtime(tmp_path, monkeypatch):
    """带外部密钥托管的运行时（等价于 Electron 拉起后端时的环境）。"""
    paths = AppPaths(tmp_path / "data").ensure()
    seed_deepseek(paths)
    secrets_file = tmp_path / "secrets.json"
    write_secrets(
        secrets_file,
        {"models": {"deepseek-chat": "sk-from-safe-storage"}, "mcp": {"srv": {"TOKEN": "t1"}}},
    )
    monkeypatch.setenv(ENV_SECRETS_FILE, str(secrets_file))
    monkeypatch.setenv("AGENT_DATA_DIR", str(paths.root))

    runtime = AppRuntime(paths)
    await runtime.initialize()
    try:
        yield runtime, secrets_file
    finally:
        await runtime.shutdown()


async def test_secrets_are_injected_and_file_removed(managed_runtime):
    runtime, secrets_file = managed_runtime

    assert runtime.secrets is not None
    # 注入必须发生在配置加载之后、注册表构建之前
    assert runtime.config.models.get("deepseek-chat").api_key == "sk-from-safe-storage"
    assert not secrets_file.exists(), "密钥文件读完必须删掉"


async def test_managed_runtime_strips_keys_on_disk(managed_runtime):
    """保存模型配置后，磁盘上不能留下明文 Key。"""
    runtime, _ = managed_runtime
    paths = runtime.paths

    models = runtime.config.models.model_dump(mode="json")
    for spec in models["models"]:
        if spec["id"] == "deepseek-chat":
            spec["api_key"] = "sk-brand-new"
    runtime.config_store.save_models(runtime.config.models.model_validate(models))

    raw = json.loads(paths.models_file.read_text(encoding="utf-8"))
    assert all(spec["api_key"] == "" for spec in raw["models"])


async def test_saving_models_keeps_key_usable_in_memory(managed_runtime):
    """保存之后内存里必须还有 Key。

    这是最容易写错的一处：`reload_models` 若从磁盘重读，拿回的是被剥离过的空 Key，
    用户会看到"刚保存完就用不了了"。所以保存路径刻意不重读磁盘。
    """
    runtime, _ = managed_runtime
    await runtime.reload_models()

    assert runtime.config.models.get("deepseek-chat").api_key == "sk-from-safe-storage"
    assert runtime.registry.has("deepseek-chat")


async def test_http_flow_keeps_key_out_of_disk(managed_runtime):
    """走完整 HTTP：改 Key -> 保存 -> 磁盘无明文、界面仍显示"已配置"。

    这里用 ASGITransport 即可：本地用例只走普通 JSON 接口，
    不存在 SSE 被缓冲的问题（那类流程必须起真实 uvicorn）。
    """
    runtime, _ = managed_runtime
    app = create_app(runtime=runtime, token=TOKEN)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1",
        headers={"X-Local-Token": TOKEN},
    ) as client:
        payload = (await client.get("/v1/models")).json()
        for spec in payload["models"]:
            if spec["id"] == "deepseek-chat":
                spec["api_key"] = "sk-typed-by-user"
        response = await client.put(
            "/v1/models", json={"default_model": "deepseek-chat", "models": payload["models"]}
        )
        assert response.status_code == 200, response.text

        after = (await client.get("/v1/models")).json()["models"]
        target = next(spec for spec in after if spec["id"] == "deepseek-chat")
        assert target["has_api_key"] is True, "内存里应当还有 Key"
        # **接口现在回传明文** —— 这是产品明确要求的（字段里永远有真字符，
        # 自动保存提交的也永远是那个真值，那一整类"空值把 Key 覆盖掉"的 bug
        # 就不存在了）。存储侧没有降级：紧接着下面断言磁盘上不含明文。
        assert target["api_key"] == "sk-typed-by-user", "接口回传明文供界面常显"

    raw = json.loads(runtime.paths.models_file.read_text(encoding="utf-8"))
    assert all("typed-by-user" not in (spec["api_key"] or "") for spec in raw["models"])


async def test_unmanaged_runtime_encrypts_keys(tmp_path, monkeypatch):
    """没设 AGENT_SECRETS_FILE 时（独立运行后端）也要保护 Key。

    这条用例原先叫 ``test_unmanaged_runtime_keeps_plaintext``，断言的正是
    "明文留在 models.json 里"。那时没有别的选择：剥离会让用户"填了 Key 一保存
    就没了"。现在 Key 走 DPAPI 加密存进同目录的 ``secrets.enc``，
    于是两个目标可以同时成立 —— **既不落明文，也不丢 Key**。

    不变量从"明文可见"换成了"重新加载后 Key 还在"，后者才是真正重要的那个。
    """
    monkeypatch.delenv(ENV_SECRETS_FILE, raising=False)
    paths = AppPaths(tmp_path / "solo").ensure()
    seed_deepseek(paths)
    runtime = AppRuntime(paths)
    await runtime.initialize()
    try:
        assert runtime.secrets is None
        models = runtime.config.models.model_dump(mode="json")
        for spec in models["models"]:
            if spec["id"] == "deepseek-chat":
                spec["api_key"] = "sk-encrypted-ok"
        runtime.config_store.save_models(runtime.config.models.model_validate(models))

        raw = json.loads(paths.models_file.read_text(encoding="utf-8"))
        assert "sk-encrypted-ok" not in [spec["api_key"] for spec in raw["models"]]
        assert (paths.models_file.parent / "secrets.enc").is_file()

        # 重新加载：Key 必须原样回来

        reloaded = _store(paths).load()
        assert reloaded.models.get("deepseek-chat").api_key == "sk-encrypted-ok"
    finally:
        await runtime.shutdown()


async def test_secrets_file_removed_even_when_empty(tmp_path, monkeypatch):
    """空密钥文件也要删掉：路径存在本身就是"由外部托管"的信号。"""
    paths = AppPaths(tmp_path / "data").ensure()
    secrets_file = tmp_path / "empty.json"
    write_secrets(secrets_file, {})
    monkeypatch.setenv(ENV_SECRETS_FILE, str(secrets_file))

    runtime = AppRuntime(paths)
    try:
        assert runtime.secrets is not None
        assert runtime.secrets.is_empty()
        assert not secrets_file.exists()
    finally:
        await runtime.shutdown()


async def test_missing_secrets_file_still_marks_managed(tmp_path, monkeypatch):
    """文件不存在（首次启动或已被核心删过）仍算托管，否则首次启动会写明文。"""
    paths = AppPaths(tmp_path / "data").ensure()
    monkeypatch.setenv(ENV_SECRETS_FILE, str(tmp_path / "never-created.json"))

    runtime = AppRuntime(paths)
    try:
        assert runtime.secrets is not None
        assert runtime.secrets.is_empty()
    finally:
        await runtime.shutdown()


def test_env_var_constant_is_stable():
    """环境变量名是主进程与核心之间的契约。

    改这个名字必须同步改 `desktop/electron/backend.ts`（写入方），
    否则密钥会静默注入失败——后端按"未托管"处理，于是继续往配置里写明文。
    """
    assert ENV_SECRETS_FILE == "AGENT_SECRETS_FILE"

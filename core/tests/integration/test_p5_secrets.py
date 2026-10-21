





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










    from my_agent.assistants.bootstrap import BuiltinAssistants
    from my_agent.config.loader import ConfigStore

    return ConfigStore(paths, builtin=BuiltinAssistants(), **kwargs)


def write_secrets(path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def seed_deepseek(paths) -> None:





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
    
    assert runtime.config.models.get("deepseek-chat").api_key == "sk-from-safe-storage"
    assert not secrets_file.exists(), "密钥文件读完必须删掉"


async def test_managed_runtime_strips_keys_on_disk(managed_runtime):

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





    runtime, _ = managed_runtime
    await runtime.reload_models()

    assert runtime.config.models.get("deepseek-chat").api_key == "sk-from-safe-storage"
    assert runtime.registry.has("deepseek-chat")


async def test_http_flow_keeps_key_out_of_disk(managed_runtime):





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
        
        
        
        assert target["api_key"] == "sk-typed-by-user", "接口回传明文供界面常显"

    raw = json.loads(runtime.paths.models_file.read_text(encoding="utf-8"))
    assert all("typed-by-user" not in (spec["api_key"] or "") for spec in raw["models"])


async def test_unmanaged_runtime_encrypts_keys(tmp_path, monkeypatch):









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

        

        reloaded = _store(paths).load()
        assert reloaded.models.get("deepseek-chat").api_key == "sk-encrypted-ok"
    finally:
        await runtime.shutdown()


async def test_secrets_file_removed_even_when_empty(tmp_path, monkeypatch):

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

    paths = AppPaths(tmp_path / "data").ensure()
    monkeypatch.setenv(ENV_SECRETS_FILE, str(tmp_path / "never-created.json"))

    runtime = AppRuntime(paths)
    try:
        assert runtime.secrets is not None
        assert runtime.secrets.is_empty()
    finally:
        await runtime.shutdown()


def test_env_var_constant_is_stable():





    assert ENV_SECRETS_FILE == "AGENT_SECRETS_FILE"

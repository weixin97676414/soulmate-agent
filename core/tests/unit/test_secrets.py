





from __future__ import annotations

import json

import pytest

from my_agent.config.loader import ConfigStore
from my_agent.config.paths import AppPaths
from my_agent.config.schemas import (
    AppConfig,
    AppSettings,
    McpConfig,
    McpServerConfig,
    ModelsConfig,
    ModelSpec,
)
from my_agent.config.secrets import (
    Secrets,
    apply_secrets,
    is_secret_key,
    parse_secrets,
    read_secrets_file,
)


def _store(paths, **kwargs):










    from my_agent.assistants.bootstrap import BuiltinAssistants

    return ConfigStore(paths, builtin=BuiltinAssistants(), **kwargs)


def make_config() -> AppConfig:
    return AppConfig(
        settings=AppSettings(),
        models=ModelsConfig(
            default_model="m1",
            models=[
                ModelSpec(id="m1", model_name="m1", adapter="openai_compat", api_key=""),
                ModelSpec(id="m2", model_name="m2", adapter="openai_compat", api_key="legacy"),
            ],
        ),
        mcp=McpConfig(
            servers=[
                McpServerConfig(name="srv", command="python", env={"LOG_LEVEL": "debug"})
            ]
        ),
    )





def test_no_path_means_not_managed(tmp_path):





    assert read_secrets_file(None) is None
    assert read_secrets_file("") is None


def test_secrets_file_is_deleted_after_read(tmp_path):

    path = tmp_path / "secrets.json"
    path.write_text(json.dumps({"models": {"m1": "sk-1"}}), encoding="utf-8")

    secrets = read_secrets_file(path)

    assert secrets is not None
    assert secrets.models == {"m1": "sk-1"}
    assert not path.exists(), "读取后必须删掉，缩短文件暴露窗口"


def test_missing_file_yields_empty_secrets(tmp_path):

    secrets = read_secrets_file(tmp_path / "nope.json")
    assert secrets is not None
    assert secrets.is_empty()


def test_broken_file_does_not_break_startup(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{不是合法 JSON", encoding="utf-8")

    secrets = read_secrets_file(path)

    assert secrets is not None
    assert secrets.is_empty()
    assert not path.exists()





def test_parse_secrets_ignores_garbage():

    secrets = parse_secrets(
        {
            "models": {"ok": "sk-1", "empty": "", "bad": 123, 456: "x"},
            "mcp": {"srv": {"TOKEN": "t", "nested": {"a": 1}}, "bad": "not-a-dict"},
        }
    )
    assert secrets.models == {"ok": "sk-1"}
    assert secrets.mcp == {"srv": {"TOKEN": "t"}}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("API_KEY", True),
        ("MY_TOKEN", True),
        ("apiKey", True),
        ("DB_PASSWORD", True),
        ("AUTH_HEADER", True),
        ("LOG_LEVEL", False),
        ("TZ", False),
        ("MCP_NOTES_DIR", False),
    ],
)
def test_is_secret_key_heuristic(name, expected):
    assert is_secret_key(name) is expected





def test_apply_secrets_fills_models_and_mcp():
    config = make_config()
    apply_secrets(
        config,
        Secrets(models={"m1": "sk-new"}, mcp={"srv": {"TOKEN": "t1"}}),
    )

    assert config.models.get("m1").api_key == "sk-new"
    assert config.mcp.get("srv").env == {"LOG_LEVEL": "debug", "TOKEN": "t1"}
    
    assert config.models.get("m2").api_key == "legacy"


def test_strip_keeps_non_secret_env(tmp_path):

    paths = AppPaths(tmp_path / "data")
    store = _store(paths, manage_secrets=True)
    store.load()
    config = make_config()
    apply_secrets(config, Secrets(mcp={"srv": {"TOKEN": "t1"}}))

    store.save_mcp(config.mcp)
    store.save_models(config.models)

    raw_mcp = json.loads(paths.mcp_file.read_text(encoding="utf-8"))
    env = raw_mcp["servers"][0]["env"]
    assert "TOKEN" not in env, "密钥类环境变量不能落盘"
    assert env["LOG_LEVEL"] == "debug", "非密钥配置应当保留，便于排查"

    raw_models = json.loads(paths.models_file.read_text(encoding="utf-8"))
    assert all(spec["api_key"] == "" for spec in raw_models["models"])


def test_standalone_encrypts_keys_instead_of_plaintext(tmp_path):









    paths = AppPaths(tmp_path / "data")
    store = _store(paths)
    store.load()

    models = ModelsConfig(
        default_model="m1",
        models=[ModelSpec(id="m1", model_name="m1", adapter="openai_compat", api_key="sk-plain")],
    )
    store.save_models(models)

    raw = json.loads(paths.models_file.read_text(encoding="utf-8"))
    assert raw["models"][0]["api_key"] == "", "明文不该出现在 models.json 里"

    
    assert _store(paths).load().models.get("m1").api_key == "sk-plain"


def test_standalone_falls_back_to_plaintext_when_encryption_unavailable(tmp_path, monkeypatch):




    from my_agent.config import keystore

    monkeypatch.setattr(keystore, "is_available", lambda: False)

    paths = AppPaths(tmp_path / "data")
    store = _store(paths)
    store.load()
    store.save_models(
        ModelsConfig(
            default_model="m1",
            models=[
                ModelSpec(id="m1", model_name="m1", adapter="openai_compat", api_key="sk-plain")
            ],
        )
    )

    raw = json.loads(paths.models_file.read_text(encoding="utf-8"))
    assert raw["models"][0]["api_key"] == "sk-plain"
    
    assert not (paths.models_file.parent / "secrets.enc").exists()


def test_deleting_all_keys_removes_the_encrypted_file(tmp_path):






    paths = AppPaths(tmp_path / "data")
    store = _store(paths)
    store.load()
    secrets_path = paths.models_file.parent / "secrets.enc"

    def models_with(key: str) -> ModelsConfig:
        return ModelsConfig(
            default_model="m1",
            models=[ModelSpec(id="m1", model_name="m1", adapter="openai_compat", api_key=key)],
        )

    store.save_models(models_with("sk-1"))
    assert secrets_path.exists(), "加密文件应当被创建"

    
    store.save_models(models_with(""))

    assert not secrets_path.exists(), "删光 Key 后旧加密文件必须一起清掉"
    assert _store(paths).load().models.get("m1").api_key == ""


def test_corrupt_secrets_file_does_not_break_startup(tmp_path):





    paths = AppPaths(tmp_path / "data").ensure()
    (paths.models_file.parent / "secrets.enc").write_bytes(
        "这不是一个 DPAPI blob".encode()
    )

    models = _store(paths).load().models

    
    assert models.get("m1") is None or models.get("m1").api_key == ""


def test_in_memory_config_keeps_keys_after_save(tmp_path):




    paths = AppPaths(tmp_path / "data")
    store = _store(paths, manage_secrets=True)
    store.load()

    models = ModelsConfig(
        default_model="m1",
        models=[ModelSpec(id="m1", model_name="m1", adapter="openai_compat", api_key="sk-live")],
    )
    saved = store.save_models(models)

    assert saved.get("m1").api_key == "sk-live"
    assert store.load().models.get("m1").api_key == "sk-live"

"""密钥注入与剥离的单元测试。

这里的每一条都对应一个"会静默丢密钥 / 会静默泄露密钥"的场景：
两种失败都不会报错，只会让用户在某天发现 Key 没了，或者反过来出现在磁盘上。
"""

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


# --------------------------------------------------------------------------- #
# 读取
# --------------------------------------------------------------------------- #
def test_no_path_means_not_managed(tmp_path):
    """没传路径 = 密钥不由外部托管，调用方据此决定不剥离。

    这个区分很关键：独立运行后端（开发调试、CLI）时没有 safeStorage，
    照样剥离的话，用户填过的 Key 会在下次保存时静默消失。
    """
    assert read_secrets_file(None) is None
    assert read_secrets_file("") is None


def test_secrets_file_is_deleted_after_read(tmp_path):
    """密钥文件必须在读取后立刻删除。"""
    path = tmp_path / "secrets.json"
    path.write_text(json.dumps({"models": {"m1": "sk-1"}}), encoding="utf-8")

    secrets = read_secrets_file(path)

    assert secrets is not None
    assert secrets.models == {"m1": "sk-1"}
    assert not path.exists(), "读取后必须删掉，缩短文件暴露窗口"


def test_missing_file_yields_empty_secrets(tmp_path):
    """文件不存在时返回空密钥（而不是 None）——路径存在即表示"由外部托管"。"""
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


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #
def test_parse_secrets_ignores_garbage():
    """输入来自另一个进程，不能假设它合法。"""
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


# --------------------------------------------------------------------------- #
# 注入与剥离
# --------------------------------------------------------------------------- #
def test_apply_secrets_fills_models_and_mcp():
    config = make_config()
    apply_secrets(
        config,
        Secrets(models={"m1": "sk-new"}, mcp={"srv": {"TOKEN": "t1"}}),
    )

    assert config.models.get("m1").api_key == "sk-new"
    assert config.mcp.get("srv").env == {"LOG_LEVEL": "debug", "TOKEN": "t1"}
    # 没有对应密钥的条目保持原样
    assert config.models.get("m2").api_key == "legacy"


def test_strip_keeps_non_secret_env(tmp_path):
    """只剥离密钥类字段，普通配置留在 mcp.json 里更透明。"""
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
    """独立运行后端时，Key **不再明文**留在 models.json 里。

    这条用例原先断言的正好相反（"Key 照旧留在配置文件里"），那是当时的权衡：
    剥离会让用户"填了 Key 一保存就没了"。现在这个顾虑不成立了 ——
    Key 被加密存进同目录的 ``secrets.enc``，重新加载时能原样恢复，
    所以既没有明文暴露，也没有丢 Key。

    真正要守的不变量是**"保存后再加载，Key 还在"**（见下面那条断言）。
    """
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

    # 重新加载：Key 必须还在（这才是不允许退化的那条）
    assert _store(paths).load().models.get("m1").api_key == "sk-plain"


def test_standalone_falls_back_to_plaintext_when_encryption_unavailable(tmp_path, monkeypatch):
    """加密不可用（非 Windows）时退回明文 + 告警，**绝不能把 Key 弄丢**。

    "少一层保护"是可以接受的降级；"保存完 Key 没了"不是。
    """
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
    # 没加密成功就不该留下一个空的加密文件 —— 那会让下次加载以为"有密钥文件但读不出"
    assert not (paths.models_file.parent / "secrets.enc").exists()


def test_deleting_all_keys_removes_the_encrypted_file(tmp_path):
    """把 Key 全删掉必须**同步删掉** secrets.enc。

    否则旧文件留在盘上，下次启动 ``_apply_encrypted_keys`` 又按 id 把它塞回去 ——
    用户看到的是"我明明删掉了，重启它又回来了"，而界面不提示任何异常。
    **删除动作没能持久化，比明文落盘更难发现。**
    """
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

    # 用户把 Key 清空后保存
    store.save_models(models_with(""))

    assert not secrets_path.exists(), "删光 Key 后旧加密文件必须一起清掉"
    assert _store(paths).load().models.get("m1").api_key == ""


def test_corrupt_secrets_file_does_not_break_startup(tmp_path):
    """密钥文件损坏/换机器解不开时，应用必须照常启动。

    这时正确的表现是"Key 需要重填"，而不是"核心起不来" ——
    后者会让用户连设置界面都进不去，也就没法重填。
    """
    paths = AppPaths(tmp_path / "data").ensure()
    (paths.models_file.parent / "secrets.enc").write_bytes(
        "这不是一个 DPAPI blob".encode()
    )

    models = _store(paths).load().models

    # 能加载出来就是目的本身；模型清单为空也合法（出厂不再硬塞默认模型）
    assert models.get("m1") is None or models.get("m1").api_key == ""


def test_in_memory_config_keeps_keys_after_save(tmp_path):
    """落盘剥离不等于内存也清空。

    如果保存完连内存里的 Key 都没了，用户会看到"刚保存就认证失败"。
    """
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









from __future__ import annotations

import json

import pytest

from my_agent.config.paths import AppPaths
from my_agent.config.schemas import FeishuBot
from my_agent.feishu import config as feishu_config
from my_agent.server.runtime import AppRuntime


@pytest.fixture
def runtime(tmp_path):
    return AppRuntime(paths=AppPaths(tmp_path / "data").ensure())


def _bot(bot_id: str = "b1", name: str = "客服小助手") -> FeishuBot:
    return FeishuBot(id=bot_id, name=name, app_id="cli_test", assistant_id="soulmate")





def test_first_load_writes_an_empty_file(runtime) -> None:

    config = feishu_config.load_bots(runtime.config_store)
    assert config.bots == []
    assert runtime.paths.feishu_file.exists()


def test_bot_round_trip(runtime) -> None:
    config = feishu_config.load_bots(runtime.config_store)
    config.upsert(_bot())
    feishu_config.save_bots(runtime.config_store, config)

    again = feishu_config.load_bots(runtime.config_store)
    saved = again.get("b1")
    assert saved is not None
    assert saved.name == "客服小助手"
    assert saved.assistant_id == "soulmate"
    assert saved.group_policy == "mention", "群聊默认只回 @"


def test_manifest_never_holds_the_secret(runtime) -> None:

    config = feishu_config.load_bots(runtime.config_store)
    config.upsert(_bot())
    feishu_config.save_bots(runtime.config_store, config)
    feishu_config.set_secret(runtime.paths, "b1", "super-secret-value")

    raw = runtime.paths.feishu_file.read_text(encoding="utf-8")
    assert "super-secret-value" not in raw
    
    assert "app_secret" not in raw


def test_broken_file_falls_back_to_empty(runtime) -> None:

    runtime.paths.feishu_file.write_text("{ 这不是 JSON", encoding="utf-8")
    assert feishu_config.load_bots(runtime.config_store).bots == []


def test_remove_bot(runtime) -> None:
    config = feishu_config.load_bots(runtime.config_store)
    config.upsert(_bot())
    feishu_config.save_bots(runtime.config_store, config)
    assert config.remove("b1") is True
    assert config.remove("b1") is False





def test_secret_set_get_drop(runtime) -> None:
    assert feishu_config.get_secret(runtime.paths, "b1") == ""

    feishu_config.set_secret(runtime.paths, "b1", "abc123")
    assert feishu_config.get_secret(runtime.paths, "b1") == "abc123"

    feishu_config.set_secret(runtime.paths, "b1", "")
    assert feishu_config.get_secret(runtime.paths, "b1") == "", "传空串 = 删除该项"


def test_multiple_bots_keep_separate_secrets(runtime) -> None:

    feishu_config.set_secret(runtime.paths, "a", "secret-a")
    feishu_config.set_secret(runtime.paths, "b", "secret-b")

    assert feishu_config.get_secret(runtime.paths, "a") == "secret-a"
    assert feishu_config.get_secret(runtime.paths, "b") == "secret-b"

    feishu_config.drop_secret(runtime.paths, "a")
    assert feishu_config.get_secret(runtime.paths, "a") == ""
    assert feishu_config.get_secret(runtime.paths, "b") == "secret-b", "删 A 不该影响 B"


def test_secret_file_is_not_plain_text_when_dpapi_available(runtime) -> None:

    from my_agent.config import keystore

    if not keystore.is_available():
        pytest.skip("当前环境没有 DPAPI，凭据按降级口径明文存储")
    feishu_config.set_secret(runtime.paths, "b1", "plain-should-not-appear")
    raw = runtime.paths.feishu_secrets_file.read_bytes()
    assert b"plain-should-not-appear" not in raw


def test_plain_text_secret_file_still_readable(runtime) -> None:

    runtime.paths.feishu_secrets_file.write_text(
        json.dumps({"b1": "legacy-secret"}), encoding="utf-8"
    )
    assert feishu_config.get_secret(runtime.paths, "b1") == "legacy-secret"





def test_masked_view_has_no_secret_field() -> None:
    view = feishu_config.masked(_bot(), has_secret=True)
    assert "app_secret" not in view
    assert view["has_secret"] is True


def test_mask_secret_edges() -> None:
    assert feishu_config.mask_secret("") == ""
    assert feishu_config.mask_secret("abc") == "***"
    masked = feishu_config.mask_secret("abcdefghijklmn")
    assert masked.startswith("abc") and masked.endswith("lmn")
    assert "defghijk" not in masked

"""DPAPI 密钥存储（``config/keystore.py``）。

只在 Windows 上能真正跑加解密，所以非 Windows 环境**跳过**而不是失败 ——
降级路径本身由 ``test_secrets.py`` 里那条 monkeypatch 用例覆盖。
"""

from __future__ import annotations

import sys

import pytest

from my_agent.config import keystore

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="DPAPI 只在 Windows 上存在"
)


class TestAvailability:
    def test_available_on_windows(self):
        assert keystore.is_available() is True


class TestRoundTrip:
    def test_protect_then_unprotect(self):
        secret = "sk-abcdef1234567890"

        blob = keystore.protect(secret.encode("utf-8"))

        assert blob is not None
        # 密文里不该出现原文的任何片段 —— 这是整件事的意义所在
        assert secret.encode("utf-8") not in blob
        assert keystore.unprotect(blob) == secret.encode("utf-8")

    def test_dump_and_load_keys(self):
        keys = {"deepseek-chat": "sk-ds-1", "qwen-plus": "sk-qw-2"}

        blob = keystore.dump_keys(keys)

        assert blob is not None
        assert keystore.load_keys(blob) == keys

    def test_non_ascii_survives(self):
        """模型 id 可能是中文（用户自己起的名字），编码不能出问题。"""
        keys = {"我的模型": "sk-中文-key"}

        assert keystore.load_keys(keystore.dump_keys(keys)) == keys


class TestFailureModes:
    def test_protect_empty_returns_none(self):
        assert keystore.protect(b"") is None

    def test_unprotect_garbage_returns_none(self):
        """损坏的数据要安静地变成 None，而不是抛异常。

        它会被用在启动路径上 —— 让一个读不出来的密钥文件把核心弄崩，
        用户连设置界面都进不去，也就没法重填 Key。
        """
        assert keystore.unprotect(b"not a dpapi blob") is None

    def test_unprotect_empty_returns_none(self):
        assert keystore.unprotect(b"") is None

    def test_load_keys_of_garbage_is_empty_dict(self):
        assert keystore.load_keys(b"\x00\x01\x02rubbish") == {}

    def test_load_keys_of_non_json_plaintext_is_empty(self):
        """能解开但内容不是 JSON —— 同样收敛成空字典。"""
        blob = keystore.protect(b"this is not json")

        assert keystore.load_keys(blob) == {}

    def test_load_keys_of_json_array_is_empty(self):
        blob = keystore.protect(b'["not", "an", "object"]')

        assert keystore.load_keys(blob) == {}

    def test_load_keys_drops_non_string_values(self):
        """脏数据只丢那一项，不牵连整份密钥 —— 少一个 Key 好过全都用不了。"""
        blob = keystore.protect(b'{"ok": "sk-1", "bad": 123, "empty": ""}')

        assert keystore.load_keys(blob) == {"ok": "sk-1"}

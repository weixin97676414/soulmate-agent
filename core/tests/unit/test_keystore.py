





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
        
        assert secret.encode("utf-8") not in blob
        assert keystore.unprotect(blob) == secret.encode("utf-8")

    def test_dump_and_load_keys(self):
        keys = {"deepseek-chat": "sk-ds-1", "qwen-plus": "sk-qw-2"}

        blob = keystore.dump_keys(keys)

        assert blob is not None
        assert keystore.load_keys(blob) == keys

    def test_non_ascii_survives(self):

        keys = {"我的模型": "sk-中文-key"}

        assert keystore.load_keys(keystore.dump_keys(keys)) == keys


class TestFailureModes:
    def test_protect_empty_returns_none(self):
        assert keystore.protect(b"") is None

    def test_unprotect_garbage_returns_none(self):





        assert keystore.unprotect(b"not a dpapi blob") is None

    def test_unprotect_empty_returns_none(self):
        assert keystore.unprotect(b"") is None

    def test_load_keys_of_garbage_is_empty_dict(self):
        assert keystore.load_keys(b"\x00\x01\x02rubbish") == {}

    def test_load_keys_of_non_json_plaintext_is_empty(self):

        blob = keystore.protect(b"this is not json")

        assert keystore.load_keys(blob) == {}

    def test_load_keys_of_json_array_is_empty(self):
        blob = keystore.protect(b'["not", "an", "object"]')

        assert keystore.load_keys(blob) == {}

    def test_load_keys_drops_non_string_values(self):

        blob = keystore.protect(b'{"ok": "sk-1", "bad": 123, "empty": ""}')

        assert keystore.load_keys(blob) == {"ok": "sk-1"}

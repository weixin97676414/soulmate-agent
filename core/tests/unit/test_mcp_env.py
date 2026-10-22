









from __future__ import annotations

import os

from my_agent.mcp.client import _ENV_ALLOWLIST, _ENV_INHERIT_FLAG, build_subprocess_env


class TestEnvMinimization:


    def test_agent_token_is_stripped(self, monkeypatch):

        monkeypatch.setenv("AGENT_TOKEN", "super-secret-token")
        monkeypatch.setenv("PATH", "/usr/bin")

        env = build_subprocess_env()

        assert "AGENT_TOKEN" not in env
        assert env["PATH"] == "/usr/bin"

    def test_data_dir_is_stripped(self, monkeypatch):

        monkeypatch.setenv("AGENT_DATA_DIR", r"C:\Users\someone\AppData\Roaming\AgentDesktop")

        env = build_subprocess_env()

        assert "AGENT_DATA_DIR" not in env

    def test_unrelated_shell_exports_are_stripped(self, monkeypatch):





        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-xxx")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp-xxx")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        env = build_subprocess_env()

        for key in ("AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "OPENAI_API_KEY"):
            assert key not in env, f"{key} 泄漏到了 MCP 子进程"

    def test_essential_vars_are_preserved(self, monkeypatch):

        monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
        monkeypatch.setenv("APPDATA", r"C:\Users\x\AppData\Roaming")
        monkeypatch.setenv("HOME", "/home/x")

        env = build_subprocess_env()

        
        
        assert env["SYSTEMROOT"] == r"C:\Windows"
        assert env["APPDATA"] == r"C:\Users\x\AppData\Roaming"
        assert env["HOME"] == "/home/x"

    def test_allowlist_contains_process_essentials(self):

        for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "PATHEXT"):
            assert key in _ENV_ALLOWLIST, f"{key} 必须放行，否则子进程无法正常运行"

    def test_matching_is_case_insensitive(self, monkeypatch):







        monkeypatch.delenv("PATH", raising=False)
        monkeypatch.delenv("Path", raising=False)
        monkeypatch.setenv("Path", r"C:\Windows\System32")

        env = build_subprocess_env()

        assert any(
            key.upper() == "PATH" and value == r"C:\Windows\System32" for key, value in env.items()
        )


class TestUserEnv:


    def test_user_env_is_always_included(self, monkeypatch):





        env = build_subprocess_env({"MY_CUSTOM_TOKEN": "abc"})

        assert env["MY_CUSTOM_TOKEN"] == "abc"

    def test_user_env_overrides_allowlist(self, monkeypatch):

        monkeypatch.setenv("PATH", "/usr/bin")

        env = build_subprocess_env({"PATH": "/custom/bin"})

        assert env["PATH"] == "/custom/bin"

    def test_user_env_values_are_coerced_to_str(self, monkeypatch):

        env = build_subprocess_env({"PORT": 8080, "DEBUG": True})

        assert env["PORT"] == "8080"
        assert env["DEBUG"] == "True"

    def test_empty_user_env_is_fine(self):
        env = build_subprocess_env(None)
        assert isinstance(env, dict)
        assert env["PYTHONIOENCODING"] == "utf-8"


class TestPythonEncoding:


    def test_encoding_vars_always_set(self, monkeypatch):
        env = build_subprocess_env()

        assert env["PYTHONIOENCODING"] == "utf-8"
        assert env["PYTHONUTF8"] == "1"

    def test_encoding_vars_survive_user_env(self, monkeypatch):

        env = build_subprocess_env({"PYTHONIOENCODING": "gbk"})

        
        assert env["PYTHONIOENCODING"] == "gbk"


class TestInheritEscapeHatch:


    def test_default_is_minimized(self, monkeypatch):

        monkeypatch.delenv(_ENV_INHERIT_FLAG, raising=False)
        monkeypatch.setenv("AGENT_TOKEN", "secret")

        env = build_subprocess_env()

        assert "AGENT_TOKEN" not in env

    def test_flag_accepts_common_truthy_forms(self, monkeypatch):
        monkeypatch.setenv("AGENT_TOKEN", "secret")

        for value in ("1", "true", "TRUE", "yes", "on"):
            monkeypatch.setenv(_ENV_INHERIT_FLAG, value)
            env = build_subprocess_env()
            assert env.get("AGENT_TOKEN") == "secret", f"{value!r} 应被识别为真"

    def test_flag_off_values_keep_minimized(self, monkeypatch):
        monkeypatch.setenv("AGENT_TOKEN", "secret")

        for value in ("0", "false", "no", ""):
            monkeypatch.setenv(_ENV_INHERIT_FLAG, value)
            env = build_subprocess_env()
            assert "AGENT_TOKEN" not in env, f"{value!r} 应被识别为假"

    def test_inherit_does_not_mutate_parent_env(self, monkeypatch):

        monkeypatch.setenv(_ENV_INHERIT_FLAG, "1")
        before = dict(os.environ)

        build_subprocess_env()

        assert dict(os.environ) == before

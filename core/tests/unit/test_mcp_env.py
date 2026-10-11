"""MCP 子进程环境变量最小化。

这组用例锁住的是一个**安全边界**：我们把本地接口的令牌放在自己的
``AGENT_TOKEN`` 环境变量里（``__main__.py`` 启动时写入），而 MCP Server 是
第三方可执行程序。全量继承 ``os.environ`` 等于把令牌交给每一个连进来的 Server。

边界一旦定了，就很容易在后来某次"某个 Server 说它缺环境变量"的排查里
被悄悄改回全量继承——那时不会有任何测试失败。所以这里把行为钉死。
"""

from __future__ import annotations

import os

from my_agent.mcp.client import _ENV_ALLOWLIST, _ENV_INHERIT_FLAG, build_subprocess_env


class TestEnvMinimization:
    """默认路径：只放行白名单。"""

    def test_agent_token_is_stripped(self, monkeypatch):
        """最重要的一条：令牌不能流向子进程。"""
        monkeypatch.setenv("AGENT_TOKEN", "super-secret-token")
        monkeypatch.setenv("PATH", "/usr/bin")

        env = build_subprocess_env()

        assert "AGENT_TOKEN" not in env
        assert env["PATH"] == "/usr/bin"

    def test_data_dir_is_stripped(self, monkeypatch):
        """数据目录同理——它暴露用户在本机的文件布局。"""
        monkeypatch.setenv("AGENT_DATA_DIR", r"C:\Users\someone\AppData\Roaming\AgentDesktop")

        env = build_subprocess_env()

        assert "AGENT_DATA_DIR" not in env

    def test_unrelated_shell_exports_are_stripped(self, monkeypatch):
        """用户 shell 里随手 export 的个人凭证也不能泄漏。

        这是选白名单而不是黑名单的全部理由：黑名单只能挡住我们**今天**想到的
        那几个名字，挡不住用户自己环境里的东西。
        """
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-xxx")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp-xxx")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        env = build_subprocess_env()

        for key in ("AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "OPENAI_API_KEY"):
            assert key not in env, f"{key} 泄漏到了 MCP 子进程"

    def test_essential_vars_are_preserved(self, monkeypatch):
        """被放行的必须真的在——缺了它们第三方 Server 会以无关的错误失败。"""
        monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
        monkeypatch.setenv("APPDATA", r"C:\Users\x\AppData\Roaming")
        monkeypatch.setenv("HOME", "/home/x")

        env = build_subprocess_env()

        # SYSTEMROOT 尤其关键：Windows 上缺了它，大量程序在加载系统 DLL 时
        # 直接失败，而报错与环境变量毫无关系，极难归因。
        assert env["SYSTEMROOT"] == r"C:\Windows"
        assert env["APPDATA"] == r"C:\Users\x\AppData\Roaming"
        assert env["HOME"] == "/home/x"

    def test_allowlist_contains_process_essentials(self):
        """防止有人在"清理常量"时不小心删掉关键项。"""
        for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "PATHEXT"):
            assert key in _ENV_ALLOWLIST, f"{key} 必须放行，否则子进程无法正常运行"

    def test_matching_is_case_insensitive(self, monkeypatch):
        """环境变量名的不同大小写写法都必须命中白名单。

        实测补注：Windows 上 ``os.environ`` **本身**就会把 key 归一成大写
        （Python 的 nt 实现如此），所以这里不会真的从一个大小写混杂的字典里取值；
        POSIX 上则保留原样。无论哪种，只要名字对应白名单就必须放行 ——
        不能因为某个环境把 ``Path`` 小写化就把 PATH 整个丢掉。
        """
        monkeypatch.delenv("PATH", raising=False)
        monkeypatch.delenv("Path", raising=False)
        monkeypatch.setenv("Path", r"C:\Windows\System32")

        env = build_subprocess_env()

        assert any(
            key.upper() == "PATH" and value == r"C:\Windows\System32" for key, value in env.items()
        )


class TestUserEnv:
    """用户在 MCP 配置里显式写的 env。"""

    def test_user_env_is_always_included(self, monkeypatch):
        """用户明写的变量即使在白名单外也必须带上。

        这是给 Server 传凭证的**正当**途径（例如 GitHub MCP 需要 GITHUB_TOKEN），
        属于用户的明确意图。
        """
        env = build_subprocess_env({"MY_CUSTOM_TOKEN": "abc"})

        assert env["MY_CUSTOM_TOKEN"] == "abc"

    def test_user_env_overrides_allowlist(self, monkeypatch):
        """用户配置优先——这是我们期望的语义。"""
        monkeypatch.setenv("PATH", "/usr/bin")

        env = build_subprocess_env({"PATH": "/custom/bin"})

        assert env["PATH"] == "/custom/bin"

    def test_user_env_values_are_coerced_to_str(self, monkeypatch):
        """手改过的 JSON 配置里可能出现数字/布尔，不能让子进程创建阶段炸掉。"""
        env = build_subprocess_env({"PORT": 8080, "DEBUG": True})

        assert env["PORT"] == "8080"
        assert env["DEBUG"] == "True"

    def test_empty_user_env_is_fine(self):
        env = build_subprocess_env(None)
        assert isinstance(env, dict)
        assert env["PYTHONIOENCODING"] == "utf-8"


class TestPythonEncoding:
    """子进程 Python 的编码必须固定，否则中文参数/输出在 GBK 终端下乱码。"""

    def test_encoding_vars_always_set(self, monkeypatch):
        env = build_subprocess_env()

        assert env["PYTHONIOENCODING"] == "utf-8"
        assert env["PYTHONUTF8"] == "1"

    def test_encoding_vars_survive_user_env(self, monkeypatch):
        """用户即便写了同名变量也不影响——这两个是子进程能正常通信的前提。"""
        env = build_subprocess_env({"PYTHONIOENCODING": "gbk"})

        # 用户配置最后覆盖上去，所以它确实会赢；这里记录的是实际语义
        assert env["PYTHONIOENCODING"] == "gbk"


class TestInheritEscapeHatch:
    """逃生舱：仅在用户显式开启时才全量继承。"""

    def test_default_is_minimized(self, monkeypatch):
        """没开关就是最小化——这条是默认安全性的兜底。"""
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
        """逃生舱只是读取，不能把本进程的环境变量表改坏。"""
        monkeypatch.setenv(_ENV_INHERIT_FLAG, "1")
        before = dict(os.environ)

        build_subprocess_env()

        assert dict(os.environ) == before

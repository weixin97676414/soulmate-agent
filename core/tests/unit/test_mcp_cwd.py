"""MCP `cwd` 的两道校验：形状 + 范围。

``cwd`` 决定第三方 Server 在**哪个目录**里读写文件。配错了它不会报错，
只会在别的地方动文件 —— 这类问题要等用户发现"我的文件被动过"才暴露。

## 为什么"范围"校验要分开关

只有用户**确实配置过** ``allowed_dirs`` 时才启用。没配的人本来就没表达过
"只许在这些目录"，凭空加限制会让原本能跑的 MCP 服务突然起不来 ——
那是一次静默的行为变更，用户只会觉得"升级之后 MCP 坏了"。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from my_agent.config.schemas import McpServerConfig
from my_agent.mcp.transports import validate_cwd
from my_agent.security.paths import PathPolicy


def server(cwd: str | None) -> McpServerConfig:
    return McpServerConfig(name="t", command="python", cwd=cwd)


class TestShape:
    def test_empty_means_no_cwd(self):
        assert validate_cwd(server(None)) is None
        assert validate_cwd(server("   ")) is None

    def test_relative_path_is_rejected(self):
        """相对路径的基准是客户端进程的当前目录，开发态与安装后完全不同。"""
        with pytest.raises(ValueError, match="绝对路径"):
            validate_cwd(server("some/relative/dir"))

    def test_missing_path_is_rejected(self, tmp_path: Path):
        with pytest.raises(ValueError, match="不存在"):
            validate_cwd(server(str(tmp_path / "nope")))

    def test_file_is_rejected(self, tmp_path: Path):
        target = tmp_path / "a.txt"
        target.write_text("x", encoding="utf-8")

        with pytest.raises(ValueError, match="不是目录"):
            validate_cwd(server(str(target)))

    def test_valid_dir_passes(self, tmp_path: Path):
        assert validate_cwd(server(str(tmp_path))) == str(tmp_path)


class TestRange:
    def test_no_policy_means_no_range_check(self, tmp_path: Path):
        """没传策略就不做范围校验 —— 保持既有行为不变。"""
        outside = tmp_path / "anywhere"
        outside.mkdir()

        assert validate_cwd(server(str(outside)), None) == str(outside)

    def test_unrestricted_policy_skips_range_check(self, tmp_path: Path):
        """用户没配白名单（``is_restricted=False``）时同样不拦。

        这条是防"静默行为变更"的：给所有用户凭空加限制，
        表现就是升级后 MCP 服务集体起不来。
        """
        outside = tmp_path / "anywhere"
        outside.mkdir()
        policy = PathPolicy([])  # 空 = 未配置

        assert policy.is_restricted is False
        assert validate_cwd(server(str(outside)), policy) == str(outside)

    def test_allowed_dir_passes(self, tmp_path: Path):
        allowed = tmp_path / "work"
        allowed.mkdir()
        policy = PathPolicy([str(allowed)])

        assert validate_cwd(server(str(allowed)), policy) == str(allowed)

    def test_subdir_of_allowed_passes(self, tmp_path: Path):
        """子目录要放行 —— 只允许恰好等于白名单那一层太不实用。"""
        allowed = tmp_path / "work"
        nested = allowed / "sub" / "deep"
        nested.mkdir(parents=True)
        policy = PathPolicy([str(allowed)])

        assert validate_cwd(server(str(nested)), policy) == str(nested)

    def test_outside_dir_is_rejected_with_actionable_message(self, tmp_path: Path):
        allowed = tmp_path / "work"
        allowed.mkdir()
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        policy = PathPolicy([str(allowed)])

        with pytest.raises(ValueError) as excinfo:
            validate_cwd(server(str(outside)), policy)

        message = str(excinfo.value)
        # 报错必须**告诉用户怎么改**，否则只是换了个地方卡住他
        assert "白名单" in message
        assert "允许目录" in message
        # 并列出当前白名单，方便比对
        assert str(allowed) in message

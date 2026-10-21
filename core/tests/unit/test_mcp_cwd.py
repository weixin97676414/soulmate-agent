











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

        outside = tmp_path / "anywhere"
        outside.mkdir()

        assert validate_cwd(server(str(outside)), None) == str(outside)

    def test_unrestricted_policy_skips_range_check(self, tmp_path: Path):





        outside = tmp_path / "anywhere"
        outside.mkdir()
        policy = PathPolicy([])  

        assert policy.is_restricted is False
        assert validate_cwd(server(str(outside)), policy) == str(outside)

    def test_allowed_dir_passes(self, tmp_path: Path):
        allowed = tmp_path / "work"
        allowed.mkdir()
        policy = PathPolicy([str(allowed)])

        assert validate_cwd(server(str(allowed)), policy) == str(allowed)

    def test_subdir_of_allowed_passes(self, tmp_path: Path):

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
        
        assert "白名单" in message
        assert "允许目录" in message
        
        assert str(allowed) in message

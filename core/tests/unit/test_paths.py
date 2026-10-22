





from __future__ import annotations

from pathlib import Path

import pytest

from my_agent.errors import PathNotAllowedError
from my_agent.security.paths import PathPolicy


@pytest.fixture
def allowed_dir(tmp_path) -> Path:
    directory = tmp_path / "允许目录"
    directory.mkdir()
    return directory


@pytest.fixture
def other_dir(tmp_path) -> Path:
    directory = tmp_path / "其他目录"
    directory.mkdir()
    return directory


def test_empty_whitelist_means_unrestricted(tmp_path):

    policy = PathPolicy([])
    assert policy.is_restricted is False
    assert policy.check(tmp_path / "任意文件.txt").name == "任意文件.txt"


def test_allowed_path_passes(allowed_dir):
    policy = PathPolicy([str(allowed_dir)])
    assert policy.is_restricted is True
    target = allowed_dir / "报表.xlsx"
    assert policy.check(str(target)) == target.resolve()


def test_subdirectory_of_allowed_passes(allowed_dir):
    policy = PathPolicy([str(allowed_dir)])
    nested = allowed_dir / "子目录" / "再深一层" / "a.txt"
    assert policy.check(str(nested)) == nested.resolve()


def test_outside_path_is_rejected(allowed_dir, other_dir):
    policy = PathPolicy([str(allowed_dir)])
    with pytest.raises(PathNotAllowedError) as exc:
        policy.check(str(other_dir / "secret.txt"))
    message = str(exc.value)
    assert "白名单之外" in message
    
    assert "设置" in message


def test_prefix_trap_is_rejected(tmp_path):




    allowed = tmp_path / "allowed"
    evil = tmp_path / "allowed-evil"
    allowed.mkdir()
    evil.mkdir()

    policy = PathPolicy([str(allowed)])
    assert policy.check(allowed / "ok.txt").name == "ok.txt"
    with pytest.raises(PathNotAllowedError):
        policy.check(evil / "bad.txt")


def test_parent_traversal_is_rejected(allowed_dir, other_dir):
    policy = PathPolicy([str(allowed_dir)])
    sneaky = allowed_dir / ".." / other_dir.name / "escape.txt"
    with pytest.raises(PathNotAllowedError):
        policy.check(str(sneaky))


def test_always_allowed_dirs_bypass_whitelist(tmp_path, other_dir):

    workspace = other_dir / "workspace"
    workspace.mkdir()
    policy = PathPolicy([str(tmp_path / "somewhere")], always_allowed=[workspace])
    assert policy.check(workspace / "upload.csv") == (workspace / "upload.csv").resolve()


def test_multiple_allowed_dirs(allowed_dir, other_dir):
    policy = PathPolicy([str(allowed_dir), str(other_dir)])
    assert policy.check(allowed_dir / "a").name == "a"
    assert policy.check(other_dir / "b").name == "b"


def test_empty_path_is_rejected():
    policy = PathPolicy([])
    with pytest.raises(PathNotAllowedError):
        policy.check("")


def test_is_allowed_helper(allowed_dir, other_dir):
    policy = PathPolicy([str(allowed_dir)])
    assert policy.is_allowed(allowed_dir / "a.txt") is True
    assert policy.is_allowed(other_dir / "b.txt") is False


def test_env_var_is_expanded(tmp_path, monkeypatch):
    target = tmp_path / "expanded"
    target.mkdir()
    monkeypatch.setenv("AGENT_TEST_DIR", str(target))
    policy = PathPolicy(["$AGENT_TEST_DIR"])
    assert policy.check(target / "x.txt").name == "x.txt"


def test_describe_and_allowed_dirs(allowed_dir):
    policy = PathPolicy([str(allowed_dir)])
    assert str(allowed_dir) in policy.describe()
    assert policy.allowed_dirs == [allowed_dir.resolve()]


def test_read_write_error_wording(allowed_dir, other_dir):
    policy = PathPolicy([str(allowed_dir)])
    with pytest.raises(PathNotAllowedError) as read_exc:
        policy.check(str(other_dir / "a.txt"), mode="read")
    assert "读取" in str(read_exc.value)

    with pytest.raises(PathNotAllowedError) as write_exc:
        policy.check(str(other_dir / "a.txt"), mode="write")
    assert "写入" in str(write_exc.value)

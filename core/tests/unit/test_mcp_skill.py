"""MCP 工具包装的单元测试：权限推断与命名空间。

这两件事直接决定安全性与可用性：
权限推断错了 = 高危操作被静默放行；命名空间错了 = 工具互相覆盖或模型网关拒收。
"""

from __future__ import annotations

import pytest

from my_agent.mcp.skill import (
    _tokens,
    infer_permission_level,
    namespaced_name,
)
from my_agent.mcp.types import McpToolInfo


# --------------------------------------------------------------------------- #
# 词元切分
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("read_file", {"read", "file"}),
        ("readFile", {"read", "file", "readfile"}),
        ("READ_FILE", {"read", "file"}),
        ("read-file-name", {"read", "file", "name"}),
        ("HTTPGet", {"http", "get", "httpget"}),
        ("listNotes", {"list", "notes", "listnotes"}),
    ],
)
def test_token_splitting(name, expected):
    assert expected <= _tokens(name)


def test_prune_is_not_matched_as_run():
    """``prune`` 里含有 ``run`` 子串，但按词元切分后不应命中写动词。

    如果用子串匹配，一个只读的清理工具会被误判成需要确认——
    反过来 ``format`` 这种也可能被漏判。这类误判很难靠肉眼发现。
    """
    tokens = _tokens("prune_cache")
    assert "run" not in tokens
    assert "prune" in tokens
    # 推断不出来 → 保守的 confirm，而不是错误地判成 safe
    assert infer_permission_level(McpToolInfo(name="prune_cache")) == "confirm"


# --------------------------------------------------------------------------- #
# 权限推断
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("tool_name", "expected"),
    [
        ("read_file", "safe"),
        ("list_notes", "safe"),
        ("get_weather", "safe"),
        ("search_repos", "safe"),
        ("query_database", "safe"),
        ("find_user", "safe"),
        ("listNotes", "safe"),
        ("write_file", "confirm"),
        ("create_issue", "confirm"),
        ("delete_note", "confirm"),
        ("remove_item", "confirm"),
        ("send_message", "confirm"),
        ("execute_command", "confirm"),
        ("upload_document", "confirm"),
        ("move_file", "confirm"),
    ],
)
def test_infer_from_name(tool_name, expected):
    assert infer_permission_level(McpToolInfo(name=tool_name)) == expected


def test_unknown_tool_defaults_to_confirm():
    """判断不出来时必须保守：第三方 Server 的工具我们一无所知。"""
    assert infer_permission_level(McpToolInfo(name="foo")) == "confirm"
    assert infer_permission_level(McpToolInfo(name="bar_baz")) == "confirm"


def test_mcp_annotations_win_over_name_heuristics():
    """Server 自己声明的注解是最可靠的依据，应优先于名字猜测。"""
    # 名字看着像写操作，但 Server 明确标了只读
    assert (
        infer_permission_level(McpToolInfo(name="update_cache", read_only=True)) == "safe"
    )
    # 名字看着无害，但 Server 明确标了破坏性
    assert (
        infer_permission_level(McpToolInfo(name="list_notes", destructive=True)) == "confirm"
    )


def test_destructive_beats_read_only_when_both_set():
    """两个注解同时为真属于 Server 自相矛盾，按更危险的来。"""
    assert (
        infer_permission_level(
            McpToolInfo(name="weird", read_only=True, destructive=True)
        )
        == "confirm"
    )


def test_write_token_wins_over_read_token_in_same_name():
    """``read_and_delete`` 同时命中读与写，必须判成写。"""
    assert infer_permission_level(McpToolInfo(name="read_and_delete")) == "confirm"


# --------------------------------------------------------------------------- #
# 命名空间
# --------------------------------------------------------------------------- #
def test_namespaced_name_basic():
    assert namespaced_name("filesystem", "read_file") == "filesystem__read_file"


def test_namespaced_name_avoids_collision():
    """单下划线无法区分这两组，双下划线可以。"""
    first = namespaced_name("a_b", "c")
    second = namespaced_name("a", "b_c")
    assert first != second


def test_namespaced_name_sanitizes_illegal_chars():
    """工具名里出现空格、点号等字符时必须替换成下划线。

    OpenAI 的函数名规范是 `^[a-zA-Z0-9_-]{1,64}$`，不合规的名称会被网关直接拒绝。
    """
    name = namespaced_name("my server", "read.file (v2)")
    assert name == "my_server__read_file__v2_"
    assert all(ch.isalnum() or ch in "_-" for ch in name)


def test_namespaced_name_truncates_without_collision():
    long_tool = "x" * 120
    first = namespaced_name("server", long_tool)
    second = namespaced_name("server", long_tool + "y")

    assert len(first) <= 64
    assert len(second) <= 64
    # 截断后仍必须唯一，否则两个工具会互相覆盖
    assert first != second
    assert all(ch.isalnum() or ch in "_-" for ch in first)


def test_namespaced_name_is_deterministic():
    assert namespaced_name("s", "t") == namespaced_name("s", "t")


# --------------------------------------------------------------------------- #
# 工具信息归一化
# --------------------------------------------------------------------------- #
def test_tool_info_to_dict_includes_schema():
    tool = McpToolInfo(
        name="read_file",
        description="读取文件",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        read_only=True,
    )
    payload = tool.to_dict()
    assert payload["name"] == "read_file"
    assert payload["read_only"] is True
    assert payload["input_schema"]["properties"]["path"]["type"] == "string"

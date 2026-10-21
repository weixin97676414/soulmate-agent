





from __future__ import annotations

import pytest

from my_agent.mcp.skill import (
    _tokens,
    infer_permission_level,
    namespaced_name,
)
from my_agent.mcp.types import McpToolInfo





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





    tokens = _tokens("prune_cache")
    assert "run" not in tokens
    assert "prune" in tokens
    
    assert infer_permission_level(McpToolInfo(name="prune_cache")) == "confirm"





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

    assert infer_permission_level(McpToolInfo(name="foo")) == "confirm"
    assert infer_permission_level(McpToolInfo(name="bar_baz")) == "confirm"


def test_mcp_annotations_win_over_name_heuristics():

    
    assert (
        infer_permission_level(McpToolInfo(name="update_cache", read_only=True)) == "safe"
    )
    
    assert (
        infer_permission_level(McpToolInfo(name="list_notes", destructive=True)) == "confirm"
    )


def test_destructive_beats_read_only_when_both_set():

    assert (
        infer_permission_level(
            McpToolInfo(name="weird", read_only=True, destructive=True)
        )
        == "confirm"
    )


def test_write_token_wins_over_read_token_in_same_name():

    assert infer_permission_level(McpToolInfo(name="read_and_delete")) == "confirm"





def test_namespaced_name_basic():
    assert namespaced_name("filesystem", "read_file") == "filesystem__read_file"


def test_namespaced_name_avoids_collision():

    first = namespaced_name("a_b", "c")
    second = namespaced_name("a", "b_c")
    assert first != second


def test_namespaced_name_sanitizes_illegal_chars():




    name = namespaced_name("my server", "read.file (v2)")
    assert name == "my_server__read_file__v2_"
    assert all(ch.isalnum() or ch in "_-" for ch in name)


def test_namespaced_name_truncates_without_collision():
    long_tool = "x" * 120
    first = namespaced_name("server", long_tool)
    second = namespaced_name("server", long_tool + "y")

    assert len(first) <= 64
    assert len(second) <= 64
    
    assert first != second
    assert all(ch.isalnum() or ch in "_-" for ch in first)


def test_namespaced_name_is_deterministic():
    assert namespaced_name("s", "t") == namespaced_name("s", "t")





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

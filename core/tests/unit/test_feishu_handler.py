









from __future__ import annotations

import pytest

from my_agent.feishu.client import parse_text, strip_mentions
from my_agent.feishu.handler import FeishuHandler, _mentions_bot
from my_agent.storage.db import Database
from my_agent.storage.sessions import SessionRecord, SessionRepository





def test_mentions_bot_matches_open_id() -> None:
    mentions = [
        {"key": "@_user_1", "id": {"open_id": "ou_other"}, "name": "张三"},
        {"key": "@_user_2", "id": {"open_id": "ou_bot"}, "name": "小助手"},
    ]
    assert _mentions_bot(mentions, "ou_bot") is True
    assert _mentions_bot(mentions, "ou_nobody") is False


def test_mentions_bot_tolerates_garbage() -> None:

    assert _mentions_bot(None, "ou_bot") is False
    assert _mentions_bot([], "ou_bot") is False
    assert _mentions_bot([{"id": None}], "ou_bot") is False
    assert _mentions_bot(["不是字典"], "ou_bot") is False





def test_strip_mentions_restores_real_names() -> None:

    text = "@_user_1 帮我看看这段代码 @_user_2"
    mentions = [
        {"key": "@_user_1", "id": {"open_id": "ou_a"}, "name": "张三"},
        {"key": "@_user_2", "id": {"open_id": "ou_b"}, "name": "李四"},
    ]
    assert strip_mentions(text, mentions) == "@张三 帮我看看这段代码 @李四"


def test_parse_text_handles_non_text_and_broken_json() -> None:
    assert parse_text('{"text": "你好"}') == "你好"
    assert parse_text("") == ""
    assert parse_text("{这不是 JSON") == ""
    
    assert parse_text('{"image_key": "img_v2_xxx"}') == ""





def test_remember_rejects_repeats() -> None:
    handler = FeishuHandler(runtime=None)  
    assert handler._remember(["evt-1", "msg-1"]) is True
    assert handler._remember(["evt-1", "msg-1"]) is False, "同一个事件重投必须被挡"


def test_remember_dedups_by_any_key() -> None:

    handler = FeishuHandler(runtime=None)  
    assert handler._remember(["evt-old", "msg-1"]) is True
    assert handler._remember(["evt-new", "msg-1"]) is False


def test_remember_caps_memory() -> None:

    from my_agent.feishu.handler import _SEEN_LIMIT

    handler = FeishuHandler(runtime=None)  
    for index in range(_SEEN_LIMIT + 50):
        handler._remember([f"msg-{index}"])
    assert len(handler._seen) == _SEEN_LIMIT


def test_remember_ignores_empty_keys() -> None:

    handler = FeishuHandler(runtime=None)  
    assert handler._remember(["", None]) is True  





@pytest.fixture
async def repo(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield SessionRepository(database)
    await database.close()


@pytest.mark.asyncio
async def test_find_by_external_matches_source_and_chat(repo) -> None:
    await repo.save_session(
        SessionRecord(
            id="s1",
            title="飞书群 A",
            assistant_id="soulmate",
            source="feishu",
            external_id="oc_aaa",
        )
    )
    hit = await repo.find_by_external("feishu", "oc_aaa", "soulmate")
    assert hit is not None and hit.id == "s1"

    
    assert await repo.find_by_external("feishu", "oc_bbb", "soulmate") is None
    assert await repo.find_by_external("local", "oc_aaa", "soulmate") is None


@pytest.mark.asyncio
async def test_find_by_external_respects_assistant(repo) -> None:

    await repo.save_session(
        SessionRecord(
            id="s1",
            title="飞书群 A",
            assistant_id="soulmate",
            source="feishu",
            external_id="oc_aaa",
        )
    )
    assert await repo.find_by_external("feishu", "oc_aaa", "soulmate") is not None
    assert await repo.find_by_external("feishu", "oc_aaa", "LoveBuddy") is None


@pytest.mark.asyncio
async def test_session_source_defaults_to_local(repo) -> None:

    await repo.save_session(SessionRecord(id="s2", title="本地对话"))
    record = await repo.get_session("s2")
    assert record is not None
    assert record.source == "local"
    assert record.external_id == ""

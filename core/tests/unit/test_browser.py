











from __future__ import annotations

import sys

import pytest

from my_agent.browser import session as browser_session
from my_agent.errors import SkillExecutionError
from my_agent.skill.builtin.browser import (
    BrowserActSkill,
    BrowserReadSkill,
    BrowserScreenshotSkill,
    BrowserSnapshotSkill,
    BrowserTabsSkill,
)





def test_read_only_browser_tools_are_safe() -> None:
    assert BrowserReadSkill.meta.permission_level == "safe"
    assert BrowserSnapshotSkill.meta.permission_level == "safe"
    assert BrowserScreenshotSkill.meta.permission_level == "safe"
    assert BrowserTabsSkill.meta.permission_level == "safe"


def test_mutating_browser_act_needs_confirm() -> None:
    assert BrowserActSkill.meta.permission_level == "confirm"





class _FakePage:
    def __init__(self, url: str, title: str) -> None:
        self.url = url
        self._title = title

    async def title(self) -> str:
        return self._title


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "title"),
    [
        ("https://example.com/login", ""),
        ("https://example.com/x", "请完成登录"),
        ("https://example.com/x", "Verify your identity"),
        ("https://example.com/x", "请输入验证码"),
        ("https://example.com/x", "Two-factor authentication"),
    ],
)
async def test_blocker_is_detected(url: str, title: str) -> None:

    reason = await browser_session.BrowserSession.detect_blocker(_FakePage(url, title))

    assert reason is not None
    assert "人工" in reason


@pytest.mark.asyncio
async def test_plain_page_is_not_blocked() -> None:


    reason = await browser_session.BrowserSession.detect_blocker(
        _FakePage("https://example.com/docs", "使用文档")
    )

    assert reason is None





def test_detect_channel_returns_a_known_channel_or_none() -> None:

    channel = browser_session._detect_channel()

    assert channel in (None, "msedge", "chrome")


def test_frozen_shim_only_acts_when_frozen(monkeypatch) -> None:

    monkeypatch.setattr(sys, "frozen", False, raising=False)
    before = dict(sys.modules)

    browser_session._apply_frozen_shim()

    
    assert "playwright" not in sys.modules or "playwright" in before


class _DeadContext:


    @property
    def pages(self) -> list:
        raise RuntimeError("Target page, context or browser has been closed")


@pytest.mark.asyncio
async def test_ensure_discards_dead_context(monkeypatch, tmp_path) -> None:







    session = browser_session.BrowserSession()
    session._context = _DeadContext()
    monkeypatch.setattr(browser_session, "_detect_channel", lambda: None)

    with pytest.raises(SkillExecutionError):
        await session.ensure(tmp_path / "profile")

    assert session._context is None, "失效的 context 必须被丢弃，不能当成可用"


def test_looks_closed_recognises_closed_errors() -> None:

    assert browser_session.BrowserSession.looks_closed(
        RuntimeError("Target page, context or browser has been closed")
    )
    assert browser_session.BrowserSession.looks_closed(
        RuntimeError("Browser has been closed")
    )
    assert not browser_session.BrowserSession.looks_closed(
        RuntimeError("net::ERR_NAME_NOT_RESOLVED")
    )


def test_detect_channel_paths_are_absolute() -> None:





    for candidate in browser_session._WIN_EDGE_PATHS + browser_session._WIN_CHROME_PATHS:
        assert candidate.is_absolute()
    for candidate in browser_session._MAC_EDGE_PATHS + browser_session._MAC_CHROME_PATHS:
        assert candidate.as_posix().startswith("/")


def test_browser_candidates_follow_platform(monkeypatch) -> None:

    monkeypatch.setattr(browser_session.sys, "platform", "darwin")
    assert browser_session._browser_candidates() == (
        browser_session._MAC_EDGE_PATHS,
        browser_session._MAC_CHROME_PATHS,
    )

    monkeypatch.setattr(browser_session.sys, "platform", "win32")
    assert browser_session._browser_candidates() == (
        browser_session._WIN_EDGE_PATHS,
        browser_session._WIN_CHROME_PATHS,
    )

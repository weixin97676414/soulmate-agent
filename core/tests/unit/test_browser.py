"""浏览器自动化技能的回归测试。

这里**不启动真实浏览器**（太重、且依赖本机装了 Edge/Chrome，不适合单测）。
真实拉起浏览器的冒烟验证在 venv 与冻结产物里分别做过。这组测试守的是
**不依赖网络、不依赖浏览器**的那部分：

1. 权限分级（读 safe / 会改状态 confirm）；
2. 登录/验证码这类"需要人工"的环节要被识别出来（对应 openclaw 范式里
   "停下来告知用户，不要死循环"）；
3. 系统浏览器的探测逻辑与冻结 shim 的基本行为。
"""

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


# --------------------------------------------------------------------------- #
# 权限分级
# --------------------------------------------------------------------------- #
def test_read_only_browser_tools_are_safe() -> None:
    assert BrowserReadSkill.meta.permission_level == "safe"
    assert BrowserSnapshotSkill.meta.permission_level == "safe"
    assert BrowserScreenshotSkill.meta.permission_level == "safe"
    assert BrowserTabsSkill.meta.permission_level == "safe"


def test_mutating_browser_act_needs_confirm() -> None:
    assert BrowserActSkill.meta.permission_level == "confirm"


# --------------------------------------------------------------------------- #
# 阻塞检测（登录 / 验证码 / 2FA）
# --------------------------------------------------------------------------- #
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
    """登录/验证码/2FA 页面要被识别出来，让模型停下来说明。"""
    reason = await browser_session.BrowserSession.detect_blocker(_FakePage(url, title))

    assert reason is not None
    assert "人工" in reason


@pytest.mark.asyncio
async def test_plain_page_is_not_blocked() -> None:
    """普通页面**不要**误报 —— 宁可漏报（用户再手动说一句），
    也不要让模型该做不做。"""
    reason = await browser_session.BrowserSession.detect_blocker(
        _FakePage("https://example.com/docs", "使用文档")
    )

    assert reason is None


# --------------------------------------------------------------------------- #
# 系统浏览器探测与冻结 shim
# --------------------------------------------------------------------------- #
def test_detect_channel_returns_a_known_channel_or_none() -> None:
    """探测结果只可能是已知值（msedge/chrome）或 None（这台机器没装）。"""
    channel = browser_session._detect_channel()

    assert channel in (None, "msedge", "chrome")


def test_frozen_shim_only_acts_when_frozen(monkeypatch) -> None:
    """非冻结环境不做任何事（不 import playwright、不改环境变量）。"""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    before = dict(sys.modules)

    browser_session._apply_frozen_shim()

    # 非冻结路径不该引入 playwright 模块
    assert "playwright" not in sys.modules or "playwright" in before


class _DeadContext:
    """模拟"用户已经把浏览器关掉"的那个 context：访问 pages 就抛错。"""

    @property
    def pages(self) -> list:
        raise RuntimeError("Target page, context or browser has been closed")


@pytest.mark.asyncio
async def test_ensure_discards_dead_context(monkeypatch, tmp_path) -> None:
    """**用户报的那个问题**：浏览器被关掉后，AI 必须能自己重新拉起来。

    这里不真的启动浏览器（太重），而是让"渠道探测"失败来中断启动流程 ——
    关键在于证明它**没有**把那个已经失效的 context 当成可用对象返回。
    以前 `ensure()` 只判断 `_context is not None`，死对象会被直接返回，
    于是用户关掉浏览器之后所有操作都在死对象上失败。
    """
    session = browser_session.BrowserSession()
    session._context = _DeadContext()
    monkeypatch.setattr(browser_session, "_detect_channel", lambda: None)

    with pytest.raises(SkillExecutionError):
        await session.ensure(tmp_path / "profile")

    assert session._context is None, "失效的 context 必须被丢弃，不能当成可用"


def test_looks_closed_recognises_closed_errors() -> None:
    """识别"目标已关闭"类错误（自愈重试的判据）。"""
    assert browser_session.BrowserSession.looks_closed(
        RuntimeError("Target page, context or browser has been closed")
    )
    assert browser_session.BrowserSession.looks_closed(
        RuntimeError("Browser has been closed")
    )
    assert not browser_session.BrowserSession.looks_closed(
        RuntimeError("net::ERR_NAME_NOT_RESOLVED")
    )


def test_detect_channel_paths_are_windows_absolute() -> None:
    """探测用到的浏览器路径必须是绝对路径，否则 ``exists()`` 永远 False。"""
    for candidate in browser_session._EDGE_PATHS + browser_session._CHROME_PATHS:
        assert candidate.is_absolute()

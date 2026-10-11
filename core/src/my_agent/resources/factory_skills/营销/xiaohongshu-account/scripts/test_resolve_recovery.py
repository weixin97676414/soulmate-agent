# -*- coding: utf-8 -*-
"""xhs_resolve.py 恢复路径的合成测试（不联网，用 FakePage 模拟）。

覆盖四条关键路径：
1. 搜索页 goto 连续超时 -> 返回 search_timeout，不抛异常
2. goto 超时一次后刷新成功 -> 正常返回候选
3. 搜索页无用户卡片 -> 返回 search_empty
4. 笔记页反查作者 -> 返回 note_author

运行：python test_resolve_recovery.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xhs_resolve import Target, _author_from_note, _search_user  # noqa: E402


class FakeAnchor:
    def __init__(self, href: str, name: str = ""):
        self._href = href
        self._name = name

    def get_attribute(self, key: str):
        return self._href if key == "href" else None

    def inner_text(self):
        return self._name


class FakeRoute:
    class _Req:
        resource_type = "image"

    request = _Req()

    def __init__(self):
        self.aborted = False

    def abort(self):
        self.aborted = True

    def continue_(self):
        pass


class FakePage:
    """最小可用的 Playwright Page 替身。"""

    def __init__(self, script: list[str], anchors: dict[str, list] | None = None):
        # script: 每次 goto 的行为，"timeout" 或 "ok"
        self.script = list(script)
        self.anchors = anchors or {}
        self.goto_calls = 0
        self.reload_calls = 0
        self.routes = []

    def route(self, pattern, handler):
        self.routes.append((pattern, handler))

    def unroute(self, pattern, handler):
        self.routes = [(p, h) for p, h in self.routes if h is not handler]

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls += 1
        behavior = self.script.pop(0) if self.script else "ok"
        if behavior == "timeout":
            raise TimeoutError(f"goto {timeout}ms exceeded")
        self._last_url = url
        return None

    def reload(self, wait_until=None, timeout=None):
        self.reload_calls += 1
        self._last_url = getattr(self, "_last_url", "")
        return None

    def wait_for_timeout(self, ms):
        return None

    def wait_for_selector(self, selector, timeout=None):
        # 有锚点就模拟渲染成功，没有就抛超时
        if self.query_selector_all(selector):
            return True
        raise TimeoutError("selector not found")

    def query_selector_all(self, selector):
        return self.anchors.get(selector, [])

    def content(self):
        return "<html></html>"


# xhs_browser 依赖真实 Playwright，测试里打个桩
import types  # noqa: E402

fake_xhs_browser = types.ModuleType("xhs_browser")
fake_xhs_browser.human_scroll = lambda page, times=1, **kw: None
fake_xhs_browser.is_password_protected = lambda page: False
sys.modules.setdefault("xhs_browser", fake_xhs_browser)

PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


PROFILE_HREF = ("https://www.xiaohongshu.com/user/profile/"
                "5f8a1b2c3d4e5f6a7b8c9d0e?xsec_token=TOK123")


def t1_search_timeout_no_exception():
    page = FakePage(["timeout", "timeout"])
    target = _search_user(page, "某品牌官方", timeout_ms=100, retries=1)
    check("连续超时返回 search_timeout", target.resolved_by == "search_timeout",
          f"got {target.resolved_by}")
    check("连续超时不产生 uid", not target.ok)


def t2_retry_after_refresh():
    page = FakePage(
        ["timeout", "ok"],
        anchors={"a[href*='/user/profile/']": [FakeAnchor(PROFILE_HREF, "某品牌官方")]},
    )
    target = _search_user(page, "某品牌官方", timeout_ms=100, retries=1)
    check("刷新重试后解析成功", target.ok and target.uid == "5f8a1b2c3d4e5f6a7b8c9d0e",
          f"got {target.resolved_by} uid={target.uid}")
    check("xsec_token 已带出", target.xsec_token == "TOK123", f"got {target.xsec_token!r}")
    check("刷新动作确实发生", page.reload_calls >= 1)


def t3_search_empty():
    page = FakePage(["ok", "ok"])  # 页面能开，但永远没有用户卡片
    target = _search_user(page, "不存在的昵称xyz", timeout_ms=100, retries=1)
    check("无结果返回 search_empty", target.resolved_by == "search_empty",
          f"got {target.resolved_by}")


def t4_author_from_note():
    page = FakePage(
        ["ok"],
        anchors={"a[href*='/user/profile/']": [FakeAnchor(PROFILE_HREF, "作者昵称")]},
    )
    target = _author_from_note(page, "https://www.xiaohongshu.com/explore/abc123")
    check("笔记页反查作者成功", target.ok and target.resolved_by == "note_author",
          f"got {target.resolved_by}")
    check("反查出昵称", target.nickname == "作者昵称")


def t5_note_timeout():
    page = FakePage(["timeout"])
    target = _author_from_note(page, "https://www.xiaohongshu.com/explore/abc123")
    check("笔记页超时返回 note_timeout", target.resolved_by == "note_timeout",
          f"got {target.resolved_by}")


def t6_route_block_and_cleanup():
    page = FakePage(["ok"], anchors={"a[href*='/user/profile/']": [FakeAnchor(PROFILE_HREF)]})
    _search_user(page, "x", timeout_ms=100, retries=0)
    check("资源屏蔽已注册且用完即卸", len(page.routes) == 0,
          f"routes left: {len(page.routes)}")


if __name__ == "__main__":
    for fn in (t1_search_timeout_no_exception, t2_retry_after_refresh, t3_search_empty,
               t4_author_from_note, t5_note_timeout, t6_route_block_and_cleanup):
        print(f"--- {fn.__name__}")
        try:
            fn()
        except Exception as err:  # noqa: BLE001
            FAIL += 1
            print(f"  FAIL  用例自身异常: {err}")
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)

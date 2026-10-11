"""官网搭子库"页面解析"的单测（2026-09-28 页面改版后重写）。

## 为什么必须有这个文件

`buddy_library_list` 在官网改版后返回过 ``count: 0``——根因是旧解析只认 .json
链接，而页面只剩 .zip。这条链路**没有别的测试覆盖**（集成测试只测闸门标志位，
不测解析本身），页面再改一次还会以"AI 说官网没有"的形式悄悄坏掉。

所以这里用**与真实页面同构的 HTML 夹具**把解析钉住，并额外钉一条用户口径：
**列清单全程不下载任何包**（"有合适的才拉包"）—— 哪天有人好心改成"拉包读
准确元数据"，这条会当场变红。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from my_agent.assistants import library as lib
from my_agent.assistants.library import BuddyLibrary
from my_agent.assistants.transfer import TransferError

# 与 china.xinjianxue.com/buddy.html 同构的最小页面：两个搭子卡 + 一个群包卡
# + 一张"缺 h4"的老式卡 + 一个 json 兼容链接。标签/属性照抄真实页面（含 class），
# 因为解析器**不该**依赖 class 名 —— 夹具里故意保留它们，证明确实没用到。
PAGE = """
<html><body>
<h3>挑一个搭子</h3>
<div class="bg-dark-100 rounded-xl shadow-card p-6">
  <h4 class="text-lg font-bold">岸</h4>
  <p class="text-gray-400 text-sm leading-relaxed mb-4">低调冷静、精准敏锐；说话不多，每一句都指向关键点。</p>
  <a href="/downloads/buddy/buddy-an-cn.zip" download class="...">下载搭子包</a>
</div>
<div class="bg-dark-100 rounded-xl shadow-card p-6">
  <h4 class="text-lg font-bold">大喜</h4>
  <p class="text-gray-400 text-sm leading-relaxed mb-4">话少、句句有用、偶尔冷幽默；算账不留情面。</p>
  <a href="/downloads/buddy/buddy-daxi-cn.zip" download class="...">下载搭子包</a>
</div>
<div class="bg-dark-100 rounded-xl shadow-card p-6">
  <a href="/downloads/buddy/buddy-bare-cn.zip" download>下载搭子包</a>
</div>
<h3>搭子群</h3>
<div class="bg-dark-100 rounded-xl shadow-card p-6">
  <h4 class="text-lg font-bold">岸·服务器岸·大喜</h4>
  <p class="text-gray-400 text-sm leading-relaxed mb-4">岸、服务器岸、大喜三个人放一个包，导入后默认按这个顺序发言。</p>
  <a href="/downloads/group/xjx-trio-cn.zip" download>下载搭子群包</a>
</div>
<a href="/downloads/buddy/legacy-cn.json">旧版导入文件</a>
</body></html>
"""


@pytest.fixture()
def fetch_log(monkeypatch):
    """把模块级 _fetch 换成记录器：返回页面本身，其余地址一律失败。

    之所以"其余地址一律失败"而不是返回空字节：列清单若偷偷去拉包/拉 json，
    会以 TransferError 的形式炸出来 —— 比静默记数更能钉住"不下载包"。
    """
    calls: list[str] = []

    def fake_fetch(url: str) -> bytes:
        calls.append(url)
        if url.endswith("buddy.html"):
            return PAGE.encode("utf-8")
        raise TransferError(f"列清单阶段不该发起这个下载：{url}")

    monkeypatch.setattr(lib, "_fetch", fake_fetch)
    return calls


def _library() -> BuddyLibrary:
    # list_available 只读 runtime.line；给个最小替身就够
    return BuddyLibrary(SimpleNamespace(line="cn"))


def test_lists_buddies_from_page_cards(fetch_log) -> None:
    """名字与简介直接来自页面卡片；群包不混进 buddies；全程只抓了页面本身。"""
    result = _library().list_available()

    assert result["ok"] is True
    # 旧版 .json 链接同样只列出、不下载（兼容老式页面）；缺 h4 的卡回退文件名 stem
    names = [item["name"] for item in result["buddies"]]
    assert names == ["岸", "大喜", "buddy-bare-cn", "legacy-cn"]
    an = result["buddies"][0]
    assert an["package_url"].endswith("/downloads/buddy/buddy-an-cn.zip")
    assert an["description"] == "低调冷静、精准敏锐；说话不多，每一句都指向关键点。"

    # 群包单独分组（产品约定：群与搭子的导入语义不同，不能混在一列里）
    assert [item["name"] for item in result["groups"]] == ["岸·服务器岸·大喜"]
    assert result["groups"][0]["package_url"].endswith("/downloads/group/xjx-trio-cn.zip")
    assert result["count"] == 4
    # "有合适的才拉包"：清单阶段只有页面这一次网络访问
    assert fetch_log == ["https://china.xinjianxue.com/buddy.html"]


def test_group_note_is_appended_to_message(fetch_log) -> None:
    """有群包时要在 message 里点名它的用法，模型才知道走 buddy_group_import。"""
    result = _library().list_available()
    assert "buddy_group_import" in result["message"]


def test_fetch_failure_reports_honestly(monkeypatch) -> None:
    """连不上时 ok=False + 原因如实带上，并置位 checked（闸门认这个标志）。"""
    monkeypatch.setattr(
        lib, "_fetch", lambda url: (_ for _ in ()).throw(TransferError("连不上 host"))
    )
    library = _library()
    result = library.list_available()

    assert result["ok"] is False
    assert "连不上 host" in result["message"]
    assert library.checked is True
    assert "连不上" in library.last_error

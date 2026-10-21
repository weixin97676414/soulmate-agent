












from __future__ import annotations

from types import SimpleNamespace

import pytest

from my_agent.assistants import library as lib
from my_agent.assistants.library import BuddyLibrary
from my_agent.assistants.transfer import TransferError




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





    calls: list[str] = []

    def fake_fetch(url: str) -> bytes:
        calls.append(url)
        if url.endswith("buddy.html"):
            return PAGE.encode("utf-8")
        raise TransferError(f"列清单阶段不该发起这个下载：{url}")

    monkeypatch.setattr(lib, "_fetch", fake_fetch)
    return calls


def _library() -> BuddyLibrary:
    
    return BuddyLibrary(SimpleNamespace(line="cn"))


def test_lists_buddies_from_page_cards(fetch_log) -> None:

    result = _library().list_available()

    assert result["ok"] is True
    
    names = [item["name"] for item in result["buddies"]]
    assert names == ["岸", "大喜", "buddy-bare-cn", "legacy-cn"]
    an = result["buddies"][0]
    assert an["package_url"].endswith("/downloads/buddy/buddy-an-cn.zip")
    assert an["description"] == "低调冷静、精准敏锐；说话不多，每一句都指向关键点。"

    
    assert [item["name"] for item in result["groups"]] == ["岸·服务器岸·大喜"]
    assert result["groups"][0]["package_url"].endswith("/downloads/group/xjx-trio-cn.zip")
    assert result["count"] == 4
    
    assert fetch_log == ["https://china.xinjianxue.com/buddy.html"]


def test_group_note_is_appended_to_message(fetch_log) -> None:

    result = _library().list_available()
    assert "buddy_group_import" in result["message"]


def test_fetch_failure_reports_honestly(monkeypatch) -> None:

    monkeypatch.setattr(
        lib, "_fetch", lambda url: (_ for _ in ()).throw(TransferError("连不上 host"))
    )
    library = _library()
    result = library.list_available()

    assert result["ok"] is False
    assert "连不上 host" in result["message"]
    assert library.checked is True
    assert "连不上" in library.last_error

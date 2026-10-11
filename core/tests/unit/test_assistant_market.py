"""助手集市：索引解析与外部地址拉取。

集市的数据来自**别人维护的外部地址**，所以要盯住三件事：

1. 一条坏数据不能废掉整个集市（逐条跳过）；
2. 外部地址要过和模型端点同一套校验（否则它是一个现成的 SSRF 入口）；
3. 响应体必须有体积上限（否则被指向的地址可以一直吐数据）。
"""

from __future__ import annotations

import json

import httpx
import pytest

from my_agent.assistants.market import (
    MAX_BYTES,
    MarketError,
    fetch_index,
    fetch_pack,
    parse_index,
)
from my_agent.errors import ConfigError


def patch_transport(monkeypatch, handler) -> None:
    """把 httpx.AsyncClient 换成挂了 MockTransport 的版本。

    这样被测代码仍然走真实的 httpx 调用链（超时、header 解析、aiter_bytes
    都是真的），只是不发网络请求。
    """
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def ok(payload) -> httpx.Response:
    return httpx.Response(200, json=payload)


# --------------------------------------------------------------------------- #
# 索引解析
# --------------------------------------------------------------------------- #
class TestParseIndex:
    def test_parses_valid_entries(self):
        entries = parse_index(
            {
                "version": 1,
                "assistants": [
                    {
                        "id": "writer",
                        "name": "公文写作",
                        "url": "https://example.com/writer.json",
                        "description": "写公文",
                        "author": "某人",
                    }
                ],
            }
        )

        assert len(entries) == 1
        assert entries[0].id == "writer"
        assert entries[0].to_dict()["author"] == "某人"

    def test_top_level_must_be_object(self):
        with pytest.raises(MarketError):
            parse_index(["not", "an", "object"])

    def test_missing_assistants_list(self):
        with pytest.raises(MarketError, match="assistants"):
            parse_index({"version": 1})

    def test_bad_entry_is_skipped_not_fatal(self):
        """一条坏数据不能废掉整个集市 —— 集市是别人维护的，写错一个 URL 很正常。"""
        entries = parse_index(
            {
                "assistants": [
                    "一个字符串条目",
                    {"id": "no-url", "name": "缺 url"},
                    {"name": "缺 id", "url": "https://example.com/a.json"},
                    {"id": "good", "name": "好的", "url": "https://example.com/good.json"},
                ]
            }
        )

        assert [entry.id for entry in entries] == ["good"]

    def test_entry_with_unsafe_url_is_skipped(self):
        """指向云元数据服务的条目直接丢掉，而不是留给后面去拦。"""
        entries = parse_index(
            {
                "assistants": [
                    {"id": "evil", "name": "x", "url": "http://169.254.169.254/latest/meta-data/"},
                    {"id": "ok", "name": "y", "url": "https://example.com/y.json"},
                ]
            }
        )

        assert [entry.id for entry in entries] == ["ok"]

    def test_duplicate_ids_are_deduped(self):
        """同 id 只留第一个：安装时重名会自动改 id，留着两条只会让用户困惑。"""
        entries = parse_index(
            {
                "assistants": [
                    {"id": "dup", "name": "第一次", "url": "https://example.com/1.json"},
                    {"id": "dup", "name": "第二次", "url": "https://example.com/2.json"},
                ]
            }
        )

        assert len(entries) == 1
        assert entries[0].name == "第一次"


# --------------------------------------------------------------------------- #
# 拉取
# --------------------------------------------------------------------------- #
class TestFetch:
    @pytest.mark.asyncio
    async def test_fetch_index_happy_path(self, monkeypatch):
        patch_transport(
            monkeypatch,
            lambda request: ok(
                {"assistants": [{"id": "a", "name": "A", "url": "https://example.com/a.json"}]}
            ),
        )

        entries = await fetch_index("https://example.com/index.json")

        assert [entry.id for entry in entries] == ["a"]

    @pytest.mark.asyncio
    async def test_non_http_scheme_is_rejected(self):
        with pytest.raises(ConfigError):
            await fetch_index("file:///etc/passwd")

    @pytest.mark.asyncio
    async def test_metadata_host_is_rejected(self):
        with pytest.raises(ConfigError):
            await fetch_index("http://169.254.169.254/latest/meta-data/")

    @pytest.mark.asyncio
    async def test_http_error_becomes_market_error(self, monkeypatch):
        patch_transport(monkeypatch, lambda request: httpx.Response(404))

        with pytest.raises(MarketError, match="404"):
            await fetch_index("https://example.com/index.json")

    @pytest.mark.asyncio
    async def test_html_page_gives_actionable_error(self, monkeypatch):
        """用户很容易把"集市网页地址"当成"索引地址"填进来。

        这时报"不是合法 JSON"并提示他填的是什么，比抛一个 JSONDecodeError 有用。
        """
        patch_transport(
            monkeypatch,
            lambda request: httpx.Response(200, text="<html><body>hi</body></html>"),
        )

        with pytest.raises(MarketError, match="JSON"):
            await fetch_index("https://example.com/page.html")

    @pytest.mark.asyncio
    async def test_oversized_body_is_rejected(self, monkeypatch):
        """体积上限：被指向的地址可以一直吐数据，不设上限就是内存放大器。"""
        huge = json.dumps({"padding": "x" * (MAX_BYTES + 1024)}).encode("utf-8")

        def handler(request: httpx.Request) -> httpx.Response:
            # 刻意**不**提供 content-length，逼代码走"边读边计数"那条路径 ——
            # 只信那个头的话，它撒个谎或干脆不给就绕过去了
            return httpx.Response(200, content=huge)

        patch_transport(monkeypatch, handler)

        with pytest.raises(MarketError, match="体积"):
            await fetch_index("https://example.com/index.json")

    @pytest.mark.asyncio
    async def test_declared_oversize_is_rejected_early(self, monkeypatch):
        patch_transport(
            monkeypatch,
            lambda request: httpx.Response(
                200, headers={"content-length": str(MAX_BYTES * 2)}, content=b"{}"
            ),
        )

        with pytest.raises(MarketError, match="体积"):
            await fetch_index("https://example.com/index.json")


class TestFetchPack:
    @pytest.mark.asyncio
    async def test_requires_assistants_list(self, monkeypatch):
        patch_transport(monkeypatch, lambda request: ok({"version": 1}))

        with pytest.raises(MarketError, match="assistants"):
            await fetch_pack("https://example.com/pack.json")

    @pytest.mark.asyncio
    async def test_returns_pack_unchanged(self, monkeypatch):
        """包内容原样返回 —— 校验交给 _install_profiles，与文件导入共用同一条路。"""
        pack = {"version": 1, "assistants": [{"id": "a", "name": "A"}]}
        patch_transport(monkeypatch, lambda request: ok(pack))

        assert await fetch_pack("https://example.com/pack.json") == pack

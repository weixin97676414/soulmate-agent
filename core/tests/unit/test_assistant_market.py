








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





    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def ok(payload) -> httpx.Response:
    return httpx.Response(200, json=payload)





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




        patch_transport(
            monkeypatch,
            lambda request: httpx.Response(200, text="<html><body>hi</body></html>"),
        )

        with pytest.raises(MarketError, match="JSON"):
            await fetch_index("https://example.com/page.html")

    @pytest.mark.asyncio
    async def test_oversized_body_is_rejected(self, monkeypatch):

        huge = json.dumps({"padding": "x" * (MAX_BYTES + 1024)}).encode("utf-8")

        def handler(request: httpx.Request) -> httpx.Response:
            
            
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

        pack = {"version": 1, "assistants": [{"id": "a", "name": "A"}]}
        patch_transport(monkeypatch, lambda request: ok(pack))

        assert await fetch_pack("https://example.com/pack.json") == pack

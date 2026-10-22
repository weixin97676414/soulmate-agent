







from contextlib import AsyncExitStack

from my_agent.config.schemas import McpServerConfig
from my_agent.mcp import transports


async def test_streamable_http_headers_go_through_http_client(monkeypatch):
    captured: dict[str, object] = {}

    class FakeHttpClient:
        async def aclose(self) -> None:
            captured["closed"] = True

    def fake_factory(*, headers=None, **kwargs):  
        captured["headers"] = headers
        return FakeHttpClient()

    class FakeContext:
        async def __aenter__(self):
            return ("read", "write", "session-id")

        async def __aexit__(self, *args):  
            return False

    def fake_streamable(url, **kwargs):
        
        assert "headers" not in kwargs, "不能再向 streamable_http_client 传 headers"
        captured["url"] = url
        captured["http_client"] = kwargs.get("http_client")
        return FakeContext()

    monkeypatch.setattr(
        "mcp.client.streamable_http.streamable_http_client", fake_streamable
    )
    monkeypatch.setattr(
        "mcp.shared._httpx_utils.create_mcp_http_client", fake_factory
    )

    config = McpServerConfig(
        name="remote",
        transport="streamable_http",
        url="https://example.com/mcp",
        headers={"Authorization": "Bearer secret"},
    )

    async with AsyncExitStack() as stack:
        read, write = await transports._open_streamable_http(config, stack)  

    assert (read, write) == ("read", "write")
    assert captured["headers"] == {"Authorization": "Bearer secret"}
    assert captured["http_client"] is not None
    assert captured["url"] == "https://example.com/mcp"








from my_agent.mcp.normalize import coerce_entry, normalize_transport


def test_streamable_http_variants():
    for declared in (
        "streamableHttp",
        "streamable_http",
        "streamable-http",
        "http",
        "",
    ):
        assert normalize_transport(declared, True) == "streamable_http", declared


def test_sse_variants():
    assert normalize_transport("sse", True) == "sse"
    assert normalize_transport("http-sse", True) == "sse"


def test_stdio_variants():
    assert normalize_transport("stdio", False) == "stdio"
    assert normalize_transport("", False) == "stdio"


def test_coerce_streamable_http_from_type_field():

    raw = {"type": "streamableHttp", "url": "https://chinaapi.xinjianxue.com/mcp"}
    config = coerce_entry("xinjianxue", raw)
    assert config.transport == "streamable_http"
    assert config.url == "https://chinaapi.xinjianxue.com/mcp"


def test_coerce_sse_when_declared():
    config = coerce_entry("legacy", {"type": "sse", "url": "https://example.com/sse"})
    assert config.transport == "sse"


def test_coerce_stdio_when_no_url():
    config = coerce_entry("local", {"command": "npx", "args": ["-y", "x"]})
    assert config.transport == "stdio"

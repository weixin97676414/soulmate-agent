





from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from my_agent.memory.embedding import ApiEmbedder


def build(handler: Any, **kwargs: Any) -> ApiEmbedder:
    return ApiEmbedder(
        base_url="https://api.example.com/v1",
        api_key="k-test",
        model_name="embed-small",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def reply(vectors: list[list[float]], *, reverse: bool = False, drop: int = 0) -> httpx.Response:
    items = [{"index": i, "embedding": vec} for i, vec in enumerate(vectors)]
    if reverse:
        items = list(reversed(items))
    if drop:
        items = items[:-drop]
    return httpx.Response(200, json={"data": items})


def test_basic_embedding():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        return reply([[1.0, 0.0], [0.0, 1.0]])

    embedder = build(handler)
    vectors = embedder(["甲乙", "丙丁"])

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert captured["url"].endswith("/v1/embeddings")
    assert captured["body"]["model"] == "embed-small"
    assert captured["body"]["input"] == ["甲乙", "丙丁"]
    assert captured["auth"] == "Bearer k-test"
    embedder.close()


def test_reordered_response_is_normalized():





    embedder = build(lambda _: reply([[1.0, 0.0], [0.0, 1.0]], reverse=True))
    vectors = embedder(["第一条", "第二条"])
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    embedder.close()


def test_count_mismatch_raises():

    embedder = build(lambda _: reply([[1.0, 0.0], [0.0, 1.0]], drop=1))
    with pytest.raises(RuntimeError, match="数量"):
        embedder(["a", "b"])
    embedder.close()


def test_http_error_is_reported_with_redaction():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid api key sk-abcdefghijklmnopqrst")

    embedder = build(handler)
    with pytest.raises(RuntimeError) as exc:
        embedder(["a"])
    message = str(exc.value)
    assert "401" in message
    
    assert "sk-abcdefghijklmnopqrst" not in message
    embedder.close()


def test_empty_input_makes_no_request():
    calls: list[int] = []

    def handler(_: httpx.Request) -> httpx.Response:
        calls.append(1)
        return reply([])

    embedder = build(handler)
    assert embedder([]) == []
    assert calls == []
    embedder.close()


def test_batches_large_inputs():

    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)["input"]
        seen.append(len(batch))
        base = len(seen) * 10
        return reply([[float(base + i)] for i in range(len(batch))])

    embedder = build(handler, batch_size=2)
    vectors = embedder(["a", "b", "c", "d", "e"])

    assert seen == [2, 2, 1]
    assert [vec[0] for vec in vectors] == [10.0, 11.0, 20.0, 21.0, 30.0]
    embedder.close()


def test_network_error_is_wrapped():
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    embedder = build(handler)
    with pytest.raises(RuntimeError, match="请求失败"):
        embedder(["a"])
    embedder.close()

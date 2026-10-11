"""API 嵌入（用厂商 /embeddings 接口做向量化）。

全部离线（httpx.MockTransport）。重点覆盖三类**不会报错、但结果静默错乱**的坑：
返回顺序不保证、数量对不上、批量拆分。
"""

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
    """有些网关**不保证返回顺序**。

    顺序错位不会报错，但会让向量和文本对不上 —— 检索结果整体错乱，
    用户只会觉得"这个功能不准"，根本查不到原因。所以必须按 index 排一次。
    """
    embedder = build(lambda _: reply([[1.0, 0.0], [0.0, 1.0]], reverse=True))
    vectors = embedder(["第一条", "第二条"])
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    embedder.close()


def test_count_mismatch_raises():
    """返回数量与输入不一致时必须报错，而不是把错位的向量交出去。"""
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
    # 厂商回显的响应体是不可信文本，可能带 Key，必须先脱敏
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
    """超过 batch_size 时要拆成多次请求，且顺序不能乱。"""
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

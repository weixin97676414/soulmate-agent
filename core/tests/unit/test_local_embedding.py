













from __future__ import annotations

import pytest

from my_agent.memory.local_embedding import build_local_embedder, find_model_dir


pytestmark = pytest.mark.skipif(
    find_model_dir() is None, reason="内置嵌入模型未下载（scripts/fetch_embedding_model.py）"
)

DOCS = [
    "数据库迁移用 alembic 管理，每个版本一个事务，跑之前会先备份。",
    "今天中午吃了拉面，加了两颗溏心蛋，味道一般。",
    "文件上传的超时被我改成了 30 秒，之前 10 秒经常失败。",
    "会议纪要在共享盘里，记得周五之前整理好。",
]


CASES = [
    
    ("数据库迁移是怎么做的？", 0),
    
    
    ("午饭吃了什么？", 1),
    ("上传文件老是失败怎么办", 2),
]


@pytest.fixture(scope="module")
def embedder():
    instance = build_local_embedder()
    assert instance is not None, "模型存在但加载失败"
    return instance


def dot(left: list[float], right: list[float]) -> float:
    
    return sum(a * b for a, b in zip(left, right, strict=True))


def test_dimension(embedder):
    vectors = embedder(DOCS)
    assert len(vectors) == len(DOCS)
    assert len(vectors[0]) == 1024


def test_vectors_are_normalized(embedder):

    for vector in embedder(DOCS):
        assert dot(vector, vector) == pytest.approx(1.0, abs=1e-3)


def test_empty_input(embedder):
    assert embedder([]) == []


@pytest.mark.parametrize(("query", "expected"), CASES)
def test_retrieval_ranks_the_right_doc_first(embedder, query, expected):

    doc_vectors = embedder(DOCS)
    query_vector = embedder.embed_query([query])[0]

    scores = [dot(query_vector, vector) for vector in doc_vectors]
    top = max(range(len(scores)), key=lambda i: scores[i])

    assert top == expected, f"查询「{query}」首位命中了第 {top} 条，期望第 {expected} 条：{scores}"


def test_query_and_document_paths_differ(embedder):




    raw = embedder(["午饭吃了什么？"])[0]
    as_query = embedder.embed_query(["午饭吃了什么？"])[0]

    assert dot(raw, as_query) < 0.999


def test_ollama_url_is_normalized():





    from my_agent.memory.embedding import normalize_ollama_url

    assert normalize_ollama_url("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434"
    assert normalize_ollama_url("http://127.0.0.1:11434/") == "http://127.0.0.1:11434"
    assert normalize_ollama_url("") == "http://127.0.0.1:11434"
    assert normalize_ollama_url("http://localhost:11434") == "http://localhost:11434"

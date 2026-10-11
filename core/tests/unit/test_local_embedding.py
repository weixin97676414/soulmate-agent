"""内置中文嵌入模型（本地 ONNX）。

这组用例存在的理由只有一个：**它防的是"不报错但结果变差"**。

池化取错位置、查询少了指令前缀、忘了归一化 —— 这三种错误**都不会抛异常**，
向量照样算出来、检索照样返回结果，只是相似度全是错的。而正确性恰恰是这里的
全部价值（换成内置模型就是为了解决那个英文模型"数据库迁移 → 吃了拉面"的问题）。

所以它测的是**检索结果对不对**，而不是"接口调通了没有"。

模型没下载时整组跳过（它是 585MB，不随仓库分发，用
``scripts/fetch_embedding_model.py`` 拉取）。
"""

from __future__ import annotations

import pytest

from my_agent.memory.local_embedding import build_local_embedder, find_model_dir

# 参与度：没拉模型就整组跳过，而不是让测试失败 —— 少一个可选依赖不该挡住 CI
pytestmark = pytest.mark.skipif(
    find_model_dir() is None, reason="内置嵌入模型未下载（scripts/fetch_embedding_model.py）"
)

DOCS = [
    "数据库迁移用 alembic 管理，每个版本一个事务，跑之前会先备份。",
    "今天中午吃了拉面，加了两颗溏心蛋，味道一般。",
    "文件上传的超时被我改成了 30 秒，之前 10 秒经常失败。",
    "会议纪要在共享盘里，记得周五之前整理好。",
]

# (查询文本, 期望命中第几条)
CASES = [
    # 这条就是当初英文模型翻车的那一组
    ("数据库迁移是怎么做的？", 0),
    # 下面两条是**纯语义命中**：查询与文档没有字面重叠，
    # 字面匹配（BM25 之类）在这里都会失败，只有语义模型能过
    ("午饭吃了什么？", 1),
    ("上传文件老是失败怎么办", 2),
]


@pytest.fixture(scope="module")
def embedder():
    instance = build_local_embedder()
    assert instance is not None, "模型存在但加载失败"
    return instance


def dot(left: list[float], right: list[float]) -> float:
    # strict=True：长度不一致说明维度坏了，静默按短的算会把问题藏起来
    return sum(a * b for a, b in zip(left, right, strict=True))


def test_dimension(embedder):
    vectors = embedder(DOCS)
    assert len(vectors) == len(DOCS)
    assert len(vectors[0]) == 1024


def test_vectors_are_normalized(embedder):
    """必须 L2 归一化：归一化后点积才是余弦相似度，下面几条断言才成立。"""
    for vector in embedder(DOCS):
        assert dot(vector, vector) == pytest.approx(1.0, abs=1e-3)


def test_empty_input(embedder):
    assert embedder([]) == []


@pytest.mark.parametrize(("query", "expected"), CASES)
def test_retrieval_ranks_the_right_doc_first(embedder, query, expected):
    """核心断言：查询应该把语义相关的那条排到第一。"""
    doc_vectors = embedder(DOCS)
    query_vector = embedder.embed_query([query])[0]

    scores = [dot(query_vector, vector) for vector in doc_vectors]
    top = max(range(len(scores)), key=lambda i: scores[i])

    assert top == expected, f"查询「{query}」首位命中了第 {top} 条，期望第 {expected} 条：{scores}"


def test_query_and_document_paths_differ(embedder):
    """文档侧不加指令前缀、查询侧加。两者向量不同 —— 说明两条路真的分开了。

    如果哪天有人把 embed_query 改回跟 __call__ 一样，这条会立刻报。
    """
    raw = embedder(["午饭吃了什么？"])[0]
    as_query = embedder.embed_query(["午饭吃了什么？"])[0]

    assert dot(raw, as_query) < 0.999


def test_ollama_url_is_normalized():
    """Ollama 的接口在根路径上，用户照 OpenAI 习惯填的 /v1 必须被剥掉。

    剥不掉的表现是"明明装了 Ollama 却拿不到模型列表"—— 而且只报 404，
    很容易被误判成"Ollama 不支持"。
    """
    from my_agent.memory.embedding import normalize_ollama_url

    assert normalize_ollama_url("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434"
    assert normalize_ollama_url("http://127.0.0.1:11434/") == "http://127.0.0.1:11434"
    assert normalize_ollama_url("") == "http://127.0.0.1:11434"
    assert normalize_ollama_url("http://localhost:11434") == "http://localhost:11434"

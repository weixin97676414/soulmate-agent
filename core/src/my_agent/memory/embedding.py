"""非内置的嵌入后端：厂商 ``/embeddings`` 接口，以及本机 Ollama。

## 默认已经不是 chromadb 自带模型了

默认走的是**随包分发的中文模型**（见 ``memory/local_embedding.py``）。
所以这里两个类的定位是"用户想换一条路"：

- ``ApiEmbedder`` —— 自定义厂商接口（要联网、消耗配额，但模型上限最高）；
- ``OllamaEmbedder`` —— 本机已经跑着 Ollama 的用户，直接复用本地模型。

## 为什么默认曾经是 chromadb 自带模型、以及为什么换掉

``all-MiniLM-L6-v2`` 有两个硬伤：**首次使用要联网下载约 79MB**（离线直接失败）；
**它是英文模型**，实测用「数据库迁移怎么做的」查询返回的是「今天中午吃了拉面」。
对中文优先的应用这是硬伤，所以内置模型上线后它退位为"最后的兜底"。

## 为什么这里是**同步**客户端

chromadb 调用嵌入函数是同步的，而 ``LongTermMemory`` 已经把整段 chromadb 调用
放进了 ``asyncio.to_thread``。也就是说这里天然运行在工作线程里，
用同步 httpx 既正确又简单；换成 async 反而要自己管事件循环，得不偿失。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..llm.adapters.openai_compat import is_loopback_url
from ..security.redact import redact

logger = logging.getLogger(__name__)

# 一次请求最多塞多少条文本。厂商普遍对 batch 有上限，而且太大的批次
# 失败后要整体重试、代价高。
DEFAULT_BATCH = 32


class ApiEmbedder:
    """把文本向量化的工作交给厂商接口。

    实例本身就是 chromadb 需要的"可调用对象"；``long_term.CallableEmbedder``
    会再把它包成带 ``name()`` 的形状。
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout: float = 30.0,
        batch_size: int = DEFAULT_BATCH,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.model_name = model_name
        self.batch_size = max(1, batch_size)
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {api_key}" if api_key else "",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout, connect=10.0),
            # 与 LLM 适配器同样的取舍：本机端点必须绕过系统代理
            # （Windows 上 httpx 会读注册表里的代理且不豁免 127.0.0.1）
            trust_env=not is_loopback_url(self.base_url),
            transport=transport,
        )

    def __call__(self, texts: list[str]) -> list[list[float]]:
        items = [str(text) for text in texts]
        if not items:
            return []

        vectors: list[list[float]] = []
        for start in range(0, len(items), self.batch_size):
            vectors.extend(self._embed_batch(items[start : start + self.batch_size]))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        payload: dict[str, Any] = {"model": self.model_name, "input": batch}
        try:
            response = self._client.post(f"{self.base_url}/embeddings", json=payload)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"嵌入接口请求失败: {exc}") from exc

        if response.status_code >= 400:
            # 厂商回显的响应体是不可信文本，可能带上 Authorization 之类的内容
            raise RuntimeError(
                f"嵌入接口返回 HTTP {response.status_code}: {redact(response.text[:300])}"
            )

        data = response.json()
        entries = data.get("data") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise RuntimeError("嵌入接口返回格式异常：缺少 data 字段")

        # 不少实现（含 OpenAI 兼容网关）**不保证返回顺序**，按 index 排一次更稳。
        # 顺序错了的后果很隐蔽：向量和文本对不上，检索结果整体错乱但不会报错。
        ordered = sorted(entries, key=lambda item: item.get("index", 0))
        vectors = [
            item.get("embedding") for item in ordered if isinstance(item, dict)
        ]
        if len(vectors) != len(batch) or any(not isinstance(vec, list) for vec in vectors):
            raise RuntimeError(
                f"嵌入接口返回的向量数量（{len(vectors)}）与输入（{len(batch)}）不一致"
            )
        return [[float(value) for value in vec] for vec in vectors]

    def close(self) -> None:
        self._client.close()


# --------------------------------------------------------------------------- #
# 本机 Ollama
# --------------------------------------------------------------------------- #
def normalize_ollama_url(raw: str) -> str:
    """把用户填的地址归一成 Ollama 的**根地址**。

    Ollama 的接口在 ``/api/...`` 上，**没有** ``/v1`` 前缀。但用户照着 OpenAI
    兼容的习惯（设置里的预设也曾经这么给过）会填成 ``http://127.0.0.1:11434/v1``，
    那样拼出来是 ``/v1/api/embed`` —— 表现就是"明明装了 Ollama 却拿不到模型列表"，
    而报错只是个 404，很容易被误判成"Ollama 不支持这个功能"。
    """
    base = (raw or "").strip().rstrip("/")
    for suffix in ("/v1", "/api"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base or "http://127.0.0.1:11434"


def list_ollama_models(base_url: str, *, timeout: float = 10.0) -> list[str]:
    """列出本机 Ollama 已装的模型（``GET /api/tags``，不需要任何密钥）。

    **连不上就返回空列表，不抛异常**：这是个探测动作，用户可能根本没开 Ollama，
    那是正常状态而不是错误 —— 抛异常会让设置页直接挂掉。
    """
    root = normalize_ollama_url(base_url)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{root}/api/tags")
            if response.status_code >= 400:
                logger.debug("Ollama /api/tags 返回 HTTP %s", response.status_code)
                return []
            payload = response.json()
    except Exception as exc:  # noqa: BLE001 - 探测失败是常态，不该打断界面
        logger.debug("读取 Ollama 模型列表失败：%s", exc)
        return []

    entries = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []
    names = [str(item.get("name", "")).strip() for item in entries if isinstance(item, dict)]
    return [name for name in names if name]


class OllamaEmbedder:
    """用本机 Ollama 做向量化。

    **刻意没有 api_key 参数**：Ollama 不需要鉴权。不为"接口形状统一"而伪造一个
    空串字段 —— 真正不需要鉴权的后端就该明确没有这个参数，否则调用方会误以为
    "填了才对"。
    """

    def __init__(self, base_url: str, model: str, *, timeout: float = 60.0) -> None:
        self.base_url = normalize_ollama_url(base_url)
        self.model = model
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def __call__(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # 新版 Ollama 有批量接口 /api/embed，老版只有逐条的 /api/embeddings。
        # 先试新的、404 再降级 —— 硬选一边会让另一部分用户"点了没反应"。
        try:
            return self._embed_batch(texts)
        except RuntimeError as exc:
            if "404" not in str(exc):
                raise
            logger.debug("Ollama 不支持 /api/embed，改用逐条的老接口：%s", exc)
            return [self._embed_one(text) for text in texts]

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client.post(
                f"{self.base_url}/api/embed", json={"model": self.model, "input": texts}
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"连不上 Ollama（{self.base_url}）：{exc}。请确认 Ollama 已启动。"
            ) from exc
        if response.status_code >= 400:
            raise RuntimeError(
                f"Ollama 返回 HTTP {response.status_code}: {redact(response.text[:200])}"
            )
        data = response.json()
        vectors = data.get("embeddings") if isinstance(data, dict) else None
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise RuntimeError("Ollama 返回的向量数量与输入不一致")
        return [[float(value) for value in vec] for vec in vectors]

    def _embed_one(self, text: str) -> list[float]:
        try:
            response = self._client.post(
                f"{self.base_url}/api/embeddings", json={"model": self.model, "prompt": text}
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"连不上 Ollama（{self.base_url}）：{exc}") from exc
        if response.status_code >= 400:
            raise RuntimeError(
                f"Ollama 返回 HTTP {response.status_code}: {redact(response.text[:200])}"
            )
        data = response.json()
        vector = data.get("embedding") if isinstance(data, dict) else None
        if not isinstance(vector, list):
            raise RuntimeError("Ollama 返回格式异常：缺少 embedding 字段")
        return [float(value) for value in vector]

    def close(self) -> None:
        self._client.close()

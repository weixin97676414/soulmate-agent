






















from __future__ import annotations

import logging
from typing import Any

import httpx

from ..llm.adapters.openai_compat import is_loopback_url
from ..security.redact import redact

logger = logging.getLogger(__name__)



DEFAULT_BATCH = 32


class ApiEmbedder:






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
            
            raise RuntimeError(
                f"嵌入接口返回 HTTP {response.status_code}: {redact(response.text[:300])}"
            )

        data = response.json()
        entries = data.get("data") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise RuntimeError("嵌入接口返回格式异常：缺少 data 字段")

        
        
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





def normalize_ollama_url(raw: str) -> str:







    base = (raw or "").strip().rstrip("/")
    for suffix in ("/v1", "/api"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base or "http://127.0.0.1:11434"


def list_ollama_models(base_url: str, *, timeout: float = 10.0) -> list[str]:





    root = normalize_ollama_url(base_url)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{root}/api/tags")
            if response.status_code >= 400:
                logger.debug("Ollama /api/tags 返回 HTTP %s", response.status_code)
                return []
            payload = response.json()
    except Exception as exc:  
        logger.debug("读取 Ollama 模型列表失败：%s", exc)
        return []

    entries = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []
    names = [str(item.get("name", "")).strip() for item in entries if isinstance(item, dict)]
    return [name for name in names if name]


class OllamaEmbedder:







    def __init__(self, base_url: str, model: str, *, timeout: float = 60.0) -> None:
        self.base_url = normalize_ollama_url(base_url)
        self.model = model
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def __call__(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        
        
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

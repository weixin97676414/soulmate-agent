

























from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..utils.timefmt import format_now

logger = logging.getLogger(__name__)


Embedder = Callable[[list[str]], list[list[float]]]

DEFAULT_COLLECTION = "knowledge"

class CallableEmbedder:












    def __init__(self, fn: Embedder, query_fn: Embedder | None = None) -> None:
        self._fn = fn
        
        
        
        self._query_fn = query_fn

    def _run(self, fn: Embedder, input: list[str]) -> list[list[float]]:  
        return [[float(value) for value in vector] for vector in fn(list(input))]

    def __call__(self, input: list[str]) -> list[list[float]]:  
        return self._run(self._fn, input)

    def embed_query(self, input: list[str]) -> list[list[float]]:  





        return self._run(self._query_fn or self._fn, input)

    def is_legacy(self) -> bool:
        
        return False

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> Any:  






        return None

    @classmethod
    def name(cls) -> str:
        
        
        return "callable-embedder"

    def get_config(self) -> dict[str, Any]:
        return {}

    def default_space(self) -> str:
        return "l2"

    def supported_spaces(self) -> list[str]:
        return ["l2", "cosine", "ip"]


@dataclass
class MemoryHit:


    id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ts(self) -> float | None:

        value = self.metadata.get("ts")
        return float(value) if isinstance(value, (int, float)) else None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "text": self.text,
            "score": round(self.score, 4),
            "metadata": self.metadata,
        }
        
        
        if self.ts is not None:
            data["when"] = format_now(self.ts)
        return data


def _time_where(since: float | None, until: float | None) -> dict[str, Any] | None:









    clauses: list[dict[str, Any]] = []
    if since is not None:
        clauses.append({"ts": {"$gte": since}})
    if until is not None:
        clauses.append({"ts": {"$lte": until}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def chromadb_available() -> bool:

    try:
        import chromadb  
    except Exception:  
        return False
    return True







DEFAULT_TOP_K = 5



REBUILD_SUFFIX = "__rebuild"



OLD_SUFFIX = "__old"


def _looks_like_dimension_error(exc: BaseException) -> bool:








    text = str(exc).lower()
    return "dimension" in text or "dimensionality" in text


class LongTermMemory:



















    
    SIG_METADATA_KEY = "embedding_sig"

    
    
    REBUILD_BATCH = 128

    
    
    
    
    
    
    
    
    REBUILD_PAGE = 1024

    def __init__(
        self,
        directory: Path,
        *,
        collection: str = DEFAULT_COLLECTION,
        namespace: str = "",
        embedder: Embedder | None = None,
        query_embedder: Embedder | None = None,
        default_top_k: int = DEFAULT_TOP_K,
        embedding_signature: str = "",
        on_rebuilt: Callable[[int], None] | None = None,
    ) -> None:
        self.directory = Path(directory)
        
        
        
        self.collection_name = self._scoped_collection(collection, namespace)
        self.namespace = namespace
        self._embedder = embedder
        
        self._query_embedder = query_embedder
        
        
        self.default_top_k = max(1, int(default_top_k))
        
        
        self.embedding_signature = (embedding_signature or "").strip()
        self._client: Any = None
        self._collection: Any = None
        self._init_error: str | None = None
        
        self._signature_checked = False
        
        self._rebuild_task: asyncio.Task[int] | None = None
        self._rebuild_lock = asyncio.Lock()
        
        self.last_rebuild_count = 0
        
        
        self._on_rebuilt = on_rebuilt

    @staticmethod
    def _scoped_collection(base: str, namespace: str) -> str:













        if not (namespace or "").strip():
            
            return base
        ns = "".join(ch if ch.isascii() and (ch.isalnum() or ch in "._-") else "_" for ch in namespace)
        
        ns = ns.strip("._-")
        if not ns:
            
            
            
            ns = hashlib.sha1((namespace or "").encode("utf-8")).hexdigest()[:12]
        
        return f"assistant_{ns}"[:512]

    
    
    
    async def adopt_legacy_collection(self, legacy_name: str) -> bool:













        if not legacy_name or legacy_name == self.collection_name:
            return False

        def run() -> bool:
            import chromadb

            client = chromadb.PersistentClient(
                path=str(self.directory), settings=self._client_settings()
            )
            names = {getattr(item, "name", item) for item in client.list_collections()}
            if legacy_name not in names:
                return False
            
            try:
                if client.get_collection(self.collection_name).count() > 0:
                    logger.info("记忆库 %s 已有数据，跳过接管 %s", self.collection_name, legacy_name)
                    return False
            except Exception:  
                pass

            try:
                client.get_collection(legacy_name).modify(name=self.collection_name)
                logger.info("已把记忆库 %s 改名为 %s", legacy_name, self.collection_name)
                return True
            except Exception as exc:  
                logger.info("记忆库改名不可用（%s），改为复制内容：%s", self.collection_name, exc)

            legacy = client.get_collection(legacy_name)
            data = legacy.get(include=["documents", "metadatas"])
            ids = list(data.get("ids") or [])
            documents = list(data.get("documents") or [])
            metadatas = list(data.get("metadatas") or [])
            if not ids:
                return False
            
            self._ensure().add(ids=ids, documents=documents, metadatas=metadatas or None)
            logger.info("已把记忆库 %s 的内容复制到 %s（旧库保留）", legacy_name, self.collection_name)
            return True

        try:
            return await asyncio.to_thread(run)
        except Exception as exc:  
            logger.warning("接管旧记忆库失败（%s）: %s", legacy_name, exc)
            return False

    @property
    def available(self) -> bool:
        if self._collection is not None:
            return True
        if self._init_error is not None:
            return False
        
        return chromadb_available()

    @property
    def init_error(self) -> str | None:
        return self._init_error

    @staticmethod
    def _client_settings() -> Any:






        try:
            from chromadb.config import Settings as ChromaSettings

            return ChromaSettings(anonymized_telemetry=False)
        except Exception:  
            return None

    def _ensure(self) -> Any:

        if self._collection is not None:
            return self._collection
        if self._init_error is not None:
            raise RuntimeError(self._init_error)

        try:
            import chromadb
        except Exception as exc:  
            self._init_error = (
                "未安装长期记忆依赖（chromadb），向量检索不可用。"
                "启用方式：pip install \"my-agent-core[memory]\""
            )
            raise RuntimeError(self._init_error) from exc

        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self.directory),
                settings=self._client_settings(),
            )
            kwargs: dict[str, Any] = {"name": self.collection_name}
            if self._embedder is not None:
                
                kwargs["embedding_function"] = CallableEmbedder(
                    self._embedder, self._query_embedder
                )
            self._collection = self._client.get_or_create_collection(**kwargs)
            
            
            
            self._collection = self._rescue_interrupted_swap(self._client, self._collection)
        except Exception as exc:  
            
            
            self._init_error = f"长期记忆初始化失败: {exc}"
            logger.exception("长期记忆初始化失败: %s", self.directory)
            raise RuntimeError(self._init_error) from exc
        return self._collection

    
    
    
    @property
    def rebuilding(self) -> bool:

        return self._rebuild_task is not None and not self._rebuild_task.done()

    def _embedding_kwargs(self, name: str) -> dict[str, Any]:

        kwargs: dict[str, Any] = {"name": name}
        if self._embedder is not None:
            kwargs["embedding_function"] = CallableEmbedder(self._embedder, self._query_embedder)
        return kwargs

    def _rescue_interrupted_swap(self, client: Any, current: Any) -> Any:













        old_name = f"{self.collection_name}{OLD_SUFFIX}"
        try:
            names = {
                item if isinstance(item, str) else getattr(item, "name", "")
                for item in client.list_collections()
            }
            if old_name not in names:
                return current
            if int(current.count()) > 0:
                
                client.delete_collection(old_name)
                return current
            logger.warning("检测到上次重建中断的残留库 %s，正在恢复被让位的记忆库…", old_name)
            client.delete_collection(self.collection_name)
            client.get_collection(**self._embedding_kwargs(old_name)).modify(
                name=self.collection_name
            )
            restored = client.get_collection(**self._embedding_kwargs(self.collection_name))
            logger.info("记忆库已从残留备份恢复：%s 条", int(restored.count()))
            return restored
        except Exception as exc:  
            logger.warning("检查残留记忆库失败（按原样继续）: %s", exc)
            return current

    def _read_signature(self, collection: Any) -> str:
        try:
            meta = dict(collection.metadata or {})
        except Exception:  
            return ""
        return str(meta.get(self.SIG_METADATA_KEY) or "")

    def _stamp_signature(self, collection: Any) -> None:





        if not self.embedding_signature:
            return
        try:
            meta = dict(collection.metadata or {})
            if meta.get(self.SIG_METADATA_KEY) == self.embedding_signature:
                return
            meta[self.SIG_METADATA_KEY] = self.embedding_signature
            collection.modify(metadata=meta)
        except Exception as exc:  
            logger.debug("写入记忆库嵌入签名失败: %s", exc)

    async def sync_signature(self) -> str:








        if not self.embedding_signature or self._signature_checked:
            return "skipped"
        self._signature_checked = True

        def run() -> str:
            collection = self._ensure()
            stored = self._read_signature(collection)
            if stored == self.embedding_signature:
                return "ok"
            if collection.count() == 0:
                
                self._stamp_signature(collection)
                return "empty"
            if not stored:
                
                
                self._stamp_signature(collection)
                return "adopted"
            return "stale"

        try:
            verdict = await asyncio.to_thread(run)
        except Exception as exc:  
            logger.debug("检查记忆库嵌入签名失败: %s", exc)
            return "skipped"

        if verdict == "stale":
            self._start_rebuild(reason="嵌入方式已变更")
        return verdict

    def _start_rebuild(self, *, reason: str) -> None:

        if self.rebuilding:
            return
        logger.info("长期记忆需要重建向量（%s）：%s", self.collection_name, reason)
        self._rebuild_task = asyncio.create_task(self.rebuild(), name="memory-rebuild")

    async def rebuild(self) -> int:










        async with self._rebuild_lock:
            try:
                moved = await asyncio.to_thread(self._rebuild_sync)
            except Exception as exc:  
                logger.warning("长期记忆重建失败（旧数据未动）: %s", exc)
                return 0
        self.last_rebuild_count = moved
        if moved:
            logger.info("长期记忆已用当前模型重建 %s 条（库 %s）", moved, self.collection_name)
            
            
            if self._on_rebuilt is not None:
                try:
                    self._on_rebuilt(moved)
                except Exception:  
                    logger.debug("重建完成回调失败", exc_info=True)
        return moved

    def _rebuild_sync(self) -> int:
        collection = self._ensure()
        client = self._client
        if client is None:
            return 0
        if int(collection.count()) == 0:
            self._stamp_signature(collection)
            return 0

        staging = f"{self.collection_name}{REBUILD_SUFFIX}"
        
        try:
            client.delete_collection(staging)
        except Exception:  
            pass

        target = client.create_collection(**self._embedding_kwargs(staging))
        step = self.REBUILD_BATCH
        
        
        
        
        
        offset = 0
        moved = 0
        while True:
            data = collection.get(
                include=["documents", "metadatas"],
                limit=self.REBUILD_PAGE,
                offset=offset,
            )
            page_ids = [str(item) for item in (data.get("ids") or [])]
            if not page_ids:
                break
            page_documents = [str(item or "") for item in (data.get("documents") or [])]
            page_metadatas = [dict(item or {}) for item in (data.get("metadatas") or [])]
            for start in range(0, len(page_ids), step):
                end = start + step
                target.add(
                    ids=page_ids[start:end],
                    documents=page_documents[start:end],
                    metadatas=page_metadatas[start:end] or None,
                )
            moved += len(page_ids)
            offset += len(page_ids)

        if not moved:
            
            return 0

        
        
        
        
        
        
        
        old_name = f"{self.collection_name}{OLD_SUFFIX}"
        try:
            client.delete_collection(old_name)
        except Exception:  
            pass
        collection.modify(name=old_name)
        target.modify(name=self.collection_name)
        self._collection = client.get_collection(**self._embedding_kwargs(self.collection_name))
        self._stamp_signature(self._collection)
        
        try:
            client.delete_collection(old_name)
        except Exception:  
            pass
        return moved

    
    
    
    async def add(
        self,
        texts: Sequence[str],
        *,
        ids: Sequence[str] | None = None,
        metadatas: Sequence[dict[str, Any]] | None = None,
    ) -> list[str]:

        
        await self.sync_signature()
        if self.rebuilding and self._rebuild_task is not None:
            
            
            
            await self._rebuild_task
        cleaned = [text.strip() for text in texts]
        keep = [(index, text) for index, text in enumerate(cleaned) if text]
        if not keep:
            return []

        keys = list(ids) if ids else [uuid.uuid4().hex[:16] for _ in cleaned]
        payload = [text for _, text in keep]
        chunk_ids = [keys[index] for index, _ in keep]
        
        
        
        
        stamp = time.time()
        chunk_meta: list[dict[str, Any]] = []
        for index, _ in keep:
            meta = dict(metadatas[index]) if metadatas else {}
            meta.setdefault("ts", stamp)
            chunk_meta.append(meta)

        def run() -> list[str]:
            collection = self._ensure()
            collection.add(ids=chunk_ids, documents=payload, metadatas=chunk_meta)
            return chunk_ids

        result = await asyncio.to_thread(run)
        logger.info("已写入 %s 条长期记忆", len(result))
        return result

    
    
    
    async def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        since: float | None = None,
        until: float | None = None,
    ) -> list[MemoryHit]:










        text = (query or "").strip()
        if not text:
            return []
        
        
        await self.sync_signature()
        if self.rebuilding:
            
            
            
            logger.info("长期记忆正在重建，本次检索跳过（库 %s）", self.collection_name)
            return []
        limit = max(1, int(top_k)) if top_k is not None else self.default_top_k

        def run() -> list[MemoryHit]:
            collection = self._ensure()
            if collection.count() == 0:
                return []
            where = _time_where(since, until)
            response = collection.query(
                query_texts=[text],
                n_results=limit,
                **({"where": where} if where else {}),
            )
            return self._to_hits(response)

        try:
            return await asyncio.to_thread(run)
        except Exception as exc:  
            logger.warning("长期记忆检索失败: %s", exc)
            
            
            if _looks_like_dimension_error(exc):
                self._start_rebuild(reason="检索时发现向量维度与当前模型不符")
            return []

    @staticmethod
    def _to_hits(response: Any) -> list[MemoryHit]:






        def first(key: str) -> list[Any]:
            value = (response or {}).get(key) if isinstance(response, dict) else getattr(response, key, None)
            if isinstance(value, (list, tuple)) and value and isinstance(value[0], (list, tuple)):
                return list(value[0])
            return list(value) if isinstance(value, (list, tuple)) else []

        ids = first("ids")
        documents = first("documents")
        metadatas = first("metadatas")
        distances = first("distances")

        hits: list[MemoryHit] = []
        for index, item_id in enumerate(ids):
            
            
            distance = distances[index] if index < len(distances) else None
            score = 1.0 / (1.0 + float(distance)) if isinstance(distance, (int, float)) else 0.0
            metadata = metadatas[index] if index < len(metadatas) else None
            hits.append(
                MemoryHit(
                    id=str(item_id),
                    text=str(documents[index]) if index < len(documents) else "",
                    score=score,
                    metadata=dict(metadata) if isinstance(metadata, dict) else {},
                )
            )
        return hits

    
    
    
    async def forget(self, ids: Sequence[str]) -> int:

        targets = [str(item) for item in ids if item]
        if not targets:
            return 0

        def run() -> int:
            collection = self._ensure()
            collection.delete(ids=targets)
            return len(targets)

        return await asyncio.to_thread(run)

    async def count(self) -> int:
        def run() -> int:
            return int(self._ensure().count())

        try:
            return await asyncio.to_thread(run)
        except Exception:  
            return 0

    async def clear(self) -> int:

        before = await self.count()

        def run() -> None:
            client = self._client
            if client is None:
                self._ensure()
                client = self._client
            client.delete_collection(self.collection_name)
            self._collection = None

        await asyncio.to_thread(run)
        return before

    def dispose(self) -> None:






        close = getattr(self._embedder, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  
                logger.debug("关闭嵌入后端失败", exc_info=True)
        self._collection = None
        self._client = None

    async def aclose(self) -> None:





        self.dispose()

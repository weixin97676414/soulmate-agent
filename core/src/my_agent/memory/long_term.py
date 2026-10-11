"""长期记忆（本地向量检索）。

对应《智能体框架开发文档》8.3 节。短期记忆管"这次对话说了什么"，
长期记忆管"以前聊过什么、用户的知识库里有什么"。

## 两个刻意的设计取舍

**1. chromadb 是可选依赖，且必须能优雅缺席。**

它是整个项目里体积最大的一块（实测裸装约 265 MB：kubernetes 74 + rust 绑定 60.5
+ onnxruntime 44 + numpy 51 + …）。没装时 ``available`` 为 False，
相关技能会**明确告诉用户怎么启用**，而不是抛一个看不懂的 ImportError。

**2. 嵌入函数可注入。**

默认用 chromadb 自带的本地 ONNX 模型（首次使用会下载约 80 MB，需要联网），
但也可以换成调用厂商的 ``/embeddings`` 接口。做成可注入的还有第二个好处：
**测试可以塞一个确定性的假嵌入**，于是向量检索的链路能在完全离线、
不下载任何模型的情况下被验证。

## 为什么所有方法都是 async

chromadb 的客户端是**同步阻塞**的，一次检索动辄几十毫秒到几百毫秒。
直接在事件循环里调会卡住所有 SSE 流，所以统一走 ``asyncio.to_thread``。
"""

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

# 嵌入函数签名：(文本列表) -> (向量列表)
Embedder = Callable[[list[str]], list[list[float]]]

DEFAULT_COLLECTION = "knowledge"

class CallableEmbedder:
    """把普通可调用对象包装成 chromadb 需要的形状（一个有 ``name()`` 的对象）。

    chromadb 1.x **不接受裸函数**：直接传会在 ``get_or_create_collection`` 里抛出
    ``'function' object has no attribute 'name'`` —— 报错完全看不出是"入参形状不对"。

    **刻意不继承 chromadb 的 ``EmbeddingFunction``。** 那需要在模块顶层
    ``import chromadb``，而 PyInstaller 的静态分析会因此把整个 chromadb 依赖树
    （实测约 265 MB：kubernetes 74 + rust 绑定 60.5 + onnxruntime 44 + numpy 51…）
    打进**默认**产物 —— 而我们的前提恰恰是"默认产物里没有它"。
    实测 duck-typing 就够：chromadb 只用到 ``name()`` 与 ``__call__``。
    """

    def __init__(self, fn: Embedder, query_fn: Embedder | None = None) -> None:
        self._fn = fn
        # 查询侧可以走**另一个**函数。内置中文模型需要它：官方用法要求查询带
        # 指令前缀、文档不带（见 memory/local_embedding.py）。少了这一路，
        # 检索仍然能跑但召回率低一截 —— 属于"不报错但更差"，所以宁可多开这个口子。
        self._query_fn = query_fn

    def _run(self, fn: Embedder, input: list[str]) -> list[list[float]]:  # noqa: A002
        return [[float(value) for value in vector] for vector in fn(list(input))]

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002 - 参数名对齐 chromadb
        return self._run(self._fn, input)

    def embed_query(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        """检索时走的是这个方法，而不是 ``__call__``。

        缺了它 query 会抛异常——而 ``search()`` 为了不打断 Agent 循环会把异常
        吞成空结果，表现成"明明存进去了却检索不到"，很容易误判成向量质量问题。
        """
        return self._run(self._query_fn or self._fn, input)

    def is_legacy(self) -> bool:
        # 不声明的话 chromadb 会退回 legacy 配置路径并打 DeprecationWarning
        return False

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> Any:  # noqa: ARG004
        """chromadb 从落盘配置重建嵌入函数时用。

        我们的嵌入函数是运行期注入的（可能是测试替身，也可能是走厂商接口），
        无法从配置里复原，所以返回 None。chromadb 会打印一条警告并退回
        "每次检索显式传 EF"的路径——功能不受影响，因为我们本来就每次都传。
        """
        return None

    @classmethod
    def name(cls) -> str:
        # 类方法：chromadb 会**在类上**调用 name() 去登记配置，
        # 写成实例方法会打印 "name() missing 1 required positional argument: 'self'"
        return "callable-embedder"

    def get_config(self) -> dict[str, Any]:
        return {}

    def default_space(self) -> str:
        return "l2"

    def supported_spaces(self) -> list[str]:
        return ["l2", "cosine", "ip"]


@dataclass
class MemoryHit:
    """一条检索结果。"""

    id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ts(self) -> float | None:
        """这条记忆写入/归档的时刻（epoch 秒）。老数据没有该字段 → None。"""
        value = self.metadata.get("ts")
        return float(value) if isinstance(value, (int, float)) else None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "text": self.text,
            "score": round(self.score, 4),
            "metadata": self.metadata,
        }
        # 给模型的那一份要有**可读**时间：metadata 里的 epoch 秒它算不明白，
        # 而"这条记忆是什么时候的"正是它判断新旧的唯一依据
        if self.ts is not None:
            data["when"] = format_now(self.ts)
        return data


def _time_where(since: float | None, until: float | None) -> dict[str, Any] | None:
    """把时间范围翻成 chromadb 的 ``where`` 条件。

    chromadb 对数值 metadata 支持 ``$gte`` / ``$lte``，但有两条实测出来的限制：

    - 没有条件时**必须返回 None**：传空 dict 进去它会报错（而"不给时间范围"是最常见的调用）；
    - **同一个字段只能挂一个操作符**。写成 ``{"ts": {"$gte": a, "$lte": b}}`` 会直接抛
      "Expected operator expression to have exactly one operator"，所以起止都要时
      必须走 ``$and``。
    """
    clauses: list[dict[str, Any]] = []
    if since is not None:
        clauses.append({"ts": {"$gte": since}})
    if until is not None:
        clauses.append({"ts": {"$lte": until}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def chromadb_available() -> bool:
    """chromadb 是否可用。用于界面提示与技能注册决策。"""
    try:
        import chromadb  # noqa: F401
    except Exception:  # noqa: BLE001 - 缺失、版本错、二进制不兼容都算不可用
        return False
    return True


# 默认取回几条记忆。**实际用的是设置页那个「默认检索条数」**（见 MemorySettings
# .vector_top_k）：runtime 构建实例时会把它注入 ``default_top_k``。
#
# 这里留一个常量兜底，是为了直接用 LongTermMemory 的调用方（测试、脚本、
# 没经过 runtime 的场合）不必被迫传参，而不是"这个值说了算"。
DEFAULT_TOP_K = 5

# 重建时用的临时库后缀。写成常量是因为它出现在**两处**（建它、清它）——
# 两边拼法不一致会留下一个永远清不掉的垃圾库。
REBUILD_SUFFIX = "__rebuild"

# 换库时"让位"的旧库后缀（第 87 批，M-14）。换库是两步（旧库让位 → 新库顶上），
# 中间被打断会留下 `<正式名>__old`；恢复逻辑见 `_rescue_interrupted_swap`。
OLD_SUFFIX = "__old"


def _looks_like_dimension_error(exc: BaseException) -> bool:
    """这个异常看着像"向量维度对不上"吗。

    chromadb 各版本、各后端抛的消息并不统一（``dimensionality`` / ``dimension`` /
    ``expected ... got ...``），所以只能按关键词粗判。

    ⚠️ 误判的代价很小：白重建一次而已 —— ``rebuild`` 全程在临时库里写，
    失败也不会动旧数据（见 :meth:`LongTermMemory.rebuild`）。
    """
    text = str(exc).lower()
    return "dimension" in text or "dimensionality" in text


class LongTermMemory:
    """基于 chromadb 的本地长期记忆。

    整个实例是**惰性**的：构造时不导入 chromadb、不建目录、不连库，
    第一次真正用到时才初始化。这样即使功能一直没被使用，
    也不会在应用启动路径上引入任何成本。

    ## 换嵌入模型之后，旧记忆怎么办

    向量检索拿"查询向量"和"库里存的向量"算距离 —— **维度不一样就算不了**
    （1024 维和 2560 维之间没有余弦相似度可言）。用户从内置模型换到别的模型
    （或反过来）时，旧库里的向量就作废了。

    ⚠️ 但**记忆本身没丢**：库里除了向量还存着**原文**（``documents``），
    向量只是原文的一份索引，索引可以拿原文重新生成。所以这里记一个
    ``embedding_sig``（这个库是用哪种嵌入方式建的），一旦发现与当前不一致，
    就**用当前模型把原文重新嵌入一遍**（见 :meth:`rebuild`）——
    重建期间检索暂时不可用，但一条记忆都不会少。
    """

    #: collection metadata 里记录"这个库是用哪种嵌入方式建的"的键。
    SIG_METADATA_KEY = "embedding_sig"

    #: 重建时每批写多少条。几千条一次性交给 chromadb 会长时间占满内存与 CPU，
    #: 分批也让"中途失败"的代价小得多（半成品写在临时库里，随时可丢）。
    REBUILD_BATCH = 128

    #: 重建时**读**一页多少条（第 91 批，L-11）。
    #:
    #: ⚠️ 以前是 `collection.get(include=[...])` 一次把**整个库**的原文与元数据读进内存 ——
    #: 每条记忆是整段正文，上万条就是一大块峰值内存，而重建只是后台任务，
    #: 没道理和正在聊天的用户抢内存。现在按页读、读完这一页就写进临时库并释放。
    #:
    #: 比 `REBUILD_BATCH` 大是刻意的：读一页的开销主要在 chroma 侧，
    #: 页太小会变成大量往返（写入仍按 `REBUILD_BATCH` 切）。
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
        # namespace（通常是 assistant_id）会把 collection 拆成**每搭子独立**：
        # 有 namespace → `assistant_<id>`，没有 → 传入的 collection（默认 knowledge）。
        # 这样知识库与对话记忆都按搭子隔离，互不串味。
        self.collection_name = self._scoped_collection(collection, namespace)
        self.namespace = namespace
        self._embedder = embedder
        # 留空表示"查询与文档用同一个函数"（除内置中文模型外的所有后端都是这样）
        self._query_embedder = query_embedder
        # 检索默认取回几条 —— 由 runtime 从设置（MemorySettings.vector_top_k）注入。
        # 调用方显式传 top_k 时以调用方为准（技能入参就是这么用的）。
        self.default_top_k = max(1, int(default_top_k))
        # 「这个库是用哪种嵌入方式建的」—— 由 runtime 按当前设置算好传进来。
        # **空串 = 不启用这项检查**：直接构造实例的调用方（测试、脚本）不必关心它。
        self.embedding_signature = (embedding_signature or "").strip()
        self._client: Any = None
        self._collection: Any = None
        self._init_error: str | None = None
        # 签名只在本进程里查一次（查一次要开一次库，而它不会自己变）
        self._signature_checked = False
        # 重建任务 + 互斥锁：同一时刻只允许一个重建在跑
        self._rebuild_task: asyncio.Task[int] | None = None
        self._rebuild_lock = asyncio.Lock()
        #: 最近一次重建搬了多少条（0 = 没重建过）。给界面/日志用。
        self.last_rebuild_count = 0
        #: 重建完成后的回调（收到"搬了多少条"）。runtime 用它推一条事件到界面 ——
        #: 产品要求重建完成要在界面上有提示，不能只写日志。
        self._on_rebuilt = on_rebuilt

    @staticmethod
    def _scoped_collection(base: str, namespace: str) -> str:
        """按 namespace 拼出 collection 名。

        chromadb 对库名有硬约束：3~512 个字符、只能含 ``[a-zA-Z0-9._-]``、
        且**首尾必须是字母或数字**。而 namespace 通常是 ``assistant_id`` ——
        搭子名可以取中文，所以这里必须真的把字符集收窄。

        ⚠️ 原先用 ``str.isalnum()`` 判定，而它**对中文也返回 True**
        （``"文".isalnum() is True``）—— 于是「文爱伴侣」拼出
        ``assistant_文爱伴侣-e07b0a``，chromadb 直接拒收，那个搭子的长期记忆
        **整个不可用**（日志里一条 ``InvalidArgumentError``，界面上只说"不可用"，
        提示还指着"开关 / 依赖"两条无关的原因）。
        ASCII 判定 + 首尾裁剪 + 摘要兜底，这三件事缺一不可。
        """
        if not (namespace or "").strip():
            # 没有 namespace：用调用方给的库名（知识库默认 `knowledge`）
            return base
        ns = "".join(ch if ch.isascii() and (ch.isalnum() or ch in "._-") else "_" for ch in namespace)
        # chromadb 还要求首尾是 [a-zA-Z0-9]：净化后可能以 `_` 开头/结尾（中文被换成 `_`）
        ns = ns.strip("._-")
        if not ns:
            # 整个 id 都是非 ASCII（搭子名全中文，例如「文爱伴侣」）→ 一个合法字符都不剩。
            # ⚠️ 这里**不能**退化成"没有 namespace"（那会让所有中文搭子共用同一个库、
            # 记忆互相串味）：用 id 的摘要当名字，同一个 id 每次得到同一个库。
            ns = hashlib.sha1((namespace or "").encode("utf-8")).hexdigest()[:12]
        # chromadb 的上限是 512 字符；超长 id 截断（摘要路径天然不会超）
        return f"assistant_{ns}"[:512]

    # ------------------------------------------------------------------ #
    # 惰性初始化
    # ------------------------------------------------------------------ #
    async def adopt_legacy_collection(self, legacy_name: str) -> bool:
        """把旧搭子 id 的记忆库接管成当前这个（内置搭子改过 id，见 presets）。

        为什么必须做：长期记忆是**按搭子分库**的（collection 名 ``assistant_<id>``），
        改 id 就等于换了一个库 —— 升级用户以前的记忆还在磁盘上，但按新 id 查不到，
        界面上表现为"我存过的资料不见了"。那比报错更糟：用户不知道该怪谁。

        取舍：
        - 当前库**已经有数据** → 什么都不做（新库优先，别把两批记忆混在一起）；
        - 旧库不存在 → 什么都不做；
        - 优先用 chromadb 的 ``modify(name=...)`` 改名（最省事）；版本不支持时退化成
          "把旧库的文本重新写进新库"，**并保留旧库**（宁可多占空间，也不丢向量）；
        - 任何异常都只记日志、返回 False —— 记忆是增强能力，不能拖垮启动。
        """
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
            # 新库已经有东西了 → 不接管（否则两批记忆会混在一起，谁也不知道哪条的来源）
            try:
                if client.get_collection(self.collection_name).count() > 0:
                    logger.info("记忆库 %s 已有数据，跳过接管 %s", self.collection_name, legacy_name)
                    return False
            except Exception:  # noqa: BLE001 - 新库不存在 = 空的，可以接管
                pass

            try:
                client.get_collection(legacy_name).modify(name=self.collection_name)
                logger.info("已把记忆库 %s 改名为 %s", legacy_name, self.collection_name)
                return True
            except Exception as exc:  # noqa: BLE001 - 版本差异：退化成复制
                logger.info("记忆库改名不可用（%s），改为复制内容：%s", self.collection_name, exc)

            legacy = client.get_collection(legacy_name)
            data = legacy.get(include=["documents", "metadatas"])
            ids = list(data.get("ids") or [])
            documents = list(data.get("documents") or [])
            metadatas = list(data.get("metadatas") or [])
            if not ids:
                return False
            # 复制而不是移动：旧库留着，万一新库出问题还能人工找回
            self._ensure().add(ids=ids, documents=documents, metadatas=metadatas or None)
            logger.info("已把记忆库 %s 的内容复制到 %s（旧库保留）", legacy_name, self.collection_name)
            return True

        try:
            return await asyncio.to_thread(run)
        except Exception as exc:  # noqa: BLE001 - 接管失败不影响别的功能
            logger.warning("接管旧记忆库失败（%s）: %s", legacy_name, exc)
            return False

    @property
    def available(self) -> bool:
        if self._collection is not None:
            return True
        if self._init_error is not None:
            return False
        # 还没初始化过：只看依赖在不在，不去建库（建库是 IO）
        return chromadb_available()

    @property
    def init_error(self) -> str | None:
        return self._init_error

    @staticmethod
    def _client_settings() -> Any:
        """chromadb 客户端设置。

        **关闭匿名遥测。** 这是一个"数据全部留在本机"的应用，
        默认往外发使用数据与产品定位直接冲突；顺带也避免了离线环境下
        初始化时卡在联网上报上（表现为"第一次用知识库要等十几秒"）。
        """
        try:
            from chromadb.config import Settings as ChromaSettings

            return ChromaSettings(anonymized_telemetry=False)
        except Exception:  # noqa: BLE001 - 版本差异，拿不到就用默认设置
            return None

    def _ensure(self) -> Any:
        """同步初始化。调用方负责放进线程。"""
        if self._collection is not None:
            return self._collection
        if self._init_error is not None:
            raise RuntimeError(self._init_error)

        try:
            import chromadb
        except Exception as exc:  # noqa: BLE001
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
                # 包一层：chromadb 1.x 只认带 name() 的对象，裸函数会直接抛 AttributeError
                kwargs["embedding_function"] = CallableEmbedder(
                    self._embedder, self._query_embedder
                )
            self._collection = self._client.get_or_create_collection(**kwargs)
            # ⚠️ 先做一次"上次换库被打断"的恢复（见 `_rescue_interrupted_swap`）。
            # 放在这里而不是只在重建路径里：崩溃之后用户**未必**会再触发一次重建，
            # 而记忆"看不见"的每一天他都会以为数据没了。
            self._collection = self._rescue_interrupted_swap(self._client, self._collection)
        except Exception as exc:  # noqa: BLE001
            # 初始化失败（磁盘只读、模型下载失败、版本不兼容…）都要变成一句人话，
            # 而不是把底层异常直接抛给用户
            self._init_error = f"长期记忆初始化失败: {exc}"
            logger.exception("长期记忆初始化失败: %s", self.directory)
            raise RuntimeError(self._init_error) from exc
        return self._collection

    # ------------------------------------------------------------------ #
    # 嵌入签名与重建（换模型后让旧记忆继续可用）
    # ------------------------------------------------------------------ #
    @property
    def rebuilding(self) -> bool:
        """是否正在用当前模型重建向量。"""
        return self._rebuild_task is not None and not self._rebuild_task.done()

    def _embedding_kwargs(self, name: str) -> dict[str, Any]:
        """建库 / 取库的统一参数。包一层是因为 chromadb 1.x 只认带 name() 的对象。"""
        kwargs: dict[str, Any] = {"name": name}
        if self._embedder is not None:
            kwargs["embedding_function"] = CallableEmbedder(self._embedder, self._query_embedder)
        return kwargs

    def _rescue_interrupted_swap(self, client: Any, current: Any) -> Any:
        """把"上一次换库中途被打断"留下的 ``__old`` 拿回来（第 87 批，M-14）。

        **为什么需要它**：换库是**两步**（旧库让位 → 新库顶上），中间被强杀 / 断电
        会留下"正式库是空的、数据还躺在 ``__old`` 里"的状态 —— 而下次启动
        ``_ensure()`` 会 get_or_create 出一个**空库**，用户看到的是"我的记忆全没了"。
        （旧实现更糟：第一步直接 ``delete_collection(正式名)``，数据连抢救的余地都没有。）

        ⚠️ **只在正式库确实为空时才接管**：正式库有数据说明 ``__old`` 只是上次没用完的
        备份，清掉它即可 —— 绝不能拿一份旧快照去覆盖用户正在用的记忆。

        本方法**绝不抛异常**：它是恢复路径，失败就按原样返回（不比现在更糟），
        也不能因此把 `_ensure()` 打成"长期记忆初始化失败"。
        """
        old_name = f"{self.collection_name}{OLD_SUFFIX}"
        try:
            names = {
                item if isinstance(item, str) else getattr(item, "name", "")
                for item in client.list_collections()
            }
            if old_name not in names:
                return current
            if int(current.count()) > 0:
                # 正式库有数据 ⇒ `__old` 是上次没用完的备份，清掉
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
        except Exception as exc:  # noqa: BLE001 - 恢复失败不能连累初始化
            logger.warning("检查残留记忆库失败（按原样继续）: %s", exc)
            return current

    def _read_signature(self, collection: Any) -> str:
        try:
            meta = dict(collection.metadata or {})
        except Exception:  # noqa: BLE001 - 版本差异拿不到 metadata，就当没记过
            return ""
        return str(meta.get(self.SIG_METADATA_KEY) or "")

    def _stamp_signature(self, collection: Any) -> None:
        """把当前签名写进 collection 的 metadata。

        ⚠️ 必须**合并**旧 metadata 再写：``modify(metadata=...)`` 是整体替换，
        只传一个新键会把库上原有的信息抹掉。
        """
        if not self.embedding_signature:
            return
        try:
            meta = dict(collection.metadata or {})
            if meta.get(self.SIG_METADATA_KEY) == self.embedding_signature:
                return
            meta[self.SIG_METADATA_KEY] = self.embedding_signature
            collection.modify(metadata=meta)
        except Exception as exc:  # noqa: BLE001 - 签名只是辅助信息，写不进去不影响使用
            logger.debug("写入记忆库嵌入签名失败: %s", exc)

    async def sync_signature(self) -> str:
        """确认库的嵌入方式与当前一致；不一致就**在后台**重建。

        返回给人看：``ok`` / ``empty``（空库，认领即可）/ ``adopted``（这项功能之前
        建的老库，无从判断旧维度）/ ``stale``（不一致，已触发重建）/ ``skipped``。

        ⚠️ 重建**不在这里等**：几千条记忆重新嵌入可能要几分钟，而调用它的很可能是
        对话路径。后台跑，期间检索由 :attr:`rebuilding` 挡住（见 ``search``）。
        """
        if not self.embedding_signature or self._signature_checked:
            return "skipped"
        self._signature_checked = True

        def run() -> str:
            collection = self._ensure()
            stored = self._read_signature(collection)
            if stored == self.embedding_signature:
                return "ok"
            if collection.count() == 0:
                # 空库：谈不上重建，认领一下就行
                self._stamp_signature(collection)
                return "empty"
            if not stored:
                # 老库（这项功能之前建的）：无从判断它当年是什么维度。先认领成当前值；
                # 万一真的对不上，检索会抛维度错，由 search 的兜底把重建补上。
                self._stamp_signature(collection)
                return "adopted"
            return "stale"

        try:
            verdict = await asyncio.to_thread(run)
        except Exception as exc:  # noqa: BLE001 - 检查失败不该影响正常检索
            logger.debug("检查记忆库嵌入签名失败: %s", exc)
            return "skipped"

        if verdict == "stale":
            self._start_rebuild(reason="嵌入方式已变更")
        return verdict

    def _start_rebuild(self, *, reason: str) -> None:
        """起一个后台重建任务（已有在跑就不重复起）。"""
        if self.rebuilding:
            return
        logger.info("长期记忆需要重建向量（%s）：%s", self.collection_name, reason)
        self._rebuild_task = asyncio.create_task(self.rebuild(), name="memory-rebuild")

    async def rebuild(self) -> int:
        """用当前嵌入模型把库里的记忆**重新嵌入**一遍（只重算向量，原文不动）。

        数据安全的三条保证：
        1. 新向量先写进一个**临时库**（``<名字>__rebuild``），全程不碰旧库；
        2. 临时库写完整了才删旧库、把临时库改成正式名；
        3. 中途任何异常都只记日志，**旧库原样保留** —— 宁可这次没重建成功，
           也不能把用户攒下来的记忆弄丢。

        返回重建的条数（0 = 没东西可重建，或失败了）。
        """
        async with self._rebuild_lock:
            try:
                moved = await asyncio.to_thread(self._rebuild_sync)
            except Exception as exc:  # noqa: BLE001 - 重建失败绝不向外抛
                logger.warning("长期记忆重建失败（旧数据未动）: %s", exc)
                return 0
        self.last_rebuild_count = moved
        if moved:
            logger.info("长期记忆已用当前模型重建 %s 条（库 %s）", moved, self.collection_name)
            # ⚠️ 只在真搬了东西时回调：`moved == 0` 说明库是空的、或者重建失败了 ——
            # 这时候弹一句"已整理好 0 条"是在说一件没发生过的事。
            if self._on_rebuilt is not None:
                try:
                    self._on_rebuilt(moved)
                except Exception:  # noqa: BLE001 - 回调失败不该连累重建本身
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
        # 上次重建失败可能留下半成品，先清掉（里面有数据也不能用：它的向量是旧的）
        try:
            client.delete_collection(staging)
        except Exception:  # noqa: BLE001 - 不存在才是常态
            pass

        target = client.create_collection(**self._embedding_kwargs(staging))
        step = self.REBUILD_BATCH
        # ⚠️ **边读边写**（第 91 批，L-11）：一次 `get()` 拿全库会按"整库正文"算峰值内存。
        # 分页之后每一页用完即弃，峰值只与 `REBUILD_PAGE` 有关（与记忆总量无关）。
        #
        # 这里不会读到"边改边读"的中间态：`rebuild()` 全程持 `_rebuild_lock`，
        # 且 `add()` 在重建期间会等它跑完（见 `add` 里的说明），所以没有并发写入。
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
            # 空库：前面 `count()` 已经拦过一次，这里是"读着读着没了"的兜底
            return 0

        # ⚠️ 到这一行才动旧数据：上面任何一步抛异常，旧库都还完好。
        #
        # ⚠️ 而这里用的是**改名让位**，不是删除（第 87 批，M-14）：以前是
        # `delete_collection(正式名)`，那一步之后、`target.modify` 之前崩溃，
        # 用户攒的记忆就**永久没了**（下次启动只会建出一个空库）。
        # 改成先让旧库改名为 `<名>__old` —— 崩溃窗口里数据**还在盘上**，
        # 下次 `_ensure()` 会由 `_rescue_interrupted_swap` 自动接管回来。
        old_name = f"{self.collection_name}{OLD_SUFFIX}"
        try:
            client.delete_collection(old_name)
        except Exception:  # noqa: BLE001 - 不存在才是常态
            pass
        collection.modify(name=old_name)
        target.modify(name=self.collection_name)
        self._collection = client.get_collection(**self._embedding_kwargs(self.collection_name))
        self._stamp_signature(self._collection)
        # 换库成功，`__old` 这份"崩溃窗口保险"可以清掉了（留着白占一份向量库的磁盘）
        try:
            client.delete_collection(old_name)
        except Exception:  # noqa: BLE001
            pass
        return moved

    # ------------------------------------------------------------------ #
    # 写入
    # ------------------------------------------------------------------ #
    async def add(
        self,
        texts: Sequence[str],
        *,
        ids: Sequence[str] | None = None,
        metadatas: Sequence[dict[str, Any]] | None = None,
    ) -> list[str]:
        """写入若干条记忆，返回它们的 id。"""
        # 换过嵌入模型时先让库跟上（第一次用到时顺带检查，之后是空操作）
        await self.sync_signature()
        if self.rebuilding and self._rebuild_task is not None:
            # ⚠️ 重建期间写入会撞上"维度对不上"。这里**等它建完**再写 ——
            # 记忆是攒出来的，少写一条就永远少一条（归档那条路径虽然有 try/except，
            # 但吞掉等于静默丢数据，而用户完全不知道）。
            await self._rebuild_task
        cleaned = [text.strip() for text in texts]
        keep = [(index, text) for index, text in enumerate(cleaned) if text]
        if not keep:
            return []

        keys = list(ids) if ids else [uuid.uuid4().hex[:16] for _ in cleaned]
        payload = [text for _, text in keep]
        chunk_ids = [keys[index] for index, _ in keep]
        # **每条记忆都必须有时间**：用户要的是"记忆有时间维度，AI 能分清现在和以前"。
        # 兜底放在这里而不是指望每个调用方都记得传 —— 漏传的代价要到检索时才暴露
        # （翻出一堆"不知道什么时候的"结果），而这里只有几行。
        # 已经带 ts 的不覆盖：把某段历史整批归档时，要保留它的原始时刻而不是"归档时刻"。
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

    # ------------------------------------------------------------------ #
    # 检索
    # ------------------------------------------------------------------ #
    async def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        since: float | None = None,
        until: float | None = None,
    ) -> list[MemoryHit]:
        """语义检索。查不到就返回空列表，不抛异常。

        ``top_k`` 不给就用 :attr:`default_top_k`（来自设置页的「默认检索条数」）。
        **不给不等于"用某个常数"**：这个值就是要让用户能改的那个设置 ——
        以前它写死在这里，设置页上那个输入框改了没有任何效果。

        ``since`` / ``until`` 是 epoch 秒（**含端点**），给"只看上周的"这类问题用。
        没有它，模型答不了"我们上个月定的口径是什么" —— 它会把三个月前和昨天的
        记忆一视同仁地摆出来，而这正是用户说的"别把旧的当当下聊"。
        """
        text = (query or "").strip()
        if not text:
            return []
        # 换过嵌入模型的话，库里的向量得先用新模型重算一遍才查得了。
        # 这一步只在**本进程第一次**用到时真正开库检查，之后是空操作。
        await self.sync_signature()
        if self.rebuilding:
            # 正在重建：这期间新旧向量维度对不上，查不了。
            # ⚠️ 这里**不能装作"没有相关记忆"** —— 上层会据此对用户说"没查到"，
            # 而真相是"正在用当前模型重建"。`rebuilding` 就是留给上层区分这两件事的。
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
        except Exception as exc:  # noqa: BLE001 - 检索失败不该打断 Agent 循环
            logger.warning("长期记忆检索失败: %s", exc)
            # 维度对不上是**唯一**一类"值得立刻重建"的失败：库是好的，只是向量过时了。
            # 其余失败（磁盘只读、chromadb 版本不兼容）重建也救不了，别白跑一趟。
            if _looks_like_dimension_error(exc):
                self._start_rebuild(reason="检索时发现向量维度与当前模型不符")
            return []

    @staticmethod
    def _to_hits(response: Any) -> list[MemoryHit]:
        """把 chromadb 的查询结果摊平成扁平列表。

        chromadb 返回的是「按查询分组」的嵌套结构（``ids: [[...]]``），
        因为一次可以查多个 query。我们每次只查一个，所以取第 0 组，
        但**仍然要处理它是空的情况**（库里没数据时它给的是空列表而不是 [ [] ]）。
        """
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
            # chromadb 默认用 L2 距离（越小越近）。转成"相似度"更符合直觉，
            # 也避免模型把"距离 0.3 比 0.8 小"理解反了。
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

    # ------------------------------------------------------------------ #
    # 遗忘与统计
    # ------------------------------------------------------------------ #
    async def forget(self, ids: Sequence[str]) -> int:
        """按 id 删除记忆。对应文档 8.4 的「可遗忘」。"""
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
        except Exception:  # noqa: BLE001
            return 0

    async def clear(self) -> int:
        """清空全部长期记忆。"""
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
        """同步释放嵌入后端并丢弃句柄。

        设置页热更新（换嵌入模型、开关长期记忆）时会替换整个实例，
        旧实例的 httpx 客户端需要在这里显式关掉，否则要等 GC —— 而 httpx
        在 GC 时会打印警告，用户会以为是出了错。
        """
        close = getattr(self._embedder, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 - 关闭失败不该打断设置保存
                logger.debug("关闭嵌入后端失败", exc_info=True)
        self._collection = None
        self._client = None

    async def aclose(self) -> None:
        """释放句柄。

        chromadb 的 PersistentClient 没有显式 close，置空引用即可；
        保留这个方法是为了让上层能统一 `await xxx.aclose()` 而不必分支。
        """
        self.dispose()

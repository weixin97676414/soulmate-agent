"""本地 ONNX 嵌入（内置模型，离线可用）。

## 为什么要有这个

长期记忆默认那条路用的是 chromadb 自带的 ``all-MiniLM-L6-v2``。它有两个硬伤：

1. **是英文模型**。实测把"数据库迁移怎么做的"匹配到"今天中午吃了拉面" ——
   中文语义判断基本不可用，而知识库检索恰恰全靠这个。
2. **首次使用要联网下载约 79MB**。离线环境直接失败，而这是个桌面应用。

所以内置一个中文模型：装完即用、不联网、不花用户的 API 配额。

## 为什么用 onnxruntime 而不是 sentence-transformers / torch

**因为运行时已经在包里了**。``onnxruntime`` 与 ``tokenizers`` 是 chromadb 的依赖
（``build/agent-core.spec`` 里已经 ``collect_all`` 了它们），而 torch 是几百 MB
且需要额外维护。用这两样，本地嵌入**不需要任何新的 Python 依赖**。

## 模型与两种精度

``Qwen3-Embedding-0.6B``，1024 维 / 32k 上下文。仓库里同时放了量化版与全精度版，
**默认选量化版**（约 585MB，全精度约 1.2GB），先用哪个由所选文件决定。

## 三个容易做错、而且错了不会报错的地方

这三处都是"结果照样返回、但向量质量悄悄变差"的类型，所以各写了注释：

1. **池化方式**。这个模型取的是**最后一个 token** 的隐状态，不是平均池化。
   取错位置不会报错，只会让相似度乱七八糟。
2. **左填充**。模型是按 ``padding_side=left`` 导出的：真实 token 在序列**尾部**，
   所以"最后一个真实 token"要靠 attention_mask 逐行算，不能简单取 ``[:, -1]``
   （批量里短句会带上右填充，取到的就是填充位）。
3. **查询要加指令前缀**。官方用法是文档存原文、查询前面加
   ``Instruct: ...\\nQuery: ...``。少了它检索仍然能跑，只是召回率低一截 ——
   属于"不报错但效果差"，最难被发现的那种。

## 输出

固定 **L2 归一化**后的向量。归一化后余弦相似度就是点积，chromadb 的默认度量
（``l2``）在单位向量上与余弦等价，所以这里统一归一化最省事也最不容易错。

## 这个 ONNX 是"带 KV 缓存"的导出，要多喂两样东西

社区导出的 Qwen3 ONNX（``onnx-community`` 那套）是为 transformers.js 服务的，
图里带着 KV 缓存的输入输出：必须额外提供 ``position_ids`` 与 **56 个空缓存张量**
（28 层 × key/value）。**不喂就直接报错**，报错信息会列出 56 个缺失的输入名，
但不会告诉你"其实只要喂空的就行"。

按 transformers.js 首步的做法喂零长度缓存即可，结果与普通编码器一致。

同时要注意：它**返回 57 个输出**（``last_hidden_state`` + 56 个 ``present.*``）。
必须**按名字只取 ``last_hidden_state``** —— 用 ``run(None, ...)`` 会让 onnxruntime
把 56 个缓存张量全部物化出来，batch 大时白白多占几十 MB 内存和一次拷贝。
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 模型目录名，随包分发
MODEL_DIRNAME = "qwen3-embedding-0.6b"
# 优先量化版（体积减半）；没有时退回全精度版
_QUANTIZED = "onnx/model_quantized.onnx"
_FULL = "onnx/model.onnx"

# 查询用的指令前缀。范围写得宽一点（"检索相关记忆与资料"），
# 因为这个嵌入既服务知识库也服务长期记忆，太窄的指令会伤到另一侧。
QUERY_INSTRUCTION = "给定一段用户提问，检索出与之相关的事实、资料或历史对话"

# 线程数上限。嵌入是本地 CPU 推理，放开会把整机占满（用户那边还在跑别的程序）。
_MAX_THREADS = 4

# ONNX 张量类型 -> numpy 类型。只有 KV 缓存要按声明类型造零张量时会用到。
_NUMPY_TYPES: dict[str, str] = {
    "tensor(float)": "float32",
    "tensor(float16)": "float16",
    "tensor(double)": "float64",
    "tensor(int64)": "int64",
    "tensor(int32)": "int32",
}


def _is_cache_input(item: Any) -> bool:
    """是否是 KV 缓存输入（这个导出带了缓存，必须喂零长度张量）。"""
    return item.name.startswith("past_key_values")


def _empty_cache_shape(declared: Any, batch: int) -> list[int]:
    """按声明形状推出"空缓存"的形状。

    声明形如 ``['batch_size', 8, 'past_sequence_length', 128]``：第一个维度是批大小、
    其余符号维度全是"过去的长度"（首步就是 0），固定维度原样保留。所以结果是
    ``[batch, 8, 0, 128]`` —— 这不是猜的，是 transformers.js 首步的做法。
    """
    shape: list[int] = []
    for index, dim in enumerate(declared):
        if isinstance(dim, int):
            shape.append(dim)
        elif index == 0:
            shape.append(batch)
        else:
            shape.append(0)
    return shape


def _env_override() -> Path | None:
    raw = os.environ.get("AGENT_EMBEDDING_MODEL_DIR", "").strip()
    return Path(raw) if raw else None


def candidate_dirs() -> list[Path]:
    """模型可能所在的位置，按优先级排列。

    做成"多候选探测"而不是一个写死的路径：同一份代码要在三种形态下跑 ——
    PyInstaller 打包后的核心、源码里直接跑、以及测试环境。任何单一写法都会
    在其中一种下找不到文件，而那种失败通常表现为"检索突然变差"而不是报错。
    """
    candidates: list[Path] = []

    override = _env_override()
    if override is not None:
        candidates.append(override)

    # 0) **用户按需下载的目录**（起模型不再随包，改成首启按需下载）：
    #    ``%APPDATA%/Soulmate Agent/models/qwen3-embedding-0.6b``。
    #    ⚠️ 与 ``voice/models.py`` 里那段**同源同规则**（含 ``AGENT_DATA_DIR`` 覆盖），
    #    两处必须一起改 —— 只改一处会出现"语音下好了、记忆还在找包里那份"。
    #    ⚠️ 这里同样不 import ``config.paths``：本模块在"核心还没初始化路径"时也会被
    #    单独 import（测试直接调 ``candidate_dirs``），依赖它会把初始化顺序搞成隐式约定。
    data_root = os.environ.get("AGENT_DATA_DIR", "").strip()
    if data_root:
        candidates.append(Path(data_root) / "models" / MODEL_DIRNAME)
    else:
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            candidates.append(Path(appdata) / "Soulmate Agent" / "models" / MODEL_DIRNAME)

    # 1) PyInstaller 打包后：sys._MEIPASS 指向 _internal，模型就放在它的 models/ 下。
    #    用 _MEIPASS 而不是靠 __file__ 往上数层级 —— 打包后模块在 PYZ 里，
    #    __file__ 的层级不一定和源码里一样，数层级是脆的。
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass) / "models" / MODEL_DIRNAME)

    here = Path(__file__).resolve()
    # 2) 源码里直接跑：<repo>/core/src/my_agent/memory/ -> <repo>/core/models/
    candidates.append(here.parents[3] / "models" / MODEL_DIRNAME)
    # 3) 兜底：沿目录往上找（覆盖其它打包形态）
    for parent in list(here.parents)[:8]:
        candidates.append(parent / "models" / MODEL_DIRNAME)

    return candidates


def find_model_dir() -> Path | None:
    """定位模型目录；找不到返回 None（调用方据此回落，而不是抛异常）。"""
    for path in candidate_dirs():
        if (path / "tokenizer.json").is_file() and (
            (path / _QUANTIZED).is_file() or (path / _FULL).is_file()
        ):
            return path
    return None


class LocalOnnxEmbedder:
    """内置模型的嵌入实现（``Embedder`` 协议：``list[str] -> list[list[float]]``）。

    **构造是廉价的、加载是惰性的**：模型有 585MB，启动时无条件加载会让冷启动
    多等好几秒，而很多用户根本没开长期记忆。第一次真正要嵌入时才加载。
    """

    def __init__(self, model_dir: Path, *, max_length: int = 8192) -> None:
        # 官方支持 32k，但本地 CPU 上 8k 已经够用，再长只是白等（注意力是平方的）。
        # 上限留在这里是为了防止一条超长文本把单次嵌入拖成几十秒。
        self.model_dir = Path(model_dir)
        self.max_length = max_length
        self._session: Any = None
        self._tokenizer: Any = None
        self._input_names: list[str] = []
        # 需要喂零长度缓存的输入名（这个导出带了 KV 缓存，见模块开头的说明）
        self._cache_inputs: list[Any] = []
        # 空缓存按 batch 缓存一份：每次调用新建 56 个数组不值当
        self._empty_cache: dict[int, dict[str, Any]] = {}
        self._output_name = "last_hidden_state"

    # ------------------------------------------------------------------ #
    # 惰性加载
    # ------------------------------------------------------------------ #
    def _ensure_loaded(self) -> None:
        if self._session is not None:
            return

        # 函数内导入：让"没开记忆的用户"完全不付这两个库的导入代价
        # （onnxruntime 的导入本身就要几百毫秒）
        import onnxruntime
        from tokenizers import Tokenizer

        model_path = self.model_dir / _QUANTIZED
        if not model_path.is_file():
            model_path = self.model_dir / _FULL

        options = onnxruntime.SessionOptions()
        # 别把整机占满：默认会按物理核数开线程，而用户那边可能还在跑别的程序
        options.intra_op_num_threads = min(_MAX_THREADS, os.cpu_count() or _MAX_THREADS)
        options.inter_op_num_threads = 1
        # 推理图优化到最高，代价是加载时多花一点时间（一次性）
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL

        logger.info("加载本地嵌入模型：%s", model_path)
        self._session = onnxruntime.InferenceSession(
            str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._input_names = [item.name for item in self._session.get_inputs()]
        self._cache_inputs = [item for item in self._session.get_inputs() if _is_cache_input(item)]
        # 输出按名字取：这个导出会返回 57 个张量，我们只要其中一个
        output_names = [item.name for item in self._session.get_outputs()]
        if self._output_name not in output_names:
            logger.warning("模型输出里没有 %s，退回取第一个输出", self._output_name)
            self._output_name = output_names[0]

        tokenizer = Tokenizer.from_file(str(self.model_dir / "tokenizer.json"))
        tokenizer.enable_truncation(max_length=self.max_length)
        # 必须左填充：模型取的是最后一个真实 token 的隐状态，右填充会让短句取到填充位
        padding = tokenizer.padding
        tokenizer.enable_padding(
            direction="left",
            pad_id=padding.get("pad_id", 151643) if isinstance(padding, dict) else 151643,
            pad_token=padding.get("pad_token", "<|endoftext|>")
            if isinstance(padding, dict)
            else "<|endoftext|>",
        )
        self._tokenizer = tokenizer
        logger.info("本地嵌入模型就绪（输入 %s）", self._input_names)

    # ------------------------------------------------------------------ #
    # 嵌入
    # ------------------------------------------------------------------ #
    def __call__(self, texts: list[str]) -> list[list[float]]:
        """文档侧：原文直接嵌入（不加指令前缀）。"""
        return self._embed(list(texts), with_instruction=False)

    def embed_query(self, texts: list[str]) -> list[list[float]]:
        """查询侧：加指令前缀。

        官方用法，缺了它检索仍然能跑、只是召回率低一截 —— 属于"不报错但更差"，
        所以宁可在这里多写几行。
        """
        return self._embed(list(texts), with_instruction=True)

    def _embed(self, texts: list[str], *, with_instruction: bool) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_loaded()

        import numpy as np

        prepared = [
            f"Instruct: {QUERY_INSTRUCTION}\nQuery: {text}" if with_instruction else text
            for text in texts
        ]
        encodings = self._tokenizer.encode_batch(prepared)

        ids = np.asarray([item.ids for item in encodings], dtype=np.int64)
        mask = np.asarray([item.attention_mask for item in encodings], dtype=np.int64)

        feeds: dict[str, Any] = {
            "input_ids": ids,
            "attention_mask": mask,
            # 这个导出要求显式的 position_ids（带左填充时不能省）
            "position_ids": np.tile(
                np.arange(ids.shape[1], dtype=np.int64), (ids.shape[0], 1)
            ),
        }
        feeds.update(self._empty_cache_for(ids.shape[0]))

        # 按名字只取 last_hidden_state：不这么做会把 56 个 present.* 缓存也物化出来
        outputs = self._session.run([self._output_name], feeds)
        hidden = outputs[0]

        vectors = self._last_token_pool(hidden, mask)
        return self._normalize(vectors)

    def _empty_cache_for(self, batch: int) -> dict[str, Any]:
        """零长度 KV 缓存（按 batch 缓存一份，避免每次调用重建几十个数组）。"""
        cached = self._empty_cache.get(batch)
        if cached is not None:
            return cached

        import numpy as np

        feeds: dict[str, Any] = {}
        for item in self._cache_inputs:
            dtype = _NUMPY_TYPES.get(item.type, "float32")
            feeds[item.name] = np.zeros(_empty_cache_shape(item.shape, batch), dtype=dtype)
        # 只留最近用过的批大小：批大小种类很少，但真出现极端值时不该无限占内存
        self._empty_cache = {batch: feeds}
        return feeds

    @staticmethod
    def _last_token_pool(hidden: Any, mask: Any) -> Any:
        """取每行**最后一个真实 token** 的隐状态。

        逐行算而不是取 ``[:, -1]``：批量里长度不一时会填充，简单取末位可能取到
        填充位。用 mask 逐行定位，左右填充都不会错。
        """
        import numpy as np

        rows = []
        for index in range(hidden.shape[0]):
            positions = np.flatnonzero(mask[index])
            last = int(positions[-1]) if positions.size else hidden.shape[1] - 1
            rows.append(hidden[index, last])
        return np.asarray(rows, dtype=np.float32)

    @staticmethod
    def _normalize(vectors: Any) -> list[list[float]]:
        """L2 归一化。单位向量上的 L2 距离与余弦相似度等价，chromadb 两种度量都能用。"""
        import numpy as np

        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        # 全零向量（理论上不会出现）会让除法产生 NaN，这里兜一下，
        # 否则一个 NaN 会顺着距离计算污染整个检索结果
        norms[norms == 0] = 1.0
        return (vectors / norms).astype(np.float32).tolist()

    @property
    def dimension(self) -> int:
        """向量维度（来自模型配置，供自检与文档使用）。"""
        self._ensure_loaded()
        for output in self._session.get_outputs():
            shape = output.shape
            if len(shape) == 3 and isinstance(shape[-1], int):
                return int(shape[-1])
        return 1024


def build_local_embedder() -> LocalOnnxEmbedder | None:
    """按需构建内置嵌入；模型不在就返回 None（调用方据此回落，而不是崩）。"""
    model_dir = find_model_dir()
    if model_dir is None:
        logger.warning(
            "未找到内置嵌入模型（%s）。长期记忆将回落到 chromadb 自带模型 —— "
            "该模型是英文的、且首次使用需要联网下载。",
            MODEL_DIRNAME,
        )
        return None
    try:
        return LocalOnnxEmbedder(model_dir)
    except Exception:  # noqa: BLE001 - 模型坏了不该拦住整个应用启动
        logger.exception("内置嵌入模型加载失败，已回落到默认嵌入")
        return None


__all__ = [
    "MODEL_DIRNAME",
    "QUERY_INSTRUCTION",
    "LocalOnnxEmbedder",
    "build_local_embedder",
    "candidate_dirs",
    "find_model_dir",
]

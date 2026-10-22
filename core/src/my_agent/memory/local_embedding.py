






















































from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


MODEL_DIRNAME = "qwen3-embedding-0.6b"

_QUANTIZED = "onnx/model_quantized.onnx"
_FULL = "onnx/model.onnx"



QUERY_INSTRUCTION = "给定一段用户提问，检索出与之相关的事实、资料或历史对话"


_MAX_THREADS = 4


_NUMPY_TYPES: dict[str, str] = {
    "tensor(float)": "float32",
    "tensor(float16)": "float16",
    "tensor(double)": "float64",
    "tensor(int64)": "int64",
    "tensor(int32)": "int32",
}


def _is_cache_input(item: Any) -> bool:

    return item.name.startswith("past_key_values")


def _empty_cache_shape(declared: Any, batch: int) -> list[int]:






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






    candidates: list[Path] = []

    override = _env_override()
    if override is not None:
        candidates.append(override)

    
    
    
    
    
    
    data_root = os.environ.get("AGENT_DATA_DIR", "").strip()
    if data_root:
        candidates.append(Path(data_root) / "models" / MODEL_DIRNAME)
    else:
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            candidates.append(Path(appdata) / "Soulmate Agent" / "models" / MODEL_DIRNAME)

    
    
    
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass) / "models" / MODEL_DIRNAME)

    here = Path(__file__).resolve()
    
    candidates.append(here.parents[3] / "models" / MODEL_DIRNAME)
    
    for parent in list(here.parents)[:8]:
        candidates.append(parent / "models" / MODEL_DIRNAME)

    return candidates


def find_model_dir() -> Path | None:

    for path in candidate_dirs():
        if (path / "tokenizer.json").is_file() and (
            (path / _QUANTIZED).is_file() or (path / _FULL).is_file()
        ):
            return path
    return None


class LocalOnnxEmbedder:






    def __init__(self, model_dir: Path, *, max_length: int = 8192) -> None:
        
        
        self.model_dir = Path(model_dir)
        self.max_length = max_length
        self._session: Any = None
        self._tokenizer: Any = None
        self._input_names: list[str] = []
        
        self._cache_inputs: list[Any] = []
        
        self._empty_cache: dict[int, dict[str, Any]] = {}
        self._output_name = "last_hidden_state"

    
    
    
    def _ensure_loaded(self) -> None:
        if self._session is not None:
            return

        
        
        import onnxruntime
        from tokenizers import Tokenizer

        model_path = self.model_dir / _QUANTIZED
        if not model_path.is_file():
            model_path = self.model_dir / _FULL

        options = onnxruntime.SessionOptions()
        
        options.intra_op_num_threads = min(_MAX_THREADS, os.cpu_count() or _MAX_THREADS)
        options.inter_op_num_threads = 1
        
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL

        logger.info("加载本地嵌入模型：%s", model_path)
        self._session = onnxruntime.InferenceSession(
            str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._input_names = [item.name for item in self._session.get_inputs()]
        self._cache_inputs = [item for item in self._session.get_inputs() if _is_cache_input(item)]
        
        output_names = [item.name for item in self._session.get_outputs()]
        if self._output_name not in output_names:
            logger.warning("模型输出里没有 %s，退回取第一个输出", self._output_name)
            self._output_name = output_names[0]

        tokenizer = Tokenizer.from_file(str(self.model_dir / "tokenizer.json"))
        tokenizer.enable_truncation(max_length=self.max_length)
        
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

    
    
    
    def __call__(self, texts: list[str]) -> list[list[float]]:

        return self._embed(list(texts), with_instruction=False)

    def embed_query(self, texts: list[str]) -> list[list[float]]:





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
            
            "position_ids": np.tile(
                np.arange(ids.shape[1], dtype=np.int64), (ids.shape[0], 1)
            ),
        }
        feeds.update(self._empty_cache_for(ids.shape[0]))

        
        outputs = self._session.run([self._output_name], feeds)
        hidden = outputs[0]

        vectors = self._last_token_pool(hidden, mask)
        return self._normalize(vectors)

    def _empty_cache_for(self, batch: int) -> dict[str, Any]:

        cached = self._empty_cache.get(batch)
        if cached is not None:
            return cached

        import numpy as np

        feeds: dict[str, Any] = {}
        for item in self._cache_inputs:
            dtype = _NUMPY_TYPES.get(item.type, "float32")
            feeds[item.name] = np.zeros(_empty_cache_shape(item.shape, batch), dtype=dtype)
        
        self._empty_cache = {batch: feeds}
        return feeds

    @staticmethod
    def _last_token_pool(hidden: Any, mask: Any) -> Any:





        import numpy as np

        rows = []
        for index in range(hidden.shape[0]):
            positions = np.flatnonzero(mask[index])
            last = int(positions[-1]) if positions.size else hidden.shape[1] - 1
            rows.append(hidden[index, last])
        return np.asarray(rows, dtype=np.float32)

    @staticmethod
    def _normalize(vectors: Any) -> list[list[float]]:

        import numpy as np

        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        
        
        norms[norms == 0] = 1.0
        return (vectors / norms).astype(np.float32).tolist()

    @property
    def dimension(self) -> int:

        self._ensure_loaded()
        for output in self._session.get_outputs():
            shape = output.shape
            if len(shape) == 3 and isinstance(shape[-1], int):
                return int(shape[-1])
        return 1024


def build_local_embedder() -> LocalOnnxEmbedder | None:

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
    except Exception:  
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

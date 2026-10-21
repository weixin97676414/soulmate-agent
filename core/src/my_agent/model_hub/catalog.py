
























from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Line = Literal["cn", "seoul"]


MODELSCOPE = "https://modelscope.cn/models/{repo}/resolve/master/{path}"

HUGGINGFACE = "https://huggingface.co/{repo}/resolve/main/{path}"


LINE_TITLES: dict[str, str] = {"cn": "国内", "seoul": "国外"}


def other_line(line: Line) -> Line:







    return "seoul" if line == "cn" else "cn"


def line_title(line: str | None) -> str:

    key = (line or "").strip().lower()
    return LINE_TITLES.get(key, key)


@dataclass(frozen=True)
class ModelFile:


    
    path: str
    
    size: int


@dataclass(frozen=True)
class ModelSpec:


    
    key: str
    
    title: str
    
    dirname: str
    
    
    
    
    
    
    
    
    subdir: str
    
    summary: str
    
    requirement: str
    
    cn_repo: str
    
    seoul_repo: str
    
    files: tuple[ModelFile, ...]

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.files)

    def url_for(self, line: Line, rel_path: str) -> str:

        if line == "cn":
            return MODELSCOPE.format(repo=self.cn_repo, path=rel_path)
        return HUGGINGFACE.format(repo=self.seoul_repo, path=rel_path)




VOICE = ModelSpec(
    key="voice",
    title="语音识别",
    dirname="sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17",
    
    subdir="voice",
    
    
    summary="本地语音识别（中 / 英 / 日 / 韩 / 粤）。",
    requirement="约 0.3 GB 磁盘 · 双核以上 CPU · 建议 8 GB 内存（识别在本机跑，不上传录音）",
    cn_repo="pengzhendong/sherpa-onnx-sense-voice-zh-en-ja-ko-yue",
    seoul_repo="csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
    files=(
        ModelFile("model.int8.onnx", 239_233_841),
        ModelFile("tokens.txt", 315_894),
    ),
)














EMBEDDING = ModelSpec(
    key="embedding",
    title="长期记忆",
    dirname="qwen3-embedding-0.6b",
    
    subdir="",
    summary="本地向量化（1024 维，中文效果好）。",
    requirement="约 0.6 GB 磁盘 · 四核以上 CPU · 建议 8 GB 内存（建索引时会短时占满 CPU）",
    cn_repo="onnx-community/Qwen3-Embedding-0.6B-ONNX",
    seoul_repo="onnx-community/Qwen3-Embedding-0.6B-ONNX",
    files=(
        ModelFile("config.json", 1_576),
        ModelFile("tokenizer_config.json", 9_731),
        ModelFile("tokenizer.json", 11_423_705),
        ModelFile("onnx/model_quantized.onnx", 613_527_631),
    ),
)


ALL: tuple[ModelSpec, ...] = (VOICE, EMBEDDING)

_BY_KEY = {item.key: item for item in ALL}


def get(key: str) -> ModelSpec | None:

    return _BY_KEY.get(key)


def keys() -> tuple[str, ...]:
    return tuple(_BY_KEY)

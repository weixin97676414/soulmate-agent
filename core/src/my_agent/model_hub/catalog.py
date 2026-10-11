"""本地模型的**清单**：每个模型要下哪些文件、从哪两个源下、多大。

## 为什么要有这一层

语音模型与嵌入模型都要"按线路选源"，而且**两条线路的文件必须逐字节一致** ——
否则会出现"大陆用户和首尔用户跑的是不同模型"这种没法复现的差异。

所以这里只写**一份**文件清单（相对路径 + 字节数），两套源地址由 ``base_url`` 拼出来。
字节数不是装饰：它是**下载完的校验依据**（下完对不上就是坏了），也是**进度条的分母**
（拿不到远端 Content-Length 时的兜底）。

## 源是怎么选的（实测）

| 模型 | 国内（cn） | 国外（seoul） |
|---|---|---|
| 语音 | ModelScope `pengzhendong/sherpa-onnx-sense-voice-zh-en-ja-ko-yue` | HuggingFace `csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17` |
| 嵌入 | ModelScope `onnx-community/Qwen3-Embedding-0.6B-ONNX` | HuggingFace `onnx-community/Qwen3-Embedding-0.6B-ONNX` |

⚠️ **两条线路的同一文件实测字节数完全相同**（语音 239,233,841 / 315,894；嵌入 613,527,631 …），
所以共用一份清单是安全的。

⚠️ **ModelScope 的大文件必须带 User-Agent**：不带一律返回 **403**（一个 HTML 拦截页，
不是 404 —— 容易被误读成"源没了"）。这条坑是在实测里踩出来的，见 ``downloader.py``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: 线路。与 ``config/lines.py`` 的取值保持一致（``cn`` = 大陆、``seoul`` = 首尔）。
Line = Literal["cn", "seoul"]

#: 国内源用的下载地址前缀（ModelScope 的 ``resolve`` 形式，逐文件）。
MODELSCOPE = "https://modelscope.cn/models/{repo}/resolve/master/{path}"
#: 国外源（HuggingFace 的 ``resolve`` 形式，逐文件）。
HUGGINGFACE = "https://huggingface.co/{repo}/resolve/main/{path}"

#: 线路的展示名（给界面用；``downloader`` 回退时也拿它组文案）。
LINE_TITLES: dict[str, str] = {"cn": "国内", "seoul": "国外"}


def other_line(line: Line) -> Line:
    """另一条线路 —— **主源失败时自动回退**用的（2026-10-08 用户确认要做）。

    只有两条线路，所以"另一条"是确定的。为什么要这个函数而不是在下载器里写
    ``"seoul" if line == "cn" else "cn"``：将来真加了第三条线路时，
    漏改一处就会变成"回退到自己"（表现为**无限重试同一条线路**，
    而两条线路都在时又看不出问题），所以把这件事收在一个地方。
    """
    return "seoul" if line == "cn" else "cn"


def line_title(line: str | None) -> str:
    """线路的展示名（不认识的线路原样返回，不抛错）。"""
    key = (line or "").strip().lower()
    return LINE_TITLES.get(key, key)


@dataclass(frozen=True)
class ModelFile:
    """模型里要下载的一个文件。"""

    #: 相对模型目录的路径（含子目录，如 ``onnx/model_quantized.onnx``）
    path: str
    #: 实测字节数。用于**校验**与**进度分母**（两条线路一致，已实测核对）
    size: int


@dataclass(frozen=True)
class ModelSpec:
    """一个可下载的本地模型。"""

    #: 内部 id（接口与前端用它，不随语言变）
    key: str
    #: 展示名
    title: str
    #: 落盘目录名（与随包时代的 ``models/<subdir>/<这里>`` **逐字一致**）
    dirname: str
    #: 落盘时多出来的**一层子目录**（语音是 ``voice``、嵌入是空）。
    #
    # ⚠️ 这一层不是可选的装饰：读取侧**就是这么找的** ——
    # ``voice/models.py::candidate_roots()`` 返回的是 ``models/voice``，
    # 再拼 ``dirname``；而嵌入那边 ``models/qwen3-embedding-0.6b`` 没有中间层。
    # 少了它，228MB 下完也永远用不了（读取侧找不到目录，自检必然失败），
    # 而界面上只会显示"模型装好了、但加载不起来" —— 没人想得到是差一层目录。
    # 判据在 `tests/unit/test_model_hub.py` 里用"下载目录 == 读取侧要找的目录"钉住。
    subdir: str
    #: 一句话说明它干什么用的
    summary: str
    #: 需要的电脑配置（首页要写明；文案来自实测与官方的保守估计）
    requirement: str
    #: 国内源仓库
    cn_repo: str
    #: 国外源仓库
    seoul_repo: str
    #: 要下的文件
    files: tuple[ModelFile, ...]

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.files)

    def url_for(self, line: Line, rel_path: str) -> str:
        """按线路拼出某个文件的下载地址。"""
        if line == "cn":
            return MODELSCOPE.format(repo=self.cn_repo, path=rel_path)
        return HUGGINGFACE.format(repo=self.seoul_repo, path=rel_path)


#: 语音模型：SenseVoice-Small（中/英/日/韩/粤 + 情感与音频事件）。
#: ⚠️ 只要 **int8** 那一份（228MB）：fp32 是 937MB，纯浪费。
VOICE = ModelSpec(
    key="voice",
    title="语音识别",
    dirname="sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17",
    # ⚠️ 语音多一层 `voice/`（`voice/models.py::VOICE_SUBDIR`），嵌入没有
    subdir="voice",
    # ⚠️ 产品要求**删掉**原来后半句"不装就用不了语音对话与语音命令"：
    # 那句话写的是事实，但它出现在"还没装"的时刻，读起来像在劝退。
    summary="本地语音识别（中 / 英 / 日 / 韩 / 粤）。",
    requirement="约 0.3 GB 磁盘 · 双核以上 CPU · 建议 8 GB 内存（识别在本机跑，不上传录音）",
    cn_repo="pengzhendong/sherpa-onnx-sense-voice-zh-en-ja-ko-yue",
    seoul_repo="csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
    files=(
        ModelFile("model.int8.onnx", 239_233_841),
        ModelFile("tokens.txt", 315_894),
    ),
)

#: 长期记忆用的嵌入模型。
#
# ⚠️ ``summary`` 只留"本地向量化（1024 维，中文效果好）"这一句。
#
# 这里**曾经**还有一句"不装会回落到自带的英文模型（首次需联网、中文检索较差）"，
# 产品要求删掉。要把两件事分开看，别把删句子理解成"行为变了"：
#
# - **句子的去留**：产品明确要求剔除，因为它出现在"还没装"的时刻，
#   读起来像在劝退；删掉之后**界面上不再提示这件事**。
# - **回落行为本身没变**：不装中文模型时，长期记忆**不会直接消失**，而是回落到
#   chromadb 自带的英文模型 ``all-MiniLM-L6-v2``（见 ``runtime._build_builtin_embedder``
#   里那条"至少能用"的兜底，**首次使用要联网下载约 79MB**，中文语义很差）。
#   它不随我们的安装包分发，是 chromadb 自己的东西。
EMBEDDING = ModelSpec(
    key="embedding",
    title="长期记忆",
    dirname="qwen3-embedding-0.6b",
    # 嵌入模型直接在 `models/` 下，没有中间层（`local_embedding.MODEL_DIRNAME`）
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

#: 全部模型（顺序 = 界面上的顺序：先语音、后长期记忆）
ALL: tuple[ModelSpec, ...] = (VOICE, EMBEDDING)

_BY_KEY = {item.key: item for item in ALL}


def get(key: str) -> ModelSpec | None:
    """按 id 取模型；不存在的返回 ``None``（调用方给出 404，不要抛异常穿透）。"""
    return _BY_KEY.get(key)


def keys() -> tuple[str, ...]:
    return tuple(_BY_KEY)

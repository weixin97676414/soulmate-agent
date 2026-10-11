"""本地模型下载（语音 / 嵌入 2026-10-08 起改为按需下载）。

这批用例钉住三件事，都是**用户看得见**的行为：

1. **两条线路的地址是对的**（国内 ModelScope / 国外 HuggingFace，逐文件路径）；
2. **主源失败会自动换另一条线路重试一次**，并且如实上报 `fallback_used`
   —— 静默换源会让用户以为"我选的国内源其实能用"；
3. **不重复下载已经下好的文件**（回退重来时进度不能算两遍、585MB 不能下第二遍）。

⚠️ 全程不联网、不写真实字节量：真模型几百 MB，用例里用一份 4 + 8 字节的假清单
（`catalog` 被整体替换成"只有这个小模型"的包）。这里验的是**逻辑**，
与文件多大无关。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import HTTPException

from my_agent.model_hub import catalog, routes
from my_agent.model_hub import downloader as downloader_mod
from my_agent.model_hub.downloader import (
    STATE_CANCELLED,
    STATE_DONE,
    STATE_FAILED,
    STATE_IDLE,
    DownloadCancelled,
    ModelDownloader,
)


def tiny_spec(*, subdir: str = "") -> catalog.ModelSpec:
    """一份"小模型"。``dirname`` 与真实模型无关，用例只看逻辑。"""
    return catalog.ModelSpec(
        key="voice",
        title="测试模型",
        dirname="tiny-model",
        subdir=subdir,
        summary="用例用的小模型",
        requirement="约 0 字节",
        cn_repo="cn/repo",
        seoul_repo="seoul/repo",
        files=(catalog.ModelFile("a.bin", 4), catalog.ModelFile("sub/b.bin", 8)),
    )


@pytest.fixture
def pack(monkeypatch):
    """把 `catalog` 换成"只有一个小模型"的包。

    ⚠️ 只 patch 函数（`get` / `keys`），**不动** `VOICE` / `EMBEDDING` 那两个常量：
    改常量会让"真实清单里的字节数"这类断言失去意义。
    """
    spec = tiny_spec()
    monkeypatch.setattr(catalog, "get", lambda key: spec if key == spec.key else None)
    monkeypatch.setattr(catalog, "keys", lambda: (spec.key,))
    return spec


def make_downloader(tmp_path: Path) -> ModelDownloader:
    return ModelDownloader(tmp_path)


async def run(dl: ModelDownloader, key: str = "voice", line: str = "cn") -> None:
    """起一次下载并等它跑完（`start` 只负责建任务，不等）。"""
    await dl.start(key, line)
    task = dl._jobs[key].task
    assert task is not None
    await task


# --------------------------------------------------------------------------- #
# 清单与地址
# --------------------------------------------------------------------------- #


def test_两条线路指向不同的仓库但路径逐文件相同():
    voice = catalog.VOICE
    cn = voice.url_for("cn", "model.int8.onnx")
    seoul = voice.url_for("seoul", "model.int8.onnx")
    assert cn == (
        "https://modelscope.cn/models/pengzhendong/sherpa-onnx-sense-voice-zh-en-ja-ko-yue"
        "/resolve/master/model.int8.onnx"
    )
    assert seoul == (
        "https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
        "/resolve/main/model.int8.onnx"
    )
    # 子目录路径也要原样拼上（嵌入模型是 onnx/model_quantized.onnx）
    assert catalog.EMBEDDING.url_for("cn", "onnx/model_quantized.onnx").endswith(
        "/resolve/master/onnx/model_quantized.onnx"
    )


def test_另一条线路是取反的():
    assert catalog.other_line("cn") == "seoul"
    assert catalog.other_line("seoul") == "cn"
    # 回退绝不能"退回自己"（那会变成无限重试同一条线路）
    assert catalog.other_line(catalog.other_line("cn")) == "cn"


def test_语音只要int8那一份():
    """fp32 是 937MB、int8 是 228MB —— 清单里只能有后者。"""
    paths = [item.path for item in catalog.VOICE.files]
    assert paths == ["model.int8.onnx", "tokens.txt"]
    assert catalog.VOICE.total_bytes == 239_233_841 + 315_894


# --------------------------------------------------------------------------- #
# 下载器
# --------------------------------------------------------------------------- #


async def test_没下过时状态是未安装(pack, tmp_path):
    dl = make_downloader(tmp_path)
    status = dl.status("voice")
    assert status["state"] == STATE_IDLE
    assert status["installed"] is False
    assert status["fallback_used"] is False
    assert status["total_bytes"] == 12


async def test_文件齐且长度对就算已安装(pack, tmp_path):
    base = tmp_path / "tiny-model"
    (base / "sub").mkdir(parents=True)
    (base / "a.bin").write_bytes(b"abcd")
    (base / "sub" / "b.bin").write_bytes(b"12345678")
    dl = make_downloader(tmp_path)
    assert dl.status("voice")["installed"] is True
    assert dl.status("voice")["state"] == STATE_DONE
    # 已经装好了就不该再下一次（585MB 重下是用户最不能接受的事之一）
    assert (await dl.start("voice", "cn"))["reason"] == "already-installed"


async def test_长度对不上不算已安装(pack, tmp_path):
    base = tmp_path / "tiny-model"
    (base / "sub").mkdir(parents=True)
    (base / "a.bin").write_bytes(b"ab")  # 只有 2 字节，清单要 4
    (base / "sub" / "b.bin").write_bytes(b"12345678")
    assert make_downloader(tmp_path).status("voice")["installed"] is False


async def test_已下好的文件不重复下载(pack, tmp_path):
    base = tmp_path / "tiny-model"
    base.mkdir(parents=True)
    (base / "a.bin").write_bytes(b"abcd")
    dl = make_downloader(tmp_path)
    fetched: list[str] = []

    async def fetch(spec, job, item, target):
        fetched.append(item.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x" * item.size)
        # ⚠️ 桩**必须**照做真实 `_fetch_one` 的记账（它是"每块 +len"，
        # 这里按整份一次加）—— 不记账的话下面那条进度断言就什么都没验
        # （真实代码是 `job.done_bytes = baseline + done` 再逐块累加）。
        job.done_bytes += item.size
        job.files[item.path] = item.size

    dl._fetch_one = fetch  # type: ignore[method-assign]
    await run(dl)
    assert fetched == ["sub/b.bin"]
    # 进度里要把"之前就算好"的那 4 字节算上，否则百分比会从 0 开始跳回去
    assert dl.status("voice")["done_bytes"] == 12


async def test_主源失败自动切备用线路且进度不重复计数(pack, tmp_path):
    dl = make_downloader(tmp_path)
    tried: list[tuple[str, str]] = []

    async def fetch(spec, job, item, target):
        tried.append((job.line, item.path))
        # 国内源把第一个文件下完、第二个文件 403 —— 真实故障里常见的样子
        if job.line == "cn" and item.path == "sub/b.bin":
            raise RuntimeError("403 Forbidden")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x" * item.size)
        # 与真实 `_fetch_one` 同一套记账（见上一条用例的说明）
        job.done_bytes += item.size
        job.files[item.path] = item.size

    dl._fetch_one = fetch  # type: ignore[method-assign]
    await run(dl, line="cn")

    status = dl.status("voice")
    assert status["state"] == STATE_DONE
    assert status["installed"] is True
    assert status["fallback_used"] is True, "换了源必须如实上报"
    assert status["line"] == "seoul"
    # 备用线路只重下失败的那份（第一份已经完好）
    assert tried == [("cn", "a.bin"), ("cn", "sub/b.bin"), ("seoul", "sub/b.bin")]
    # ⚠️ 进度不能把 a.bin 算两遍 —— 累加式记账会让进度条冲到 200%
    assert status["done_bytes"] == 12


async def test_两条线路都失败就是失败且只回退一次(pack, tmp_path):
    dl = make_downloader(tmp_path)
    attempts: list[str] = []

    async def always_fail(spec, job, item, target):
        attempts.append(job.line)
        raise RuntimeError("boom")

    dl._fetch_one = always_fail  # type: ignore[method-assign]
    await run(dl, line="cn")

    status = dl.status("voice")
    assert status["state"] == STATE_FAILED
    assert "boom" in status["error"]
    assert status["fallback_used"] is True
    # **只回退一次**：两条都失败就停，否则源整个挂掉时会互相无限重试
    assert attempts == ["cn", "seoul"]


async def test_取消后停在cancelled且已下的部分留着(pack, tmp_path):
    dl = make_downloader(tmp_path)

    async def fetch_then_cancel(spec, job, item, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x" * item.size)
        job.cancel.set()  # 模拟"用户在第一份下完后点了取消"

    dl._fetch_one = fetch_then_cancel  # type: ignore[method-assign]
    await run(dl)

    status = dl.status("voice")
    assert status["state"] == STATE_CANCELLED
    assert status["fallback_used"] is False, "取消不是失败，不该被当成换过源"
    # 取消**不删**已下好的文件（下次点下载接着下）
    assert (tmp_path / "tiny-model" / "a.bin").is_file()


async def test_取消不在跑的任务是幂等的(pack, tmp_path):
    dl = make_downloader(tmp_path)
    result = await dl.cancel("voice")
    assert result["ok"] is False and result["reason"] == "not-running"
    # 不认识的模型 id 也不抛异常（交给路由给 404）
    assert (await dl.start("nope", "cn"))["reason"] == "unknown-model"


async def test_关闭时会等下载任务真的退出(pack, tmp_path):
    dl = make_downloader(tmp_path)
    waiting = asyncio.Event()

    async def patient_fetch(spec, job, item, target):
        waiting.set()
        await job.cancel.wait()  # 取消旗一立就返回（不会真的等下去）
        raise DownloadCancelled

    dl._fetch_one = patient_fetch  # type: ignore[method-assign]
    await dl.start("voice", "cn")
    await waiting.wait()
    await dl.shutdown()
    assert dl._jobs["voice"].task is not None
    assert dl._jobs["voice"].task.done(), "shutdown 必须等它真的退出，不能只立个旗"


# --------------------------------------------------------------------------- #
# 落盘位置 == 读取侧要找的位置（本次最容易错、错了又最难查的一处）
# --------------------------------------------------------------------------- #


def test_语音模型的落盘位置就是读取侧要找的位置(monkeypatch, tmp_path):
    """⚠️ 语音是 `models/**voice**/<名>`、嵌入是 `models/<名>` —— 差这一层就完了。

    差一层的表现：228MB 下完了、卡片显示"装好了、但加载不起来"，
    而**运行时**也永远找不到模型（`voice/models.py::find_model_dir` 只认
    `models/voice/...`）⇒ 语音功能永远不可用，且没有任何地方会说是路径问题。

    这条断言不看注释、不看约定，只比对**两边的真实拼法**：
    下载器的目标目录 vs 语音读取侧会命中的目录。
    """
    from my_agent.config.paths import AppPaths
    from my_agent.voice import models as voice_models

    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    monkeypatch.delenv(voice_models.ENV_VOICE_DIR, raising=False)
    paths = AppPaths.resolve()
    target = downloader_mod._target_dir(paths.models_dir, catalog.VOICE)

    target.mkdir(parents=True)
    (target / "model.int8.onnx").write_bytes(b"x")
    (target / "tokens.txt").write_bytes(b"y")

    found = voice_models.find_model_dir(catalog.VOICE.dirname)
    assert found is not None, "读取侧找不到下载器写出来的目录 —— 十有八九是少了一层 voice/"
    assert found.resolve() == target.resolve()


def test_嵌入模型的落盘位置就是读取侧要找的位置(monkeypatch, tmp_path):
    """嵌入这边**没有**中间层（`models/qwen3-embedding-0.6b`），同样要钉住。"""
    from my_agent.config.paths import AppPaths
    from my_agent.memory import local_embedding

    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AGENT_EMBEDDING_MODEL_DIR", raising=False)
    paths = AppPaths.resolve()
    target = downloader_mod._target_dir(paths.models_dir, catalog.EMBEDDING)

    (target / "onnx").mkdir(parents=True)
    (target / "tokenizer.json").write_bytes(b"x")
    (target / "onnx" / "model_quantized.onnx").write_bytes(b"y")

    found = local_embedding.find_model_dir()
    assert found is not None
    assert found.resolve() == target.resolve()
    assert local_embedding.MODEL_DIRNAME == catalog.EMBEDDING.dirname


async def test_语音落盘会带上voice这一层子目录(monkeypatch, tmp_path):
    """上面那条比的是"拼法"，这条比的是**真的写到哪里**（写入路径也要对）。"""
    spec = tiny_spec(subdir="voice")
    monkeypatch.setattr(catalog, "get", lambda key: spec if key == spec.key else None)
    patch_transport(monkeypatch, {"a.bin": b"abcd", "sub/b.bin": b"12345678"})
    dl = make_downloader(tmp_path)
    await run(dl)
    assert dl.status("voice")["installed"] is True
    assert (tmp_path / "voice" / "tiny-model" / "a.bin").read_bytes() == b"abcd"
    assert (tmp_path / "voice" / "tiny-model" / "sub" / "b.bin").read_bytes() == b"12345678"


# --------------------------------------------------------------------------- #
# 真实下载链路（用假的 httpx，验"半截文件不能被当成下好了"）
# --------------------------------------------------------------------------- #


class _FakeStream:
    """假的 `client.stream(...)` 返回值：按 URL 供字节（可选模拟断点续传）。"""

    def __init__(self, body: bytes, status: int, headers: dict[str, str], url: str) -> None:
        self.status_code = status
        self._url = url
        if status == 206 and "Range" in headers:
            start = int(headers["Range"].split("=")[1].split("-")[0])
            body = body[start:]
        self._body = body

    async def __aenter__(self) -> _FakeStream:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", self._url),
                response=httpx.Response(self.status_code),
            )

    async def aiter_bytes(self, chunk_size: int):
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start : start + chunk_size]


class _FakeClient:
    """假的 `httpx.AsyncClient`：只实现下载器用到的那几个成员。"""

    def __init__(self, served: dict[str, bytes], *, fail: set[str] | None = None) -> None:
        self._served = served
        self._fail = fail or set()

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def stream(self, method: str, url: str, headers: dict[str, str] | None = None) -> _FakeStream:
        headers = headers or {}
        name = "sub/b.bin" if url.endswith("/b.bin") else "a.bin"
        if name in self._fail:
            return _FakeStream(b"", 403, headers, url)
        # 带 Range 就当服务端支持续传（206）—— 这也是真机上常见的一种响应
        return _FakeStream(self._served[name], 206 if "Range" in headers else 200, headers, url)


def patch_transport(monkeypatch, served: dict[str, bytes], *, fail: set[str] | None = None) -> None:
    """把下载器用的 HTTP 客户端工厂换成假的（用完由 monkeypatch 自动还原）。

    ⚠️ 替换的是 `utils/http.async_client` 而不是 `httpx.AsyncClient`：
    生产代码必须走那个工厂（每次裸建客户端要重建 SSL 上下文，Windows 上约 500ms，
    有静态闸钉着 —— 见 `test_http_client.py`）。
    """
    monkeypatch.setattr(
        "my_agent.model_hub.downloader.async_client",
        lambda **kwargs: _FakeClient(served, fail=fail),
    )


async def test_真实链路把字节落对且不残留part(pack, tmp_path, monkeypatch):
    patch_transport(monkeypatch, {"a.bin": b"abcd", "sub/b.bin": b"12345678"})
    dl = make_downloader(tmp_path)
    await run(dl)
    assert dl.status("voice")["state"] == STATE_DONE
    base = tmp_path / "tiny-model"
    assert (base / "a.bin").read_bytes() == b"abcd"
    assert (base / "sub" / "b.bin").read_bytes() == b"12345678"
    assert not list(base.rglob("*.part")), "下完必须没有 .part 残留"


async def test_字节数对不上当失败且不留半截文件(pack, tmp_path, monkeypatch):
    """远端给的字节比清单少（半截 / 拦截图）⇒ 必须报错，绝不能改名成正式文件。

    这正是"目录里有文件、长度不对"这一类静默故障的入口：改名成功了，
    读取方只判目录存在，用户就会遇到"明明装好了却用不了"。
    """
    patch_transport(monkeypatch, {"a.bin": b"ab", "sub/b.bin": b"12345678"})
    dl = make_downloader(tmp_path)
    await run(dl)
    status = dl.status("voice")
    assert status["state"] == STATE_FAILED
    assert "下载不完整" in status["error"]
    base = tmp_path / "tiny-model"
    assert not (base / "a.bin").exists()
    assert not list(base.rglob("*.part"))


async def test_part已完整时直接改名不再发请求(pack, tmp_path, monkeypatch):
    """上次在"写完、还没改名"那一刻被杀掉（关窗口 / 断电）会留下**完整**的 `.part`。

    这时照常发 `Range: bytes=<size>-` 会拿到 **416**，于是两条线路都判失败 ——
    而文件其实早就下好了。所以这种情况必须直接改名。
    """
    base = tmp_path / "tiny-model"
    base.mkdir(parents=True)
    (base / "a.bin.part").write_bytes(b"abcd")  # 完整的一份，只是还没改名
    patch_transport(monkeypatch, {"a.bin": b"abcd", "sub/b.bin": b"12345678"})
    dl = make_downloader(tmp_path)
    await run(dl)
    status = dl.status("voice")
    assert status["state"] == STATE_DONE
    assert status["done_bytes"] == 12
    assert (base / "a.bin").read_bytes() == b"abcd"
    assert not list(base.rglob("*.part"))


async def test_两处都给403时报失败并带原因(pack, tmp_path, monkeypatch):
    patch_transport(monkeypatch, {"a.bin": b"abcd"}, fail={"a.bin"})
    dl = make_downloader(tmp_path)
    await run(dl)
    status = dl.status("voice")
    assert status["state"] == STATE_FAILED
    assert "403" in status["error"]
    assert status["fallback_used"] is True


# --------------------------------------------------------------------------- #
# 路由（四个端点 + 参数校验）
# --------------------------------------------------------------------------- #


class _FakeRuntime:
    """只带路由真正读的两个东西：当前线路与下载器。

    这里**刻意不**起真的 `AppRuntime`：那要连数据库、装技能、建记忆，
    而本次的路由只依赖这两项（见 `model_hub/routes.py` 的 `_downloader`）。
    """

    def __init__(self, root: Path) -> None:
        self.line = "cn"
        self.model_downloader = ModelDownloader(root)


def _request(runtime: Any) -> Any:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=runtime)))


async def test_状态端点下发线路与两个模型(pack, tmp_path):
    payload = await routes.model_status(_request(_FakeRuntime(tmp_path)))
    assert payload["ok"] is True
    assert payload["line"] == "cn"
    assert payload["line_title"] == "国内"
    assert [item["key"] for item in payload["models"]] == ["voice"]


async def test_未知模型给404(pack, tmp_path):
    request = _request(_FakeRuntime(tmp_path))
    with pytest.raises(HTTPException) as exc:
        await routes.model_download(routes.DownloadPayload(key="nope"), request)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc2:
        await routes.model_verify(routes.KeyPayload(key="nope"), request)
    assert exc2.value.status_code == 404


async def test_未知线路给422而不是闷头按国外源去下(pack, tmp_path):
    request = _request(_FakeRuntime(tmp_path))
    with pytest.raises(HTTPException) as exc:
        await routes.model_download(routes.DownloadPayload(key="voice", line="mars"), request)
    assert exc.value.status_code == 422


async def test_校验没装时如实回答not_installed(pack, tmp_path):
    payload = await routes.model_verify(routes.KeyPayload(key="voice"), _request(_FakeRuntime(tmp_path)))
    assert payload["ok"] is False
    assert payload["reason"] == "not-installed"

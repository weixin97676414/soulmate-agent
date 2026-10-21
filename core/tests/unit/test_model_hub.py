













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





    spec = tiny_spec()
    monkeypatch.setattr(catalog, "get", lambda key: spec if key == spec.key else None)
    monkeypatch.setattr(catalog, "keys", lambda: (spec.key,))
    return spec


def make_downloader(tmp_path: Path) -> ModelDownloader:
    return ModelDownloader(tmp_path)


async def run(dl: ModelDownloader, key: str = "voice", line: str = "cn") -> None:

    await dl.start(key, line)
    task = dl._jobs[key].task
    assert task is not None
    await task







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
    
    assert catalog.EMBEDDING.url_for("cn", "onnx/model_quantized.onnx").endswith(
        "/resolve/master/onnx/model_quantized.onnx"
    )


def test_另一条线路是取反的():
    assert catalog.other_line("cn") == "seoul"
    assert catalog.other_line("seoul") == "cn"
    
    assert catalog.other_line(catalog.other_line("cn")) == "cn"


def test_语音只要int8那一份():

    paths = [item.path for item in catalog.VOICE.files]
    assert paths == ["model.int8.onnx", "tokens.txt"]
    assert catalog.VOICE.total_bytes == 239_233_841 + 315_894







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
    
    assert (await dl.start("voice", "cn"))["reason"] == "already-installed"


async def test_长度对不上不算已安装(pack, tmp_path):
    base = tmp_path / "tiny-model"
    (base / "sub").mkdir(parents=True)
    (base / "a.bin").write_bytes(b"ab")  
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
        
        
        
        job.done_bytes += item.size
        job.files[item.path] = item.size

    dl._fetch_one = fetch  
    await run(dl)
    assert fetched == ["sub/b.bin"]
    
    assert dl.status("voice")["done_bytes"] == 12


async def test_主源失败自动切备用线路且进度不重复计数(pack, tmp_path):
    dl = make_downloader(tmp_path)
    tried: list[tuple[str, str]] = []

    async def fetch(spec, job, item, target):
        tried.append((job.line, item.path))
        
        if job.line == "cn" and item.path == "sub/b.bin":
            raise RuntimeError("403 Forbidden")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x" * item.size)
        
        job.done_bytes += item.size
        job.files[item.path] = item.size

    dl._fetch_one = fetch  
    await run(dl, line="cn")

    status = dl.status("voice")
    assert status["state"] == STATE_DONE
    assert status["installed"] is True
    assert status["fallback_used"] is True, "换了源必须如实上报"
    assert status["line"] == "seoul"
    
    assert tried == [("cn", "a.bin"), ("cn", "sub/b.bin"), ("seoul", "sub/b.bin")]
    
    assert status["done_bytes"] == 12


async def test_两条线路都失败就是失败且只回退一次(pack, tmp_path):
    dl = make_downloader(tmp_path)
    attempts: list[str] = []

    async def always_fail(spec, job, item, target):
        attempts.append(job.line)
        raise RuntimeError("boom")

    dl._fetch_one = always_fail  
    await run(dl, line="cn")

    status = dl.status("voice")
    assert status["state"] == STATE_FAILED
    assert "boom" in status["error"]
    assert status["fallback_used"] is True
    
    assert attempts == ["cn", "seoul"]


async def test_取消后停在cancelled且已下的部分留着(pack, tmp_path):
    dl = make_downloader(tmp_path)

    async def fetch_then_cancel(spec, job, item, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x" * item.size)
        job.cancel.set()  

    dl._fetch_one = fetch_then_cancel  
    await run(dl)

    status = dl.status("voice")
    assert status["state"] == STATE_CANCELLED
    assert status["fallback_used"] is False, "取消不是失败，不该被当成换过源"
    
    assert (tmp_path / "tiny-model" / "a.bin").is_file()


async def test_取消不在跑的任务是幂等的(pack, tmp_path):
    dl = make_downloader(tmp_path)
    result = await dl.cancel("voice")
    assert result["ok"] is False and result["reason"] == "not-running"
    
    assert (await dl.start("nope", "cn"))["reason"] == "unknown-model"


async def test_关闭时会等下载任务真的退出(pack, tmp_path):
    dl = make_downloader(tmp_path)
    waiting = asyncio.Event()

    async def patient_fetch(spec, job, item, target):
        waiting.set()
        await job.cancel.wait()  
        raise DownloadCancelled

    dl._fetch_one = patient_fetch  
    await dl.start("voice", "cn")
    await waiting.wait()
    await dl.shutdown()
    assert dl._jobs["voice"].task is not None
    assert dl._jobs["voice"].task.done(), "shutdown 必须等它真的退出，不能只立个旗"







def test_语音模型的落盘位置就是读取侧要找的位置(monkeypatch, tmp_path):









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

    spec = tiny_spec(subdir="voice")
    monkeypatch.setattr(catalog, "get", lambda key: spec if key == spec.key else None)
    patch_transport(monkeypatch, {"a.bin": b"abcd", "sub/b.bin": b"12345678"})
    dl = make_downloader(tmp_path)
    await run(dl)
    assert dl.status("voice")["installed"] is True
    assert (tmp_path / "voice" / "tiny-model" / "a.bin").read_bytes() == b"abcd"
    assert (tmp_path / "voice" / "tiny-model" / "sub" / "b.bin").read_bytes() == b"12345678"







class _FakeStream:


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
        
        return _FakeStream(self._served[name], 206 if "Range" in headers else 200, headers, url)


def patch_transport(monkeypatch, served: dict[str, bytes], *, fail: set[str] | None = None) -> None:






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





    base = tmp_path / "tiny-model"
    base.mkdir(parents=True)
    (base / "a.bin.part").write_bytes(b"abcd")  
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







class _FakeRuntime:






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

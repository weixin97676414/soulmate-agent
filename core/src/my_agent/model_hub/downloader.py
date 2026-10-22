





























from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from ..utils.http import async_client
from . import catalog

logger = logging.getLogger(__name__)


CHUNK = 256 * 1024


USER_AGENT = "SoulmateAgent/0.1 (+local-model-fetch)"


TIMEOUT = httpx.Timeout(connect=20.0, read=60.0, write=30.0, pool=20.0)


PROGRESS_MIN_DELTA_PCT = 1
PROGRESS_MIN_INTERVAL = 0.4


SPEED_WINDOW = 3.0


STATE_IDLE = "idle"  
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"


class DownloadCancelled(Exception):
    pass


@dataclass
class _Job:


    key: str
    line: catalog.Line
    root: Path
    state: str = STATE_IDLE
    done_bytes: int = 0
    total_bytes: int = 0
    
    current_file: str = ""
    error: str = ""
    
    
    
    fallback_used: bool = False
    
    requested_line: str = ""
    
    files: dict[str, int] = field(default_factory=dict)
    
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None
    
    samples: list[tuple[float, int]] = field(default_factory=list)

    def speed(self) -> float:

        now = time.monotonic()
        self.samples.append((now, self.done_bytes))
        
        while len(self.samples) > 2 and now - self.samples[0][0] > SPEED_WINDOW:
            self.samples.pop(0)
        first_at, first_bytes = self.samples[0]
        span = now - first_at
        if span <= 0.05:
            return 0.0
        return max(0.0, (self.done_bytes - first_bytes) / span)


def _target_dir(root: Path, spec: catalog.ModelSpec) -> Path:





    return root / spec.subdir / spec.dirname


def _is_complete(root: Path, spec: catalog.ModelSpec) -> bool:

    base = _target_dir(root, spec)
    for item in spec.files:
        path = base / item.path
        if not path.is_file() or path.stat().st_size != item.size:
            return False
    return True


class ModelDownloader:


    def __init__(self, root: Path, publish: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None):
        self._root = root
        self._publish = publish
        self._jobs: dict[str, _Job] = {}

    

    def status(self, key: str) -> dict[str, Any]:

        spec = catalog.get(key)
        if spec is None:
            return {"key": key, "state": "unknown", "installed": False}
        job = self._jobs.get(key)
        installed = _is_complete(self._root, spec)
        
        state = STATE_DONE if installed else (job.state if job else STATE_IDLE)
        payload: dict[str, Any] = {
            "key": key,
            "title": spec.title,
            "summary": spec.summary,
            "requirement": spec.requirement,
            "state": state,
            "installed": installed,
            "total_bytes": spec.total_bytes,
            "fallback_used": job.fallback_used if job else False,
            "line": job.line if job else None,
            "files": [{"path": item.path, "size": item.size} for item in spec.files],
        }
        if job:
            payload.update(
                {
                    "done_bytes": job.done_bytes,
                    "current_file": job.current_file,
                    "error": job.error,
                    "speed": int(job.speed()) if job.state == STATE_RUNNING else 0,
                    "files": [
                        {
                            "path": item.path,
                            "size": item.size,
                            "done": job.files.get(item.path, 0),
                        }
                        for item in spec.files
                    ],
                }
            )
        else:
            payload.update({"done_bytes": 0, "current_file": "", "error": "", "speed": 0})
        return payload

    def all_status(self) -> list[dict[str, Any]]:
        return [self.status(key) for key in catalog.keys()]

    

    async def start(self, key: str, line: catalog.Line) -> dict[str, Any]:

        spec = catalog.get(key)
        if spec is None:
            return {"ok": False, "reason": "unknown-model", "key": key}
        if _is_complete(self._root, spec):
            return {"ok": True, "reason": "already-installed", "key": key}

        job = self._jobs.get(key)
        if job and job.task and not job.task.done():
            return {"ok": True, "reason": "already-running", "key": key}

        job = _Job(key=key, line=line, root=self._root, state=STATE_RUNNING)
        job.requested_line = line
        job.total_bytes = spec.total_bytes
        self._jobs[key] = job
        job.task = asyncio.create_task(self._run(spec, job))
        await self._emit(job)
        return {"ok": True, "reason": "started", "key": key}

    async def cancel(self, key: str) -> dict[str, Any]:
        job = self._jobs.get(key)
        if not job or not job.task or job.task.done():
            return {"ok": False, "reason": "not-running", "key": key}
        job.cancel.set()
        return {"ok": True, "reason": "cancelling", "key": key}

    async def shutdown(self) -> None:






        jobs = [job for job in self._jobs.values() if job.task and not job.task.done()]
        for job in jobs:
            job.cancel.set()
        for job in jobs:
            with contextlib.suppress(Exception):
                await job.task  

    

    async def _emit(self, job: _Job) -> None:
        if self._publish is None:
            return
        spec = catalog.get(job.key)
        with contextlib.suppress(Exception):
            await self._publish(
                "model_download",
                {
                    "key": job.key,
                    "title": spec.title if spec else job.key,
                    "state": job.state,
                    "done_bytes": job.done_bytes,
                    "total_bytes": job.total_bytes,
                    "current_file": job.current_file,
                    "speed": int(job.speed()) if job.state == STATE_RUNNING else 0,
                    "error": job.error,
                    "fallback_used": job.fallback_used,
                    "line": job.line,
                },
            )

    async def _run(self, spec: catalog.ModelSpec, job: _Job) -> None:











        lines: list[catalog.Line] = [job.line, catalog.other_line(job.line)]
        try:
            for attempt, line in enumerate(lines):
                job.line = line
                try:
                    await self._download_all(spec, job)
                except DownloadCancelled:
                    job.state = STATE_CANCELLED
                    logger.info("模型 %s 下载被取消", spec.key)
                    return
                except Exception as exc:  
                    job.error = f"{type(exc).__name__}: {exc}"
                    if attempt + 1 >= len(lines):
                        job.state = STATE_FAILED
                        logger.warning("模型 %s 两条线路都失败，最后一次：%s", spec.key, exc)
                        return
                    
                    job.fallback_used = True
                    job.current_file = ""
                    
                    job.samples.clear()
                    logger.warning(
                        "模型 %s 在 %s 线路下载失败（%s），已切换到备用线路 %s 重试",
                        spec.key,
                        catalog.line_title(line),
                        exc,
                        catalog.line_title(lines[attempt + 1]),
                    )
                    await self._emit(job)
                    continue
                job.state = STATE_DONE
                job.current_file = ""
                job.error = ""
                logger.info("模型 %s 下载完成（线路 %s）", spec.key, job.line)
                return
        finally:
            await self._emit(job)

    async def _download_all(self, spec: catalog.ModelSpec, job: _Job) -> None:

        base = _target_dir(self._root, spec)
        base.mkdir(parents=True, exist_ok=True)
        
        
        job.done_bytes = 0
        job.files = {}
        for item in spec.files:
            if job.cancel.is_set():
                raise DownloadCancelled
            target = base / item.path
            target.parent.mkdir(parents=True, exist_ok=True)
            
            if target.is_file() and target.stat().st_size == item.size:
                job.files[item.path] = item.size
                job.done_bytes += item.size
                continue
            job.current_file = item.path
            await self._fetch_one(spec, job, item, target)
            job.files[item.path] = item.size

    async def _fetch_one(
        self, spec: catalog.ModelSpec, job: _Job, item: catalog.ModelFile, target: Path
    ) -> None:

        url = spec.url_for(job.line, item.path)
        part = target.with_name(target.name + ".part")
        done = part.stat().st_size if part.is_file() else 0
        if done > item.size:  
            part.unlink(missing_ok=True)
            done = 0
        if done == item.size:
            
            
            
            
            part.replace(target)
            
            
            job.done_bytes += item.size
            job.files[item.path] = item.size
            return
        
        baseline = job.done_bytes
        job.done_bytes = baseline + done

        headers = {"User-Agent": USER_AGENT}
        if done:
            headers["Range"] = f"bytes={done}-"

        last_pct = -100
        last_at = 0.0
        
        
        
        async with async_client(timeout=TIMEOUT, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                if done and resp.status_code != 206:
                    
                    done = 0
                    job.done_bytes = baseline
                resp.raise_for_status()
                mode = "ab" if (done and resp.status_code == 206) else "wb"
                with part.open(mode) as handle:
                    async for chunk in resp.aiter_bytes(CHUNK):
                        if job.cancel.is_set():
                            raise DownloadCancelled
                        handle.write(chunk)
                        job.done_bytes += len(chunk)
                        now = time.monotonic()
                        pct = job.done_bytes * 100 // max(1, job.total_bytes)
                        if pct >= last_pct + PROGRESS_MIN_DELTA_PCT or now - last_at >= PROGRESS_MIN_INTERVAL:
                            last_pct = pct
                            last_at = now
                            await self._emit(job)

        
        actual = part.stat().st_size
        if actual != item.size:
            part.unlink(missing_ok=True)
            raise RuntimeError(f"{item.path} 下载不完整（{actual} != {item.size}）")
        part.replace(target)

    

    async def verify(self, key: str) -> dict[str, Any]:









        spec = catalog.get(key)
        if spec is None:
            return {"ok": False, "reason": "unknown-model"}
        if not _is_complete(self._root, spec):
            return {"ok": False, "reason": "not-installed"}

        try:
            if key == "voice":
                detail = await asyncio.to_thread(self._verify_voice, spec)
            else:
                detail = await asyncio.to_thread(self._verify_embedding, spec)
        except Exception as exc:  
            logger.warning("模型 %s 自检失败：%s", key, exc)
            return {"ok": False, "reason": "load-failed", "detail": f"{type(exc).__name__}: {exc}"}
        return {"ok": True, "reason": "ok", "detail": detail}

    def _verify_voice(self, spec: catalog.ModelSpec) -> str:

        from ..voice import models as voice_models

        found = voice_models.find_model_dir(spec.dirname)
        if found is None:
            raise FileNotFoundError(f"未找到语音模型目录 {spec.dirname}")
        import sherpa_onnx  

        return f"识别模型已就绪：{found}"

    def _verify_embedding(self, spec: catalog.ModelSpec) -> str:

        from ..memory.local_embedding import build_local_embedder

        embedder = build_local_embedder()
        if embedder is None:
            raise RuntimeError("嵌入模型未能构建")
        dim = getattr(embedder, "dimension", None) or getattr(embedder, "dim", None)
        return f"嵌入模型已就绪（{dim or '维度未知'} 维）"


def install_root(paths: Any) -> Path:

    return Path(paths.models_dir)

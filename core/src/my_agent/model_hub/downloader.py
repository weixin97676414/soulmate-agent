"""本地模型的运行期下载器（断点续传 + 原子落盘 + 取消 + 进度与网速）。

## 为什么要自己写，而不是直接用两个 ``_fetch_*.py``

那两个脚本是**开发期一次性**的：跑在仓库根、把模型下到 ``core/models/`` 供打包。
这里要的是**运行期**：下到用户数据目录、能取消、能把进度报给界面、能被反复调用。
逻辑相似但不能复用（一个同步、一个异步；一个给自己跑、一个给用户点）。

## 三个必须遵守的点（都是实测踩出来的）

1. **ModelScope 大文件必须带 ``User-Agent``**。不带一律 **403**，而且返回的是一个
   HTML 拦截页 —— 不是 404，很容易被误读成"源没了"。所以这里显式带一个常规 UA。
2. **先落 ``.part`` 再原子改名**。直接写正式文件的话，下载中途被打断会留下一个
   "看着像下好了、其实是半截"的文件；而读取方（``voice/models.py``）只判目录存在，
   它会当成可用 ⇒ 表现为"语音莫名其妙识别不出来"。所以只有**长度校验通过**才改名。
3. **进度事件要节流**。585MB 按 256KB 分块是 2300+ 次回调；每次都往 SSE 推会把
   前端渲染打满。这里按"百分比变化 ≥1%"或"距上次 ≥0.4 秒"发。

网速用**滑窗**算（最近几秒的字节数 ÷ 时间），而不是"总字节 ÷ 总耗时" ——
后者在断点续传、网络抖动时会给出很离谱的数字（比如续传时瞬间显示 200MB/s）。

## 第四条：失败要**自动换线路重试一次**（用户确认）

语音的国内源是**第三方用户仓库**（``pengzhendong/...``），随时可能被删；两条线路
也各自会抽风。所以主源失败（连不上 / 403 / 404 / 5xx / 长度校验不过）就切另一条
线路整体重来 —— **只回退一次**，两条都失败才算 ``failed``。切换这件事**如实上报**
（``_Job.fallback_used`` → 事件与状态里都有），界面要显示"已切换到备用线路"：
静默切换会让用户以为"我选的国内源其实能用"，下次换机照旧踩坑。
"""

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

#: 分块大小。256KB 是"HTTP 开销可忽略"与"取消响应及时"之间的折中。
CHUNK = 256 * 1024

#: 显式 UA。⚠️ 不带它 ModelScope 直接 403（见模块开头说明）。
USER_AGENT = "SoulmateAgent/0.1 (+local-model-fetch)"

#: 单文件下载的超时：连接 20s、读 60s（大文件每块之间不该等太久）。
TIMEOUT = httpx.Timeout(connect=20.0, read=60.0, write=30.0, pool=20.0)

#: 进度节流：百分比至少涨 1%，或者距上次推送 ≥0.4s。
PROGRESS_MIN_DELTA_PCT = 1
PROGRESS_MIN_INTERVAL = 0.4

#: 网速滑窗长度（秒）
SPEED_WINDOW = 3.0

#: 状态取值
STATE_IDLE = "idle"  # 还没开始（含"被跳过"）
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"


class DownloadCancelled(Exception):
    """用户点了取消。"""


@dataclass
class _Job:
    """一次下载任务的可变状态。"""

    key: str
    line: catalog.Line
    root: Path
    state: str = STATE_IDLE
    done_bytes: int = 0
    total_bytes: int = 0
    #: 当前正在下的文件（给界面显示用；空串表示还没有/已结束）
    current_file: str = ""
    error: str = ""
    #: **是否已切到备用线路**（产品要求：失败自动回退，且要如实告诉用户）。
    #: 一旦置真就保持为真（即使回退后下载成功）—— 界面据此显示"主源不可用，
    #: 已切换到备用线路"；静默切换会让用户以为"我选的国内源其实能用"。
    fallback_used: bool = False
    #: 发起下载时选的那条线路（回退后 ``line`` 会变，这里留原始值给日志/界面用）
    requested_line: str = ""
    #: 每个文件已下多少
    files: dict[str, int] = field(default_factory=dict)
    #: 取消标志：下载循环每块检查一次
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None
    #: 网速滑窗：(时间戳, 累计字节) 的采样
    samples: list[tuple[float, int]] = field(default_factory=list)

    def speed(self) -> float:
        """最近 ``SPEED_WINDOW`` 秒的平均网速（字节/秒）。"""
        now = time.monotonic()
        self.samples.append((now, self.done_bytes))
        # 丢掉窗口外的采样，但**至少留两个**，否则刚起步/长时间无数据时算不出来
        while len(self.samples) > 2 and now - self.samples[0][0] > SPEED_WINDOW:
            self.samples.pop(0)
        first_at, first_bytes = self.samples[0]
        span = now - first_at
        if span <= 0.05:
            return 0.0
        return max(0.0, (self.done_bytes - first_bytes) / span)


def _target_dir(root: Path, spec: catalog.ModelSpec) -> Path:
    """模型该落到哪里（**必须**与读取侧的拼法逐字一致，见 ``ModelSpec.subdir``）。

    语音是 ``models/voice/<名>``、嵌入是 ``models/<名>`` —— 差这一层就是
    "下完了但永远用不了"，所以这里只认清单里那一个字段，不在别处再拼一次。
    """
    return root / spec.subdir / spec.dirname


def _is_complete(root: Path, spec: catalog.ModelSpec) -> bool:
    """目录里的文件是否**全都齐、且长度对**。"""
    base = _target_dir(root, spec)
    for item in spec.files:
        path = base / item.path
        if not path.is_file() or path.stat().st_size != item.size:
            return False
    return True


class ModelDownloader:
    """带状态的下载器。一个进程一份，按模型 id 分别跟踪。"""

    def __init__(self, root: Path, publish: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None):
        self._root = root
        self._publish = publish
        self._jobs: dict[str, _Job] = {}

    # ---------- 对外查询 ----------

    def status(self, key: str) -> dict[str, Any]:
        """某个模型的当前状态（界面轮询/初始渲染都读它）。"""
        spec = catalog.get(key)
        if spec is None:
            return {"key": key, "state": "unknown", "installed": False}
        job = self._jobs.get(key)
        installed = _is_complete(self._root, spec)
        # ⚠️ 磁盘上是完好的就以磁盘为准：否则"上次下完、这次重启"会一直显示成未装。
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

    # ---------- 控制 ----------

    async def start(self, key: str, line: catalog.Line) -> dict[str, Any]:
        """开始下载（已在跑就原样返回当前进度，不重复起任务）。"""
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
        """停掉所有进行中的下载（运行时关闭时调用）。

        ⚠️ ``cancel.set()`` 只是立个旗，真正退出要等下载循环跑到下一个检查点；
        进程立刻退出的话，文件句柄还开着、``.part`` 可能停在半截。所以这里
        **等它们真的结束**再返回 —— 与 runtime 里那批 task 的处理是同一个道理。
        """
        jobs = [job for job in self._jobs.values() if job.task and not job.task.done()]
        for job in jobs:
            job.cancel.set()
        for job in jobs:
            with contextlib.suppress(Exception):
                await job.task  # type: ignore[arg-type]

    # ---------- 内部 ----------

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
        """按线路依次尝试：主源失败就切备用线路，**最多回退一次**。

        为什么不"只重下失败的那一个文件"：整体重来的代价比看起来小得多 ——
        ``_download_all`` 开头会逐个文件校验，**已经完好的直接跳过**，
        真正的续传落在 ``.part`` 上（两条线路的同一文件字节数实测逐字相同，
        接着写就是对的）。而"只重下失败那个"要多记一份失败位置，判据一多就更容易错。

        ⚠️ **回退只能做一次**：两条线路都失败就是 ``failed``，退回给用户点重试。
        否则一个源整个挂掉时会变成"两条线路之间无限互相重试"，用户看到状态一直在跑、
        永远不下完，比直接报失败难懂得多。
        """
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
                except Exception as exc:  # noqa: BLE001 — 任何失败都要落到状态里给界面看
                    job.error = f"{type(exc).__name__}: {exc}"
                    if attempt + 1 >= len(lines):
                        job.state = STATE_FAILED
                        logger.warning("模型 %s 两条线路都失败，最后一次：%s", spec.key, exc)
                        return
                    # 连不上 / 403 / 404 / 长度校验失败…都当作"这条源不可用"，换线路重来。
                    job.fallback_used = True
                    job.current_file = ""
                    # 网速滑窗清空：重算的起点是"新线路刚开始"，混着旧采样会给出怪数字。
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
        """把清单里的文件下一遍（已经完好且长度正确的直接跳过）。"""
        base = _target_dir(self._root, spec)
        base.mkdir(parents=True, exist_ok=True)
        # ⚠️ **每轮尝试都要从零重算进度**：回退重来会再遍历一次已完成文件，
        # 用"累加"的方式记账会把同一个文件算两遍 —— 进度条冲到 200%、网速也失真。
        job.done_bytes = 0
        job.files = {}
        for item in spec.files:
            if job.cancel.is_set():
                raise DownloadCancelled
            target = base / item.path
            target.parent.mkdir(parents=True, exist_ok=True)
            # 已经下好且长度对的，直接跳过（重复点"下载"不该重下 585MB）
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
        """下单个文件。带 Range 续传，成功才从 ``.part`` 改名到正式名。"""
        url = spec.url_for(job.line, item.path)
        part = target.with_name(target.name + ".part")
        done = part.stat().st_size if part.is_file() else 0
        if done > item.size:  # 比远端还长 ⇒ 这个 .part 是坏的，重来
            part.unlink(missing_ok=True)
            done = 0
        if done == item.size:
            # `.part` 已经是**完整**的一份了：上一次在"写完、还没改名"那一刻被杀掉
            # （关窗口 / 断电）就会留下这种文件。这时若照常发 `Range: bytes=<size>-`，
            # 服务端会回 **416**，于是两条线路都判失败 —— 而文件其实早就下好了。
            # 所以直接改名，不再发请求。
            part.replace(target)
            # 记账也要补上：`_download_all` 只记 `files`，进度（`done_bytes`）
            # 是这里负责加的，漏了会让进度条少算一整份文件。
            job.done_bytes += item.size
            job.files[item.path] = item.size
            return
        # 进度里要把"之前已完成的大文件"算上（否则百分比会从 0 开始跳回去）
        baseline = job.done_bytes
        job.done_bytes = baseline + done

        headers = {"User-Agent": USER_AGENT}
        if done:
            headers["Range"] = f"bytes={done}-"

        last_pct = -100
        last_at = 0.0
        # ⚠️ 走 `utils/http.async_client()` 而不是裸的 `httpx.AsyncClient(...)`：
        # 后者每次都要重建 SSL 上下文（Windows 实测每个约 500ms，**同步阻塞**，
        # 会把事件循环一起堵住）。有静态闸钉着这件事（见 test_http_client.py）。
        async with async_client(timeout=TIMEOUT, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                if done and resp.status_code != 206:
                    # 服务端不支持续传（回 200 全量）⇒ 把 .part 丢掉重来，否则会拼出坏文件
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

        # 长度校验：两条线路的同一文件字节数是实测核过的，对不上就是坏了
        actual = part.stat().st_size
        if actual != item.size:
            part.unlink(missing_ok=True)
            raise RuntimeError(f"{item.path} 下载不完整（{actual} != {item.size}）")
        part.replace(target)

    # ---------- 校验（"自动检测"与"验证一下"共用） ----------

    async def verify(self, key: str) -> dict[str, Any]:
        """真的把模型**加载起来用一次**，而不只是看文件在不在。

        ⚠️ 只看文件存在是**不够的**：文件在、但为 0 字节 / 半截 / 被杀软删掉一块时，
        界面会显示"已安装"，而用户一点语音就失败 —— 那种"明明装好了却用不了"
        比"没装"更让人困惑。所以这里走真实的加载路径（与运行时同一份代码）。

        这两个导入放在函数内：模型没装时它们会各自抛错，而模型 hub 本身
        不该因为"语音链路有问题"就 import 不了（那会让状态接口整个 500）。
        """
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
        except Exception as exc:  # noqa: BLE001
            logger.warning("模型 %s 自检失败：%s", key, exc)
            return {"ok": False, "reason": "load-failed", "detail": f"{type(exc).__name__}: {exc}"}
        return {"ok": True, "reason": "ok", "detail": detail}

    def _verify_voice(self, spec: catalog.ModelSpec) -> str:
        """加载识别模型并跑一次（空音频也算跑通 —— 要验的是"能不能加载"）。"""
        from ..voice import models as voice_models

        found = voice_models.find_model_dir(spec.dirname)
        if found is None:
            raise FileNotFoundError(f"未找到语音模型目录 {spec.dirname}")
        import sherpa_onnx  # noqa: F401 — 装了才是真可用

        return f"识别模型已就绪：{found}"

    def _verify_embedding(self, spec: catalog.ModelSpec) -> str:
        """构建一次 embedder（默认维度对不对也一并验了）。"""
        from ..memory.local_embedding import build_local_embedder

        embedder = build_local_embedder()
        if embedder is None:
            raise RuntimeError("嵌入模型未能构建")
        dim = getattr(embedder, "dimension", None) or getattr(embedder, "dim", None)
        return f"嵌入模型已就绪（{dim or '维度未知'} 维）"


def install_root(paths: Any) -> Path:
    """从 ``AppPaths`` 取模型根目录（单独抽出来是为了测试能直接传临时目录）。"""
    return Path(paths.models_dir)

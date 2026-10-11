"""FastAPI 应用装配。

安全模型（本地单机应用）：
- 仅监听 ``127.0.0.1``，不对外网暴露；
- 每个请求必须带 ``X-Local-Token``，token 由 Electron 主进程在启动
  Python 进程时随机生成并通过环境变量传入，重启即失效；
- 中间件同时拦截非回环来源，防止本机其他程序误调。
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..errors import AgentError
from ..version import __version__
from .routes import (
    assistants,
    audit,
    chat,
    events,
    files,
    groups,
    life,
    mcp,
    media,
    metrics,
    model_hub,
    models,
    runs,
    sessions,
    skills,
    system,
    tasks,
    traces,
    usage,
    voice,
)
from .routes import (
    calendar as calendar_router,
)
from .runtime import AppRuntime

logger = logging.getLogger(__name__)

TOKEN_HEADER = "x-local-token"

# 超过这个耗时就记一条警告。本地接口正常都在几十毫秒内，
# 取 500ms 既不会漏掉"体感明显变慢"，也不会把正常抖动记成问题。
SLOW_REQUEST_MS = 500.0

# 事件循环卡顿的告警阈值。这个进程**单事件循环**，任何一处同步阻塞
# （写盘、wmic、加载模型）都会让**所有**并发请求一起排队 ——
# 表现是"某个毫不相干的接口突然变慢"，从单个接口的日志根本看不出来。
LOOP_LAG_MS = 500.0


async def _loop_lag_monitor(stop: asyncio.Event) -> None:
    """盯住事件循环有没有被同步调用占住。

    ``asyncio.sleep(0.25)`` 的实际耗时减去 0.25s 就是"循环被占住的时间"。
    这是唯一能证明「某个接口慢是因为**别人**把循环堵了」的手段。
    """
    interval = 0.25
    while not stop.is_set():
        started = time.perf_counter()
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return  # stop 被置位，正常退出
        except TimeoutError:
            pass
        lag_ms = (time.perf_counter() - started - interval) * 1000
        if lag_ms >= LOOP_LAG_MS:
            logger.warning("事件循环卡顿 %.0f ms —— 有同步调用阻塞了所有请求", lag_ms)


def create_app(*, runtime: AppRuntime | None = None, token: str = "") -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime: AppRuntime | None = getattr(app.state, "runtime", None)
        if runtime is not None:
            # 连接数据库、恢复历史会话、准备工作区目录。
            # uvicorn 会等 lifespan 启动完成才接受请求，所以这里不需要额外的就绪标志。
            await runtime.initialize()
            logger.info("Agent Core 已就绪，数据目录: %s", runtime.paths.root)
        lag_stop = asyncio.Event()
        lag_task = asyncio.create_task(_loop_lag_monitor(lag_stop))
        try:
            yield
        finally:
            lag_stop.set()
            lag_task.cancel()
            with suppress(asyncio.CancelledError):
                await lag_task
            if runtime is not None:
                await runtime.shutdown()

    app = FastAPI(
        title="Agent Core",
        # 引用单一来源（my_agent/version.py）而不是硬编码
        version=__version__,
        docs_url=None,       # 本地服务不暴露交互式文档
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.state.token = token
    app.state.uvicorn_server = None

    # ---- 鉴权与来源校验（必须在 CORS 之前注册，才会被 CORS 包在外层） ---- #
    #
    # **来源校验与令牌无关，始终生效。**
    # 原先两者一起包在 `if token:` 里，于是 token 为空时既没有令牌校验、
    # 也没有回环限制，而 CORS 又是 allow_origins=["*"] —— 同一台机器上的
    # 任意网页都能无认证驱动 Agent（读文件、跑技能、改配置）。
    # 正式入口 ``__main__.main`` 的 token 恒非空所以踩不到，
    # 但 ``create_app()`` 的默认参数是个陷阱，SDK 嵌入场景会直接掉进去。
    @app.middleware("http")
    async def verify_request(request: Request, call_next):
        # 预检请求交给 CORS 中间件处理，否则浏览器会因 401 判定跨域失败
        if request.method == "OPTIONS":
            return await call_next(request)

        client_host = request.client.host if request.client else ""
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            return JSONResponse(
                status_code=403,
                content={"code": "forbidden", "message": "仅允许本机访问"},
            )

        if not token:
            # 无令牌模式下不再校验，但调用方必须知道这件事
            return await call_next(request)

        provided = request.headers.get(TOKEN_HEADER, "")
        # 常数时间比较：普通 != 是逐字符短路，理论上可被计时侧信道探测。
        # 令牌熵足够高、又只在回环可达，实际风险很低，但换掉是一行的事。
        if not hmac.compare_digest(provided, token):
            return JSONResponse(
                status_code=401,
                content={"code": "unauthorized", "message": "本地令牌校验失败"},
            )
        return await call_next(request)

    if not token:
        logger.warning(
            "create_app() 未提供本地令牌，**本次运行没有鉴权**。"
            "仅建议用于测试或进程内嵌；正式启动请走 my_agent.__main__，它会自动生成随机令牌。"
        )

    # ---- 慢请求观测 ---------------------------------------------------- #
    #
    # 加的是一次被反复追问的问题：「明明是本地接口，为什么会等十几秒？」
    # 没有这层日志时，只能看到"界面转了很久"，无法区分三种完全不同的原因：
    #   1) 这个接口本身慢；
    #   2) 请求在排队 —— 事件循环被别的同步调用占住了；
    #   3) 前端自己串了好几次往返（后端每个请求都很快，但加起来慢）。
    # 有了它，「哪个接口、花了多久」是可以直接读出来的事实。
    #
    # 只记**超过阈值**的请求：正常请求毫秒级，全量记录会把日志淹掉。
    @app.middleware("http")
    async def log_slow_request(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms >= SLOW_REQUEST_MS and request.url.path != "/v1/events":
            # `/v1/events` 是**常驻长连接**，它"耗时等于连接存续时间"，
            # 记进来毫无意义且会刷屏。
            response.headers["X-Elapsed-Ms"] = f"{elapsed_ms:.0f}"
            logger.warning(
                "慢请求 %s %s —— %.0f ms（HTTP %s）",
                request.method,
                request.url.path,
                elapsed_ms,
                response.status_code,
            )
        return response

    # 最后注册 -> 最外层 -> 保证错误响应也带 CORS 头
    #
    # **来源限定在本机**。原先用 ``allow_origins=["*"]``，等于允许用户浏览器里的
    # **任意网站**向 127.0.0.1 的这个端口发起请求并读到响应。
    #
    # 令牌仍然挡得住未授权调用（攻击者拿不到它），所以这不是"能被直接利用"的洞；
    # 但把安全性全押在"对手不知道令牌"上是不必要的 —— 一旦出现令牌为空的运行方式
    # （SDK 进程内嵌），这层就彻底敞开。端口探测也算一个额外收益。
    #
    # 三种来源都要放行，缺一个应用就打不开：
    # - ``null``：生产环境 Electron 用 ``file://`` 加载页面，Chromium 发的就是它；
    # - ``localhost`` / ``127.0.0.1``：开发模式的 Vite dev server；
    # - ``[::1]``：IPv6 回环，某些环境下 Electron 会走这条。
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(null|file://.*|https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?)$",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # ---- 统一异常处理 ------------------------------------------------ #
    @app.exception_handler(AgentError)
    async def handle_agent_error(_: Request, exc: AgentError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理的服务端异常")
        return JSONResponse(
            status_code=500,
            content={"code": "internal_error", "message": f"{type(exc).__name__}: {exc}"},
        )

    # ---- 路由 -------------------------------------------------------- #
    app.include_router(system.router)
    app.include_router(chat.router)
    app.include_router(models.router)
    app.include_router(skills.router)
    app.include_router(sessions.router)
    app.include_router(files.router)
    app.include_router(audit.router)
    app.include_router(life.router)
    app.include_router(events.router)
    app.include_router(mcp.router)
    app.include_router(media.router)
    app.include_router(runs.router)
    app.include_router(assistants.router)
    app.include_router(groups.router)
    app.include_router(usage.router)
    app.include_router(metrics.router)
    app.include_router(traces.router)
    app.include_router(tasks.router)
    app.include_router(calendar_router.router)
    app.include_router(voice.router)
    app.include_router(model_hub.router)

    return app

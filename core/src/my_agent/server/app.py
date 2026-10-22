








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



SLOW_REQUEST_MS = 500.0




LOOP_LAG_MS = 500.0


async def _loop_lag_monitor(stop: asyncio.Event) -> None:





    interval = 0.25
    while not stop.is_set():
        started = time.perf_counter()
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return  
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
        
        version=__version__,
        docs_url=None,       
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.state.token = token
    app.state.uvicorn_server = None

    
    
    
    
    
    
    
    
    @app.middleware("http")
    async def verify_request(request: Request, call_next):
        
        if request.method == "OPTIONS":
            return await call_next(request)

        client_host = request.client.host if request.client else ""
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            return JSONResponse(
                status_code=403,
                content={"code": "forbidden", "message": "仅允许本机访问"},
            )

        if not token:
            
            return await call_next(request)

        provided = request.headers.get(TOKEN_HEADER, "")
        
        
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

    
    
    
    
    
    
    
    
    
    
    @app.middleware("http")
    async def log_slow_request(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms >= SLOW_REQUEST_MS and request.url.path != "/v1/events":
            
            
            response.headers["X-Elapsed-Ms"] = f"{elapsed_ms:.0f}"
            logger.warning(
                "慢请求 %s %s —— %.0f ms（HTTP %s）",
                request.method,
                request.url.path,
                elapsed_ms,
                response.status_code,
            )
        return response

    
    
    
    
    
    
    
    
    
    
    
    
    
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(null|file://.*|https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?)$",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    
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

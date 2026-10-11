"""FastAPI 依赖注入。"""

from __future__ import annotations

from fastapi import Request

from .runtime import AppRuntime


def get_runtime(request: Request) -> AppRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:  # pragma: no cover - 启动流程保证不会发生
        raise RuntimeError("AppRuntime 尚未初始化")
    return runtime

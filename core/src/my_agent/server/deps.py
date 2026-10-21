

from __future__ import annotations

from fastapi import Request

from .runtime import AppRuntime


def get_runtime(request: Request) -> AppRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:  
        raise RuntimeError("AppRuntime 尚未初始化")
    return runtime

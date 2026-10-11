"""HTTP 路由集合。"""

# 本地模型下载（语音 / 嵌入模型按需下载）。**路由模块住在自己的包里**
# （``my_agent/model_hub/routes.py``）：它与 catalog / downloader 是一个整体，
# 拆开就要来回跳。这里只是把它挂进"路由集合"这个名字空间，
# 装配方式与其它路由一致（见 server/app.py 的 include_router）。
from ...model_hub import routes as model_hub
from . import (
    assistants,
    audit,
    chat,
    events,
    files,
    life,
    mcp,
    metrics,
    models,
    sessions,
    skills,
    system,
    tasks,
    traces,
    usage,
)

__all__ = [
    "assistants",
    "audit",
    "chat",
    "events",
    "files",
    "life",
    "mcp",
    "metrics",
    "model_hub",
    "models",
    "sessions",
    "skills",
    "system",
    "tasks",
    "traces",
    "usage",
]

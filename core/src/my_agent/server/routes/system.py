"""系统级接口：健康检查、设置读写、优雅退出。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...config.lines import DEFAULT_LINE, ENDPOINTS, endpoints_for
from ...config.schemas import AppSettings, ConfirmMode
from ...version import __version__
from ..deps import get_runtime
from ..runtime import AppRuntime

router = APIRouter(tags=["system"])


class ConfirmModePayload(BaseModel):
    mode: ConfirmMode


class ConfirmModeState(BaseModel):
    mode: ConfirmMode
    """全局设置里的值（含 assistant_override 是否压过它）"""

    assistant_override: ConfirmMode | None = None
    effective: ConfirmMode


class LinePayload(BaseModel):
    """当前线路（大陆 / 首尔）。"""

    line: str


@router.put("/v1/client/line")
async def set_line(payload: LinePayload, request: Request) -> dict[str, Any]:
    """同步"当前线路"给核心。

    核心自己不知道客户端算出来的线路（那是主进程按系统语言 + 探测定下来的），
    但**官网搭子库的地址**与**兑换码接口的域名**都跟着线路走，所以主进程在
    核心就绪后、以及每次线路结论变化时把它推过来（见 config/lines.py）。

    不进配置文件：线路是**每次启动重算**的运行期结论，落盘反而会留下过期值。
    """
    runtime: AppRuntime = get_runtime(request)
    line = payload.line.strip().lower() or DEFAULT_LINE
    if line not in ENDPOINTS:
        raise HTTPException(status_code=422, detail=f"未知线路：{payload.line}")
    runtime.line = line
    return {"ok": True, "line": line, "endpoints": endpoints_for(line)}


class SessionPayload(BaseModel):
    """当前登录会话的凭证（心鉴学报告接口要用的那个）。"""

    session_token: str = ""


@router.put("/v1/client/session")
async def set_session(payload: SessionPayload, request: Request) -> dict[str, Any]:
    """同步"当前登录凭证"给核心（报告接口的凭证由核心代发）。

    与上面的线路同一个形状、同一个理由：凭证是**运行期结论**，由主进程在登录成功、
    会话刷新、登出这三个时刻推过来（见 desktop/electron/backend.ts），核心只放内存。

    ⚠️ 返回值里**绝不回显凭证本身**，只回"收到没收到"：这个响应会进主进程日志。
    空串是合法输入，表示"用户登出了"—— 之后模型去拉报告会拿到"需要重新登录"这句
    如实的提示，而不是一个莫名其妙的 401。
    """
    runtime: AppRuntime = get_runtime(request)
    runtime.set_session_token(payload.session_token)
    return {"ok": True, "has_token": runtime.has_session_token}


@router.get("/v1/health")
async def health(request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    from ...mcp.client import sdk_available
    from ...memory.long_term import chromadb_available

    return {
        "status": "ok",
        # 引用单一来源而不是硬编码：这两处（这里与 app.py 的 FastAPI version）
        # 曾经各自写死一个 "0.1.0"，发版时最容易漏改
        "version": __version__,
        "default_model": runtime.registry.default_id,
        "models": runtime.registry.ids(),
        #: 顶部「N 个工具」的口径 = **可调用的工具 + 已启用的指导型技能**。
        #:
        #: ⚠️ 只数 `len(runtime.skills)` 会**少计**：`instruction` 类技能不进工具表
        #: （它只往 system 里注入指导文本，见 `skill/custom.py` 的 `sync_custom_skills`），
        #: 于是用户上传一个"只有 SKILL.md"的技能包之后，界面上的数字纹丝不动 ——
        #: 他会以为上传失败了，然后反复重传。
        #:
        #: 实测反馈"上传了指导型技能，没有被正确计数"就是它。
        "skills": len(runtime.skills)  # type: ignore[arg-type]
        + sum(
            1
            # ⚠️ `custom_skills` 是 `CustomSkillsConfig`（一个包着列表的配置对象），
            # 不是列表本身 —— 直接迭代它会 TypeError。
            for item in (getattr(runtime.custom_skills, "skills", None) or [])
            if getattr(item, "kind", "") == "instruction" and getattr(item, "enabled", True)
        ),
        "sessions": len(runtime.sessions),
        "running_tasks": len(runtime.tasks),
        "data_dir": str(runtime.paths.root),
        "persistent": runtime.db_ready,
        # 可选依赖的**实际可用性**（而不是配置里写没写）。
        # 暴露出来有两个用处：验收脚本能在真实 exe 里断言"确实打包完整"；
        # 界面上的「关于」也能如实显示，用户不用去猜为什么知识库是灰的。
        # 这两项都是首次调用后由 Python 缓存的 import，开销可忽略。
        "optional": {
            "mcp": sdk_available(),
            "memory": chromadb_available(),
        },
        "long_term_enabled": runtime.config.settings.memory.long_term_enabled,
    }


@router.get("/v1/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    return runtime.config.settings.model_dump(mode="json")


@router.put("/v1/settings")
async def update_settings(
    payload: AppSettings, request: Request, clear_calendar_password: bool = False
) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    current = runtime.config.settings

    # ⚠️ 忽略入参里的定时任务，永远以当前配置为准。
    #
    # 定时任务确实是配置（也存在 settings.json 里），但它有自己的增删改接口
    # （``/v1/tasks``）。设置页保存时提交的是**整份** settings，其中那份
    # ``scheduled_tasks`` 是它打开页面那一刻的快照 —— 用户开着设置页、同时在
    # 「定时」页新建了一个任务，下一次自动保存就会把新任务悄悄抹掉。
    # 这类丢数据的路径一旦存在，用户只会看到"我建的任务过一会儿自己没了"。
    payload.agent.scheduled_tasks = list(current.agent.scheduled_tasks)

    # 日历密码：**空值 = 用户没动它**，保留内存里的那一份（与模型 Key 同一套语义）。
    # 不做这层保护的话，设置页任何一次自动保存（改个皮肤、改个温度都会触发）
    # 都会把密码清成空串，用户看到的现象是"用着用着日历就读不到了"。
    # 真要清空得显式说：``?clear_calendar_password=true``。
    if clear_calendar_password:
        payload.calendar.caldav_password = ""
    elif not payload.calendar.caldav_password:
        payload.calendar.caldav_password = current.calendar.caldav_password

    saved = runtime.apply_settings(payload)
    # 下发时**不回显密码**：它的真相来源是 Electron 的加密存储，
    # 回显只会让密码多一条无谓的传播路径
    response = saved.model_dump(mode="json")
    response.setdefault("calendar", {})["caldav_password"] = ""
    return response


@router.get("/v1/security/confirm-mode")
async def get_confirm_mode(
    request: Request, assistant_id: str | None = None
) -> dict[str, Any]:
    """读取「权限确认」当前实际生效的模式。

    界面需要区分两件事：全局设置是什么、本轮对话实际按什么执行。
    助手预设可以给单个会话指定专属策略（优先级高于全局），
    如果只回全局值，用户在输入栏旁边看到的就是一个**不生效**的开关。
    """
    runtime: AppRuntime = get_runtime(request)
    global_mode = runtime.config.settings.security.confirm_mode
    profile = runtime.resolve_assistant(assistant_id) if assistant_id else None
    override = profile.confirm_mode if profile else None
    return {
        "mode": global_mode,
        "assistant_override": override,
        "effective": override or global_mode,
    }


@router.put("/v1/security/confirm-mode")
async def set_confirm_mode(
    payload: ConfirmModePayload, request: Request
) -> dict[str, Any]:
    """只改「权限确认模式」这一个字段。

    做成独立接口而不是复用 ``PUT /v1/settings``：后者要求提交**整个**
    AppSettings，而输入栏旁边的快捷开关只改一个字段，全量提交会把用户
    正在设置页里编辑、还没保存的其他修改一起覆盖掉。

    ``runtime.apply_settings`` 会顺带把新值同步给权限守卫（``guard.set_confirm_mode``），
    所以改完立即生效，不需要重启核心。
    """
    runtime: AppRuntime = get_runtime(request)
    current = runtime.config.settings
    updated = current.model_copy(
        update={"security": current.security.model_copy(update={"confirm_mode": payload.mode})}
    )
    saved = runtime.apply_settings(updated)
    return {"mode": saved.security.confirm_mode}


@router.get("/v1/paths")
async def get_paths(request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    paths = runtime.paths
    return {
        "root": str(paths.root),
        "config": str(paths.config_dir),
        "data": str(paths.data_dir),
        "logs": str(paths.logs_dir),
        "workspace": str(paths.workspace_dir),
        "artifacts": str(paths.artifacts_dir),
        # 让界面能如实展示"当前到底限制了哪些目录"
        "allowed_dirs": [str(item) for item in runtime.path_policy.allowed_dirs],
        "restricted": runtime.path_policy.is_restricted,
    }


@router.post("/v1/shutdown")
async def shutdown(request: Request) -> dict[str, Any]:
    """优雅退出。由 Electron 主进程在关闭窗口时调用。"""
    runtime: AppRuntime = get_runtime(request)
    await runtime.shutdown()

    server = getattr(request.app.state, "uvicorn_server", None)
    if server is not None:
        server.should_exit = True
    return {"ok": True}

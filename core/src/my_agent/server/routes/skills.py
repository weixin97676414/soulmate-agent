"""Skill 管理接口（设置中心「技能」页签使用）。

本模块只做**三件事**：路由、参数校验、把结果转成人话。
真正的解析 / 落盘 / 记账在 ``skill/`` 包里（``archive`` / ``formats`` / ``package`` /
``folder`` / ``install`` / ``inbox``），因为那几件事**四条路都要用**：
上传、从链接下载、导入本机文件夹、扫描技能投放区。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from ...config.schemas import CustomSkillDef
from ...config.skill_secrets import parse_skill_secrets
from ...skill import locked
from ...skill.builtin import xjx
from ...skill.inbox import inbox_dir, scan_inbox_async
from ...skill.install import (
    SkillRejected,
    install_mcp_roots,
    install_package,
    package_file_list,
    remove_package_dir,
    validate_defn,
)
from ...skill.package import parse_directory, parse_package
from ..deps import get_runtime
from ..runtime import AppRuntime

logger = logging.getLogger(__name__)

router = APIRouter(tags=["skills"], prefix="/v1/skills")

VALID_PERMISSIONS = {"safe", "confirm", "admin"}


class SkillSecretsBody(BaseModel):
    """``POST /v1/skill-secrets`` 的请求体：**用户给技能的密钥**的整份内容。

    ⚠️ 与 ``secrets.bin`` 那条链路无关（不同文件、不同注入变量）。
    由 Electron 主进程在写完 ``skill-secrets.bin`` 之后调用 —— 因为核心只在
    **启动时**读一次那个临时文件（读完即删），运行期新增的密钥得靠这里推过来。

    ⚠️ 本接口**仅供本机主进程调用**（核心只监听 127.0.0.1，且要本地令牌）。
    内容**绝不落任何日志**：`runtime.apply_skill_secrets` 只记条数。
    """

    keys: dict[str, str] = Field(default_factory=dict)


@router.post("/v1/skill-secrets")
async def set_skill_secrets(payload: SkillSecretsBody, request: Request) -> dict[str, Any]:
    """运行时更新"用户给技能的密钥"（Electron 写完盘后调）。

    ## 为什么是"整份替换"而不是增量

    主进程那份是**唯一真相来源**（它有删除入口，见管理面板），核心这份只是镜像。
    增量合并会让"用户在面板里删掉一条"永远同步不过来 ——
    镜像比正本多几条，而没有任何地方会报错。

    ## 为什么必须存在

    用户在弹窗里粘贴密钥后应当**立刻**能被 ``{{secret:名字}}`` 用到。
    没有这条路径的话，只能重启客户端才生效（核心启动时才读注入文件）。
    """
    runtime: AppRuntime = get_runtime(request)
    # 走与启动注入**同一个** parse：非法名字在两条路径上的处理必须一致，
    # 否则会出现"启动时能用的名字、热更新之后不能用了"这种诡异差异。
    secrets = parse_skill_secrets({"keys": payload.keys})
    count = runtime.apply_skill_secrets(secrets)
    return {"ok": True, "count": count}

# 不进技能页的工具：它们是心鉴学那两个专属技能的**内部零件**（地点核对、报告代取），
# 用户既关不掉也不该关心 —— 摆出来只会让人以为"这是个能自己用的功能"。
# 真正要露脸的是那四个专属技能本身（见下面 list_skills 里补的条目），
# 它们不是真工具，所以不在 SkillManager 里，得在这里单独拼上去。
HIDDEN_SKILL_NAMES: frozenset[str] = xjx.XJX_TOOL_NAMES


def _xjx_entries(runtime: AppRuntime) -> list[dict[str, Any]]:
    """当前线路下应当露脸的专属技能条目（形状对齐 SkillMeta.to_dict）。"""
    return [xjx.describe(item) for item in xjx.active_skills(runtime.line)]


def _instruction_entries(runtime: AppRuntime) -> list[dict[str, Any]]:
    """**指导型**自定义技能的条目（形状对齐 ``SkillMeta.to_dict``）。

    ⚠️ 它们不是工具：按设计不注册进 `SkillManager`（没有动作，注册了只会让模型看到
    一个"调了也没意义"的工具，见 `skill/custom.py::sync_custom_skills`）。
    但四分类之后"没勾 = 不注入"（见 `skill/groups.py`），**能不能被勾选**就决定了
    用户装的技能能不能生效 —— 列表里没有它，用户会遇到"技能装好了、技能页也有，
    可搭子就是用不上"，而且怎么找都找不到原因。

    ⚠️ 它们的启用 / 删除走自定义技能自己的接口（技能页「我的技能」那一栏），
    **不走** `PATCH /v1/skills/{name}`（那会 404）—— 前端别把它们当普通技能开关。
    """
    from ...skill import groups

    result: list[dict[str, Any]] = []
    for defn in getattr(runtime.custom_skills, "skills", []) or []:
        if defn.kind != "instruction":
            continue
        result.append(
            {
                "name": defn.id,
                "display_name": defn.name or defn.id,
                "description": defn.description,
                "parameters": {"type": "object", "properties": {}},
                "category": "custom",
                "permission_level": defn.permission_level,
                "timeout": defn.timeout,
                "enabled": defn.enabled,
                "tags": ["指导型"],
                "source": "custom",
                # ⚠️ 修：`bucket` 与 `domain` 必须**跟着定义走**。
                # 原先这里写死 `BUCKET_MINE` 且完全不下发 domain —— 于是批量导入的
                # 244 个第三方技能（全是指导型）全被塞进「我的技能」栏，
                # 「通用技能」栏里空空如也、那排分类按钮根本不出现、
                # 「完全免费」标签也永远不显示（它的判据是 domain 非空）。
                # `SkillMeta.to_dict`（注册成工具的技能）那条路本来就是对的，
                # 而指导型技能不走那里 —— 两处口径必须一致。
                "bucket": groups.bucket_of(defn.id, "custom", defn.domain),
                "domain": defn.domain,
                # ⚠️ 归属与硬锁**跟着名单走**：这里原来写死
                # `owners: []` / `owner_label: ""` / `locked: False`，于是"转成专属 / 内置的
                # 那批指导型技能"在界面上看不出任何归属，而且**仍然画一个开关** ——
                # 点下去落到 `patch_skill` 的 404（它们不在 `SkillManager` 里），
                # 用户看到的是「Skill 不存在」，而它明明就显示在眼前。
                #
                # 现在：专属那 8 个有归属 + 「Buddy Manager」文案；两批都 `locked=True`。
                # ⚠️ `locked` 是前端"不画开关"的**唯一**判据（见 SkillSettings.tsx 里
                # `skill.locked` 那处），漏了它界面就会出现一个点了报错的开关。
                "owners": list(groups.owners_of(defn.id)),
                "owner_label": groups.owner_label(groups.owners_of(defn.id)),
                "locked": groups.is_locked_instruction(defn.id),
                # 前端据此标出"指导型"：它不是一个能被调用的工具
                "instruction_only": True,
            }
        )
    return result


@router.get("")
async def list_skills(request: Request, enabled_only: bool = False) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    metas = [
        m
        for m in runtime.skills.list_metas(enabled_only=enabled_only)
        if m.name not in HIDDEN_SKILL_NAMES
    ]
    xjx_entries = _xjx_entries(runtime)
    # 指导型自定义技能也要列出来（它们不注册成工具，但必须能被勾选，见上面的说明）
    instruction_entries = [
        item for item in _instruction_entries(runtime) if not enabled_only or item["enabled"]
    ]
    skills = [m.to_dict() for m in metas] + xjx_entries + instruction_entries
    return {
        # 计数要把专属技能与指导型技能都算进去：界面顶部写着"共 N 项"，
        # 两个表对不上时用户会以为技能列表漏了东西
        "total": len(skills),
        "enabled": len([m for m in runtime.skills.list_metas() if m.name not in HIDDEN_SKILL_NAMES])
        + len(xjx_entries)
        + len([item for item in instruction_entries if item["enabled"]]),
        "skills": skills,
        "categories": sorted({item["category"] for item in skills}),
    }


class SkillPatch(BaseModel):
    """``PATCH /v1/skills/{name}`` 的请求体。

    ⚠️ 两个字段都必须**可缺省**（``None`` = "这一项这次不动"）：
    界面切开关时只发 ``enabled``，改权限时只发 ``permission_level``。
    写成必填的话，切个开关会因为"没带 permission_level"被 422 挡掉，
    而 422 返回的是 pydantic 的字段体检报告 —— 用户完全看不懂。
    """

    enabled: bool | None = None
    permission_level: str | None = None


@router.patch("/{name}")
async def patch_skill(name: str, payload: SkillPatch, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)

    # 专属技能不在 SkillManager 里（它们没有"动作"，只有指导正文），所以没有
    # ``meta.locked`` 可读，得先于 404 判定 —— 否则用户点一下开关收到的会是
    # 「Skill 不存在」，而它明明就显示在眼前。
    if xjx.is_xjx_skill(name):
        raise HTTPException(status_code=409, detail=xjx.locked_message(name))

    # 指导型技能里的**专属 / 常驻**那批：同样先于 404 拦。
    # ⚠️ 它们不在 `SkillManager` 里（只有指导正文、没有"动作"），`has()` 查不到 ——
    # 不先拦的话，用户点一下开关收到的是「Skill 不存在」，而它明明就显示在眼前。
    # ⚠️ 用 409 而不是静默忽略：静默忽略会让界面显示"已关闭"、实际还在生效
    # （与上面 `meta.locked` 那条同一个理由）。关不掉的**真实原因**也一样 ——
    # 它们按归属 / 常驻自动生效，落盘里根本没有可改的状态。
    from ...skill import groups

    if groups.is_locked_instruction(name):
        display = name
        for defn in getattr(runtime.custom_skills, "skills", []) or []:
            if defn.id == name and defn.name:
                display = defn.name
                break
        raise HTTPException(
            status_code=409,
            detail=(
                f"「{display}」是内置或专属技能，按搭子归属自动生效、没有开关，"
                "不需要也无法手动关闭。"
            ),
        )

    if not runtime.skills.has(name):
        raise HTTPException(status_code=404, detail=f"Skill {name} 不存在")

    meta = runtime.skills.get(name).meta

    # 被硬锁的技能（见 skill/locked.py）**明确拒绝**，而不是静默忽略。
    # 静默忽略是最坏的选择：界面显示"已关闭"，实际还在跑，用户永远查不出来。
    #
    # 这里先于 SkillManager 拦一道，是为了给接口一个稳定的契约（409）；
    # SkillManager 那层还会再拒一次 —— 那条是给别的调用路径兜底的。
    if meta.locked:
        display = meta.display_name or name
        # 「打开」是幂等的放行（界面重载时可能整体回放一次状态），只有"关掉/改权限"才是错误
        wants_disable = payload.enabled is False
        wants_permission_change = (
            payload.permission_level is not None
            and payload.permission_level != meta.permission_level
        )
        if wants_disable or wants_permission_change:
            # 文案按名字自适应：心鉴学那几个的理由和"记忆与人格"无关，
            # 写死一句会让用户以为技能坏在别处（见 skill/locked.py）
            raise HTTPException(status_code=409, detail=locked.locked_message(display))

    if payload.permission_level is not None:
        if payload.permission_level not in VALID_PERMISSIONS:
            raise HTTPException(
                status_code=422,
                detail=f"权限级别必须是 {sorted(VALID_PERMISSIONS)} 之一",
            )
        # MCP 技能的权限落盘由 SkillManager 的权限变更回调统一处理
        # （见 runtime._persist_mcp_permission），这里不需要再单独做一次
        runtime.skills.set_permission(name, payload.permission_level)

    if payload.enabled is not None:
        runtime.skills.set_enabled(name, payload.enabled)

    return runtime.skills.get(name).meta.to_dict()


# --------------------------------------------------------------------------- #
# 用户自定义技能
# --------------------------------------------------------------------------- #
class CustomSkillPayload(BaseModel):
    skill: CustomSkillDef


@router.get("/custom")
async def list_custom(request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    return {"skills": [item.model_dump(mode="json") for item in runtime.custom_skills.skills]}


def _validate_custom(runtime: AppRuntime, defn: CustomSkillDef) -> None:
    """HTTP 版的校验：把 :class:`SkillRejected` 转成带状态码的 ``HTTPException``。"""
    try:
        validate_defn(runtime, defn)
    except SkillRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/custom")
async def upsert_custom(payload: CustomSkillPayload, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    defn = payload.skill
    if not defn.source_format:
        # 界面手填的技能也要有来源标识，否则详情里"来源"一栏是空的，
        # 用户会以为这条是导入来的、样式却没跟上
        defn = defn.model_copy(update={"source_format": "manual"})
    _validate_custom(runtime, defn)

    config = runtime.custom_skills.model_copy(deep=True)
    config.upsert(defn)
    runtime.config_store.save_custom_skills(config)
    total = runtime.reload_custom_skills(config)
    return {"ok": True, "skill": defn.model_dump(mode="json"), "total": total}


@router.delete("/custom/{skill_id}")
async def delete_custom(skill_id: str, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    config = runtime.custom_skills.model_copy(deep=True)
    if not config.remove(skill_id):
        raise HTTPException(status_code=404, detail=f"自定义技能「{skill_id}」不存在")
    # 落盘目录一起清掉（见 install.remove_package_dir 的说明）
    remove_package_dir(runtime, skill_id)
    runtime.config_store.save_custom_skills(config)
    total = runtime.reload_custom_skills(config)
    return {"ok": True, "total": total}


@router.get("/custom/{skill_id}/files")
async def skill_files(skill_id: str, request: Request) -> dict[str, Any]:
    """技能包的落盘文件清单（详情弹窗的"包内文件"用）。

    只读、不含内容 —— 界面要展示"包里到底带了什么"，但没必要把几 MB 的模板
    塞进接口响应里。
    """
    runtime: AppRuntime = get_runtime(request)
    root = runtime.paths.skills_dir / skill_id
    files = package_file_list(runtime, skill_id)
    entries: list[dict[str, Any]] = []
    for name in files:
        try:
            size = (root / name).stat().st_size
        except OSError:
            size = 0
        entries.append({"path": name, "size": size})
    return {"skill_id": skill_id, "dir": str(root), "files": entries}


# --------------------------------------------------------------------------- #
# 技能文件夹（投放区）
# --------------------------------------------------------------------------- #
@router.get("/custom/folder")
async def skill_folder(request: Request) -> dict[str, Any]:
    """技能文件夹的位置（界面用它显示路径、并用系统资源管理器打开）。"""
    runtime: AppRuntime = get_runtime(request)
    root = inbox_dir(runtime)
    return {
        "skills_dir": str(runtime.paths.skills_dir),
        "inbox": str(root),
        "exists": root.is_dir(),
    }


class ScanRequest(BaseModel):
    """``POST /custom/scan``：重新扫描技能文件夹。``only`` 留空表示全部。"""

    only: str = Field("", description="只扫描投放区里这个名字的条目（留空 = 全部）")


@router.post("/custom/scan")
async def scan_folder(payload: ScanRequest, request: Request) -> dict[str, Any]:
    """扫描技能投放区并接入（幂等：内容没变的不动）。

    与启动时的那次扫描走**同一份实现**（``skill/inbox.py``），
    只是这里还会把包里的 MCP 配置一并接进来（那一步是 async 的）。
    """
    runtime: AppRuntime = get_runtime(request)
    outcome = await scan_inbox_async(runtime, only=payload.only.strip())
    outcome.pop("mcp_roots", None)
    return outcome


# --------------------------------------------------------------------------- #
# 上传技能包
# --------------------------------------------------------------------------- #
# 一个包里允许同时放多种东西（产品明确要求）：
#   - ``skill.json``：声明式定义（http / command），**能执行动作**
#   - ``SKILL.md``：Claude/Anthropic Agent Skills 的指导技能（可带 frontmatter）
#   - 规则文件（AGENTS.md / .cursorrules / *.mdc / .clinerules）/ 脚本 / MCP 配置
# 识别规则见 ``skill/formats.py``；解析与落盘见 ``skill/package.py``、``skill/folder.py``。
#
# 本模块**不再自己解析 zip**：以前这里与内置技能里各有一份解析逻辑，
# 已经开始漂移（一处落整包、一处只装定义），所以统一收敛到 ``skill/install.py``。


async def _install_package_bytes(
    runtime: AppRuntime, payload: bytes, package_name: str, filename: str = ""
) -> dict[str, Any]:
    """解析技能包字节并逐条安装（上传与 URL 下载共用同一套逻辑）。

    **逐条校验、逐条报告**：一个包里可以有多条定义，坏一条不该拖垮其它条；
    前端把每条的成功/失败原样展示出来，用户才知道具体哪一项要修。
    """
    try:
        parsed = parse_package(payload, package_name, filename=filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    outcome = install_package(runtime, parsed, source_label=filename or package_name)

    mcp_records = await install_mcp_roots(runtime, parsed.mcp_roots)
    if mcp_records:
        outcome["mcp"] = mcp_records
        ok = sum(1 for item in mcp_records if item.get("ok"))
        outcome["message"] = f"{outcome['message']}MCP 服务接入：{ok}/{len(mcp_records)} 个成功。"
    return outcome


@router.post("/custom/import")
async def import_package(
    request: Request, package: UploadFile = File(...)  # noqa: B008  FastAPI 标准注入写法
) -> dict[str, Any]:
    """上传技能包（zip / tar.gz / 单个技能文件），解析并逐条安装。

    ⚠️ 容器类型**按内容识别**（见 ``archive.iter_members``），不只看后缀 ——
    用户常常把包改名，或者直接从浏览器拖来一个没有后缀的文件。
    """
    runtime: AppRuntime = get_runtime(request)
    payload = await package.read()
    filename = (package.filename or "skill.zip").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    package_name = filename.rsplit(".", 1)[0] or "skill"
    return await _install_package_bytes(runtime, payload, package_name, filename)


class ImportUrlRequest(BaseModel):
    """从 URL 下载技能包并安装。"""

    url: str = Field(..., min_length=1, description="技能包（zip）的下载地址")


@router.post("/custom/import-url")
async def import_from_url(payload: ImportUrlRequest, request: Request) -> dict[str, Any]:
    """从 URL 下载技能包并安装（产品要求）。

    让模型能在用户给出一个链接时"自己下载并加载这个 skill"。
    与上传走**同一套**解析/校验/安装逻辑，避免两条路各自漂移。
    """
    import asyncio

    import httpx

    from ...security.urls import validate_endpoint
    from ...skill.archive import MAX_PACKAGE_BYTES
    from ...utils.http import async_client

    runtime: AppRuntime = get_runtime(request)
    url = payload.url.strip()
    # 与集市、自定义 HTTP 技能同一套 SSRF 校验：拒绝内网/云元数据地址
    validate_endpoint(url, field="技能包地址")

    try:
        async with async_client(timeout=httpx.Timeout(20.0, connect=8.0)) as client:
            response = await asyncio.wait_for(
                client.get(url, follow_redirects=True), timeout=20.0
            )
            response.raise_for_status()
            data = response.content
    except Exception as exc:  # noqa: BLE001 - 统一转成人话
        raise HTTPException(status_code=400, detail=f"下载技能包失败：{exc}") from exc

    if len(data) > MAX_PACKAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"技能包超过 {MAX_PACKAGE_BYTES // 1024 // 1024}MB，已拒绝下载。",
        )

    filename = url.rsplit("/", 1)[-1].rsplit("?", 1)[0] or "skill.zip"
    package_name = filename.rsplit(".", 1)[0] or "skill"
    return await _install_package_bytes(runtime, data, package_name, filename)


class ImportPathRequest(BaseModel):
    """``POST /custom/import-path``：导入本机文件夹（多层嵌套原样导入）。"""

    path: str = Field(..., min_length=1, description="要导入的文件夹的绝对路径")
    name: str = Field("", description="技能名（留空则用文件夹名）")
    domain: str = Field(
        "",
        description=(
            "技能**小分类**（技能页「通用技能」栏那排分类按钮按它分组）："
            "电商 / 金融 / 营销 / 教育 / 医疗 / 科技 / 学术 / 设计 / 法律 / 人力 / "
            "办公 / 生活 / 媒体 / 系统。留空 = 不归类。"
            "⚠️ 包内路径里读不到它 —— 批量导入第三方素材库时必须由调用方按源目录分类传进来。"
        ),
    )


@router.post("/custom/import-path")
async def import_from_path(payload: ImportPathRequest, request: Request) -> dict[str, Any]:
    """直接把本机文件夹当技能包导入（界面上的「导入文件夹」）。

    **为什么让核心自己遍历，而不是在渲染层打包上传**：
    - 没有 50MB 与浏览器文件数限制，多层嵌套完整保留；
    - 复用已经存在的目录选择通道（``dialog:pick-directory``），不必新增 IPC；
    - 核心本来就持有本机文件系统权限（内置文件技能），安全面没有扩大。
    """
    runtime: AppRuntime = get_runtime(request)
    raw = payload.path.strip().strip('"')
    target = Path(raw).expanduser()
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"文件夹不存在：{raw}")
    try:
        parsed = parse_directory(target, payload.name.strip() or target.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    outcome = install_package(
        runtime,
        parsed,
        source_label=f"文件夹 {target.name}",
        domain=payload.domain.strip(),
    )
    mcp_records = await install_mcp_roots(runtime, parsed.mcp_roots)
    if mcp_records:
        outcome["mcp"] = mcp_records
        ok = sum(1 for item in mcp_records if item.get("ok"))
        outcome["message"] = f"{outcome['message']}MCP 服务接入：{ok}/{len(mcp_records)} 个成功。"
    outcome["source_path"] = str(target)
    return outcome


__all__ = [
    "HIDDEN_SKILL_NAMES",
    "VALID_PERMISSIONS",
    "_install_package_bytes",
    "router",
]

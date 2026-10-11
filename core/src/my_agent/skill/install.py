"""技能安装：**校验 → 去重 → 落盘 → 回填 → 记账** 的唯一一份实现。

## 为什么单独抽出来

"装一个技能"这件事有**四条路**进来：

1. 上传压缩包 / 从链接下载（HTTP 路由 + 内置技能 ``skill_package_install``）；
2. 导入本机文件夹；
3. 启动时扫描技能投放区（``skills/inbox``）；
4. 搭子包里内嵌的技能包。

老实现把逻辑散在路由与技能里，两边已经开始漂移（一处落整包、一处只装定义）。
现在全部走这里，行为只有一种。

## 落盘范围来自定义本身

``CustomSkillDef.pack_files``（该技能在包内占哪几个文件）为空时按
``package_root`` 落整棵子树 —— 这样一个包含三个技能的包，三个技能目录里
各自只有自己那份文件，不再互相覆盖。
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from typing import Any

from ..config.schemas import CustomSkillDef
from . import locked
from .folder import extract_members, packaged_files
from .package import ParsedPackage, bind_script_commands, slugify

logger = logging.getLogger(__name__)

VALID_PERMISSIONS = {"safe", "confirm", "admin"}

# 保留的技能 id。``inbox`` 是技能投放区**自己**的目录名 —— 允许一个技能叫 inbox，
# 等于让它把用户投放区整个覆盖掉（删技能时会连投放区一起删）。
RESERVED_SKILL_IDS: frozenset[str] = frozenset({"inbox"})

# "内容敏感"字段：扫描技能文件夹时用它判断"包里的内容变没变"，
# 变了才更新（不变就不动，避免每次启动都重写一遍配置）。
_CONTENT_FIELDS = (
    "kind",
    "name",
    "description",
    "instructions",
    "command_template",
    "url",
    "method",
    "body_template",
    "package_root",
    "source_format",
    "scripts",
    "pack_files",
    "allowed_tools",
)


class SkillRejected(Exception):
    """技能不可安装。``status_code`` 让路由能直接转成 HTTP 状态码。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def validate_defn(runtime: Any, defn: CustomSkillDef) -> None:
    """只拦"装上了也用不了"的写法，字段级的问题交给 pydantic。

    抛 :class:`SkillRejected`（带状态码），由调用方决定是转 HTTP 还是记进逐条结果。
    """
    # 占名先查：心鉴学的专属技能与配套工具是"看不见开关、删不掉"的，
    # 允许自建一个同名技能，用户会看到两张同名卡而只有一张能删 ——
    # 那种"看起来一样、行为不一样"的坑最难解释。
    if locked.is_reserved(defn.id) or locked.is_reserved(defn.name or ""):
        raise SkillRejected(
            f"名字「{defn.name or defn.id}」是内置技能占用的名称，请换一个。", 409
        )
    if defn.id in RESERVED_SKILL_IDS or slugify(defn.name or "") in RESERVED_SKILL_IDS:
        raise SkillRejected(
            f"「{'/'.join(sorted(RESERVED_SKILL_IDS))}」是技能文件夹的保留名字，请换一个。", 409
        )
    if defn.kind == "instruction":
        # 指导型：description 是模型判断"这段话是否适用"的依据，同样不能空
        if not defn.description.strip():
            raise SkillRejected("说明不能为空：模型靠它判断这份指导什么时候适用。")
        if not defn.instructions.strip():
            raise SkillRejected("指导内容（SKILL.md）不能为空。")
        return
    if not defn.description.strip():
        # description 是模型决定要不要调用的**唯一**依据。留空的话技能能装上，
        # 但模型永远不知道什么时候该用它 —— 表现为"装了却从来不被调用"。
        raise SkillRejected("说明不能为空：模型靠它决定什么时候用这个技能。")
    if defn.kind == "http" and not defn.url.strip():
        raise SkillRejected("HTTP 技能必须填写请求地址。")
    if defn.kind == "command" and not defn.command_template.strip() and not defn.scripts:
        # 脚本型技能的命令模板要等落盘拿到绝对路径才回填，这里不能拦
        raise SkillRejected("命令技能必须填写要执行的命令。")
    # 与内置技能重名：注册时后者会覆盖前者，表现为"内置技能突然没了"，必须当场拦下
    if runtime.skills.has(defn.id):
        existing = runtime.skills.get(defn.id)
        if existing.meta.source != "custom":
            raise SkillRejected(f"名字「{defn.id}」已被内置技能占用，请换一个。", 409)


def unique_id(config: Any, base: str) -> str:
    """在配置里没被占用时原样返回，否则 ``-2`` / ``-3`` 递增。"""
    if config.get(base) is None:
        return base
    suffix = 2
    while config.get(f"{base}-{suffix}") is not None:
        suffix += 1
    return f"{base}-{suffix}"


def same_content(current: CustomSkillDef, incoming: CustomSkillDef) -> bool:
    """两个定义"实质相同"吗（用于扫描时的幂等判断）。"""
    return all(getattr(current, key) == getattr(incoming, key) for key in _CONTENT_FIELDS)


def install_defs(
    runtime: Any,
    defs: list[CustomSkillDef],
    results: list[dict[str, Any]],
    *,
    prepare: Callable[[CustomSkillDef], CustomSkillDef] | None = None,
) -> tuple[list[CustomSkillDef], int]:
    """把若干条定义装进配置（逐条校验、逐条报告），返回 ``(装上的, 当前总数)``。

    ``prepare``：在"校验通过、id 已定"之后、写配置之前调用一次，
    用来落盘并把结果回填进定义（脚本技能的命令模板就是这么来的）。
    它抛异常时这一条记为失败，其余条照装 —— 一个坏条目不该拖垮整批。
    """
    config = runtime.custom_skills.model_copy(deep=True)
    installed: list[CustomSkillDef] = []
    for defn in defs:
        base_id = defn.id.strip() or slugify(defn.name)
        defn = defn.model_copy(update={"id": base_id})
        try:
            validate_defn(runtime, defn)
        except SkillRejected as exc:
            results.append(
                {
                    "name": defn.name or defn.id,
                    "ok": False,
                    "message": exc.message,
                    "source_format": defn.source_format,
                }
            )
            continue
        defn = defn.model_copy(update={"id": unique_id(config, defn.id)})
        if prepare is not None:
            try:
                defn = prepare(defn) or defn
            except (OSError, ValueError) as exc:
                logger.warning("技能落盘失败（%s）：%s", defn.id, exc)
                results.append(
                    {
                        "name": defn.name or defn.id,
                        "ok": False,
                        "message": f"文件落盘失败：{exc}",
                        "source_format": defn.source_format,
                    }
                )
                continue
        config.upsert(defn)
        installed.append(defn)
        results.append(
            {
                "name": defn.name,
                "id": defn.id,
                "ok": True,
                "kind": defn.kind,
                "source_format": defn.source_format,
                "note": defn.note,
            }
        )

    if installed:
        runtime.config_store.save_custom_skills(config)
        total = runtime.reload_custom_skills(config)
    else:
        total = len(config.skills)
    return installed, total


def unpack_for(
    runtime: Any, defn: CustomSkillDef, members: list[tuple[str, bytes]], source: str = ""
) -> dict[str, Any]:
    """按这条定义的范围落盘（``pack_files`` 优先，否则整棵 ``package_root`` 子树）。"""
    only_files = tuple(defn.pack_files)
    dest = runtime.paths.skills_dir / defn.id
    return extract_members(
        members,
        dest,
        only_root="" if only_files else defn.package_root,
        only_files=only_files,
        source=source,
    )


def install_package(
    runtime: Any,
    parsed: ParsedPackage,
    *,
    source_label: str = "",
    domain: str = "",
) -> dict[str, Any]:
    """把一个已解析的包装进配置并落盘，返回给界面逐条展示的结果。

    只处理技能；MCP 配置由 :func:`install_mcp_roots` 单独接（它要 await MCP 管理器）。

    ``domain`` 是**技能小分类**（技能页那排分类按钮按它分组）。整包共用同一个值，
    由调用方传进来 —— 包内路径里读不到它（`parse_members` 只看包内，看不到
    "这个包是从 `电商/` 目录拖出来的"）。
    """
    results = list(parsed.results)
    unpacked: dict[str, int] = {}

    def prepare(defn: CustomSkillDef) -> CustomSkillDef:
        # 小分类在这里落进定义（落盘之后、写进配置之前）。技能自己带了就不覆盖 ——
        # 包里显式声明的比"从文件夹名推的"更可信。
        if domain and not defn.domain:
            defn = defn.model_copy(update={"domain": domain})
        summary = unpack_for(runtime, defn, parsed.members.members, source_label)
        if summary["count"]:
            unpacked[defn.id] = summary["count"]
        return bind_script_commands(defn, runtime.paths.skills_dir / defn.id)

    installed, total = install_defs(runtime, parsed.defs, results, prepare=prepare)

    ok_count = sum(1 for item in results if item.get("ok"))
    notes: list[str] = [f"导入完成：{ok_count}/{len(results)} 条成功。"]
    if unpacked:
        notes.append("整包已落盘：" + "、".join(f"{k}（{v} 个文件）" for k, v in unpacked.items()) + "。")
    if parsed.unrecognized:
        notes.append(
            f"另有 {len(parsed.unrecognized)} 个文件未参与识别，已随包原样保留"
            "（在技能详情里能看到完整清单）。"
        )
    if parsed.members.skipped:
        notes.append(f"{len(parsed.members.skipped)} 个条目因路径不安全被跳过。")
    return {
        "ok": ok_count > 0,
        "installed": [item.model_dump(mode="json") for item in installed],
        "results": results,
        "unpacked": unpacked,
        "unrecognized": parsed.unrecognized,
        "skipped": parsed.members.skipped,
        "total": total,
        "message": "".join(notes),
    }


async def install_mcp_roots(runtime: Any, roots: list[Any]) -> list[dict[str, Any]]:
    """把包里识别到的 MCP 配置逐条接进来（复用 MCP 已有的导入实现）。

    逐条报告成功 / 失败；**同名不覆盖**（与 MCP 页面上的"粘贴导入"默认行为一致，
    用户不会期望"装个技能包顺手改掉我的 MCP 服务"）。
    """
    if not roots:
        return []
    # 局部导入：MCP 的归一化实现只有一份（现在是 ``mcp/normalize.py``），
    # 在这里重抄一遍必然与它漂移 —— 而"粘贴能导入、包里导入报字段错"最难查。
    #
    # ⚠️ 原先这里 import 的是 ``server.routes.mcp`` 里的**私有函数**（审计 H-06）：
    # 技能层为了一段配置的归一化，要反向依赖路由层，而且依赖的是 `_` 开头的"内部实现"。
    # 归一化已在 下沉到 ``mcp/normalize.py``，这一行正过来了。
    from pydantic import ValidationError

    from ..errors import McpServerError
    from ..mcp.normalize import coerce_entry, first_error

    records: list[dict[str, Any]] = []
    for root in roots:
        for raw in root.mcp_servers:
            name = str(raw.get("name") or "").strip()
            if not name:
                continue
            try:
                config = coerce_entry(name, {k: v for k, v in raw.items() if k != "name"})
            except (ValueError, ValidationError) as exc:
                message = first_error(exc) if isinstance(exc, ValidationError) else str(exc)
                records.append({"name": name, "ok": False, "message": message})
                continue
            if runtime.mcp.status(name) is not None:
                records.append({"name": name, "ok": False, "message": "本机已有同名 MCP 服务，未覆盖"})
                continue
            try:
                await runtime.mcp.add_server(config)
            except McpServerError as exc:
                detail = exc.to_dict()
                records.append(
                    {"name": name, "ok": False, "message": str(detail.get("message") or detail)}
                )
                continue
            records.append({"name": name, "ok": True, "message": "MCP 服务已接入"})
    return records


def remove_package_dir(runtime: Any, skill_id: str) -> None:
    """删技能时把它的落盘目录一起清掉。

    留着的话，同名技能重新安装时会看到上一版的残留文件（覆盖只覆盖同名文件），
    说明里提到的文件可能来自上一个版本 —— 最难查的一类问题。
    """
    package_dir = runtime.paths.skills_dir / skill_id
    if package_dir.is_dir():
        shutil.rmtree(package_dir, ignore_errors=True)


def package_file_list(runtime: Any, skill_id: str) -> list[str]:
    """某个技能包目录里的文件清单（详情弹窗展示用；没落盘过返回空列表）。"""
    return packaged_files(runtime.paths.skills_dir / skill_id)


__all__ = [
    "RESERVED_SKILL_IDS",
    "SkillRejected",
    "VALID_PERMISSIONS",
    "install_defs",
    "install_mcp_roots",
    "install_package",
    "package_file_list",
    "remove_package_dir",
    "same_content",
    "unique_id",
    "unpack_for",
    "validate_defn",
]

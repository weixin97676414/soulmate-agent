




















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



RESERVED_SKILL_IDS: frozenset[str] = frozenset({"inbox"})



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


    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def validate_defn(runtime: Any, defn: CustomSkillDef) -> None:




    
    
    
    if locked.is_reserved(defn.id) or locked.is_reserved(defn.name or ""):
        raise SkillRejected(
            f"名字「{defn.name or defn.id}」是内置技能占用的名称，请换一个。", 409
        )
    if defn.id in RESERVED_SKILL_IDS or slugify(defn.name or "") in RESERVED_SKILL_IDS:
        raise SkillRejected(
            f"「{'/'.join(sorted(RESERVED_SKILL_IDS))}」是技能文件夹的保留名字，请换一个。", 409
        )
    if defn.kind == "instruction":
        
        if not defn.description.strip():
            raise SkillRejected("说明不能为空：模型靠它判断这份指导什么时候适用。")
        if not defn.instructions.strip():
            raise SkillRejected("指导内容（SKILL.md）不能为空。")
        return
    if not defn.description.strip():
        
        
        raise SkillRejected("说明不能为空：模型靠它决定什么时候用这个技能。")
    if defn.kind == "http" and not defn.url.strip():
        raise SkillRejected("HTTP 技能必须填写请求地址。")
    if defn.kind == "command" and not defn.command_template.strip() and not defn.scripts:
        
        raise SkillRejected("命令技能必须填写要执行的命令。")
    
    if runtime.skills.has(defn.id):
        existing = runtime.skills.get(defn.id)
        if existing.meta.source != "custom":
            raise SkillRejected(f"名字「{defn.id}」已被内置技能占用，请换一个。", 409)


def unique_id(config: Any, base: str) -> str:

    if config.get(base) is None:
        return base
    suffix = 2
    while config.get(f"{base}-{suffix}") is not None:
        suffix += 1
    return f"{base}-{suffix}"


def same_content(current: CustomSkillDef, incoming: CustomSkillDef) -> bool:

    return all(getattr(current, key) == getattr(incoming, key) for key in _CONTENT_FIELDS)


def install_defs(
    runtime: Any,
    defs: list[CustomSkillDef],
    results: list[dict[str, Any]],
    *,
    prepare: Callable[[CustomSkillDef], CustomSkillDef] | None = None,
) -> tuple[list[CustomSkillDef], int]:






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








    results = list(parsed.results)
    unpacked: dict[str, int] = {}

    def prepare(defn: CustomSkillDef) -> CustomSkillDef:
        
        
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





    if not roots:
        return []
    
    
    
    
    
    
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





    package_dir = runtime.paths.skills_dir / skill_id
    if package_dir.is_dir():
        shutil.rmtree(package_dir, ignore_errors=True)


def package_file_list(runtime: Any, skill_id: str) -> list[str]:

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

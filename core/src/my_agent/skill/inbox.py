

























from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .archive import iter_members
from .install import (
    SkillRejected,
    install_mcp_roots,
    same_content,
    unique_id,
    unpack_for,
    validate_defn,
)
from .package import ParsedPackage, bind_script_commands, parse_directory, parse_members, slugify

logger = logging.getLogger(__name__)

INBOX_NAME = "inbox"


def inbox_dir(runtime: Any) -> Path:
    paths = getattr(runtime, "paths", None)
    root = getattr(paths, "skills_inbox_dir", None)
    if root is None:
        return Path(paths.skills_dir) / INBOX_NAME
    return Path(root)


def inbox_entries(runtime: Any) -> list[Path]:





    root = inbox_dir(runtime)
    if not root.is_dir():
        return []
    return [
        item
        for item in sorted(root.iterdir())
        if not item.name.startswith((".", "_"))
    ]


def parse_entry(entry: Path) -> ParsedPackage:

    if entry.is_dir():
        return parse_directory(entry, entry.name)
    packed = iter_members(entry.read_bytes(), entry.name)
    return parse_members(packed, entry.stem or entry.name)


def scan_inbox(runtime: Any, *, only: str = "") -> dict[str, Any]:













    entries = inbox_entries(runtime)
    if only:
        entries = [item for item in entries if item.name == only]
    if not entries:
        
        return {
            "ok": True,
            "installed": [],
            "results": [],
            "unpacked": {},
            "unrecognized": [],
            "skipped": [],
            "total": len(getattr(runtime.custom_skills, "skills", []) or []),
            "scanned": 0,
            "counts": {"added": 0, "updated": 0, "skipped": 0, "failed": 0},
            "message": "技能文件夹是空的：把技能文件夹或技能文件放进去再扫描。",
        }

    results: list[dict[str, Any]] = []
    mcp_roots: list[Any] = []
    config = runtime.custom_skills.model_copy(deep=True)
    changed = False
    counts = {"added": 0, "updated": 0, "skipped": 0, "failed": 0}

    for entry in entries:
        try:
            parsed = parse_entry(entry)
        except ValueError as exc:
            counts["failed"] += 1
            results.append({"name": entry.name, "ok": False, "message": str(exc)})
            continue
        results.extend(parsed.results)
        mcp_roots.extend(parsed.mcp_roots)

        for defn in parsed.defs:
            base_id = defn.id.strip() or slugify(defn.name)
            defn = defn.model_copy(update={"id": base_id})
            try:
                validate_defn(runtime, defn)
            except SkillRejected as exc:
                counts["failed"] += 1
                results.append(
                    {"name": defn.name or defn.id, "ok": False, "message": exc.message}
                )
                continue

            dest = runtime.paths.skills_dir / defn.id
            bound = bind_script_commands(defn, dest)
            existing = config.get(defn.id)

            if existing is not None and same_content(existing, bound):
                counts["skipped"] += 1
                results.append(
                    {
                        "name": bound.name,
                        "id": bound.id,
                        "ok": True,
                        "skipped": True,
                        "source_format": bound.source_format,
                        "message": "内容没变，已跳过",
                    }
                )
                continue

            if existing is not None:
                
                bound = bound.model_copy(
                    update={
                        "enabled": existing.enabled,
                        "permission_level": existing.permission_level,
                    }
                )
            else:
                bound = bound.model_copy(update={"id": unique_id(config, bound.id)})
                
                dest = runtime.paths.skills_dir / bound.id
                bound = bind_script_commands(bound, dest)

            try:
                summary = unpack_for(runtime, bound, parsed.members.members, parsed.members.container)
            except (OSError, ValueError) as exc:
                counts["failed"] += 1
                results.append(
                    {"name": bound.name, "ok": False, "message": f"文件落盘失败：{exc}"}
                )
                continue

            config.upsert(bound)
            changed = True
            action = "updated" if existing is not None else "added"
            counts[action] += 1
            results.append(
                {
                    "name": bound.name,
                    "id": bound.id,
                    "ok": True,
                    "kind": bound.kind,
                    "source_format": bound.source_format,
                    "note": bound.note,
                    "updated": existing is not None,
                    "files": summary.get("count", 0),
                    "message": "已更新（内容有变化）" if existing is not None else "已接入",
                }
            )

    if changed:
        runtime.config_store.save_custom_skills(config)
        runtime.reload_custom_skills(config)

    message = (
        f"扫描完成：新增 {counts['added']}、更新 {counts['updated']}、"
        f"跳过 {counts['skipped']}、失败 {counts['failed']}。"
    )
    if mcp_roots:
        
        
        message += f"另有 {len(mcp_roots)} 份 MCP 服务配置，会一并接入（同名的不覆盖）。"
    
    
    
    return {
        "ok": counts["failed"] == 0,
        "installed": [],
        "results": results,
        "unpacked": {},
        "unrecognized": [],
        "skipped": [],
        "total": len(config.skills),
        "scanned": len(entries),
        "counts": counts,
        "mcp_roots": mcp_roots,
        "message": message,
    }


async def scan_inbox_async(runtime: Any, *, only: str = "") -> dict[str, Any]:

    outcome = scan_inbox(runtime, only=only)
    roots = outcome.pop("mcp_roots", [])
    records = await install_mcp_roots(runtime, roots)
    if records:
        outcome["mcp"] = records
        ok = sum(1 for item in records if item.get("ok"))
        outcome["message"] = (
            f"{outcome['message']} MCP 服务接入：{ok}/{len(records)} 个成功。"
        )
    return outcome


__all__ = [
    "INBOX_NAME",
    "inbox_dir",
    "inbox_entries",
    "parse_entry",
    "scan_inbox",
    "scan_inbox_async",
]

"""技能投放区（``skills/inbox``）：用户把文件夹或文件丢进去，应用扫描接入。

## 为什么要有投放区

用户手上可能有一整套现成的技能目录（从别处拷来的、自己攒的、从别的 AI 客户端
导出的一整个 ``skills/`` 目录）。一个个打包再上传太麻烦 —— 直接复制进去就够了。

## 为什么必须与解包区分离

应用自己解出来的包写在 ``skills/<技能id>/``。如果扫描把整个 ``skills/`` 当投放区，
就会把**自己解出来的包再导入一次**，产生 ``xxx-2``、``xxx-3`` …… 每次启动长一条。
所以投放区固定是 ``skills/inbox``，且 ``inbox`` 是保留技能名
（见 ``install.RESERVED_SKILL_IDS``）。

## 幂等规则

投放区是"源"，**以文件为准**：

- 同名技能不存在 → 新增；
- 同名存在且内容相同 → 跳过（不重写配置，免得每次启动都动一次盘）；
- 同名存在但内容变了 → 更新，并**保留用户改过的启用状态与权限档**。

内容不同的判断见 ``install.same_content``。界面上要如实说明"技能文件夹里的文件是源"，
否则用户会以为"我改了界面上的说明怎么下次启动又变回去了"。
"""

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
    """投放区第一层的条目（跳过隐藏项与 ``_`` 开头的临时文件）。

    只扫**一层**：用户丢一个目录进来就把它整个当一个技能包解析，
    不会钻进它的子目录去找"更多技能"——那样一个大型目录会炸出几百个技能。
    """
    root = inbox_dir(runtime)
    if not root.is_dir():
        return []
    return [
        item
        for item in sorted(root.iterdir())
        if not item.name.startswith((".", "_"))
    ]


def parse_entry(entry: Path) -> ParsedPackage:
    """把一个投放条目解析成技能包（文件与目录都收）。"""
    if entry.is_dir():
        return parse_directory(entry, entry.name)
    packed = iter_members(entry.read_bytes(), entry.name)
    return parse_members(packed, entry.stem or entry.name)


def scan_inbox(runtime: Any, *, only: str = "") -> dict[str, Any]:
    """扫描投放区并接入（幂等）。返回给界面逐条展示的结果。

    ⚠️ **这里不接 MCP**：接入 MCP 是 async 且会真的拉起子进程 / 建网络连接，
    而这个函数走在**启动路径**上（同步、不能 await），不能拖住客户端启动。
    包里的 MCP 配置原样放在返回值的 ``mcp_roots`` 里，由调用方决定怎么接：

    - ``scan_inbox_async``（HTTP 路由 ``/custom/scan`` 走的那条）；
    - ``Runtime._connect_inbox_mcp`` —— 启动完成后的**后台任务**。

    2026-10-06 之前只有第一条路接 MCP，界面上靠「重新扫描」按钮触发；
    那个按钮已被移除（技能页只留一个入口），所以启动后的后台任务成了
    默认那条路 —— 否则投放区里的 MCP 配置就此再无入口。
    """
    entries = inbox_entries(runtime)
    if only:
        entries = [item for item in entries if item.name == only]
    if not entries:
        # 形状要和"有内容"的那条路一致（前端只有一套结果弹窗在吃它）
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
                # 更新：保留用户改过的启用状态与权限档，别把"关掉的技能"又打开
                bound = bound.model_copy(
                    update={
                        "enabled": existing.enabled,
                        "permission_level": existing.permission_level,
                    }
                )
            else:
                bound = bound.model_copy(update={"id": unique_id(config, bound.id)})
                # ⚠️ id 变了的话，落盘目录要跟着变
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
        # 两条调用路都会真的去接（async 路由 / 启动后的后台任务），
        # 所以这里只说"会一并接入"，不指路到某个按钮 —— 那个按钮已经没了。
        message += f"另有 {len(mcp_roots)} 份 MCP 服务配置，会一并接入（同名的不覆盖）。"
    # 形状与其它三条导入路**保持一致**（前端只有一个结果弹窗）：
    # 扫描没有"整包落盘清单"与"未识别文件"的概念，但字段必须在，
    # 否则前端读 `skipped.length` 会直接崩。
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
    """界面上的「重新扫描」：在同步扫描的基础上，把 MCP 配置也接进来。"""
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

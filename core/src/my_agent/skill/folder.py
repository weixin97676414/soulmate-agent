
































from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from .archive import Member, iter_members

logger = logging.getLogger(__name__)



MAX_LISTING = 40


INDEX_FILE = "_pack_index.md"


def _human(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / 1024 / 1024:.1f}MB"


def _clear(dest: Path) -> None:





    if not dest.is_dir():
        return
    for item in dest.iterdir():
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            try:
                item.unlink()
            except OSError as exc:  
                logger.warning("技能包旧文件删除失败：%s（%s）", item, exc)


def _collapse(name: str, used: set[str]) -> str:





    base = name.rsplit("/", 1)[-1]
    if base and base not in used:
        return base
    return name


def write_index(dest: Path, entries: list[tuple[str, int]], *, source: str = "") -> None:





    lines = ["# 技能包文件清单", ""]
    if source:
        lines.append(f"来源：{source}")
    lines.append(f"共 {len(entries)} 个文件。")
    lines.append("")
    lines.extend(f"- {name}（{_human(size)}）" for name, size in entries)
    try:
        (dest / INDEX_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("技能包清单写入失败：%s（%s）", dest, exc)


def extract_members(
    members: list[Member],
    dest: Path,
    *,
    only_root: str = "",
    only_files: tuple[str, ...] | list[str] = (),
    source: str = "",
) -> dict[str, Any]:









    dest.mkdir(parents=True, exist_ok=True)
    _clear(dest)

    wanted: list[tuple[str, bytes]] = []
    wanted_files = set(only_files)
    for name, data in members:
        if wanted_files:
            if name in wanted_files:
                wanted.append((name, data))
            continue
        if only_root:
            if name == only_root:
                continue
            if not name.startswith(f"{only_root}/"):
                continue
            wanted.append((name[len(only_root) + 1 :], data))
            continue
        wanted.append((name, data))

    used: set[str] = set()
    written: list[tuple[str, int]] = []
    skipped: list[str] = []
    root_path = dest.resolve()
    for name, data in wanted:
        relative = _collapse(name, used) if wanted_files else name
        if not relative:
            continue
        target = dest / relative
        
        try:
            target.resolve().relative_to(root_path)
        except ValueError:
            skipped.append(name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_bytes(data)
        except OSError as exc:  
            logger.warning("技能包条目写入失败：%s（%s）", name, exc)
            skipped.append(name)
            continue
        used.add(relative)
        written.append((relative, len(data)))

    write_index(dest, written, source=source)
    if skipped:
        logger.info("技能包解包跳过 %d 个条目（路径不安全或写入失败）", len(skipped))
    return {
        "count": len(written),
        "files": sorted(name for name, _ in written),
        "root": only_root,
        "skipped": skipped,
    }


def extract_package(
    payload: bytes,
    dest: Path,
    *,
    filename: str = "package.zip",
    only_root: str = "",
    only_files: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:





    packed = iter_members(payload, filename)
    return extract_members(
        packed.members, dest, only_root=only_root, only_files=only_files, source=packed.container
    )


def packaged_files(dest: Path) -> list[str]:




    if not dest.is_dir():
        return []
    return sorted(
        item.relative_to(dest).as_posix()
        for item in dest.rglob("*")
        if item.is_file() and item.name != INDEX_FILE
    )


def listing_hint(dest: Path, *, limit: int = MAX_LISTING) -> str:










    files = packaged_files(dest)
    if not files:
        return ""
    shown = files[: max(1, limit)]
    lines = []
    for name in shown:
        try:
            size = (dest / name).stat().st_size
        except OSError:
            size = 0
        lines.append(f"- {name}（{_human(size)}）")
    if len(files) > len(shown):
        lines.append(
            f"- …另有 {len(files) - len(shown)} 个文件，完整清单见 "
            f"{dest / INDEX_FILE}（该文件列出全部 {len(files)} 个文件）"
        )
    return "\n".join(lines)


__all__ = [
    "INDEX_FILE",
    "MAX_LISTING",
    "extract_members",
    "extract_package",
    "listing_hint",
    "packaged_files",
    "write_index",
]

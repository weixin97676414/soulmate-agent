



















from __future__ import annotations

import io
import logging
import os
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .formats import Member

logger = logging.getLogger(__name__)

MAX_PACKAGE_BYTES = 50 * 1024 * 1024
MAX_UNPACKED_BYTES = 300 * 1024 * 1024
MAX_MEMBERS = 5000


SINGLE_FILE_SUFFIXES = (".md", ".txt", ".json", ".yaml", ".yml", ".mdc")
TAR_SUFFIXES = (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")



SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".svn",
        ".hg",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".idea",
    }
)


def _mb(size: int) -> str:
    return f"{size / 1024 / 1024:.1f}MB"


@dataclass
class PackageMembers:







    members: list[Member] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    container: str = ""  
    root: str = ""  

    @property
    def count(self) -> int:
        return len(self.members)

    def as_files(self) -> dict[str, bytes]:

        return {name: data for name, data in self.members}


def safe_relative(name: str) -> str | None:





    raw = name.replace("\\", "/").strip()
    if not raw or raw.endswith("/"):
        return None
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        return None
    parts = [chunk for chunk in raw.split("/") if chunk not in ("", ".")]
    if not parts or any(chunk == ".." for chunk in parts):
        return None
    return "/".join(parts)


def common_root(names: list[str]) -> str:









    roots: set[str] = set()
    for name in names:
        cleaned = name.replace("\\", "/").strip("/")
        if not cleaned:
            continue
        roots.add(cleaned.split("/", 1)[0])
    if len(roots) == 1:
        only = next(iter(roots))
        if any("/" in item.replace("\\", "/").strip("/") for item in names):
            return only
    return ""


def _strip_common_root(members: list[Member]) -> tuple[list[Member], str]:

    root = common_root([name for name, _ in members])
    if not root:
        return members, ""
    result: list[Member] = []
    for name, data in members:
        parts = [chunk for chunk in name.split("/") if chunk]
        if parts and parts[0] == root:
            parts = parts[1:]
        if not parts:
            continue
        result.append(("/".join(parts), data))
    return result, root


def _filter_safe(members: list[Member]) -> tuple[list[Member], list[str]]:
    safe: list[Member] = []
    skipped: list[str] = []
    for name, data in members:
        cleaned = safe_relative(name)
        if cleaned is None:
            skipped.append(name)
            continue
        safe.append((cleaned, data))
    return safe, skipped


def _from_zip(payload: bytes) -> tuple[list[Member], list[str]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ValueError("不是合法的 zip 压缩包。") from exc

    members: list[Member] = []
    skipped: list[str] = []
    total = 0
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if len(members) >= MAX_MEMBERS:
                raise ValueError(
                    f"包内文件太多（超过 {MAX_MEMBERS} 个），已拒绝导入 —— "
                    "请确认这个包是不是技能包。"
                )
            total += info.file_size
            if total > MAX_UNPACKED_BYTES:
                raise ValueError(
                    f"解压后体积过大（超过 {_mb(MAX_UNPACKED_BYTES)}），已拒绝导入 —— "
                    "请确认这个包是不是技能包。"
                )
            try:
                data = archive.read(info)
            except (zipfile.BadZipFile, OSError) as exc:  
                logger.warning("技能包条目读取失败：%s（%s）", info.filename, exc)
                skipped.append(info.filename)
                continue
            members.append((info.filename, data))
    return members, skipped


def _from_tar(payload: bytes) -> tuple[list[Member], list[str]]:
    try:
        archive = tarfile.open(fileobj=io.BytesIO(payload), mode="r:*")
    except tarfile.TarError as exc:
        raise ValueError("不是合法的 tar 压缩包。") from exc

    members: list[Member] = []
    skipped: list[str] = []
    total = 0
    with archive:
        for info in archive.getmembers():
            
            
            if not info.isfile():
                if not info.isdir():
                    skipped.append(info.name)
                continue
            if len(members) >= MAX_MEMBERS:
                raise ValueError(
                    f"包内文件太多（超过 {MAX_MEMBERS} 个），已拒绝导入 —— "
                    "请确认这个包是不是技能包。"
                )
            total += info.size
            if total > MAX_UNPACKED_BYTES:
                raise ValueError(
                    f"解压后体积过大（超过 {_mb(MAX_UNPACKED_BYTES)}），已拒绝导入 —— "
                    "请确认这个包是不是技能包。"
                )
            try:
                handle = archive.extractfile(info)
                data = handle.read() if handle is not None else b""
            except (tarfile.TarError, OSError) as exc:
                logger.warning("技能包条目读取失败：%s（%s）", info.name, exc)
                skipped.append(info.name)
                continue
            members.append((info.name, data))
    return members, skipped


def _decode_name(filename: str) -> str:
    return filename.replace("\\", "/").rsplit("/", 1)[-1].strip()


def _from_single_file(payload: bytes, filename: str) -> tuple[list[Member], list[str]]:

    name = _decode_name(filename) or "SKILL.md"
    return [(name, payload)], []


def iter_members(payload: bytes, filename: str) -> PackageMembers:






    if len(payload) > MAX_PACKAGE_BYTES:
        raise ValueError(
            f"技能包超过 {_mb(MAX_PACKAGE_BYTES)}（实测 {_mb(len(payload))}），"
            "请检查是否传错了文件。"
        )
    lower = filename.lower()
    if payload[:2] == b"PK" or lower.endswith(".zip"):
        raw, skipped = _from_zip(payload)
        container = "zip"
    elif (
        payload[:2] == b"\x1f\x8b"  
        or lower.endswith(TAR_SUFFIXES)
        or tarfile.is_tarfile(io.BytesIO(payload)) is True
    ):
        raw, skipped = _from_tar(payload)
        container = "tar"
    else:
        raw, skipped = _from_single_file(payload, filename)
        container = "file"

    safe, unsafe = _filter_safe(raw)
    stripped, root = _strip_common_root(safe)
    return PackageMembers(
        members=stripped, skipped=[*skipped, *unsafe], container=container, root=root
    )


def members_from_directory(root: Path) -> PackageMembers:









    if not root.is_dir():
        raise ValueError(f"文件夹不存在：{root}")

    members: list[Member] = []
    skipped: list[str] = []
    total = 0
    for current, dirnames, filenames in os.walk(root):
        
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIR_NAMES]
        for filename in sorted(filenames):
            item = Path(current) / filename
            relative = str(item.relative_to(root)).replace("\\", "/")
            if item.is_symlink():
                
                skipped.append(relative)
                continue
            cleaned = safe_relative(relative)
            if cleaned is None:
                skipped.append(relative)
                continue
            if len(members) >= MAX_MEMBERS:
                raise ValueError(
                    f"文件夹里文件太多（超过 {MAX_MEMBERS} 个），已拒绝导入 —— "
                    "请确认选的是技能文件夹，不是整个磁盘目录。"
                )
            try:
                data = item.read_bytes()
            except OSError as exc:
                logger.warning("技能文件夹里读不出文件：%s（%s）", item, exc)
                skipped.append(relative)
                continue
            total += len(data)
            if total > MAX_UNPACKED_BYTES:
                raise ValueError(
                    f"文件夹体积过大（超过 {_mb(MAX_UNPACKED_BYTES)}），已拒绝导入 —— "
                    "请确认选的是技能文件夹，不是整个磁盘目录。"
                )
            members.append((cleaned, data))

    if not members:
        raise ValueError("这个文件夹里没有任何文件。")
    return PackageMembers(members=members, skipped=skipped, container="folder", root="")


__all__ = [
    "MAX_MEMBERS",
    "MAX_PACKAGE_BYTES",
    "MAX_UNPACKED_BYTES",
    "SKIP_DIR_NAMES",
    "Member",
    "PackageMembers",
    "common_root",
    "iter_members",
    "members_from_directory",
    "safe_relative",
]

"""压缩包：**只看内容，不解压**（产品约定）。

## 为什么只读、不落盘

用户的原话是「先只做"看内容"，不做解压」—— 能列出压缩包里有什么、能读其中某个文件的
内容，但**不往磁盘写任何东西**。这个取舍很省事也很安全：不需要路径穿越（zip slip）
防护、不会把用户的目录搞乱、也不会因为解压出一个几百 MB 的东西把磁盘塞满。

真要把里面的文件拿出来时，模型还有别的路：读取内容后自己用 write 类技能写出去
（那一步是 confirm 级、用户看得见）。

## 支持哪些格式

标准库覆盖的：``.zip``（含 ``.jar``/``.whl`` 这类 zip 容器）、``.tar``、``.tar.gz``/
``.tgz``、``.tar.bz2``、``.tar.xz``。**7z / rar 明确不支持** —— 它们要新增依赖
（py7zr / rarfile，后者还要外部程序），而本项目的口径是不加依赖。不支持时给一句
可读的说明，而不是抛一个模块导入错误。

## 两处必须有的闸

1. **单成员读取上限**：压缩包是典型的"解压炸弹"载体（几 KB 压出几个 GB），
   所以读取时按字节截断，并如实说明"只读了前面 N 字节"；
2. **条目数上限**：几万条目的包列表出来会直接撑爆上下文。
"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ..base import BaseSkill, SkillContext
from ..decorator import skill

# 列表最多回多少条目（超出如实说明"还有 N 条没列"）
MAX_ENTRIES = 500
# 单个成员最多读多少字符（防解压炸弹；超出时明确告知截断位置）
MAX_CHARS = 20_000
# 判定"这是不是文本"的采样长度
SNIFF_BYTES = 2048

_TAR_SUFFIXES = (".tar", ".tgz", ".tar.gz", ".tar.bz2", ".tar.xz", ".tbz2", ".txz")
# 这些格式**故意不支持**，并且要把原因说清楚（用户会问"为什么 rar 不行"）
_UNSUPPORTED = {
    ".7z": "7z",
    ".rar": "rar",
    ".iso": "iso 镜像",
    ".cab": "cab 压缩包",
}


def _format_of(path: Path) -> str:
    """判断归档格式；不认识就给一句人能看懂的说明。"""
    name = path.name.lower()
    if name.endswith(".zip") or name.endswith(".jar") or name.endswith(".whl"):
        return "zip"
    if any(name.endswith(suffix) for suffix in _TAR_SUFFIXES):
        return "tar"
    for suffix, label in _UNSUPPORTED.items():
        if name.endswith(suffix):
            raise SkillExecutionError(
                f"暂不支持 {label} 格式的压缩包（本应用只用 Python 标准库，不额外装解压组件）。"
                "如果里面是文档/表格，可以先解压或用系统自带的解压工具展开，再让我读那些文件。"
            )
    if zipfile.is_zipfile(path):
        # 后缀不认识但内容确实是 zip（比如 .apk / .docx）——按 zip 处理
        return "zip"
    raise SkillExecutionError(
        f"这个文件不是压缩包，或者格式不支持：{path.name}。"
        "目前支持 zip 与 tar（含 .tar.gz / .tgz / .tar.bz2 / .tar.xz）。"
    )


def _entries(path: Path, fmt: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if fmt == "zip":
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                out.append(
                    {
                        "name": info.filename,
                        "size": info.file_size,
                        "compressed_size": info.compress_size,
                        "modified": f"{info.date_time[0]:04d}-{info.date_time[1]:02d}-{info.date_time[2]:02d}"
                        f" {info.date_time[3]:02d}:{info.date_time[4]:02d}",
                        "is_dir": info.is_dir(),
                    }
                )
        return out
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            out.append(
                {
                    "name": member.name,
                    "size": member.size,
                    "compressed_size": None,
                    "modified": _stamp(member.mtime),
                    "is_dir": member.isdir(),
                }
            )
    return out


def _stamp(epoch: float | int | None) -> str:
    if not epoch:
        return ""
    from datetime import datetime

    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")


def _read_member(path: Path, fmt: str, member: str, max_chars: int) -> dict[str, Any]:
    """读单个成员的内容（按字节采样 + 截断）。"""
    if fmt == "zip":
        with zipfile.ZipFile(path) as archive:
            target = _match_zip(archive, member)
            with archive.open(target) as handle:
                raw = handle.read(SNIFF_BYTES)
                if _looks_binary(raw):
                    return {"binary": True, "name": target.filename, "size": target.file_size}
                rest = handle.read(MAX_CHARS * 4)
        text = (raw + rest).decode("utf-8", errors="replace")
        size = target.file_size
    else:
        with tarfile.open(path) as archive:
            info = _match_tar(archive, member)
            if not info.isfile():
                raise SkillExecutionError(f"「{member}」在压缩包里不是一个普通文件。")
            handle = archive.extractfile(info)
            if handle is None:  # pragma: no cover - tarfile 对普通文件不会返回 None
                raise SkillExecutionError(f"读不到「{member}」的内容。")
            raw = handle.read(SNIFF_BYTES)
            if _looks_binary(raw):
                return {"binary": True, "name": info.name, "size": info.size}
            text = (raw + handle.read(MAX_CHARS * 4)).decode("utf-8", errors="replace")
            size = info.size

    truncated = len(text) > max_chars
    return {
        "binary": False,
        "text": text[:max_chars],
        "truncated": truncated,
        "total_chars": len(text),
        "size": size,
    }


def _looks_binary(raw: bytes) -> bool:
    """是不是二进制：含 NUL 字节基本可以断定（文本文件里不会有它）。"""
    return b"\x00" in raw


def _match_zip(archive: zipfile.ZipFile, member: str) -> zipfile.ZipInfo:
    wanted = member.strip().lstrip("/")
    for info in archive.infolist():
        if info.filename == wanted or info.filename.endswith(f"/{wanted}"):
            return info
    raise SkillExecutionError(
        f"压缩包里没有「{member}」。先用 archive_list 看一遍里面的文件名（要写全，含目录）。"
    )


def _match_tar(archive: tarfile.TarFile, member: str) -> tarfile.TarInfo:
    wanted = member.strip().lstrip("/")
    for info in archive.getmembers():
        if info.name == wanted or info.name.endswith(f"/{wanted}"):
            return info
    raise SkillExecutionError(
        f"压缩包里没有「{member}」。先用 archive_list 看一遍里面的文件名（要写全，含目录）。"
    )


class ArchiveListParams(BaseModel):
    file_path: str = Field(..., description="压缩包的路径（工作区里的文件，或用户上传的附件）")


@skill(
    name="archive_list",
    display_name="查看压缩包内容",
    description=(
        "列出压缩包里有哪些文件（文件名、原始大小、压缩后大小、修改时间）。"
        "当用户说「看看这个压缩包里有什么」「这份 zip 里有哪些文件」时使用。"
        "⚠️ 它**不会解压**任何东西、不往磁盘写文件；要看某个文件的内容请接着用 archive_read。"
    ),
    params_model=ArchiveListParams,
    category="office",
    permission_level="safe",
    tags=["压缩包", "文件"],
)
class ArchiveListSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ArchiveListParams(**params)
        path = ctx.resolve_input_file(args.file_path)
        fmt = _format_of(path)
        items = _entries(path, fmt)
        files = [item for item in items if not item["is_dir"]]
        shown = items[:MAX_ENTRIES]
        result: dict[str, Any] = {
            "format": fmt,
            "entry_count": len(items),
            "file_count": len(files),
            "total_size": sum(int(item["size"] or 0) for item in files),
            "entries": shown,
        }
        if len(items) > len(shown):
            # 不静默截断：说清还有多少条没列
            result["note"] = f"条目太多，这里只列了前 {len(shown)} 条（共 {len(items)} 条）。"
        return result


class ArchiveReadParams(BaseModel):
    file_path: str = Field(..., description="压缩包的路径")
    member: str = Field(
        ...,
        description="要读的文件名（**含目录**，先用 archive_list 拿到准确名字）",
    )
    max_chars: int = Field(
        MAX_CHARS, ge=100, le=200_000, description="最多读多少字符（默认 2 万）"
    )


@skill(
    name="archive_read",
    display_name="读取压缩包内文件",
    description=(
        "读取压缩包里**某一个**文件的内容（不解压、不写盘）。"
        "当用户说「看看这个 zip 里那份说明写了什么」时使用。"
        "先用 archive_list 拿到准确的文件名；内容太长时会截断并说明，"
        "二进制文件会如实告知而不是吐出乱码。"
    ),
    params_model=ArchiveReadParams,
    category="office",
    permission_level="safe",
    tags=["压缩包", "文件"],
)
class ArchiveReadSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ArchiveReadParams(**params)
        path = ctx.resolve_input_file(args.file_path)
        fmt = _format_of(path)
        data = _read_member(path, fmt, args.member, args.max_chars)
        if data.get("binary"):
            return {
                "binary": True,
                "name": data["name"],
                "size": data["size"],
                "message": (
                    f"「{data['name']}」是二进制文件（{data['size']} 字节），"
                    "没法当文本读。如果是图片，可以直接作为附件发给我看。"
                ),
            }
        result: dict[str, Any] = {
            "name": args.member,
            "size": data["size"],
            "content": data["text"],
        }
        if data.get("truncated"):
            result["truncated"] = True
            result["note"] = (
                f"内容较长，只读了前 {len(data['text'])} 个字符"
                f"（全文约 {data['total_chars']} 字符）。可以调大 max_chars 继续读。"
            )
        return result

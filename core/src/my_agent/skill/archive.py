"""技能包**容器层**：把 zip / tar.gz / 单个文件 / 本机文件夹，统一枚举成成员序列。

## 为什么要有这一层

用户手里的技能包形态五花八门：有人发 zip、有人发 tar.gz、有人直接给一份 ``SKILL.md``、
还有人干脆说"就在我 D 盘那个文件夹里"。

如果每种形态各写一条解析路径，就会出现"上传能用、文件夹导入装不上"这类最难查的问题
（两条路各自漂移，谁也不知道哪边是对的）。所以这里把四种来源**收敛成同一个成员序列**，
下游的识别（``formats.py``）与落盘（``folder.py``）各只有一份实现。

## 三道闸（全部**报错**，绝不静默截断）

1. **包体积** 50MB —— 声明式技能只是文本，超出必然传错了文件；
2. **解压总量** 300MB —— 防 zip bomb：一个 1KB 的包能解出几十 GB；
3. **成员数** 5000 —— 防"包体积很小但文件几十万个"把落盘与清单撑爆。

超限时抛 :class:`ValueError` 并带上实测数字（用户要知道自己那个包到底多大）。
"""

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

# 这些后缀按"单文件技能"处理（不用解包，整份内容就是技能本体）
SINGLE_FILE_SUFFIXES = (".md", ".txt", ".json", ".yaml", ".yml", ".mdc")
TAR_SUFFIXES = (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")

# 「导入文件夹」时跳过的工程噪音目录：用户很可能从项目目录里选错一层，
# 把 node_modules 整个搬进来 —— 那不是技能内容，只会撑爆成员数上限。
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
    """一次"取成员"的结果。

    ``members`` 已经是**剥掉公共根目录**、**过完路径安全闸**的相对路径集合，
    下游可以直接拿来识别与落盘；``skipped`` 是被挡下的条目（路径穿越、
    符号链接、读不出来的坏条目）—— 它必须一路带到界面，不能悄悄吞掉。
    """

    members: list[Member] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    container: str = ""  # zip / tar / file / folder
    root: str = ""  # 被剥掉的公共根目录名（给日志与界面排查用）

    @property
    def count(self) -> int:
        return len(self.members)

    def as_files(self) -> dict[str, bytes]:
        """转成"路径 → 字节"的字典（识别层要的形状）。同名后来的覆盖先前的。"""
        return {name: data for name, data in self.members}


def safe_relative(name: str) -> str | None:
    """把包内条目名转成**安全的相对路径**（``/`` 分隔）；不安全返回 ``None``。

    挡掉三类：绝对路径、含 ``..`` 段、含盘符（``C:`` 这种在 Windows 上会被
    ``Path`` 当成绝对路径的另一半，Linux 上则是个普通文件名 —— 两边都要挡）。
    """
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
    """包里的**公共顶层目录**；没有（或不止一个）时返回空串。

    几乎所有 zip 都是 ``my-skill/SKILL.md``、``my-skill/assets/…`` 这样打出来的。
    原样解开会让用户在 ``skills/<技能id>/`` 下看到一层多余的同名目录，
    技能说明里写的相对路径（``assets/x.png``）也就全错位了。

    ⚠️ 只有一个顶层"目录"还不够：包本身就是摊平的（只有一两个文件、名字里没有 ``/``）时
    剥掉会把文件弄没，所以还要确认**确实存在嵌套**。
    """
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
    """按公共根目录剥一层；只剥一层（包的常见打包方式）。"""
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
            except (zipfile.BadZipFile, OSError) as exc:  # 单个坏条目不该毁掉整包
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
            # 只收普通文件：符号链接 / 硬链接 / 设备文件 / 目录一律不收。
            # 符号链接指向包外路径时能把文件写到数据目录之外，属于路径穿越的变体。
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
    """单个文件当"包"：整份内容就是技能本体（``SKILL.md`` 直接拖进来也能装）。"""
    name = _decode_name(filename) or "SKILL.md"
    return [(name, payload)], []


def iter_members(payload: bytes, filename: str) -> PackageMembers:
    """把一份"包字节"枚举成成员（zip / tar.gz / 单文件自动识别）。

    **按内容而不是按后缀**判断容器类型：用户常常把 zip 改名成别的后缀，
    或者发来一个没有后缀的文件。内容对不上再退回"单文件"处理 ——
    这样"把 SKILL.md 直接拖进来"也能装，而不是报"不是合法的 zip"。
    """
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
        payload[:2] == b"\x1f\x8b"  # gzip
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
    """把本机文件夹（多层嵌套）枚举成同一形态 —— 「导入文件夹」那条路用它。

    ⚠️ 与 zip 不同，这里**不能**剥"公共根目录"：用户选中 ``my-skill`` 这个文件夹时，
    他自己就是那个"公共根"。剥掉会让技能根变成包根，落盘后说明里的
    ``assets/x.png`` 反而错位。

    工程噪音目录（见 :data:`SKIP_DIR_NAMES`）直接跳过：用户很可能从项目目录里
    选错一层，把 ``node_modules`` 整个搬进来 —— 那不是技能内容，只会撑爆成员数上限。
    """
    if not root.is_dir():
        raise ValueError(f"文件夹不存在：{root}")

    members: list[Member] = []
    skipped: list[str] = []
    total = 0
    for current, dirnames, filenames in os.walk(root):
        # 原地改 dirnames 才能真的剪枝（os.walk 的行为）
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIR_NAMES]
        for filename in sorted(filenames):
            item = Path(current) / filename
            relative = str(item.relative_to(root)).replace("\\", "/")
            if item.is_symlink():
                # 符号链接可能指向目录之外，与 zip 的路径穿越同等风险，一律不收
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

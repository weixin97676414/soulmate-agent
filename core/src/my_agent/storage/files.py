"""工作区文件管理：附件上传与 Skill 产物归档。

两条安全底线：
1. **文件名不可信**：存储名由服务端生成（uuid + 白名单后缀），原始文件名
   只作为展示字段入库，绝不参与路径拼接；
2. **路径不可越界**：任何按 id 解析路径的操作都会验证结果仍位于根目录内，
   防止 ``../`` 之类的构造逃逸。
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .db import Database

logger = logging.getLogger(__name__)

FileKind = Literal["upload", "artifact"]

# 单文件大小上限
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# 存储名里**不允许**出现的字符：路径分隔符与 Windows 保留字符（这些名字在
# Windows 上根本创建不出来，放过去只会在写盘时报一个看不懂的系统错误），
# 外加控制字符。**其余一律放行，包括中文**。
#
# ⚠️ 这里曾经是一条"只允许字母数字"的白名单（`^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$`），
# 结果是 AI 写出的中文名产物（如「业务架构图.svg」）**预览与另存为一起失效**，
# 界面只显示"非法的文件标识"（实测反馈缺陷）。
#
# 为什么是"放宽"而不是"登记时把存储名改成 uuid"：产物是**技能直接写进
# artifacts 目录**的，`register_artifact` 只是事后补登记（id 就是磁盘上的文件名）。
# 改名只能救新产物，**救不了用户磁盘上已经存在的那些中文名文件** —— 它们会永远打不开。
#
# 真正的越界防护是 `resolve()` 里紧随其后的 `candidate.parent != base`
# （配合 `is_file()`），那一条**必须保留**；这里只是"名字长得合法不合法"。
_FORBIDDEN_ID_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
# Windows 会静默去掉文件名**结尾**的点与空格，于是"库里的 id"与"盘上的文件名"
# 对不上；开头是点则等于隐藏文件（扫描时会跳过）。这两头直接拒绝，不留歧义。
_ID_MAX_CHARS = 200
_SUFFIX = re.compile(r"^[A-Za-z0-9]{1,12}$")


def is_safe_file_id(file_id: str) -> bool:
    """存储名是否可用（放行中文，挡住路径与系统不允许的写法）。"""
    if not file_id or len(file_id) > _ID_MAX_CHARS:
        return False
    if ".." in file_id:
        return False
    if file_id[0] in ". " or file_id[-1] in ". ":
        return False
    return _FORBIDDEN_ID_CHARS.search(file_id) is None

# 这些后缀即便只是落地也不该出现在工作区里
BLOCKED_SUFFIXES = {
    ".exe", ".dll", ".com", ".scr", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".js",
    ".jse", ".wsf", ".wsh", ".hta", ".cpl", ".jar", ".lnk", ".reg",
}

INSERT_FILE = """
INSERT INTO files (id, original_name, kind, size, mime, session_id, note, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

# 统计与清空要走"全量"，不能用列表接口的默认 limit —— 那会让统计值静默偏小。
# 这个数字只是给 SQL 的 LIMIT 用一个实际不会触发的上限。
_ALL_RECORDS = 10**9


class WorkspaceError(RuntimeError):
    """文件操作失败（含安全校验不通过）。"""


@dataclass
class FileRecord:
    id: str
    original_name: str
    kind: FileKind = "upload"
    size: int = 0
    mime: str | None = None
    session_id: str | None = None
    note: str | None = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "original_name": self.original_name,
            "kind": self.kind,
            "size": self.size,
            "mime": self.mime,
            "session_id": self.session_id,
            "note": self.note,
            "created_at": self.created_at,
        }


def sanitize_suffix(filename: str) -> str:
    """从原始文件名里取出安全的后缀，取不到就返回空串。"""
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix and _SUFFIX.match(suffix):
        return f".{suffix}"
    return ""


def is_blocked(filename: str) -> bool:
    return Path(filename).suffix.lower() in BLOCKED_SUFFIXES


class WorkspaceStore:
    """工作区目录 + 文件元数据仓储。"""

    def __init__(self, *, workspace_dir: Path, artifacts_dir: Path, db: Database | None = None) -> None:
        self.workspace_dir = workspace_dir
        self.artifacts_dir = artifacts_dir
        self._db = db

    def ensure_dirs(self) -> None:
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 路径解析
    # ------------------------------------------------------------------ #
    def base_dir(self, kind: FileKind) -> Path:
        return self.workspace_dir if kind == "upload" else self.artifacts_dir

    def resolve(self, file_id: str, kind: FileKind = "upload") -> Path:
        """把文件 id 解析为磁盘路径，并校验未越出根目录。

        ⚠️ 这里的 `candidate.parent != base` 才是**越界的真防护**（`../` 之类
        构造出的路径哪怕名字合法，也会在这里被挡下）。上面那道名字校验只是
        提前把明显不对的输入挡掉、给出更清楚的报错，**不要**把它当成安全边界，
        也不要为了"更严"把它改回纯 ASCII 白名单（那会让中文名产物打不开）。
        """
        if not is_safe_file_id(file_id):
            raise WorkspaceError(f"非法的文件标识: {file_id!r}")

        base = self.base_dir(kind).resolve()
        candidate = (base / file_id).resolve()
        if candidate.parent != base:
            raise WorkspaceError("文件路径越界，已拒绝访问")
        if not candidate.is_file():
            raise WorkspaceError(f"文件不存在: {file_id}")
        return candidate

    # ------------------------------------------------------------------ #
    # 写入
    # ------------------------------------------------------------------ #
    async def save_upload(
        self,
        *,
        filename: str,
        content: bytes,
        session_id: str | None = None,
    ) -> FileRecord:
        if len(content) > MAX_UPLOAD_BYTES:
            raise WorkspaceError(
                f"文件过大（{len(content) / 1024 / 1024:.1f} MB），"
                f"单文件上限 {MAX_UPLOAD_BYTES // 1024 // 1024} MB"
            )
        if is_blocked(filename):
            raise WorkspaceError(f"出于安全考虑，不支持上传 {Path(filename).suffix} 类型的文件")

        self.ensure_dirs()
        suffix = sanitize_suffix(filename)
        file_id = f"{uuid.uuid4().hex[:16]}{suffix}"
        target = self.workspace_dir / file_id
        # 落盘是阻塞 IO：50MB 的写入足以卡住事件循环，把所有会话的 SSE 一起拖住。
        # 丢到线程里做，代价只是一个 await。
        await asyncio.to_thread(target.write_bytes, content)

        record = FileRecord(
            id=file_id,
            original_name=Path(filename).name or file_id,
            kind="upload",
            size=len(content),
            mime=mimetypes.guess_type(filename)[0],
            session_id=session_id,
        )
        await self._persist(record)
        logger.info("已接收附件 %s（%s 字节）", record.original_name, record.size)
        return record

    async def register_artifact(
        self, path: Path, *, note: str | None = None, session_id: str | None = None
    ) -> FileRecord:
        """把 Skill 产出的文件登记为产物。

        Skill 直接往 artifacts 目录写文件，这里只补登记元数据；
        文件不存在时抛错，避免登记出打不开的幽灵条目。
        """
        if not path.is_file():
            raise WorkspaceError(f"产物文件不存在: {path}")
        # 名字本身不合法的产物（Windows 不允许的字符、开头是点……）同样**不许登记**：
        # 登记了也只会变成一条"点开就报非法的文件标识"的幽灵条目 —— 那正是这条
        # 检查要拦的东西。让它在这里带着**原始文件名**报错，模型有机会换个名字重写。
        if not is_safe_file_id(path.name):
            raise WorkspaceError(f"产物文件名不可用（含系统不允许的字符）: {path.name}")

        record = FileRecord(
            id=path.name,
            original_name=path.name,
            kind="artifact",
            size=path.stat().st_size,
            mime=mimetypes.guess_type(path.name)[0],
            session_id=session_id,
            note=note,
        )
        await self._persist(record)
        return record

    async def _persist(self, record: FileRecord) -> None:
        if self._db is None:
            return
        await self._db.execute(
            INSERT_FILE,
            (
                record.id,
                record.original_name,
                record.kind,
                record.size,
                record.mime,
                record.session_id,
                record.note,
                record.created_at,
            ),
        )

    # ------------------------------------------------------------------ #
    # 查询与删除
    # ------------------------------------------------------------------ #
    async def list_files(self, *, kind: FileKind | None = None, limit: int = 200) -> list[FileRecord]:
        if self._db is not None:
            if kind:
                rows = await self._db.fetch_all(
                    "SELECT * FROM files WHERE kind = ? ORDER BY created_at DESC LIMIT ?",
                    (kind, limit),
                )
            else:
                rows = await self._db.fetch_all(
                    "SELECT * FROM files ORDER BY created_at DESC LIMIT ?", (limit,)
                )
            return [self._row_to_record(row) for row in rows]

        # 无数据库时退化为扫描目录，保证功能可用
        return self._scan_without_db(kind, limit)

    @staticmethod
    def _row_to_record(row: dict[str, Any]) -> FileRecord:
        return FileRecord(
            id=row["id"],
            original_name=row["original_name"],
            kind=row["kind"],
            size=int(row.get("size") or 0),
            mime=row.get("mime"),
            session_id=row.get("session_id"),
            note=row.get("note"),
            created_at=float(row.get("created_at") or 0),
        )

    def _scan_without_db(self, kind: FileKind | None, limit: int) -> list[FileRecord]:
        kinds: list[FileKind] = [kind] if kind else ["upload", "artifact"]
        records: list[FileRecord] = []
        for current in kinds:
            directory = self.base_dir(current)
            if not directory.is_dir():
                continue
            for entry in directory.iterdir():
                if not entry.is_file() or entry.name.startswith("."):
                    continue
                stat = entry.stat()
                records.append(
                    FileRecord(
                        id=entry.name,
                        original_name=entry.name,
                        kind=current,
                        size=stat.st_size,
                        mime=mimetypes.guess_type(entry.name)[0],
                        created_at=stat.st_mtime,
                    )
                )
        records.sort(key=lambda item: item.created_at, reverse=True)
        return records[:limit]

    async def get(self, file_id: str, *, kind: FileKind | None = None) -> FileRecord | None:
        if self._db is not None:
            if kind:
                row = await self._db.fetch_one(
                    "SELECT * FROM files WHERE id = ? AND kind = ?", (file_id, kind)
                )
            else:
                row = await self._db.fetch_one("SELECT * FROM files WHERE id = ?", (file_id,))
            if row:
                return self._row_to_record(row)
            return None
        for record in self._scan_without_db(kind, 500):
            if record.id == file_id:
                return record
        return None

    async def delete(self, file_id: str, *, kind: FileKind | None = None) -> bool:
        record = await self.get(file_id, kind=kind)
        if record is None:
            return False
        try:
            self.resolve(record.id, record.kind).unlink()
        except WorkspaceError:
            pass  # 元数据存在但文件已被手工删除，继续清理记录
        if self._db is not None:
            await self._db.execute("DELETE FROM files WHERE id = ?", (file_id,))
        return True

    async def clear(self, *, kind: FileKind | None = None) -> int:
        records = await self.list_files(kind=kind, limit=_ALL_RECORDS)
        if not records:
            return 0

        # 先删磁盘文件，再**一次性**删元数据。
        # 原实现逐条调 ``delete()``，而每条 delete 都要先 SELECT 再 DELETE ——
        # 清空 500 个产物就是 1000 次数据库往返，界面会明显卡住。
        for record in records:
            try:
                self.resolve(record.id, record.kind).unlink()
            except WorkspaceError:
                pass  # 文件已被手工删除，继续清理记录

        if self._db is not None:
            ids = [record.id for record in records]
            placeholders = ",".join("?" for _ in ids)
            await self._db.execute(
                f"DELETE FROM files WHERE id IN ({placeholders})", tuple(ids)
            )
        return len(records)

    async def stats(self) -> dict[str, Any]:
        """工作区统计（**以磁盘为准**）。

        两条路都数磁盘：

        - 有数据库时**不能**只信 ``SUM(size)``：文件是用户能在资源管理器里
          直接删/加的，记录与磁盘必然逐渐对不上。用户看到"共 12 个文件"
          而目录里只有 9 个，只会以为应用坏了 —— 而"应用自己统计自己"本来
          就该以事实（磁盘）为准，记录只是索引。
        - 没有数据库时更不能拿"最近 N 条"充数（``list_files`` 有 limit）。

        所以这里一律遍历 ``workspace`` / ``artifacts`` 两个目录真数一遍。
        目录规模是"用户自己攒的产物"量级（几百到几千），一次 stat 完全可接受；
        真要长到上万，再考虑加索引缓存也不迟。
        """
        # ⚠️ 丢进**线程**（第 87 批，M-05）：遍历目录 + 逐文件 `stat()` 是同步 IO，
        # 而 `GET /v1/files` 每次请求都会调它 —— 产物攒到几千个之后，
        # 前端每轮询一次文件列表就会在事件循环上 stat 上千个文件，
        # 表现为**周期性卡顿**（本项目其余重活都走了 `to_thread`，
        # 例如同一个文件里的 `preview_file`）。
        return await asyncio.to_thread(self._stats_sync)

    def _stats_sync(self) -> dict[str, Any]:
        uploads = self._scan_dir("upload")
        artifacts = self._scan_dir("artifact")
        return {
            "total": len(uploads) + len(artifacts),
            "uploads": len(uploads),
            "artifacts": len(artifacts),
            "total_bytes": sum(item.stat().st_size for item in uploads + artifacts),
            "workspace_dir": str(self.workspace_dir),
            "artifacts_dir": str(self.artifacts_dir),
        }

    def _scan_dir(self, kind: FileKind) -> list[Path]:
        """一个目录里的真实文件（跳过隐藏文件：``.gitkeep`` 这类不该算进统计）。"""
        directory = self.base_dir(kind)
        if not directory.is_dir():
            return []
        return [
            entry
            for entry in directory.iterdir()
            if entry.is_file() and not entry.name.startswith(".")
        ]

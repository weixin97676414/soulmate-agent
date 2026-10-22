








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


MAX_UPLOAD_BYTES = 50 * 1024 * 1024















_FORBIDDEN_ID_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


_ID_MAX_CHARS = 200
_SUFFIX = re.compile(r"^[A-Za-z0-9]{1,12}$")


def is_safe_file_id(file_id: str) -> bool:

    if not file_id or len(file_id) > _ID_MAX_CHARS:
        return False
    if ".." in file_id:
        return False
    if file_id[0] in ". " or file_id[-1] in ". ":
        return False
    return _FORBIDDEN_ID_CHARS.search(file_id) is None


BLOCKED_SUFFIXES = {
    ".exe", ".dll", ".com", ".scr", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".js",
    ".jse", ".wsf", ".wsh", ".hta", ".cpl", ".jar", ".lnk", ".reg",
}

INSERT_FILE = """
INSERT INTO files (id, original_name, kind, size, mime, session_id, note, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""



_ALL_RECORDS = 10**9


class WorkspaceError(RuntimeError):
    pass


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

    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix and _SUFFIX.match(suffix):
        return f".{suffix}"
    return ""


def is_blocked(filename: str) -> bool:
    return Path(filename).suffix.lower() in BLOCKED_SUFFIXES


class WorkspaceStore:


    def __init__(self, *, workspace_dir: Path, artifacts_dir: Path, db: Database | None = None) -> None:
        self.workspace_dir = workspace_dir
        self.artifacts_dir = artifacts_dir
        self._db = db

    def ensure_dirs(self) -> None:
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    
    
    
    def base_dir(self, kind: FileKind) -> Path:
        return self.workspace_dir if kind == "upload" else self.artifacts_dir

    def resolve(self, file_id: str, kind: FileKind = "upload") -> Path:







        if not is_safe_file_id(file_id):
            raise WorkspaceError(f"非法的文件标识: {file_id!r}")

        base = self.base_dir(kind).resolve()
        candidate = (base / file_id).resolve()
        if candidate.parent != base:
            raise WorkspaceError("文件路径越界，已拒绝访问")
        if not candidate.is_file():
            raise WorkspaceError(f"文件不存在: {file_id}")
        return candidate

    
    
    
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





        if not path.is_file():
            raise WorkspaceError(f"产物文件不存在: {path}")
        
        
        
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
            pass  
        if self._db is not None:
            await self._db.execute("DELETE FROM files WHERE id = ?", (file_id,))
        return True

    async def clear(self, *, kind: FileKind | None = None) -> int:
        records = await self.list_files(kind=kind, limit=_ALL_RECORDS)
        if not records:
            return 0

        
        
        
        for record in records:
            try:
                self.resolve(record.id, record.kind).unlink()
            except WorkspaceError:
                pass  

        if self._db is not None:
            ids = [record.id for record in records]
            placeholders = ",".join("?" for _ in ids)
            await self._db.execute(
                f"DELETE FROM files WHERE id IN ({placeholders})", tuple(ids)
            )
        return len(records)

    async def stats(self) -> dict[str, Any]:














        
        
        
        
        
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

        directory = self.base_dir(kind)
        if not directory.is_dir():
            return []
        return [
            entry
            for entry in directory.iterdir()
            if entry.is_file() and not entry.name.startswith(".")
        ]

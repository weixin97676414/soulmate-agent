












from __future__ import annotations

import os
import re
from pathlib import Path

from ..errors import PathNotAllowedError


_DRIVE = re.compile(r"^[A-Za-z]:")

_EXTENDED_PREFIXES = ("\\\\?\\", "\\\\.\\")



_PATH_SYNTAX_RULES: tuple[tuple[str, str], ...] = (
    ("空字节", "路径包含空字节（\\x00）"),
    ("控制字符", "路径包含控制字符"),
    ("数据流", "路径包含 NTFS 数据流分隔符"),
)


def _reject_unsafe_syntax(raw: str) -> None:












    if not raw:
        return
    if "\x00" in raw:
        raise PathNotAllowedError(f"{_PATH_SYNTAX_RULES[0][1]}：已拒绝该路径。")
    if any(ord(ch) < 32 for ch in raw):
        raise PathNotAllowedError(f"{_PATH_SYNTAX_RULES[1][1]}：已拒绝该路径。")

    
    
    remainder = raw
    for prefix in _EXTENDED_PREFIXES:
        if remainder.startswith(prefix):
            remainder = remainder[len(prefix) :]
            break
    remainder = _DRIVE.sub("", remainder, count=1)
    if ":" in remainder:
        raise PathNotAllowedError(
            f"{_PATH_SYNTAX_RULES[2][1]}：已拒绝该路径。"
            "如需访问文件内容，请使用不带冒号的完整路径。"
        )


class PathPolicy:


    def __init__(
        self,
        allowed_dirs: list[str] | None = None,
        *,
        always_allowed: list[Path] | None = None,
    ) -> None:
        roots: list[str] = list(allowed_dirs or [])
        for extra in always_allowed or []:
            roots.append(str(extra))

        self._allowed: list[Path] = []
        for raw in roots:
            if not raw:
                continue
            try:
                resolved = Path(os.path.expandvars(raw)).expanduser().resolve()
            except (OSError, RuntimeError, ValueError):
                
                
                
                continue
            if resolved not in self._allowed:
                self._allowed.append(resolved)

        self._configured = bool(allowed_dirs and any(allowed_dirs))

    
    
    
    @property
    def allowed_dirs(self) -> list[Path]:
        return list(self._allowed)

    @property
    def is_restricted(self) -> bool:

        return self._configured

    def describe(self) -> str:
        if not self._configured:
            return "未限制目录"
        return "、".join(str(item) for item in self._allowed)

    
    
    
    def check(self, path: str | os.PathLike[str], *, mode: str = "read") -> Path:




        if not path:
            raise PathNotAllowedError("未提供文件路径")

        raw = str(path)
        _reject_unsafe_syntax(raw)

        try:
            resolved = Path(os.path.expandvars(raw)).expanduser().resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            
            
            
            raise PathNotAllowedError(f"无法解析路径 {path}: {exc}") from exc

        if not self._configured:
            return resolved

        for root in self._allowed:
            if resolved == root or root in resolved.parents:
                return resolved

        action = {"read": "读取", "write": "写入"}.get(mode, "访问")
        raise PathNotAllowedError(
            f"出于安全考虑，不允许{action}白名单之外的路径：{resolved}\n"
            f"当前允许的目录：{self.describe()}\n"
            f"如需访问，请让用户在「设置 → 安全与通用 → 文件访问白名单」中添加该目录。"
        )

    def is_allowed(self, path: str | os.PathLike[str]) -> bool:
        try:
            self.check(path)
        except PathNotAllowedError:
            return False
        return True

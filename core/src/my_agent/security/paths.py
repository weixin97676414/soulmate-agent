"""文件访问白名单。

对应《智能体框架开发文档》10.2.3 节。所有涉及文件读写的技能都必须先经过
``PathPolicy.check()``，避免出现"让智能体整理一下 D 盘"这种越权操作。

两条设计约定：

1. **白名单为空 = 不限制**（并在界面上明确提示风险）。这是个人桌面应用的
   合理默认——用户装了就是为了让它处理自己电脑上的文件；
2. **工作区与产物目录永远在白名单内**，无论用户怎么配。否则会出现
   "上传了附件但技能读不了"的荒谬情况。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from ..errors import PathNotAllowedError

# 盘符前缀，例如 ``C:``
_DRIVE = re.compile(r"^[A-Za-z]:")
# Windows 扩展长度前缀：``\\?\C:\...`` / ``\\.\C:\...``
_EXTENDED_PREFIXES = ("\\\\?\\", "\\\\.\\")

# 路径里**不该出现**的结构。这些不是"看起来奇怪的写法"，而是能真正改变
# 被访问对象的语法，所以统一拒绝而不是尽力解析。
_PATH_SYNTAX_RULES: tuple[tuple[str, str], ...] = (
    ("空字节", "路径包含空字节（\\x00）"),
    ("控制字符", "路径包含控制字符"),
    ("数据流", "路径包含 NTFS 数据流分隔符"),
)


def _reject_unsafe_syntax(raw: str) -> None:
    """拒绝带有特殊语法的路径。

    这些写法有一个共同特点：**白名单按路径组件比对时它们是通过校验的**，
    但真正被访问的东西与字面看起来的不是同一个。

    - NTFS 数据流：``C:\\data\\report.txt:hidden`` 读写的是该文件的**备用数据流**，
      而不是 ``report.txt`` 本身。按组件比对时它是 ``data`` 目录下的一个文件，
      白名单当然放行；
    - 空字节：部分底层接口会把它当成字符串终止符，于是 ``ok.txt\\x00.exe``
      在检查时像 ``ok.txt``、打开时像 ``ok.txt``（或截断到别处），两边看到的不一样；
    - 控制字符：界面上不可见，用户无法判断自己批准的是哪个路径。
    """
    if not raw:
        return
    if "\x00" in raw:
        raise PathNotAllowedError(f"{_PATH_SYNTAX_RULES[0][1]}：已拒绝该路径。")
    if any(ord(ch) < 32 for ch in raw):
        raise PathNotAllowedError(f"{_PATH_SYNTAX_RULES[1][1]}：已拒绝该路径。")

    # 冒号只有在**盘符**位置才是合法的。先剥掉扩展长度前缀，再剥盘符，
    # 剩下的部分出现冒号就一定是数据流语法。
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
    """把路径限制在允许的目录集合内。"""

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
                # 路径无法解析（盘符不存在、写法非法等）就直接忽略，
                # 不让它污染白名单。ValueError 同样要接住，否则一个手改坏的
                # 配置会让整个应用起不来 —— 而它的影响只是少一条白名单
                continue
            if resolved not in self._allowed:
                self._allowed.append(resolved)

        self._configured = bool(allowed_dirs and any(allowed_dirs))

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    @property
    def allowed_dirs(self) -> list[Path]:
        return list(self._allowed)

    @property
    def is_restricted(self) -> bool:
        """用户是否真的配置了白名单（只有工作区/产物目录不算"限制"）。"""
        return self._configured

    def describe(self) -> str:
        if not self._configured:
            return "未限制目录"
        return "、".join(str(item) for item in self._allowed)

    # ------------------------------------------------------------------ #
    # 校验
    # ------------------------------------------------------------------ #
    def check(self, path: str | os.PathLike[str], *, mode: str = "read") -> Path:
        """解析并校验路径。不通过时抛 ``PathNotAllowedError``。

        ``mode`` 只用于错误提示（读写分开表述更清楚），校验规则一致。
        """
        if not path:
            raise PathNotAllowedError("未提供文件路径")

        raw = str(path)
        _reject_unsafe_syntax(raw)

        try:
            resolved = Path(os.path.expandvars(raw)).expanduser().resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            # ValueError 必须一起捕获：畸形路径（内嵌空字节、非法字符）
            # 会让 resolve() 抛它，漏掉的话技能会以一个 500 结束 ——
            # 而"路径不合法"本该是一个可读的权限错误。
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

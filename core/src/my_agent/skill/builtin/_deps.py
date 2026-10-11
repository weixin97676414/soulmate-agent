"""可选依赖的懒加载。

办公类技能依赖 openpyxl / pypdf / python-docx 等第三方库。它们放在
``my-agent-core[office]`` 这个 extra 里，用户可能没装。

这里统一处理导入失败：给出**可操作**的提示（告诉用户装哪个 extra），
而不是抛一个莫名其妙的 ``ModuleNotFoundError`` 让模型和用户都摸不着头脑。
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any

from ...errors import SkillExecutionError

# 模块名 -> (extra 名, 用途描述)
_REQUIREMENTS: dict[str, tuple[str, str]] = {
    "openpyxl": ("office", "处理 Excel 文件"),
    "docx": ("office", "解析 Word 文档"),
    "pypdf": ("office", "解析 PDF 文档"),
}


def require(module_name: str, purpose: str = "") -> ModuleType:
    """导入模块，失败时抛出对用户友好的错误。"""
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        extra, default_purpose = _REQUIREMENTS.get(module_name, ("office", ""))
        what = purpose or default_purpose or f"使用 {module_name}"
        raise SkillExecutionError(
            f"{what}需要额外依赖 {module_name}，当前环境未安装。\n"
            f"请执行：pip install \"my-agent-core[{extra}]\""
        ) from exc


def optional(module_name: str) -> ModuleType | Any | None:
    """尝试导入，失败返回 None（用于「有则增强、无则跳过」的场景）。"""
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None

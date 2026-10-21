








from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any

from ...errors import SkillExecutionError


_REQUIREMENTS: dict[str, tuple[str, str]] = {
    "openpyxl": ("office", "处理 Excel 文件"),
    "docx": ("office", "解析 Word 文档"),
    "pypdf": ("office", "解析 PDF 文档"),
}


def require(module_name: str, purpose: str = "") -> ModuleType:

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

    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None

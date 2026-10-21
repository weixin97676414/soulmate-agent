





















from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def resources_dir() -> Path:

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "my_agent" / "resources"
    
    return Path(__file__).resolve().parent.parent / "resources"


def resource_path(*parts: str) -> Path:

    return resources_dir().joinpath(*parts)


def read_text(*parts: str) -> str:

    path = resource_path(*parts)
    if not path.is_file():
        raise FileNotFoundError(
            f"内置资源缺失：{path}（资源根目录 {resources_dir()}）。"
            "开发态请确认文件已随仓库提交；打包后请检查 agent-core.spec 的 datas。"
        )
    return path.read_text(encoding="utf-8")


def load_json(*parts: str) -> Any:

    return json.loads(read_text(*parts))


def has_resource(*parts: str) -> bool:
    return resource_path(*parts).is_file()


__all__ = ["has_resource", "load_json", "read_text", "resource_path", "resources_dir"]

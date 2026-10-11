"""随核心一起打包的**只读**资源（内置技能正文、地点库）的定位与读取。

## 为什么要单独一层

同一份资源在两种形态下的物理位置不同：

- 开发态：``<仓库>/core/src/my_agent/resources/…``
- PyInstaller（onedir）：``<release>/agent-core/_internal/my_agent/resources/…``

判据是 ``sys._MEIPASS``（PyInstaller 注入的解包根）。写死其一就会得到
"开发时好好的、打包后功能静默失效" —— 而这类问题只有在发给用户之后才会暴露。

打包侧必须同步：``core/build/agent-core.spec`` 里把 ``src/my_agent/resources``
整个目录塞进 ``datas``（data 文件不会被 ``collect_submodules`` 带进去）。

## 为什么缺文件直接抛异常

这些资源**就是**内置技能的正文本身：读不到等于技能没有内容，模型只能
照着一段空文本"假装会用"，用户看到的是答非所问。宁可当场报错（日志里有
明确文件名与查找路径），也不要静默降级成"技能看起来装上了但没作用"。
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def resources_dir() -> Path:
    """内置资源根目录。"""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "my_agent" / "resources"
    # utils/resources.py → utils → my_agent → resources
    return Path(__file__).resolve().parent.parent / "resources"


def resource_path(*parts: str) -> Path:
    """拼出某个资源的绝对路径（**不校验存在性**，校验交给读取处）。"""
    return resources_dir().joinpath(*parts)


def read_text(*parts: str) -> str:
    """读取文本资源；文件缺失或编码异常时抛出带路径的 ``FileNotFoundError``。"""
    path = resource_path(*parts)
    if not path.is_file():
        raise FileNotFoundError(
            f"内置资源缺失：{path}（资源根目录 {resources_dir()}）。"
            "开发态请确认文件已随仓库提交；打包后请检查 agent-core.spec 的 datas。"
        )
    return path.read_text(encoding="utf-8")


def load_json(*parts: str) -> Any:
    """读取 JSON 资源。"""
    return json.loads(read_text(*parts))


def has_resource(*parts: str) -> bool:
    return resource_path(*parts).is_file()


__all__ = ["has_resource", "load_json", "read_text", "resource_path", "resources_dir"]

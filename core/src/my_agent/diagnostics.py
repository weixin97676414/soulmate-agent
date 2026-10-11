"""自检：在**打包后的真实二进制**里验证可选依赖到底能不能用。

## 为什么需要它

PyInstaller 是静态分析，漏打包**不会让构建失败**，只会让 exe 起来之后
"少一半功能"。而这些可选功能平时不会走 —— 用户点开「知识库」才发现用不了，
那时已经离开发环境很远了，你手里的信息只有一个"报错了"。

``verify-core-exe.mjs`` 覆盖了 MCP，但长期记忆涉及一个**运行期下载的 ONNX 模型**
（约 79 MB）与 onnxruntime 的原生库，静态分析完全看不出能不能加载。
所以需要一条能在冻结环境里跑完整链路的自检。

## 用法

```
agent-core.exe self-check           # 只做 import 检查（快，不联网）
agent-core.exe self-check --deep    # 真的写入+检索一次（首次会下载模型）
```

输出是一行 JSON，便于脚本解析，也便于让用户直接贴给你。
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def _check_mcp() -> dict[str, Any]:
    try:
        import importlib.metadata as metadata

        import mcp  # noqa: F401

        return {"available": True, "version": metadata.version("mcp")}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def _check_memory(*, deep: bool) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        import chromadb

        info: dict[str, Any] = {
            "available": True,
            "version": getattr(chromadb, "__version__", "unknown"),
            "import_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    # onnxruntime 是默认嵌入函数的推理后端，单独测：
    # 它带原生 DLL，是打包最容易漏的一环，且失败时的报错与"模型加载"
    # 混在一起很难区分
    try:
        import onnxruntime  # noqa: F401

        info["onnxruntime"] = getattr(onnxruntime, "__version__", "unknown")
    except Exception as exc:  # noqa: BLE001
        info["onnxruntime"] = None
        info["onnxruntime_error"] = f"{type(exc).__name__}: {exc}"

    if not deep:
        return info

    # 深检：真的写入 + 检索一次。这一步会触发嵌入模型下载（首次约 79 MB），
    # 所以必须是显式请求才做。
    #
    # 刻意**不用** `TemporaryDirectory` 上下文管理器：它在退出时会同步删目录，
    # 而 chromadb 这时仍持有 sqlite/bin 句柄，Windows 上会抛
    # `PermissionError: [WinError 32] 另一个程序正在使用此文件`。
    # 那个异常会把 deep_ok 判成 False —— 明明功能是好的，却报"不可用"。
    # 清理是尽力而为，绝不能影响结论。
    tmp = tempfile.mkdtemp(prefix="agent-selfcheck-")
    try:
        client = chromadb.PersistentClient(
            path=str(Path(tmp) / "vectors"),
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        collection = client.get_or_create_collection("selfcheck")
        mark = time.perf_counter()
        collection.add(ids=["a", "b"], documents=["self check alpha", "self check beta"])
        info["embed_ms"] = round((time.perf_counter() - mark) * 1000, 1)

        mark = time.perf_counter()
        result = collection.query(query_texts=["self check alpha"], n_results=1)
        info["query_ms"] = round((time.perf_counter() - mark) * 1000, 1)
        info["hit"] = (result.get("documents") or [[]])[0][0] if result else None
        info["deep_ok"] = True
    except Exception as exc:  # noqa: BLE001 - 自检本身绝不能抛异常出去
        info["deep_ok"] = False
        info["deep_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    return info


def run_self_check(*, deep: bool = False) -> dict[str, Any]:
    """返回一份自检报告。**不抛异常**，所有失败都落在返回值里。"""
    return {
        "python": sys.version.split()[0],
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "optional": {
            "mcp": _check_mcp(),
            "memory": _check_memory(deep=deep),
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    deep = "--deep" in args
    report = run_self_check(deep=deep)
    # 单独一行 JSON：既好读，也方便用户直接复制粘贴回来
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0

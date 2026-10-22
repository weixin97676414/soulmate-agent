





















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

        import mcp  

        return {"available": True, "version": metadata.version("mcp")}
    except Exception as exc:  
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
    except Exception as exc:  
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    
    
    
    try:
        import onnxruntime  

        info["onnxruntime"] = getattr(onnxruntime, "__version__", "unknown")
    except Exception as exc:  
        info["onnxruntime"] = None
        info["onnxruntime_error"] = f"{type(exc).__name__}: {exc}"

    if not deep:
        return info

    
    
    
    
    
    
    
    
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
    except Exception as exc:  
        info["deep_ok"] = False
        info["deep_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    return info


def run_self_check(*, deep: bool = False) -> dict[str, Any]:

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
    
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0

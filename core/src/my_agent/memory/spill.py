



























from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)






SPILL_DIRNAME = "tool-output"







DEFAULT_DELIVER_CHARS = 12_000

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(part: str, *, fallback: str) -> str:





    cleaned = _UNSAFE.sub("_", (part or "").strip())[:64].strip("._-")
    return cleaned or fallback


def spill_filename(session_id: str, call_id: str) -> str:






    digest = hashlib.sha1(f"{session_id}\x00{call_id}".encode()).hexdigest()[:12]
    return f"{_safe_name(call_id, fallback='call')}-{digest}.txt"


def write_spill(root: Path, session_id: str, call_id: str, text: str) -> Path:





    root.mkdir(parents=True, exist_ok=True)
    target = root / spill_filename(session_id, call_id)
    tmp = target.with_suffix(target.suffix + ".part")
    
    
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    os.replace(tmp, target)
    return target


def skip_chars(handle: Any, count: int, *, chunk: int = 65536) -> None:









    remaining = count
    while remaining > 0:
        got = handle.read(min(chunk, remaining))
        if not got:
            return
        remaining -= len(got)


def read_range(
    path: Path, *, offset: int = 0, limit: int = DEFAULT_DELIVER_CHARS
) -> dict[str, Any]:






    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        skip_chars(handle, offset)
        text = handle.read(limit)
        has_more = bool(handle.read(1))
    return {
        "path": str(path),
        "offset": offset,
        "content": text,
        "chars_returned": len(text),
        "next_offset": offset + len(text),
        "eof": not has_more,
        "size_bytes": path.stat().st_size,
    }


def deliver_pointer(path: Path, *, total_chars: int, delivered_chars: int) -> str:










    remaining = max(0, total_chars - delivered_chars)
    lines = [
        "",
        f"[完整内容共 {total_chars} 字符，此处先给出前 {delivered_chars} 字符。",
        f"剩余 {remaining} 字符**没有丢失** —— 全文已原样保存到本机文件：",
        f"  {path}",
        "要继续读取，请调用 read_tool_output：",
        f'  read_tool_output(path="{path}", offset={delivered_chars})',
        "该文件内容与本说明无关，未被删改、未被省略。]",
    ]
    return "\n".join(lines)






















from __future__ import annotations

import json
from typing import Any

__all__ = ["format_sse", "parse_sse"]


def format_sse(event: str, data: dict[str, Any]) -> str:






    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def parse_sse(chunk: str) -> tuple[str, dict[str, Any]] | None:








    if not chunk.startswith("event: "):
        return None
    lines = chunk.split("\n")
    event = lines[0][len("event: ") :].strip()
    data_line = next((line for line in lines if line.startswith("data: ")), "")
    try:
        payload = json.loads(data_line[len("data: ") :] or "{}")
    except ValueError:
        return None
    return event, payload if isinstance(payload, dict) else {}

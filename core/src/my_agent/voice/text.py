







from __future__ import annotations

import re



_ALLOWED = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")


def clean_text(text: str) -> str:

    return "".join(_ALLOWED.findall(text or ""))


__all__ = ["clean_text"]

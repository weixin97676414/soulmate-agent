































from __future__ import annotations

import re
from collections.abc import Mapping






SECRET_NAME_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"



REF_PATTERN = re.compile(r"\{\{secret:([A-Za-z0-9_-]{1,64})\}\}")


def find_refs(text: str) -> list[str]:





    if not text:
        return []
    seen: dict[str, None] = {}
    for name in REF_PATTERN.findall(text):
        seen.setdefault(name, None)
    return list(seen)


def resolve(text: str, keys: Mapping[str, str]) -> tuple[str, list[str], list[str]]:











    used: list[str] = []
    missed: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        value = keys.get(name)
        if value is None:
            if name not in missed:
                missed.append(name)
            
            return match.group(0)
        if name not in used:
            used.append(name)
        return value

    if not text:
        return text, used, missed
    return REF_PATTERN.sub(_sub, text), used, missed


def has_ref(text: str) -> bool:

    return bool(text) and REF_PATTERN.search(text) is not None


__all__ = [
    "REF_PATTERN",
    "SECRET_NAME_PATTERN",
    "find_refs",
    "has_ref",
    "resolve",
]

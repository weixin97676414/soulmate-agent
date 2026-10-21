





from __future__ import annotations

import re

Pattern = tuple[re.Pattern[str], str]

PATTERNS: list[Pattern] = [
    
    
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "<手机号>"),
    
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "<身份证>"),

    
    
    
    
    (re.compile(r"\b(sk-ant-[A-Za-z0-9_\-]{8,})"), "<API_KEY>"),
    (re.compile(r"\b(sk-[A-Za-z0-9_\-]{8,})"), "<API_KEY>"),
    
    (re.compile(r"\b(ghp_[A-Za-z0-9]{16,})"), "<API_KEY>"),
    (re.compile(r"\b(github_pat_[A-Za-z0-9_]{16,})"), "<API_KEY>"),
    (re.compile(r"\b(gho_|ghu_|ghs_|ghr_)[A-Za-z0-9]{16,}"), "<API_KEY>"),
    
    (re.compile(r"\b(AKIA[0-9A-Z]{12,})"), "<API_KEY>"),
    (re.compile(r"\b(ASIA[0-9A-Z]{12,})"), "<API_KEY>"),
    
    (re.compile(r"\b(AIza[0-9A-Za-z_\-]{20,})"), "<API_KEY>"),
    
    (re.compile(r"\b((sk|rk)_(live|test)_[A-Za-z0-9]{10,})"), "<API_KEY>"),
    (re.compile(r"\b(xox[baprs]-[A-Za-z0-9\-]{10,})"), "<API_KEY>"),

    
    (
        re.compile(r"\b(eyJ[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,})"),
        "<JWT>",
    ),

    
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"), "Bearer <TOKEN>"),
    
    
    (
        re.compile(
            r"(?i)(x-local-token|agent_token|local[_-]?token)\s*[:=]\s*[\"']?([A-Za-z0-9_\-]{8,})"
        ),
        r"\1: <LOCAL_TOKEN>",
    ),

    
    
    (
        re.compile(
            r'(?i)"?(api[_-]?key|access[_-]?token|secret[_-]?key|client[_-]?secret'
            r'|password|authorization)"?\s*[:=]\s*"([^"]{4,})"'
        ),
        r'"\1": "<REDACTED>"',
    ),
]


def redact(text: str, *, enabled: bool = True) -> str:

    if not enabled or not text:
        return text
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_obj(value: object, *, enabled: bool = True) -> object:

    if not enabled:
        return value
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_obj(v, enabled=enabled) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_obj(v, enabled=enabled) for v in value]
    return value

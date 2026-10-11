"""敏感信息脱敏。

对应《智能体框架开发文档》10.4 节。应用点：所有日志输出、Trace 记录、
审计落库、长期记忆写入前统一调用 ``redact()``。
"""

from __future__ import annotations

import re

Pattern = tuple[re.Pattern[str], str]

PATTERNS: list[Pattern] = [
    # ---- 个人身份信息 ---------------------------------------------------- #
    # 中国手机号
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "<手机号>"),
    # 18 位身份证（末位可为 X）
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "<身份证>"),

    # ---- 密钥 ------------------------------------------------------------ #
    # 顺序有讲究：更具体的前缀必须排在更宽泛的前面，否则会被先吃掉。
    # 例如 ``sk-ant-xxx`` 若先被 ``sk-`` 规则匹配，就只会变成 <API_KEY> ——
    # 结果同样是脱敏，但会掩盖"这是 Anthropic 的 key"这个信息。
    (re.compile(r"\b(sk-ant-[A-Za-z0-9_\-]{8,})"), "<API_KEY>"),
    (re.compile(r"\b(sk-[A-Za-z0-9_\-]{8,})"), "<API_KEY>"),
    # GitHub：经典 PAT 与细粒度 PAT
    (re.compile(r"\b(ghp_[A-Za-z0-9]{16,})"), "<API_KEY>"),
    (re.compile(r"\b(github_pat_[A-Za-z0-9_]{16,})"), "<API_KEY>"),
    (re.compile(r"\b(gho_|ghu_|ghs_|ghr_)[A-Za-z0-9]{16,}"), "<API_KEY>"),
    # AWS Access Key ID（Secret Key 没有固定格式，只能靠字段名，见最后一条规则）
    (re.compile(r"\b(AKIA[0-9A-Z]{12,})"), "<API_KEY>"),
    (re.compile(r"\b(ASIA[0-9A-Z]{12,})"), "<API_KEY>"),
    # Google API Key
    (re.compile(r"\b(AIza[0-9A-Za-z_\-]{20,})"), "<API_KEY>"),
    # Stripe / Slack / 微信类前缀
    (re.compile(r"\b((sk|rk)_(live|test)_[A-Za-z0-9]{10,})"), "<API_KEY>"),
    (re.compile(r"\b(xox[baprs]-[A-Za-z0-9\-]{10,})"), "<API_KEY>"),

    # JWT：三段式 base64url。网关把请求回显出来时经常带着它
    (
        re.compile(r"\b(eyJ[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,})"),
        "<JWT>",
    ),

    # ---- 请求头 ---------------------------------------------------------- #
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"), "Bearer <TOKEN>"),
    # 本项目自己的本地令牌。它的形态是 token_urlsafe(24)，与普通随机串无法区分，
    # 所以只能靠**出现位置**识别：它只会出现在这几个名字后面。
    (
        re.compile(
            r"(?i)(x-local-token|agent_token|local[_-]?token)\s*[:=]\s*[\"']?([A-Za-z0-9_\-]{8,})"
        ),
        r"\1: <LOCAL_TOKEN>",
    ),

    # ---- 结构化字段 ------------------------------------------------------ #
    # 放在最后：它依赖字段名而不是值本身的形态，优先级低于上面那些确定的模式
    (
        re.compile(
            r'(?i)"?(api[_-]?key|access[_-]?token|secret[_-]?key|client[_-]?secret'
            r'|password|authorization)"?\s*[:=]\s*"([^"]{4,})"'
        ),
        r'"\1": "<REDACTED>"',
    ),
]


def redact(text: str, *, enabled: bool = True) -> str:
    """对文本做脱敏；``enabled=False`` 时原样返回（用于关掉脱敏的场景）。"""
    if not enabled or not text:
        return text
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_obj(value: object, *, enabled: bool = True) -> object:
    """递归脱敏 dict / list / str，便于直接处理工具参数与结果。"""
    if not enabled:
        return value
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_obj(v, enabled=enabled) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_obj(v, enabled=enabled) for v in value]
    return value

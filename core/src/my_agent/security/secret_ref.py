"""``{{secret:名字}}`` 的扫描与替换 —— 让模型能"引用"一把它看不见的密钥。

## 它解决的是什么

用户通过 ``request_secret`` 技能提供的密钥，存在**本机一份独立的加密文件**里
（Electron 侧 ``skill-secrets.ts``，DPAPI 加密；与 ``secrets.bin`` 完全无关）。
模型拿到的只是一个名字，它看不见明文，也不该看见 —— 所以它发请求时写：

    Authorization: Bearer {{secret:exchange_api_key}}

真正发出去的那一刻，由本模块把占位符换成明文。

## ⚠️⚠️ 本模块是**全仓唯一会把明文带进字符串**的地方

所以有两条铁律，改这个文件的人必须守住：

1. **`resolve()` 的返回值只许交给 httpx**。不许写日志、不许进审计、
   不许回填到工具结果、不许拼进给用户的提示 —— 上面任何一处都会让明文
   落进"消息表 / 对话上下文 / 日志"这三条中的至少一条（``storage/sessions.py``、
   ``memory/short_term.py``、``observability/logger.py`` 都会原样收下）。
   要记录，记**名字**（``find_refs`` 的结果）。
2. **不要指望 ``security/redact.py`` 兜底**。它只认已知格式（`sk-` / `ghp_` /
   `AKIA` / JWT…），而**裸 hex 与 base58 私钥不匹配任何规则**，会原样穿过它。
   "反正日志会脱敏"在这里是错的。

## 为什么未命中时**保留原样**而不是替换成空串

替换成空串的话，模型会拿到一个 `Authorization: Bearer ` 的请求 —— 它会以为
"用户提供了但内容为空"，然后去别处找原因。保留 `{{secret:xxx}}` 原样并把名字报出来，
模型一眼就知道"这个名字在本地不存在，得先让用户提供"。
"""

from __future__ import annotations

import re
from collections.abc import Mapping

#: 引用名的合法字符集。
#:
#: ⚠️ 这个规则**必须**与 ``skill/builtin/request_secret.py`` 里 pydantic 字段的
#: ``pattern`` 逐字一致：那边是"存进去时"的校验，这里是"取出来时"的匹配，
#: 两边不同就会出现"用户明明填了、模型却引用不到"——而且两头都不报错。
SECRET_NAME_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"

#: 占位符整体形态。名字捕获组与上面的字符集一致（**不加 `^$`**：
#: 这里是在长文本里找，不是整串匹配）。
REF_PATTERN = re.compile(r"\{\{secret:([A-Za-z0-9_-]{1,64})\}\}")


def find_refs(text: str) -> list[str]:
    """扫出文本里用到的所有引用名（**去重、保持首次出现的顺序**）。

    这个函数**不碰明文**，所以它的结果可以安全地进日志与审计 ——
    这正是"记用了哪个密钥"该用的东西。
    """
    if not text:
        return []
    seen: dict[str, None] = {}
    for name in REF_PATTERN.findall(text):
        seen.setdefault(name, None)
    return list(seen)


def resolve(text: str, keys: Mapping[str, str]) -> tuple[str, list[str], list[str]]:
    """把 ``text`` 里的占位符换成明文。

    返回 ``(替换后文本, 用到的名字, 未命中的名字)``。

    ⚠️ **第一个返回值里有明文**，只许交给 httpx（见模块顶部第 1 条规定）。
    另外两个返回值不含明文，可以放心记日志。

    未命中的占位符**原样保留**（理由见模块顶部），并把名字放进第三项 ——
    调用方应当据此告诉模型"这个名字本地没有"，而不是让它对着一个
    没被替换的占位符猜。
    """
    used: list[str] = []
    missed: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        value = keys.get(name)
        if value is None:
            if name not in missed:
                missed.append(name)
            # 原样返回整个匹配（含 `{{secret:` 与 `}}`）
            return match.group(0)
        if name not in used:
            used.append(name)
        return value

    if not text:
        return text, used, missed
    return REF_PATTERN.sub(_sub, text), used, missed


def has_ref(text: str) -> bool:
    """文本里有没有引用（用于"要不要白跑一遍 replace"的快速判断）。"""
    return bool(text) and REF_PATTERN.search(text) is not None


__all__ = [
    "REF_PATTERN",
    "SECRET_NAME_PATTERN",
    "find_refs",
    "has_ref",
    "resolve",
]

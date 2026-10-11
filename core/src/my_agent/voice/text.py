"""语音里的文本处理。

这个模块原先是 ``keywords.py`` —— 一起做"中文 → KWS 要的拼音音素"转换，
并把用户填的唤醒词/命令词写进关键词文件。**2026-10-04 KWS 被彻底弃用**后
（原因见 ``server/routes/voice.py`` 的 ``voice_wake``：小模型对真人命中率太糟），
只留下这一个函数，于是搬出来单独放，免得文件名继续误导人。
"""

from __future__ import annotations

import re

#: 允许出现在唤醒词 / 命令词里的字符：汉字、字母、数字。其余（空格、标点、emoji）
#: 直接丢掉而不是报错 —— 用户填「你好，搭子！」时他想要的就是「你好搭子」。
_ALLOWED = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")


def clean_text(text: str) -> str:
    """去掉标点与空格，只留能被发音的部分。"""
    return "".join(_ALLOWED.findall(text or ""))


__all__ = ["clean_text"]

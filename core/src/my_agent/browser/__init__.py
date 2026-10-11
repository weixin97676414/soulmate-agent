"""浏览器自动化（包入口）。

能力放在 ``session.py``（会话/驱动）里，对外暴露一个进程级单例 ``browser``，
供 ``skill/builtin/browser.py`` 的技能调用。

设计要点见 ``session.py`` 顶部的模块说明。
"""

from .session import browser

__all__ = ["browser"]

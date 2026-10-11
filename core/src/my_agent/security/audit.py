"""审计事件的数据结构与回调类型。

放置位置与 ``confirm.py`` 同理：审计属于安全域概念，被 Skill 上下文与
持久化层共同依赖，独立成模块可以避免这两者之间产生循环导入。
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuditEntry:
    """一次需要留痕的操作。

    ``status`` 取值：``ok`` / ``error`` / ``denied`` / ``timeout``。

    ## 两类记录共用这一个结构

    - ``kind="skill"``（默认）：一次**技能/工具调用**，有 ``skill_name``、权限级别、
      参数与耗时；
    - 其它 ``kind``（``assistant`` / ``group`` / ``session`` / ``task`` / ``permission``）：
      一次**实体操作** —— "谁在什么时候对什么做了什么"。用户的原话是"哪个搭子在什么时候
      做了什么，出了问题能查"，那类动作原先**完全没有留痕**。

    两类进同一张表，是为了能在同一个时间轴上排着看（"任务失败前他先删了个会话"这种
    前后关系，分两张表就看不出来了）。
    """

    skill_name: str
    status: str
    permission_level: str = "safe"
    session_id: str | None = None
    params: dict[str, Any] | None = None
    duration_ms: float | None = None
    detail: str | None = None
    ts: float = field(default_factory=time.time)
    # 记录来源：skill / assistant / group / session / task / permission
    kind: str = "skill"
    # 动作主体（搭子 id；纯用户操作留空）。"哪个搭子"靠它回答。
    actor_id: str | None = None
    # 动作名，例如 create / update / delete / run / interrupt / resume / approve
    action: str = ""
    # 作用对象（任务 id、群 id、会话 id、技能名……），配合 kind 就能定位到具体那一个
    target: str = ""


# 审计写入回调：服务层实现，把事件落进 SQLite
AuditCallback = Callable[[AuditEntry], Awaitable[None]]

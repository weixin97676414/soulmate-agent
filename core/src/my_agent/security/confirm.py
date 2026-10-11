"""人工确认请求的数据结构与回调类型。

放在 ``security`` 包而非 ``skill`` 包，是为了打断
``skill.manager -> security.permission -> skill.base`` 的循环导入：
确认（confirm）本质上是安全域的概念，权限守卫与 Skill 上下文都需要它。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConfirmRequest:
    """一次人工确认请求，由服务层转成 SSE 事件发给客户端弹窗。"""

    request_id: str
    skill_name: str
    display_name: str
    description: str
    permission_level: str
    params: dict[str, Any] = field(default_factory=dict)
    prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "skill_name": self.skill_name,
            "display_name": self.display_name,
            "description": self.description,
            "permission_level": self.permission_level,
            "params": self.params,
            "prompt": self.prompt,
        }


# 确认回调：服务层实现，返回用户是否批准
ConfirmCallback = Callable[[ConfirmRequest], Awaitable[bool]]

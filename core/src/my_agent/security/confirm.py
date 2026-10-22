






from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConfirmRequest:


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



ConfirmCallback = Callable[[ConfirmRequest], Awaitable[bool]]







from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuditEntry:
















    skill_name: str
    status: str
    permission_level: str = "safe"
    session_id: str | None = None
    params: dict[str, Any] | None = None
    duration_ms: float | None = None
    detail: str | None = None
    ts: float = field(default_factory=time.time)
    
    kind: str = "skill"
    
    actor_id: str | None = None
    
    action: str = ""
    
    target: str = ""



AuditCallback = Callable[[AuditEntry], Awaitable[None]]

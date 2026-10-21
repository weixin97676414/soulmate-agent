
































from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any







KIND_CHOICE = "choice"
KIND_SECRET = "secret"
INTERACTION_KINDS: frozenset[str] = frozenset({KIND_CHOICE, KIND_SECRET})


@dataclass
class InteractionRequest:


    request_id: str
    skill_name: str
    display_name: str
    kind: str
    
    payload: dict[str, Any] = field(default_factory=dict)
    
    prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "skill_name": self.skill_name,
            "display_name": self.display_name,
            "kind": self.kind,
            "payload": self.payload,
            "prompt": self.prompt,
        }








InteractionCallback = Callable[[InteractionRequest], Awaitable[dict[str, Any]]]

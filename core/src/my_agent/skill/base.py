





from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..errors import SkillExecutionError
from ..security.audit import AuditCallback
from ..security.confirm import ConfirmCallback, ConfirmRequest
from ..security.interaction import InteractionCallback, InteractionRequest
from ..security.paths import PathPolicy

if TYPE_CHECKING:
    from ..config.schemas import AppSettings
    from ..observability.tracer import Tracer

PermissionLevel = str  












TERMINATION_MARKER = "⟪stop⟫"


def mark_terminate(text: str) -> str:

    return f"{text}\n{TERMINATION_MARKER}"


def wants_terminate(text: str) -> bool:

    return TERMINATION_MARKER in text


@dataclass
class SkillMeta:


    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    
    
    
    category: str = "general"
    permission_level: PermissionLevel = "safe"
    timeout: float = 30.0
    requires: list[str] = field(default_factory=list)
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    source: str = "builtin"  
    display_name: str = ""
    
    
    locked: bool = False
    
    
    
    
    
    domain: str = ""
    
    
    
    
    
    command_preview: Callable[[dict[str, Any]], str] | None = None

    def to_dict(self) -> dict[str, Any]:
        
        
        
        from . import groups  

        owners = groups.owners_of(self.name)
        return {
            "name": self.name,
            "display_name": self.display_name or self.name,
            "description": self.description,
            "parameters": self.parameters,
            "category": self.category,
            "permission_level": self.permission_level,
            "timeout": self.timeout,
            "enabled": self.enabled,
            "tags": list(self.tags),
            "source": self.source,
            
            
            
            "bucket": groups.bucket_of(
                self.name,
                self.source,
                self.domain or groups.BUILTIN_DOMAINS.get(self.name, ""),
            ),
            
            "owners": list(owners),
            "owner_label": groups.owner_label(owners),
            
            
            "locked": self.locked,
            
            
            
            "domain": self.domain or groups.domain_of(self.name),
        }


class SkillContext:


    def __init__(
        self,
        *,
        settings: AppSettings | None = None,
        logger: logging.Logger | None = None,
        tracer: Tracer | None = None,
        paths: Any = None,
        confirm: ConfirmCallback | None = None,
        interaction: InteractionCallback | None = None,
        audit: AuditCallback | None = None,
        session_id: str | None = None,
        assistant_id: str | None = None,
        group_id: str | None = None,
        workspace: Any = None,
        path_policy: PathPolicy | None = None,
        extra: dict[str, Any] | None = None,
        confirm_mode: str | None | Callable[[], str | None] = None,
        allow_admin: bool = False,
    ) -> None:
        self.settings = settings
        self.logger = logger or logging.getLogger("my_agent.skill")
        self.tracer = tracer
        self.paths = paths
        self.confirm = confirm
        
        
        
        self.interaction = interaction
        self.audit = audit
        self.session_id = session_id
        
        
        self.assistant_id = assistant_id
        
        
        
        
        
        
        self.group_id = group_id or ""
        
        
        
        
        
        
        
        
        self.confirm_mode = confirm_mode
        
        
        
        
        self.allow_admin = allow_admin
        
        self.workspace = workspace
        self.path_policy = path_policy or PathPolicy()
        self.extra = extra or {}

    @property
    def has_confirm_channel(self) -> bool:

        return self.confirm is not None

    async def ask_confirm(self, request: ConfirmRequest) -> bool:

        if self.confirm is None:
            self.logger.warning("Skill %s 需要确认但无确认通道，已拒绝", request.skill_name)
            return False
        return await self.confirm(request)

    @property
    def has_interaction_channel(self) -> bool:






        return self.interaction is not None

    async def ask_interaction(self, request: InteractionRequest) -> dict[str, Any]:





















        if self.interaction is None:
            self.logger.warning(
                "Skill %s 需要用户交互但无交互通道（无人值守？），已按「未作答」降级",
                request.skill_name,
            )
            return {"cancelled": True, "reason": "no_channel"}
        return await self.interaction(request)

    
    @property
    def workspace_dir(self) -> Path:
        if self.paths is None:
            return Path.cwd()
        return Path(self.paths.workspace_dir)

    @property
    def artifacts_dir(self) -> Path:
        if self.paths is None:
            return Path.cwd() / "artifacts"
        return Path(self.paths.artifacts_dir)

    
    def resolve_path(self, path: str, *, mode: str = "read") -> Path:





        return self.path_policy.check(path, mode=mode)

    def resolve_input_file(self, path: str) -> Path:






        resolved = self.resolve_path(path, mode="read")
        if not resolved.is_file():
            raise SkillExecutionError(f"文件不存在：{resolved}")
        return resolved

    def artifact_output(self, filename: str) -> Path:





        safe_name = Path(filename).name.strip() or "output"
        
        for char in '<>:"/\\|?*':
            safe_name = safe_name.replace(char, "_")
        if not safe_name.strip("._"):
            safe_name = "output"

        target = self.artifacts_dir / safe_name
        stem, suffix = target.stem, target.suffix
        index = 1
        while target.exists():
            target = self.artifacts_dir / f"{stem}({index}){suffix}"
            index += 1
        return target

    def service(self, name: str) -> Any:





        value = self.extra.get(name)
        if value is None:
            raise SkillExecutionError(
                f"技能依赖的服务「{name}」当前不可用。可能原因是数据库未就绪（当前为内存模式），"
                f"请检查应用日志。"
            )
        return value

    async def register_artifact(self, path: Path, note: str | None = None) -> dict[str, Any]:

        if self.workspace is None:
            return {"id": path.name, "path": str(path)}
        try:
            record = await self.workspace.register_artifact(
                path, note=note, session_id=self.session_id
            )
            return record.to_dict()
        except Exception as exc:  
            self.logger.warning("产物登记失败 %s: %s", path, exc)
            return {"id": path.name, "path": str(path)}


class BaseSkill:


    meta: SkillMeta

    async def run(self, ctx: SkillContext, **params: Any) -> Any:
        raise NotImplementedError

    
    async def before_run(self, ctx: SkillContext, **params: Any) -> None:
        return None

    async def after_run(self, ctx: SkillContext, result: Any) -> None:
        return None



__all__ = [
    "TERMINATION_MARKER",
    "AuditCallback",
    "BaseSkill",
    "ConfirmCallback",
    "ConfirmRequest",
    "InteractionCallback",
    "InteractionRequest",
    "SkillContext",
    "SkillMeta",
    "mark_terminate",
    "wants_terminate",
]

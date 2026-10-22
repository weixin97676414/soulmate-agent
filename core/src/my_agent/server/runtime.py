










from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

from ..agent.evolution_tasks import ensure_builtin_tasks, upgrade_builtin_prompts
from ..agent.history import HistorySearch
from ..agent.orchestrator import Orchestrator
from ..agent.scheduler import TaskScheduler
from ..agent.session import Session, SessionManager
from ..agent.task_store import ScheduledTaskStore
from ..assistants.bootstrap import BuiltinAssistants
from ..assistants.library import BuddyLibrary
from ..config.lines import DEFAULT_LINE
from ..config.loader import ConfigStore
from ..config.paths import AppPaths
from ..config.schemas import (
    AppConfig,
    AppSettings,
    AssistantProfile,
    AssistantsConfig,
    GroupsConfig,
    ModelsConfig,
    ModelSpec,
    ScheduledTaskSpec,
)
from ..config.secrets import ENV_SECRETS_FILE, apply_secrets, read_secrets_file
from ..config.skill_secrets import (
    ENV_SKILL_SECRETS_FILE,
    SkillSecrets,
    read_skill_secrets_file,
)
from ..errors import LLMError
from ..llm.base import BaseLLM
from ..llm.factory import build_llm, build_registry
from ..llm.registry import LlmRegistry
from ..mcp.manager import McpManager
from ..memory.long_term import LongTermMemory
from ..model_hub import ModelDownloader
from ..observability.metrics import METRICS
from ..observability.request_context import current_session_id
from ..observability.trace_store import TraceStore
from ..observability.tracer import Tracer
from ..security.confirm import ConfirmRequest
from ..security.paths import PathPolicy
from ..security.permission import PermissionGuard
from ..services import AuditService, UsageService
from ..skill.manager import SkillManager
from ..storage.audit import AuditRepository
from ..storage.db import Database
from ..storage.files import WorkspaceStore
from ..storage.group_events import GroupEventRepository
from ..storage.group_threads import GroupThreadRepository
from ..storage.life import ExpenseRepository, ReminderRepository
from ..storage.runs import RunStore
from ..storage.sessions import SessionRepository
from ..storage.usage import UsageRepository
from ..utils.timefmt import format_now
from .events import EventBus, ReminderScheduler




SHUTDOWN_GRACE_SECONDS = 5.0

logger = logging.getLogger(__name__)


class RunningTask:


    def __init__(self, task_id: str, session_id: str, task: asyncio.Task) -> None:
        self.id = task_id
        self.session_id = session_id
        self.task = task
        self.started_at = time.time()
        self.tracer = Tracer()


@dataclass
class PendingConfirm:











    owner: str
    future: asyncio.Future[bool]
    interrupted: bool = False


@dataclass
class PendingPlan:














    owner: str
    future: asyncio.Future[tuple[bool, str]]


@dataclass
class PendingInteraction:





















    owner: str
    future: asyncio.Future[dict[str, Any]]


class AppRuntime:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths.ensure()

        
        
        self.secrets = read_secrets_file(os.environ.get(ENV_SECRETS_FILE))
        
        
        
        
        self.skill_secrets = read_skill_secrets_file(os.environ.get(ENV_SKILL_SECRETS_FILE))
        
        
        self.config_store = ConfigStore(
            paths,
            manage_secrets=self.secrets is not None,
            builtin=BuiltinAssistants(),
        )
        self.config: AppConfig = self.config_store.load()
        if self.secrets is not None:
            apply_secrets(self.config, self.secrets)

        
        
        
        self.groups: GroupsConfig = self.config_store.load_groups()
        
        
        
        self._group_history: dict[tuple[str, str], list[dict[str, str]]] = {}
        
        
        self._group_history_summary: dict[tuple[str, str], str] = {}

        settings = self.config.settings
        self.skills = SkillManager(
            PermissionGuard(
                confirm_mode=settings.security.confirm_mode,
                allow_admin=False,
            )
        )
        
        
        from ..config.schemas import CustomSkillsConfig

        self.custom_skills: CustomSkillsConfig = CustomSkillsConfig(skills=[])

        
        from ..skill.custom import CustomSkillStore

        self._custom_skill_store = CustomSkillStore(
            self.config_store.load_custom_skills,
            self.config_store.save_custom_skills,
            self.reload_custom_skills,
            skills_root=self.paths.skills_dir,
            
            skills=self.skills,
        )
        self.registry: LlmRegistry = build_registry(
            self.config.models, on_fallback=self._on_model_fallback
        )

        
        self.db = Database(paths.db_file)
        self.sessions_repo = SessionRepository(self.db)
        self.audit_repo = AuditRepository(self.db)
        self.expense_repo = ExpenseRepository(self.db)
        self.reminder_repo = ReminderRepository(self.db)
        self.usage_repo = UsageRepository(self.db)
        
        
        
        
        
        self.usage = UsageService(self)
        self.audit = AuditService(self)
        self.group_event_repo = GroupEventRepository(self.db)
        
        self.group_thread_repo = GroupThreadRepository(self.db, self.group_event_repo)
        
        self.runs = RunStore(self.db)
        self.workspace = WorkspaceStore(
            workspace_dir=paths.workspace_dir,
            artifacts_dir=paths.artifacts_dir,
            db=self.db,
        )
        self.sessions = SessionManager(
            repository=self.sessions_repo,
            on_persist_error=self._on_session_persist_error,
        )

        
        
        
        self._embedder_pair: tuple[Any, Any] | None = None
        
        
        self._memory_by_assistant: dict[str, LongTermMemory] = {}

        
        
        self.long_term = self._build_long_term_memory(paths)
        self.db_ready = False

        self.tasks: dict[str, RunningTask] = {}
        self.pending_confirms: dict[str, PendingConfirm] = {}
        
        self.pending_plans: dict[str, PendingPlan] = {}
        
        self.pending_interactions: dict[str, PendingInteraction] = {}
        
        self._chat_slots: asyncio.Semaphore | None = None
        self._chat_slots_limit: int | None = None
        
        
        
        self._inbox_mcp_task: asyncio.Task[None] | None = None

        
        self.events = EventBus()
        
        
        
        self.traces = TraceStore()
        self.reminder_scheduler = ReminderScheduler(self.reminder_repo, self.events)
        
        self.task_scheduler = TaskScheduler(self)
        
        
        self.task_store = ScheduledTaskStore(self)
        
        
        
        self.orchestrator = Orchestrator(self)
        
        
        self.history_search = HistorySearch(self)
        
        
        self.buddy_library = BuddyLibrary(self)
        
        
        
        
        self.line: str = DEFAULT_LINE

        
        
        
        
        
        
        self.model_downloader = ModelDownloader(
            paths.models_dir, publish=self._publish_model_event
        )

        
        
        
        
        
        
        
        self.session_token: str = ""

        
        self.path_policy = self._build_path_policy()
        self._register_builtin_skills()

        
        
        self.mcp = McpManager(
            self.config.mcp,
            self.skills,
            persist=self.config_store.save_mcp,
            on_status_change=self._on_mcp_status,
            
            
            path_policy=self.path_policy,
        )
        
        
        self.skills.set_permission_listener(self._persist_mcp_permission)

    
    
    
    def set_session_token(self, token: str) -> None:





        self.session_token = (token or "").strip()

    @property
    def has_session_token(self) -> bool:

        return bool(self.session_token)

    def _persist_mcp_permission(self, skill: Any, level: str) -> None:

        server = getattr(skill, "mcp_server", None)
        tool = getattr(skill, "mcp_tool", None)
        if server and tool:
            self.mcp.set_tool_permission(server, tool, level)

    def _build_path_policy(self) -> PathPolicy:
        security = self.config.settings.security
        return PathPolicy(
            security.allowed_dirs,
            
            
            
            
            
            
            
            
            
            
            
            always_allowed=[
                self.paths.workspace_dir,
                self.paths.artifacts_dir,
                self.paths.skills_dir,
            ],
        )

    
    
    
    @property
    def assistants(self) -> AssistantsConfig:
        return self.config.assistants

    def resolve_assistant(self, assistant_id: str | None) -> AssistantProfile | None:

        if not assistant_id:
            return None
        return self.assistants.get(assistant_id)

    
    
    
    
    
    
    
    def assistant_confirm_mode(self, assistant_id: str | None) -> str | None:

        profile = self.resolve_assistant(assistant_id)
        return profile.confirm_mode if profile else None

    def save_assistants(self, config: AssistantsConfig) -> AssistantsConfig:
        saved = self.config_store.save_assistants(config)
        
        
        self.config = self.config.model_copy(update={"assistants": saved})
        return saved

    async def save_scheduled_tasks(
        self, specs: list[ScheduledTaskSpec]
    ) -> list[ScheduledTaskSpec]:






        settings = self.config.settings.model_copy(
            update={
                "agent": self.config.settings.agent.model_copy(
                    update={"scheduled_tasks": specs}
                )
            }
        )
        saved = self.config_store.save_settings(settings)
        self.config = self.config.model_copy(update={"settings": saved})
        await self.task_scheduler.restart()
        return list(saved.agent.scheduled_tasks)

    def seed_evolution_tasks(self) -> None:














        assistants = list(self.config.assistants.assistants)
        current = list(self.config.settings.agent.scheduled_tasks or [])
        upgraded, upgraded_ids = upgrade_builtin_prompts(current, assistants)
        merged = ensure_builtin_tasks(upgraded, assistants)
        if merged is current:
            return
        settings = self.config.settings.model_copy(
            update={
                "agent": self.config.settings.agent.model_copy(
                    update={"scheduled_tasks": merged}
                )
            }
        )
        saved = self.config_store.save_settings(settings)
        self.config = self.config.model_copy(update={"settings": saved})
        added = len(merged) - len(upgraded)
        if added:
            logger.info("已播种内置搭子的「全员进化」任务：新增 %d 条", added)
        if upgraded_ids:
            
            logger.info(
                "已把「全员进化」预置任务的提示词升级到出厂新版: %s",
                ", ".join(upgraded_ids),
            )

    @property
    def skill_services(self) -> dict[str, Any]:

        return self.skill_services_for(None)

    def skill_services_for(
        self, assistant_id: str | None, group_id: str | None = None
    ) -> dict[str, Any]:









        if not self.db_ready:
            services: dict[str, Any] = {"expenses": None, "reminders": None}
        else:
            services = {"expenses": self.expense_repo, "reminders": self.reminder_repo}

        
        
        
        
        
        
        services["skill_secrets"] = self.skill_secrets

        
        
        if self.config.settings.memory.long_term_enabled:
            services["memory"] = (
                self.memory_for_group(group_id) if group_id else self.memory_for(assistant_id)
            )
        services["custom_skill_store"] = self._custom_skill_store
        
        
        services["team"] = self.orchestrator
        
        services["buddy"] = self.buddy_library
        
        
        services["history"] = self.history_search
        
        
        services["tasks"] = self.task_store
        
        
        from ..calendar.service import CalendarService

        services["calendar"] = CalendarService(self.config.settings.calendar, self.paths)
        
        
        
        from ..skill.builtin.xjx_report import XjxGateway

        services["xjx"] = XjxGateway(self)
        return services

    
    
    
    async def _adopt_legacy_memory_namespaces(self) -> None:






        if not self.config.settings.memory.long_term_enabled:
            return
        from ..assistants.presets import RENAMED_BUILTIN_IDS

        for old_id, new_id in RENAMED_BUILTIN_IDS.items():
            try:
                legacy = self._build_long_term_memory(self.paths, namespace=old_id)
                target = self.memory_for(new_id)
                if await target.adopt_legacy_collection(legacy.collection_name):
                    logger.info("已接管旧搭子记忆库: %s → %s", old_id, new_id)
            except Exception as exc:  
                logger.warning("接管旧搭子记忆库失败（%s → %s）: %s", old_id, new_id, exc)

    async def initialize(self) -> None:

        try:
            await self.db.connect()
            self.db_ready = True
        except Exception as exc:  
            logger.error("数据库初始化失败，降级为纯内存模式（数据不会保留）: %s", exc)
            self.db_ready = False
            self.sessions = SessionManager(repository=None)
            self.workspace = WorkspaceStore(
                workspace_dir=self.paths.workspace_dir,
                artifacts_dir=self.paths.artifacts_dir,
                db=None,
            )

        self.workspace.ensure_dirs()
        
        
        
        await self._adopt_legacy_memory_namespaces()
        restored = await self.sessions.initialize()
        await self.reminder_scheduler.start()
        
        await self.mcp.start_all()
        self.mcp.start_health_loop()
        
        
        
        inbox = self.scan_skill_inbox()
        
        
        
        
        roots = inbox.get("mcp_roots") if isinstance(inbox, dict) else None
        if roots:
            self._inbox_mcp_task = asyncio.create_task(
                self._connect_inbox_mcp(roots), name="inbox-mcp"
            )
        
        
        self.seed_evolution_tasks()
        
        
        await self.task_scheduler.start()
        
        
        
        
        from ..skill import groups

        missing = groups.validate_registry(self.skills.source_map())
        if missing:
            logger.warning(
                "技能分类名单里有 %d 个名字对不上任何已注册技能（它们会被当成内置技能）：%s",
                len(missing),
                "、".join(missing),
            )
        logger.info(
            "运行时已就绪：持久化=%s，历史会话=%s，模型=%s，技能=%s",
            "开启" if self.db_ready else "关闭",
            restored,
            len(self.registry),
            len(self.skills),
        )

        if self.db_ready:
            try:
                await self.audit_repo.purge_older_than(
                    self.config.settings.security.audit_retention_days
                )
            except Exception as exc:  
                logger.warning("清理过期审计记录失败: %s", exc)

            
            
            try:
                await self.runs.clear_running()
                await self.runs.purge_older_than(30)
            except Exception as exc:  
                logger.warning("清理运行记录失败: %s", exc)

            try:
                
                
                await self.usage_repo.purge_older_than(
                    self.config.settings.usage.retention_days
                )
            except Exception as exc:  
                logger.warning("清理过期用量记录失败: %s", exc)

    def _register_builtin_skills(self) -> None:
        from ..skill.builtin import discover_builtin_skills
        from ..skill.custom import backfill_display_names, sync_custom_skills
        from ..skill.factory import seed_factory_skills

        count = 0
        for skill_cls in discover_builtin_skills():
            try:
                self.skills.register(skill_cls)
                count += 1
            except Exception as exc:  
                logger.error("注册 Skill 失败 %s: %s", skill_cls, exc)
        logger.info("已注册 %s 个内置 Skill", count)

        
        
        
        self.custom_skills = self.config_store.load_custom_skills()

        
        
        
        
        factory = seed_factory_skills(self)
        
        
        
        logger.info("出厂技能：%s", factory)

        
        
        
        
        
        
        
        
        
        
        if backfill_display_names(self.custom_skills, self.paths.skills_dir):
            self.custom_skills = self.config_store.save_custom_skills(self.custom_skills)
        custom = sync_custom_skills(self.skills, self.custom_skills)
        if custom:
            logger.info("已注册 %s 个自定义技能", custom)

        
        
        from ..skill.custom import CustomSkillInstallSkill, SkillPackageInstallSkill

        try:
            self.skills.register(CustomSkillInstallSkill)
        except Exception as exc:  
            logger.error("注册自定义技能安装器失败: %s", exc)

        
        try:
            self.skills.register(SkillPackageInstallSkill)
        except Exception as exc:  
            logger.error("注册技能包安装器失败: %s", exc)

    def reload_custom_skills(self, config: Any) -> int:











        from ..skill.custom import sync_custom_skills

        self.custom_skills = config
        total = sync_custom_skills(self.skills, config)
        self.events.publish("skills_changed", total=total)
        return total

    def scan_skill_inbox(self) -> dict[str, Any]:










        from ..skill.inbox import scan_inbox

        try:
            outcome = scan_inbox(self)
        except Exception as exc:  
            logger.error("技能文件夹扫描失败：%s", exc)
            
            
            return {
                "ok": False,
                "installed": [],
                "results": [],
                "unpacked": {},
                "unrecognized": [],
                "skipped": [],
                "total": len(getattr(self.custom_skills, "skills", []) or []),
                "scanned": 0,
                "counts": {"added": 0, "updated": 0, "skipped": 0, "failed": 0},
                "message": f"技能文件夹扫描失败：{exc}",
            }
        if outcome.get("scanned"):
            logger.info("技能文件夹扫描：%s", outcome.get("message"))
        return outcome

    async def _connect_inbox_mcp(self, roots: list[Any]) -> None:












        from ..skill.install import install_mcp_roots

        try:
            records = await install_mcp_roots(self, roots)
        except Exception as exc:  
            logger.warning("投放区 MCP 服务接入失败：%s", exc)
            return
        if not records:
            return
        ok = sum(1 for item in records if item.get("ok"))
        logger.info("投放区 MCP 服务接入：%s/%s 个成功", ok, len(records))
        for item in records:
            if item.get("ok"):
                continue
            
            logger.warning(
                "投放区 MCP 服务未接入 · %s：%s", item.get("name"), item.get("message")
            )
        if not ok:
            return
        
        
        
        self.events.publish("skills_changed", total=len(self.skills.list_metas(enabled_only=False)))

    def utility_llm(self, fallback: BaseLLM) -> BaseLLM:






        from ..llm.factory import resolve_utility_llm

        return resolve_utility_llm(
            self.registry, self.config.settings.agent.utility_model_id, fallback
        )

    
    
    
    def _reload_config(self) -> None:






        self.config = self.config_store.load(reload=True)
        if self.secrets is not None:
            apply_secrets(self.config, self.secrets)

    async def reload_models(self, models: ModelsConfig | None = None) -> None:






        marks: list[tuple[str, float]] = []
        started = time.perf_counter()

        def mark(label: str) -> None:
            marks.append((label, (time.perf_counter() - started) * 1000))

        if models is not None:
            
            
            
            
            self.config_store.save_models(models)
            mark("write_config")
            self.config = self.config_store.load()
            mark("load_config")
        else:
            self._reload_config()
            mark("reload_config")

        old = self.registry
        self.registry = build_registry(
            self.config.models, on_fallback=self._on_model_fallback
        )
        mark("build_registry")
        
        
        
        
        
        
        
        
        
        
        
        
        await old.retire()
        mark("retire_old")

        total = marks[-1][1] if marks else 0.0
        steps = " ".join(
            f"{label}={value - (marks[index - 1][1] if index else 0):.0f}ms"
            for index, (label, value) in enumerate(marks)
        )
        logger.info(
            "模型注册表已重建，默认: %s（总 %.0fms；%s）",
            self.registry.default_id,
            total,
            steps,
        )

    def _embedder_cache(self) -> tuple[Any, Any]:





        if self._embedder_pair is not None:
            return self._embedder_pair
        settings = self.config.settings.memory
        backend = self._resolve_embedding_backend(settings)
        if backend == "api":
            embedder = self._build_api_embedder(settings)
            query_embedder = None
        elif backend == "ollama":
            embedder = self._build_ollama_embedder(settings)
            query_embedder = None
        else:
            embedder, query_embedder = self._build_builtin_embedder()
        self._embedder_pair = (embedder, query_embedder)
        return self._embedder_pair

    def _build_long_term_memory(
        self, paths: Any, *, namespace: str = ""
    ) -> LongTermMemory:











        embedder, query_embedder = self._embedder_cache()
        return LongTermMemory(
            paths.data_dir / "vectors",
            namespace=namespace,
            embedder=embedder,
            query_embedder=query_embedder,
            
            
            default_top_k=self.config.settings.memory.vector_top_k,
            
            
            embedding_signature=self._embedding_signature(),
            
            
            
            
            
            on_rebuilt=self._on_memory_rebuilt,
        )

    def _on_memory_rebuilt(self, count: int) -> None:

        if count <= 0:
            return
        self.events.publish("memory_rebuilt", count=count)

    async def _publish_model_event(self, event_type: str, data: dict[str, Any]) -> None:






        self.events.publish(event_type, **data)

    def _embedding_signature(self) -> str:










        settings = self.config.settings.memory
        backend = self._resolve_embedding_backend(settings)
        if backend == "builtin":
            return "builtin"
        if backend == "ollama":
            url = str(getattr(settings, "embedding_ollama_url", "") or "").strip()
            model = str(getattr(settings, "embedding_ollama_model", "") or "").strip()
            return f"ollama|{url}|{model}"
        url = str(getattr(settings, "embedding_base_url", "") or "").strip()
        model = str(getattr(settings, "embedding_model", "") or "").strip()
        return f"api|{url}|{model}"

    def memory_for(self, assistant_id: str | None) -> LongTermMemory:









        return self._memory_by_key(assistant_id or "")

    def memory_for_group(self, group_id: str | None) -> LongTermMemory:










        return self._memory_by_key(f"group_{group_id}" if group_id else "")

    def groups_for_assistant(self, assistant_id: str | None) -> list[str]:








        if not assistant_id:
            return []
        return [
            group.id
            for group in self.groups.groups
            if assistant_id in (getattr(group, "member_assistant_ids", None) or [])
        ]

    def _memory_by_key(self, key: str) -> LongTermMemory:






        if not key:
            return self.long_term
        instance = self._memory_by_assistant.get(key)
        if instance is None:
            instance = self._build_long_term_memory(self.paths, namespace=key)
            self._memory_by_assistant[key] = instance
        return instance

    async def archive_turn(
        self,
        *,
        assistant_id: str | None,
        session_id: str,
        user_text: str,
        assistant_text: str,
    ) -> None:







        if not self.config.settings.memory.long_term_enabled:
            return
        
        
        
        
        if not assistant_id:
            logger.info("会话 %s 没有绑定搭子，本轮不写入长期记忆（避免串台）", session_id)
            return
        user = (user_text or "").strip()
        assistant = (assistant_text or "").strip()
        if not user or not assistant:
            return
        
        
        
        
        record = f"[{format_now(time.time())}] 用户：{user}\n助手：{assistant}"
        try:
            await self.memory_for(assistant_id).add(
                [record],
                metadatas=[{"source": "chat", "session_id": session_id}],
            )
        except Exception:  
            logger.warning("对话落库失败 assistant=%s session=%s", assistant_id, session_id)

    async def archive_group_turn(
        self,
        *,
        group_id: str,
        speaker: str,
        text: str,
        thread_id: str = "",
    ) -> None:











        if not self.config.settings.memory.long_term_enabled:
            return
        body = (text or "").strip()
        if not group_id or not body:
            return
        who = (speaker or "成员").strip()
        record = f"[{format_now(time.time())}] {who}：{body}"
        try:
            await self.memory_for_group(group_id).add(
                [record],
                metadatas=[{"source": "group", "group_id": group_id, "thread_id": thread_id}],
            )
        except Exception:  
            logger.warning("群发言落库失败 group=%s speaker=%s", group_id, who)

    @staticmethod
    def _resolve_embedding_backend(settings: Any) -> str:






        backend = (getattr(settings, "embedding_backend", "builtin") or "builtin").strip()
        if backend != "builtin":
            return backend
        if getattr(settings, "use_api_embedding", False) and (
            getattr(settings, "embedding_model_id", "")
            or getattr(settings, "embedding_base_url", "")
        ):
            return "api"
        return "builtin"

    def _build_api_embedder(self, settings: Any) -> Any:






        reused = self.config.models.get(
            getattr(settings, "embedding_key_model_id", "")
            or getattr(settings, "embedding_model_id", "")
        )
        base_url = (getattr(settings, "embedding_base_url", "") or "").strip() or (
            reused.base_url if reused else ""
        )
        model = (getattr(settings, "embedding_model", "") or "").strip() or (
            reused.model_name if reused else ""
        )
        key = (getattr(settings, "embedding_api_key", "") or "").strip() or (
            reused.api_key if reused else ""
        )

        if not base_url:
            logger.warning("长期记忆已设为接口嵌入，但拿不到端点地址；已回落到内置模型")
            return None

        from ..memory.embedding import ApiEmbedder

        logger.info("长期记忆使用接口嵌入：%s", model or "(未指定模型)")
        return ApiEmbedder(base_url=base_url, api_key=key, model_name=model)

    def _build_ollama_embedder(self, settings: Any) -> Any:
        model = (getattr(settings, "embedding_ollama_model", "") or "").strip()
        if not model:
            logger.warning("长期记忆已设为 Ollama，但没有选模型；已回落到内置模型")
            return None

        from ..memory.embedding import OllamaEmbedder

        logger.info("长期记忆使用 Ollama：%s", model)
        return OllamaEmbedder(getattr(settings, "embedding_ollama_url", ""), model)

    @staticmethod
    def _build_builtin_embedder() -> tuple[Any, Any]:





        from ..memory.local_embedding import build_local_embedder

        builtin = build_local_embedder()
        if builtin is None:
            logger.warning("内置中文嵌入模型不可用，已回落到自带模型（英文、首次需联网）")
            return None, None
        return builtin, builtin.embed_query

    def apply_settings(self, settings: AppSettings) -> AppSettings:
        previous = self.config.settings
        saved = self.config_store.save_settings(settings)
        self._reload_config()
        self.skills.guard.set_confirm_mode(saved.security.confirm_mode)
        
        self.path_policy = self._build_path_policy()
        
        
        
        
        
        
        
        
        
        
        
        if saved.memory != previous.memory:
            self.long_term.dispose()
            for instance in self._memory_by_assistant.values():
                instance.dispose()
            self._memory_by_assistant.clear()
            self._embedder_pair = None
            self.long_term = self._build_long_term_memory(self.paths)
            logger.info("长期记忆已按新设置重建（含每搭子实例与嵌入器缓存）")
        return saved

    
    
    
    def effective_context_tokens(self, model_id: str | None) -> int:









        window = 0
        try:
            window = self.registry.get(model_id).token_limit
        except Exception:  
            logger.debug("取不到模型 %s 的上下文窗口，按硬上限处理", model_id)

        cap = self.config.settings.agent.max_context_tokens
        if window <= 0:
            
            
            
            return cap if cap > 0 else 32768
        return min(window, cap) if cap > 0 else window

    async def get_session(self, session_id: str | None, *, model_id: str | None = None) -> Session:
        from ..memory.spill import SPILL_DIRNAME

        session = await self.sessions.get_or_create(session_id, model_id=model_id)
        session.memory.configure(
            
            
            max_context_tokens=self.effective_context_tokens(model_id or session.model_id),
            
            
            
            
            
            
            
            
            
            spill_root=self.paths.artifacts_dir / SPILL_DIRNAME,
            spill_session=session.id,
        )
        return session

    async def persist_session(self, session: Session) -> None:















        await self.sessions.persist(session, include_messages=True, mode="append")

    
    
    
    def _ensure_slots(self) -> asyncio.Semaphore:







        limit = self.config.settings.agent.max_concurrent_chats
        if self._chat_slots is None or self._chat_slots_limit != limit:
            self._chat_slots = asyncio.Semaphore(limit)
            self._chat_slots_limit = limit
            logger.info("对话并发上限已设为 %s", limit)
        return self._chat_slots

    async def acquire_chat_slot(self) -> asyncio.Semaphore | None:

        semaphore = self._ensure_slots()
        timeout = self.config.settings.agent.queue_wait_seconds
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=timeout)
        except TimeoutError:
            return None
        return semaphore

    @staticmethod
    def release_chat_slot(semaphore: asyncio.Semaphore) -> None:
        semaphore.release()

    def _on_model_fallback(self, failed: str, taken_over: str, reason: str) -> None:








        
        
        
        
        METRICS.inc("llm_fallback_total", model=failed, to=taken_over or "none")
        self.events.publish(
            "model_fallback",
            session_id=current_session_id.get(),
            failed_model=failed,
            taken_over=taken_over,
            reason=reason,
            message=(
                f"模型 {failed} 调用失败，已切换到 {taken_over}。"
                if taken_over
                else f"模型 {failed} 调用失败，且没有可用的备用模型。"
            ),
        )

    def _on_session_persist_error(self, session: Session, error: Exception) -> None:






        self.events.publish(
            "session_save_failed",
            session_id=session.id,
            message="这一轮对话未能保存到本机数据库，重启后可能丢失。请检查磁盘空间与日志。",
            detail=str(error),
        )

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    

    
    
    
    def _on_mcp_status(self, status: Any) -> None:





        self.events.publish("mcp_status", server=status.to_dict())

    
    
    
    def register_task(self, session_id: str, task: asyncio.Task) -> RunningTask:
        running = RunningTask(uuid.uuid4().hex[:8], session_id, task)
        self.tasks[running.id] = running
        return running

    def unregister_task(self, task_id: str) -> None:
        self.tasks.pop(task_id, None)

    def cancel_task(self, task_id: str) -> bool:
        running = self.tasks.get(task_id)
        if running is None or running.task.done():
            return False
        running.task.cancel()
        return True

    def cancel_session_tasks(self, session_id: str) -> int:
        return sum(
            1
            for running in list(self.tasks.values())
            if running.session_id == session_id and self.cancel_task(running.id)
        )

    
    
    
    async def request_confirm(self, request: ConfirmRequest, emit, owner: str) -> bool:
























        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        holder = PendingConfirm(owner=owner, future=future)
        self.pending_confirms[request.request_id] = holder
        try:
            await emit(request)
            approved = await future
            if not approved and holder.interrupted:
                
                
                logger.info("确认请求因任务被打断而作废: %s", request.skill_name)
            return approved
        finally:
            self.pending_confirms.pop(request.request_id, None)

    def resolve_confirm(self, request_id: str, approved: bool) -> bool:
        pending = self.pending_confirms.get(request_id)
        if pending is None or pending.future.done():
            return False
        pending.future.set_result(approved)
        return True

    async def request_plan_decision(self, plan_id: str, owner: str) -> tuple[bool, str]:















        loop = asyncio.get_running_loop()
        future: asyncio.Future[tuple[bool, str]] = loop.create_future()
        self.pending_plans[plan_id] = PendingPlan(owner=owner, future=future)
        try:
            return await future
        finally:
            self.pending_plans.pop(plan_id, None)

    def resolve_plan(self, plan_id: str, approved: bool, feedback: str = "") -> bool:

        pending = self.pending_plans.get(plan_id)
        if pending is None or pending.future.done():
            return False
        pending.future.set_result((approved, feedback))
        return True

    async def request_interaction(
        self, request: Any, emit: Any, owner: str
    ) -> dict[str, Any]:





















        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self.pending_interactions[request.request_id] = PendingInteraction(
            owner=owner, future=future
        )
        try:
            await emit(request)
            return await future
        finally:
            self.pending_interactions.pop(request.request_id, None)

    def resolve_interaction(self, request_id: str, answer: dict[str, Any]) -> bool:

        pending = self.pending_interactions.get(request_id)
        if pending is None or pending.future.done():
            return False
        pending.future.set_result(answer)
        return True

    def apply_skill_secrets(self, secrets: SkillSecrets) -> int:

















        self.skill_secrets = secrets
        logger.info("用户给技能的密钥已更新：%s 条", len(secrets.keys))
        return len(secrets.keys)

    def reject_pending(self, owner: str | None = None) -> int:







        count = 0
        for pending in list(self.pending_confirms.values()):
            if owner is not None and pending.owner != owner:
                continue
            if not pending.future.done():
                pending.interrupted = True
                pending.future.set_result(False)
                count += 1
        
        
        for pending in list(self.pending_plans.values()):
            if owner is not None and pending.owner != owner:
                continue
            if not pending.future.done():
                pending.future.set_result((False, ""))
                count += 1
        
        
        
        
        
        for pending in list(self.pending_interactions.values()):
            if owner is not None and pending.owner != owner:
                continue
            if not pending.future.done():
                pending.future.set_result({"cancelled": True, "interrupted": True})
                count += 1
        return count

    
    
    
    async def test_model(self, spec: ModelSpec) -> dict[str, Any]:
        llm = build_llm(spec)
        started = time.perf_counter()
        try:
            models = await llm.list_models()
            return {
                "ok": True,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "models": models,
            }
        except LLMError as exc:
            return {"ok": False, "error": exc.message}
        except Exception as exc:  
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            await llm.aclose()

    
    
    
    async def shutdown(self) -> None:
        self.reject_pending()
        
        
        await self.model_downloader.shutdown()
        
        
        await self.task_scheduler.stop()
        
        await self.orchestrator.shutdown()
        await self.reminder_scheduler.stop()
        
        await self.mcp.stop_all()
        await self.long_term.aclose()
        pending = [r.task for r in list(self.tasks.values()) if not r.task.done()]
        for task in pending:
            task.cancel()

        
        
        
        
        
        if pending:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    asyncio.gather(*pending, return_exceptions=True),
                    timeout=SHUTDOWN_GRACE_SECONDS,
                )
        self.tasks.clear()

        await self.registry.aclose()
        if self.db_ready:
            await self.db.close()
        
        from ..browser.session import browser

        await browser.close()
        logger.info("运行时已关闭")


def create_runtime(paths: AppPaths | None = None) -> AppRuntime:




    return AppRuntime(paths or AppPaths.resolve())


__all__ = ["AppRuntime", "PendingConfirm", "RunningTask", "create_runtime"]































































from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..config.schemas import ScheduledTaskSpec
from ..errors import ConfigError
from ..skill.custom import persona_with_instructions
from ..storage.runs import RunRecord
from .task_store import locked_for_user

logger = logging.getLogger(__name__)


MIN_TICK_SECONDS = 10



CONDITION_FETCH_TIMEOUT = 20.0









CONDITION_MAX_BYTES = 2 * 1024 * 1024



CATCH_UP_WINDOW_SECONDS = 24 * 3600


STATE_FILENAME = "scheduler_state.json"

STATE_VERSION = 1


class TaskScheduler:


    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        self._task: asyncio.Task[None] | None = None
        
        
        self._last_run: dict[str, float] = {}
        
        
        
        self._last_exec: dict[str, float] = {}
        
        
        
        
        self._first_seen: dict[str, float] = {}
        
        self._catch_up: dict[str, float] = {}
        self._state_loaded = False
        self._running: set[str] = set()
        
        
        self._fingerprints: dict[str, str] = {}
        
        
        
        self._condition_errors: dict[str, str] = {}
        
        
        
        
        
        
        
        self._running_tasks: set[asyncio.Task[None]] = set()

    
    
    
    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running:
            return

        specs = self._specs()
        if not specs:
            
            
            logger.debug("未配置自动化任务，调度器不启动")
            return

        self._load_state()
        now = time.time()

        
        
        
        self._catch_up = {}
        for spec in specs:
            if spec.id in self._last_run or not spec.enabled:
                continue
            point = self._overdue_point(spec, now)
            if point is not None:
                self._catch_up[spec.id] = point

        
        
        for spec in specs:
            point = self._catch_up.get(spec.id)
            self._last_run.setdefault(spec.id, now if point is None else point)
            self._first_seen.setdefault(spec.id, now)
        
        
        self._save_state()

        self._task = asyncio.create_task(self._loop(), name="task-scheduler")
        enabled = sum(1 for spec in specs if spec.enabled)
        logger.info("自动化任务调度器已启动：共 %s 项，其中 %s 项已启用", len(specs), enabled)
        for spec in specs:
            point = self._catch_up.get(spec.id)
            if point is not None:
                logger.info(
                    "自动化任务 %s 错过了 %s 的那一次，本次启动补跑一次",
                    spec.id,
                    datetime.fromtimestamp(point).strftime("%Y-%m-%d %H:%M"),
                )

    async def restart(self) -> None:










        await self.stop()
        alive = {spec.id for spec in self._specs()}
        self._last_run = {key: value for key, value in self._last_run.items() if key in alive}
        self._last_exec = {key: value for key, value in self._last_exec.items() if key in alive}
        self._first_seen = {key: value for key, value in self._first_seen.items() if key in alive}
        self._fingerprints = {
            key: value for key, value in self._fingerprints.items() if key in alive
        }
        self._condition_errors = {
            key: value for key, value in self._condition_errors.items() if key in alive
        }
        await self.start()

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        
        
        
        
        pending, self._running_tasks = list(self._running_tasks), set()
        for item in pending:
            item.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
            logger.debug("已取消 %s 个在跑的自动化任务", len(pending))

    
    
    
    def _state_path(self) -> Path | None:





        paths = getattr(self._runtime, "paths", None)
        data_dir = getattr(paths, "data_dir", None)
        if not data_dir:
            return None
        return Path(data_dir) / STATE_FILENAME

    def _load_state(self) -> None:





        if self._state_loaded:
            return
        self._state_loaded = True
        path = self._state_path()
        if path is None:
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:  
            logger.warning("自动化任务状态文件读不出来（本次不补跑）%s: %s", path, exc)
            return
        if not isinstance(raw, dict) or raw.get("version") != STATE_VERSION:
            
            
            logger.info("自动化任务状态文件版本不认识，丢弃不用：%s", path)
            return
        tasks = raw.get("tasks")
        if not isinstance(tasks, dict):
            return
        for task_id, entry in tasks.items():
            if not isinstance(entry, dict):
                continue
            last = entry.get("last_run_at")
            seen = entry.get("first_seen_at")
            if isinstance(last, (int, float)):
                self._last_exec[str(task_id)] = float(last)
            if isinstance(seen, (int, float)):
                self._first_seen[str(task_id)] = float(seen)

    def _save_state(self) -> None:





        path = self._state_path()
        if path is None:
            return
        payload: dict[str, dict[str, float]] = {}
        for spec in self._specs():
            entry: dict[str, float] = {}
            if spec.id in self._first_seen:
                entry["first_seen_at"] = self._first_seen[spec.id]
            if spec.id in self._last_exec:
                entry["last_run_at"] = self._last_exec[spec.id]
            if entry:
                payload[spec.id] = entry
        body = {"version": STATE_VERSION, "tasks": payload}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            
            
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning("自动化任务状态文件写不进去 %s: %s", path, exc)

    def _mark_handled(self, spec: ScheduledTaskSpec, now: float) -> None:





        self._last_exec[spec.id] = now
        self._save_state()

    def _overdue_point(self, spec: ScheduledTaskSpec, now: float) -> float | None:

        if spec.id not in self._first_seen:
            
            
            
            
            return None

        if spec.trigger == "interval":
            
            anchor = self._last_exec.get(spec.id)
            if anchor is None:
                anchor = self._first_seen[spec.id]
            start = self._start_point(spec)
            if start is not None:
                
                
                
                anchor = max(anchor, start)
            point = anchor + spec.interval_minutes * 60
        else:
            point = self._last_occurrence(spec, now)
            if point is None:
                return None
            last = self._last_exec.get(spec.id)
            if last is not None and last >= point:
                
                return None

        if point > now:
            return None  
        if now - point > CATCH_UP_WINDOW_SECONDS:
            return None  

        first = self._first_seen.get(spec.id)
        if first is not None and first > point:
            return None  
        return point

    def _spawn(
        self,
        spec: ScheduledTaskSpec,
        *,
        resume: RunRecord | None = None,
        catch_up: bool = False,
    ) -> None:









        task = asyncio.create_task(
            self._run_task(spec, resume=resume, catch_up=catch_up),
            name=f"scheduled-{spec.id}",
        )
        self._running_tasks.add(task)
        task.add_done_callback(self._running_tasks.discard)

    
    
    
    def _specs(self) -> list[ScheduledTaskSpec]:
        return list(self._runtime.config.settings.agent.scheduled_tasks or [])

    def describe(self) -> list[dict[str, Any]]:

        now = time.time()
        items: list[dict[str, Any]] = []
        for spec in self._specs():
            
            
            last = self._last_exec.get(spec.id)
            items.append(
                {
                    **spec.model_dump(),
                    
                    
                    
                    "locked": locked_for_user(spec),
                    "last_run_at": last,
                    "running": spec.id in self._running,
                    
                    
                    "next_run_in_seconds": self._next_run_in_seconds(spec, now),
                    
                    
                    "condition_ready": spec.id in self._fingerprints,
                }
            )
        return items

    async def run_now(self, task_id: str) -> bool:

        spec = next((item for item in self._specs() if item.id == task_id), None)
        if spec is None:
            return False
        if spec.id in self._running:
            
            
            return False
        now = time.time()
        self._last_run[spec.id] = now
        
        
        self._mark_handled(spec, now)
        self._spawn(spec)
        return True

    
    
    
    async def _loop(self) -> None:
        while True:
            
            
            
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:  
                logger.exception("自动化任务调度出错，下一轮继续")

            tick = max(
                MIN_TICK_SECONDS,
                int(self._runtime.config.settings.agent.scheduler_tick_seconds),
            )
            await asyncio.sleep(tick)

    async def _tick(self) -> None:
        now = time.time()
        
        due: list[tuple[ScheduledTaskSpec, bool]] = []
        for spec in self._specs():
            if not spec.enabled or spec.id in self._running:
                continue
            
            
            catching_up = spec.id in self._catch_up
            if not catching_up and not self._is_due(spec, now):
                continue
            
            
            self._catch_up.pop(spec.id, None)
            
            
            
            
            
            
            self._last_run[spec.id] = now
            self._mark_handled(spec, now)
            due.append((spec, catching_up))

        if not due:
            return

        
        
        
        
        
        
        
        
        
        
        
        
        outcomes = await asyncio.gather(
            *(self._condition_met(spec) for spec, _ in due),
            return_exceptions=True,
        )
        for (spec, catching_up), outcome in zip(due, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                logger.error("条件检查异常 task=%s：%s", spec.id, outcome, exc_info=outcome)
                continue
            if not outcome:
                continue
            self._spawn(spec, catch_up=catching_up)

    
    
    
    def _start_point(self, spec: ScheduledTaskSpec) -> float | None:






        raw = (spec.start_at or "").strip()
        if not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%dT%H:%M").timestamp()
        except ValueError:
            logger.warning("自动化任务 %s 的起始时间不合法（%s），按未设置处理", spec.id, raw)
            return None

    def _is_due(self, spec: ScheduledTaskSpec, now: float) -> bool:

        last = self._last_run.get(spec.id)

        if spec.trigger == "interval":
            start = self._start_point(spec)
            if start is not None and now < start:
                return False  
            if start is not None and (last is None or last < start):
                
                
                
                
                return True
            return last is None or now - last >= spec.interval_minutes * 60

        occurrence = self._last_occurrence(spec, now)
        
        
        
        return occurrence is not None and (last is None or last < occurrence)

    def _last_occurrence(self, spec: ScheduledTaskSpec, now: float) -> float | None:

        hour, minute = (int(part) for part in spec.at_time.split(":"))
        current = datetime.fromtimestamp(now)
        candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if spec.trigger == "daily":
            if candidate > current:
                candidate -= timedelta(days=1)
            return candidate.timestamp()

        
        days_back = (current.weekday() - spec.weekday) % 7
        candidate -= timedelta(days=days_back)
        if candidate > current:
            candidate -= timedelta(days=7)
        return candidate.timestamp()

    def _next_run_in_seconds(self, spec: ScheduledTaskSpec, now: float) -> float | None:

        if spec.trigger == "interval":
            start = self._start_point(spec)
            if start is not None and now < start:
                return max(0.0, start - now)  
            last = self._last_run.get(spec.id)
            if last is None:
                return None
            if start is not None and last < start:
                return 0.0  
            return max(0.0, spec.interval_minutes * 60 - (now - last))

        occurrence = self._last_occurrence(spec, now)
        if occurrence is None:
            return None
        step = timedelta(days=1 if spec.trigger == "daily" else 7)
        upcoming = occurrence
        while upcoming <= now:
            upcoming = (datetime.fromtimestamp(upcoming) + step).timestamp()
        
        
        last = self._last_run.get(spec.id)
        if last is not None and last >= upcoming:
            upcoming = (datetime.fromtimestamp(upcoming) + step).timestamp()
        return max(0.0, upcoming - now)

    
    
    
    async def _condition_met(self, spec: ScheduledTaskSpec) -> bool:





        if spec.condition == "none":
            return True
        try:
            if spec.condition == "url_changed":
                return await self._url_changed(spec)
            if spec.condition == "file_changed":
                return self._file_changed(spec)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  
            self._note_condition_error(spec, str(exc))
            return False
        return True

    async def _url_changed(self, spec: ScheduledTaskSpec) -> bool:






        from ..security.urls import validate_endpoint
        from ..utils.http import async_client

        target = spec.condition_target.strip()
        try:
            validate_endpoint(target, field="监控的网页地址")
        except ConfigError as exc:
            self._note_condition_error(spec, exc.message)
            return False

        
        
        
        
        
        
        
        
        
        
        collected = bytearray()
        truncated = False
        async with async_client(timeout=CONDITION_FETCH_TIMEOUT) as client:
            async with client.stream("GET", target) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    if not chunk:
                        continue
                    collected.extend(chunk)
                    if len(collected) > CONDITION_MAX_BYTES:
                        truncated = True
                        break

        body = bytes(collected[:CONDITION_MAX_BYTES])
        size = len(body)
        fingerprint = hashlib.sha256(body).hexdigest()
        previous = self._fingerprints.get(spec.id)
        self._fingerprints[spec.id] = fingerprint
        self._condition_errors.pop(spec.id, None)
        
        
        scope = (
            f"前 {size} 字节（已截断，上限 {CONDITION_MAX_BYTES}）"
            if truncated
            else f"{size} 字节"
        )

        if previous is None:
            logger.info("自动化任务 %s 已建立网页基线（%s），本次不执行", spec.id, scope)
            return False
        if previous == fingerprint:
            logger.debug("自动化任务 %s 的网页没有变化，本次不执行", spec.id)
            return False
        logger.info("自动化任务 %s 监控的网页有变化（%s），开始执行", spec.id, scope)
        return True

    def _file_changed(self, spec: ScheduledTaskSpec) -> bool:





        target = os.path.expanduser(spec.condition_target.strip())
        try:
            stat = os.stat(target)
        except OSError as exc:
            self._note_condition_error(spec, f"无法读取 {target}：{exc.strerror or exc}")
            return False

        fingerprint = f"{stat.st_mtime_ns}:{stat.st_size}"
        previous = self._fingerprints.get(spec.id)
        self._fingerprints[spec.id] = fingerprint
        self._condition_errors.pop(spec.id, None)

        if previous is None:
            logger.info("自动化任务 %s 已建立文件基线（%s），本次不执行", spec.id, target)
            return False
        if previous == fingerprint:
            logger.debug("自动化任务 %s 的文件没有变化，本次不执行", spec.id)
            return False
        logger.info("自动化任务 %s 监控的文件有更新（%s），开始执行", spec.id, target)
        return True

    def _note_condition_error(self, spec: ScheduledTaskSpec, reason: str) -> None:





        logger.warning("自动化任务 %s 的条件检查失败：%s", spec.id, reason)
        if self._condition_errors.get(spec.id) == reason:
            return
        self._condition_errors[spec.id] = reason
        
        
        if spec.silent:
            return
        self._runtime.events.publish(
            "scheduled_task_failed",
            task_id=spec.id,
            name=spec.name,
            message=(
                f"自动化任务「{spec.name}」的条件检查失败，本轮没有执行：{reason}"
                "（修好地址或路径后会自动恢复，无需重建任务）"
            ),
        )

    async def _run_task(
        self,
        spec: ScheduledTaskSpec,
        *,
        resume: RunRecord | None = None,
        catch_up: bool = False,
    ) -> None:
        self._running.add(spec.id)
        
        
        prefix = "（补跑：客户端关闭期间错过的那一次）" if catch_up else ""
        session_id = ""
        try:
            session_id = await self._execute(spec, resume=resume)
            
            
            
            if not spec.silent:
                self._runtime.events.publish(
                    "scheduled_task_done",
                    task_id=spec.id,
                    name=spec.name,
                    
                    
                    session_id=session_id,
                    message=f"自动化任务「{spec.name}」已完成{prefix}，结果在新会话里。",
                )
            
            
            await self._runtime.audit.op(
                kind="task",
                action="resume" if resume is not None else "run",
                actor_id=spec.assistant_id or None,
                target=spec.id,
                session_id=session_id,
                detail=f"「{spec.name}」执行完成{prefix}",
            )
        except asyncio.CancelledError:
            await self._runtime.audit.op(
                kind="task",
                action="interrupt",
                actor_id=spec.assistant_id or None,
                target=spec.id,
                status="error",
                detail=f"「{spec.name}」被中断（应用退出或主动停止）{prefix}",
            )
            raise
        except Exception as exc:  
            logger.exception("自动化任务 %s 执行失败", spec.id)
            
            
            if not spec.silent:
                self._runtime.events.publish(
                    "scheduled_task_failed",
                    task_id=spec.id,
                    name=spec.name,
                    message=f"自动化任务「{spec.name}」执行失败{prefix}：{exc}",
                )
            await self._runtime.audit.op(
                kind="task",
                action="fail",
                actor_id=spec.assistant_id or None,
                target=spec.id,
                status="error",
                detail=f"「{spec.name}」执行失败{prefix}：{exc}"[:400],
            )
        finally:
            self._running.discard(spec.id)

    async def resume(self, run: RunRecord) -> bool:





        spec = next((item for item in self._specs() if item.id == run.ref_id), None)
        if spec is None:
            logger.warning("续跑失败：任务已不存在 id=%s", run.ref_id)
            return False
        if run.ref_id in self._running:
            
            logger.info("续跑忽略：任务正在执行 id=%s", run.ref_id)
            return False
        self._spawn(spec, resume=run)
        return True

    def _resolve_runner(self, runtime: Any, spec: ScheduledTaskSpec) -> Any:










        if spec.assistant_id:
            found = runtime.resolve_assistant(spec.assistant_id)
            if found is not None:
                return found
            logger.warning(
                "自动化任务 %s 指定的搭子「%s」已不存在，改用默认搭子",
                spec.id,
                spec.assistant_id,
            )
        config = runtime.assistants
        if config.default_assistant:
            found = config.get(config.default_assistant)
            if found is not None:
                return found
        ordered = config.sorted()
        return ordered[0] if ordered else None

    async def _execute(self, spec: ScheduledTaskSpec, *, resume: RunRecord | None = None) -> str:






        from ..observability.tracer import Tracer
        from ..skill.base import SkillContext
        from .context import ContextPolicy
        from .engine import Agent, AgentConfig

        runtime = self._runtime
        settings = runtime.config.settings

        
        
        if resume is not None:
            
            
            session = await runtime.sessions.get_or_create(resume.session_id)
            run_id = resume.id
        else:
            session = await runtime.sessions.create(title=f"[自动化] {spec.name}")
            
            
            run_id = await runtime.runs.start(kind="task", ref_id=spec.id, session_id=session.id)
        
        
        profile = self._resolve_runner(runtime, spec)
        if profile is not None:
            session.apply_assistant(profile)

        model_id = session.model_id or runtime.config.models.default_model
        llm = runtime.registry.get(model_id)
        tracer = Tracer(enabled=settings.trace_enabled)
        agent_cfg = settings.agent

        ctx = SkillContext(
            settings=settings,
            tracer=tracer,
            paths=runtime.paths,
            
            
            
            audit=runtime.audit.record,
            session_id=session.id,
            assistant_id=session.assistant_id,
            workspace=runtime.workspace,
            path_policy=runtime.path_policy,
            extra=runtime.skill_services_for(session.assistant_id),
            
            
            
            
            
            
            
            confirm_mode="auto_approve",
            
            
            
            
            
            allow_admin=True,
        )
        agent = Agent(
            llm=llm,
            
            utility_llm=runtime.utility_llm(llm),
            skill_manager=runtime.skills,
            memory=session.memory,
            config=AgentConfig(
                max_iterations=agent_cfg.max_iterations,
                max_tool_calls_per_turn=agent_cfg.max_tool_calls_per_turn,
                temperature=agent_cfg.temperature,
                top_p=agent_cfg.top_p,
                frequency_penalty=agent_cfg.frequency_penalty,
                presence_penalty=agent_cfg.presence_penalty,
                
                
                persona=lambda: persona_with_instructions(  
                    runtime, session.assistant_id, session.enabled_skills
                ),
                
                
                enabled_skills=runtime.skills.allowed_names(
                    assistant_id=session.assistant_id,
                    enabled_skills=session.enabled_skills,
                ),
                
                target_assistant=session.assistant_id or "",
                token_limit=runtime.effective_context_tokens(model_id),
                context_policy=ContextPolicy(
                    keep_recent=agent_cfg.keep_recent_messages,
                    compress_threshold=agent_cfg.compress_threshold,
                ),
            ),
            ctx=ctx,
            tracer=tracer,
        )

        
        
        
        
        prompt = spec.prompt
        if resume is not None:
            prompt = (
                f"[续跑] 上一次这条任务在第 {resume.step} 步中断"
                f"（{resume.error or '被中断'}），最后在做的是「{resume.last_action or '不确定'}」。"
                "请接着把剩下的做完；**已经完成、已经确认过的部分不要重做**，"
                "需要前面的结果时按这个会话里已有的记录继续。\n\n原始任务：\n"
                f"{spec.prompt}"
            )

        step = 0
        last_action = ""
        
        
        
        
        iterations = 0
        try:
            async for event in agent.run_stream(prompt):
                
                if event.type == "done":
                    iterations = int(event.data.get("iterations") or 0)
                if event.type == "tool_result":
                    step += 1
                    last_action = str(
                        event.data.get("display_name") or event.data.get("name") or ""
                    )
                    await runtime.runs.progress(run_id, step=step, last_action=last_action)
        except asyncio.CancelledError:
            
            
            
            await runtime.persist_session(session)
            await runtime.runs.interrupt(
                run_id,
                status="cancelled",
                step=step,
                last_action=last_action,
                error="任务被中断（应用退出或主动停止）",
            )
            raise
        except Exception as exc:  
            await runtime.persist_session(session)
            await runtime.runs.interrupt(
                run_id,
                status="failed",
                step=step,
                last_action=last_action,
                error=str(exc)[:500],
            )
            raise

        await runtime.sessions.persist(session, include_messages=True)
        
        await runtime.runs.finish(run_id)
        await runtime.usage.record(
            session_id=session.id,
            model_id=model_id,
            usage=tracer.usage,
            trace_id=tracer.trace_id,
            
            
            iterations=iterations,
        )
        
        
        
        
        if settings.trace_enabled:
            runtime.traces.put(tracer.trace_id, tracer.export())
        logger.info("自动化任务 %s 完成，会话 %s", spec.id, session.id)
        return session.id




























from __future__ import annotations

import time
from datetime import datetime, timedelta

from ..assistants import evolution, locked_builtins
from ..config.schemas import AssistantProfile, ScheduledTaskSpec


BUILTIN_TASK_ID_PREFIX = "builtin-evolve-"


WEEK_MINUTES = 7 * 24 * 60


MONTH_MINUTES = 30 * 24 * 60


MANAGER_REVIEW_TASK_ID = f"{BUILTIN_TASK_ID_PREFIX}monthly-review"


MANAGER_ASSISTANT_ID = "BuddyManager"


FIRST_RUN_WEEKDAY = 6  
FIRST_RUN_HOUR = 3
FIRST_RUN_MINUTE = 7


STAGGER_MINUTES = 15


def task_id(assistant_id: str) -> str:
    return f"{BUILTIN_TASK_ID_PREFIX}{assistant_id}"


def first_run_at(now: float, offset_minutes: int) -> str:








    moment = datetime.fromtimestamp(now)
    target = moment.replace(hour=FIRST_RUN_HOUR, minute=FIRST_RUN_MINUTE, second=0, microsecond=0)
    days_ahead = (FIRST_RUN_WEEKDAY - target.weekday()) % 7
    if days_ahead == 0 and target < moment:
        days_ahead = 7
    
    
    target += timedelta(days=days_ahead, minutes=offset_minutes)
    return target.strftime("%Y-%m-%dT%H:%M")


def builtin_specs(
    assistants: list[AssistantProfile], now: float | None = None
) -> list[ScheduledTaskSpec]:



















    stamp = time.time() if now is None else now
    locked = [item for item in assistants if locked_builtins.is_locked(item.id)]
    locked.sort(key=lambda item: (item.sort_order, item.name))
    specs: list[ScheduledTaskSpec] = []
    for slot, profile in enumerate(locked):
        name = (profile.nickname or profile.name).strip() or profile.name
        specs.append(
            ScheduledTaskSpec(
                id=task_id(profile.id),
                name=evolution.task_name(name),
                
                prompt=evolution.builtin_prompt(name, profile.id),
                assistant_id=profile.id,
                enabled=True,
                trigger="interval",
                interval_minutes=WEEK_MINUTES,
                start_at=first_run_at(stamp, slot * STAGGER_MINUTES),
                
                origin="builtin",
                silent=True,
            )
        )

    
    if any(item.id == MANAGER_ASSISTANT_ID for item in locked):
        specs.append(
            ScheduledTaskSpec(
                id=MANAGER_REVIEW_TASK_ID,
                name="全员进化月度复盘",
                prompt=evolution.manager_review_prompt(),
                assistant_id=MANAGER_ASSISTANT_ID,
                enabled=True,
                trigger="interval",
                interval_minutes=MONTH_MINUTES,
                start_at=first_run_at(stamp, len(locked) * STAGGER_MINUTES),
                origin="builtin",
                
                silent=False,
            )
        )
    return specs


def ensure_builtin_tasks(
    specs: list[ScheduledTaskSpec],
    assistants: list[AssistantProfile],
    now: float | None = None,
) -> list[ScheduledTaskSpec]:




    existing = {item.id for item in specs}
    missing = [item for item in builtin_specs(assistants, now) if item.id not in existing]
    if not missing:
        return specs
    return [*specs, *missing]


def upgrade_builtin_prompts(
    specs: list[ScheduledTaskSpec],
    assistants: list[AssistantProfile],
) -> tuple[list[ScheduledTaskSpec], list[str]]:
























    by_id = {
        item.id: ((item.nickname or item.name).strip() or item.name) for item in assistants
    }
    upgraded: list[str] = []
    result: list[ScheduledTaskSpec] = []
    for spec in specs:
        if not spec.id.startswith(BUILTIN_TASK_ID_PREFIX) or spec.id == MANAGER_REVIEW_TASK_ID:
            result.append(spec)
            continue
        name = by_id.get(spec.assistant_id, "")
        new_prompt = evolution.upgraded_builtin_prompt(spec.prompt, spec.assistant_id, name)
        if new_prompt is None:
            result.append(spec)
            continue
        result.append(spec.model_copy(update={"prompt": new_prompt}))
        upgraded.append(spec.id)
    return (result, upgraded) if upgraded else (specs, upgraded)

"""「全员进化」那**四条预置任务**的播种。

## 它是什么

四个内置搭子各挂一条自动化任务：**每周一次，让那个搭子整理自己的记忆与人格**。
每条只属于一个搭子，因为框架里「改人格」的技能只能写**当前会话绑定的那个搭子** ——
"一个搭子替全员改"做不到。这也是 OpenClaw 那份规格的做法（每个 agent 一条）。

## 三条设计取舍

1. **用「每隔一段时间 + 起始时间」而不是「每周」**：后者没有起始时间这个字段，
   而我们要的是"从某个周日凌晨的某个时刻开始，之后每 7 天一次"。间隔上限正好是
   10080 分钟（= 7 天），卡在上限上。
2. **错峰**：四条各差 15 分钟。不错开的话，四个搭子会在同一秒一起调用模型 ——
   会排队，也会把费用堆在同一个时刻。这与 OpenClaw 用"种子 + agentId"算相位是同一件事，
   只是我们的错峰锚点是**可读的**（用户能看见、也能让搭子改）。
3. **默认开启、静默**：用户口径是"内置搭子我们创建好自动进化"，所以是开着的；
   静默是因为"每周自己跑一次"没必要次次弹窗（结果在那个 `[自动化] …` 会话里）。

## 幂等

任务 id 固定为 ``builtin-evolve-<搭子 id>``：播种只补"还没有的那几条"，
用户改过的时间、搭子改过的一切都不会被覆盖回来。
（用户删不掉这几条 —— 它们是 ``origin="builtin"``，见 ``task_store.locked_for_user``；
这里的幂等是给"配置文件被手改 / 老版本升级上来"兜底的。）
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from ..assistants import evolution, locked_builtins
from ..config.schemas import AssistantProfile, ScheduledTaskSpec

#: 任务 id 前缀。带上搭子 id，于是"这条任务属于谁"一眼可见，也让播种天然幂等
BUILTIN_TASK_ID_PREFIX = "builtin-evolve-"

#: 一周的分钟数（也是 ``interval_minutes`` 允许的上限）
WEEK_MINUTES = 7 * 24 * 60

#: 首次执行的时间锚点：安装后的第一个**周日 03:07**
FIRST_RUN_WEEKDAY = 6  # 0=周一 … 6=周日
FIRST_RUN_HOUR = 3
FIRST_RUN_MINUTE = 7

#: 四个搭子之间的错峰间隔（分钟）
STAGGER_MINUTES = 15


def task_id(assistant_id: str) -> str:
    return f"{BUILTIN_TASK_ID_PREFIX}{assistant_id}"


def first_run_at(now: float, offset_minutes: int) -> str:
    """算出"安装后第一个周日 03:07 + 错峰分钟"，返回 ``YYYY-MM-DDTHH:MM``（本机时间）。

    - 今天就是周日、且还没到那个时刻 → 用今天（用户装完当天就能看到它跑一次）；
    - 否则顺延到下一个周日。

    ⚠️ 用**本机时间**拼字符串（与用户在界面上填的格式、以及调度器的解析口径完全一致）：
    图省事用 ``toISOString()`` 那类 UTC 写法，东八区用户会看到"早了 8 小时"的起始时间。
    """
    moment = datetime.fromtimestamp(now)
    target = moment.replace(hour=FIRST_RUN_HOUR, minute=FIRST_RUN_MINUTE, second=0, microsecond=0)
    days_ahead = (FIRST_RUN_WEEKDAY - target.weekday()) % 7
    if days_ahead == 0 and target < moment:
        days_ahead = 7
    # ⚠️ 错峰必须在**最后**加：先加 offset 再 replace(hour/minute) 会把错峰整个抹掉，
    # 四条任务就会全部落在同一分钟（实测踩过），错峰的意义也就没了
    target += timedelta(days=days_ahead, minutes=offset_minutes)
    return target.strftime("%Y-%m-%dT%H:%M")


def builtin_specs(
    assistants: list[AssistantProfile], now: float | None = None
) -> list[ScheduledTaskSpec]:
    """按四个内置搭子生成四条任务（纯函数，便于测试）。

    只认 ``locked_builtins.is_locked()`` 判定出来的那四个 —— 自建 / AI 建的搭子**不预置**，
    它们走"自己问用户要不要建"那条路（见 ``assistants/evolution.py``）。
    错峰顺序按 ``sort_order`` 排：那是搭子在界面上的固定顺序，稳定且可解释。
    """
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
                prompt=evolution.builtin_prompt(name),
                assistant_id=profile.id,
                enabled=True,
                trigger="interval",
                interval_minutes=WEEK_MINUTES,
                start_at=first_run_at(stamp, slot * STAGGER_MINUTES),
                # 来源=预置：用户不能手动改/关/删（见 task_store.locked_for_user）
                origin="builtin",
                silent=True,
            )
        )
    return specs


def ensure_builtin_tasks(
    specs: list[ScheduledTaskSpec],
    assistants: list[AssistantProfile],
    now: float | None = None,
) -> list[ScheduledTaskSpec]:
    """把缺失的预置任务补齐；**没变化就原样返回**（调用方据此决定要不要落盘）。

    只补不删也不改：用户/搭子对这几条的任何调整（时间、内容）都不该被"启动"抹掉。
    """
    existing = {item.id for item in specs}
    missing = [item for item in builtin_specs(assistants, now) if item.id not in existing]
    if not missing:
        return specs
    return [*specs, *missing]

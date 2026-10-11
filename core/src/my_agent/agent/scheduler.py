"""自动化任务：按固定间隔自动跑一次助手。

对应《智能体框架开发文档》9.4 节。

## 和「提醒」的区别

两者都靠同一个事件通道通知，但成本量级完全不同：

- **提醒（reminder）**：到点**提醒人**，只发一条通知，不花钱；
- **自动化任务（本模块）**：到点**干活** —— 真的调用模型、消耗 token、产出一份结果。

所以这里的默认值刻意保守到底：列表为空 + 每一项 `enabled=False`。

## 「上次执行时间」不放配置里

配置里只放**用户能编辑的东西**。把一个每隔几分钟就变的运行状态混进 ``settings.json``，
会导致"改个任务名字触发整份配置重写"这类互相干扰。运行状态因此单独落一份
（``<data_dir>/scheduler_state.json``，见下面两节），配置文件始终是干净的。

## 重启后补跑一次（产品要求反转）

启动时如果发现"错过的那一个时间点"还没跑过，就**补跑一次**，只补最近一次。

这里曾经是**刻意不补跑**（理由：一个关了两天的客户端一打开就把两天里该跑的全跑一遍，
会瞬间烧掉大量 token 而用户完全没预期）。产品约定是"关着的时候错过的那次
要补上"，于是反转成补跑，但用三道闸把代价框住：

1. **只补一次**，不按次数补齐（关一周也只补一次）；
2. **24 小时窗口**（``CATCH_UP_WINDOW_SECONDS``）：错过的时间点距今超过一天就不补，
   直接等下一个周期 —— "关太久"的任务再跑一遍对用户没什么价值，白花钱；
3. **跑过的不重复**：上一次接管的时间点落盘，所以"重启前那一刻已经跑过"的任务不会
   因为重启再跑一次。这是补跑最容易出的错，用户看到的症状是"为什么刚开机又跑一遍"。

``interval`` 型同样算过期（每 30 分钟的任务关了 5 小时：启动补一次，然后重新计时），
但它的"上一次"不落盘就无从判断，所以改用落盘的"上一次接管时刻 + 间隔"推算 ——
于是"刚跑完 10 分钟就重启"不会补跑，而"关了一周"则落在 24 小时窗口之外、不补。

带条件的任务补跑时**只重建基线、不执行**：条件的第一眼永远只建立基线
（见下面"两种可选的该不该跑"），重启后那一眼不能算作"内容变了"。

## 运行状态为什么落盘

条件基线（网页摘要 / 文件 mtime）仍然只存内存：重启后第一次检查只重建基线，
不会把重启当成"内容变了"。

但"上一次接管了哪个时间点"**必须落盘** —— 不落盘就分不清"这个时间点还没跑"和
"跑过了、只是进程重启把记录丢了"，而这两种情况的处理正好相反（前者要补、后者绝不能补）。
落盘的是每个任务的 ``first_seen_at``（第一次被调度器看见的时刻，用来判断"任务比错过的时间点
还新"）与 ``last_run_at``（上一次接管某个时间点的时刻）。

## 三种时间轴 + 两种可选的"该不该跑"

- ``interval``：每 N 分钟（老行为）；
- ``daily``：每天 ``HH:MM``；
- ``weekly``：每周几的 ``HH:MM``。

时间轴之上还能叠一个**条件**（``url_changed`` / ``file_changed``）：到点先看一眼，
变了才真的执行。条件的基线（网页摘要 / 文件修改时间）只存在内存里，
第一次检查**只建立基线不执行** —— 否则"新建监控任务"这个动作本身就会立刻跑一轮。
重启后基线归零，同样只重建基线，不会把重启当成"内容变了"。
"""

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

# tick 的下限。比 10 秒更密的轮询对"分钟级间隔"毫无意义，只是白耗 CPU。
MIN_TICK_SECONDS = 10

# 条件检查里抓网页的超时（秒）。它跑在调度循环里，所以必须有个上限：
# 一个连不上的地址不能把整轮调度卡住，那会让**其它**任务集体迟到。
CONDITION_FETCH_TIMEOUT = 20.0

# 参与"网页变了没"比较的**最大字节数**（第 91 批，L-10）。
#
# ⚠️ 目标地址是**用户填的**，而这条路径由应用在后台定时跑：
# 不设上限的话，一个几 GB 的地址（或被挂着的流式响应）就能把内存吃满，
# 而且用户不在场、看到的只是"客户端越来越卡"。
# 2MB 的依据：判定"内容有没有变"只需要页面前面这部分（正文与主要结构都在这里），
# 再往后的差异（分页脚注、轮播广告位）拿来触发任务反而是噪音。
# 代价是**超过 2MB 的部分参与不了比较** —— 这个代价要如实写进日志（见 `_url_changed`）。
CONDITION_MAX_BYTES = 2 * 1024 * 1024

# 补跑窗口（秒）：错过的时间点距今超过这么久就不再补跑，等下一个周期。
# 24 小时这个值来自产品约定："昨天该跑没跑的我认，关了一周的就算了"。
CATCH_UP_WINDOW_SECONDS = 24 * 3600

# 运行状态的落盘文件名（放在 ``paths.data_dir`` 下，与配置分开）。
STATE_FILENAME = "scheduler_state.json"
# 状态文件的结构版本。以后改字段形状时靠它判断"要不要丢弃重来"。
STATE_VERSION = 1


class TaskScheduler:
    """按间隔触发自动化任务。"""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        self._task: asyncio.Task[None] | None = None
        # 计时游标：调度**内部**用它判断"这个任务下次什么时候检查"。
        # 重启时会被重新播种（见 start()），所以它不等于"上次真的执行过"。
        self._last_run: dict[str, float] = {}
        # 落盘的那一份：上一次**接管**某个时间点的时刻（不管最后有没有真的执行 ——
        # 条件没满足也算接管了，否则重启后会把同一个时间点再算一遍）。
        # 界面上的"上次执行"也用它，所以它在重启后仍然说得出话。
        self._last_exec: dict[str, float] = {}
        # 第一次被调度器看见的时刻。用途有两个：判断"任务比错过的时间点还新"
        # （今天 10 点建的任务，不该补跑今天 9 点那一次）；以及——它为空就表示
        # "这个任务完全没有历史"，那时只播种、不补跑（首次安装 / 刚升级上来）。
        # 所以它也被当作"有没有历史"的开关，见 ``_overdue_point``。
        self._first_seen: dict[str, float] = {}
        # 本次启动要补跑的任务：任务 id → 错过的时间点。
        self._catch_up: dict[str, float] = {}
        self._state_loaded = False
        self._running: set[str] = set()
        # 条件触发用的基线指纹（网页正文摘要 / 文件的 mtime:size）。
        # 刻意不落盘：见模块说明里"重启后只重建基线"那段。
        self._fingerprints: dict[str, str] = {}
        # 上次条件检查失败的原因，按任务记。
        # 用途是**去重**：抓不到网页时每个时间点都会失败一次，每次都推一条通知
        # 等于把用户的通知栏刷爆；只在"错误内容变了"时提示一次。
        self._condition_errors: dict[str, str] = {}
        # 正在执行的自动化任务。
        #
        # **必须持有引用并在 stop() 里取消**：这些任务是 fire-and-forget 起的，
        # 不登记的话关停时它们会继续跑 —— 而 ``shutdown()`` 紧接着就会
        # ``registry.aclose()`` / ``db.close()``，于是它们在已关闭的 LLM 客户端上
        # 发请求、在已关闭的数据库上写会话，报"数据库尚未连接"，那一轮结果直接丢。
        # 不持有引用还会让解释器在退出时报 "Task was destroyed but it is pending"。
        self._running_tasks: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running:
            return

        specs = self._specs()
        if not specs:
            # 没有配置就完全不建任务：省一个常驻协程，也让"到底有没有在跑"
            # 这件事在日志里一眼可辨
            logger.debug("未配置自动化任务，调度器不启动")
            return

        self._load_state()
        now = time.time()

        # 谁该补跑：只算**还没有计时游标**的任务（= 本次进程首次见到它）。
        # 有游标的说明是改配置触发的 ``restart()`` —— 那时绝不能重算，
        # 否则"改一个任务的名字"会变成"所有任务集体补跑一次"。
        self._catch_up = {}
        for spec in specs:
            if spec.id in self._last_run or not spec.enabled:
                continue
            point = self._overdue_point(spec, now)
            if point is not None:
                self._catch_up[spec.id] = point

        # 计时从**现在**开始（补跑的那几个除外：它们的游标落在错过的时间点上，
        # 这样第一轮 tick 立刻接管，且界面的倒计时不会显示成"还有一整个周期"）。
        for spec in specs:
            point = self._catch_up.get(spec.id)
            self._last_run.setdefault(spec.id, now if point is None else point)
            self._first_seen.setdefault(spec.id, now)
        # 立刻落一次：新任务的 ``first_seen_at`` 不写下去，下次启动又会把它当成没见过的，
        # 那样"任务比错过的时间点还新"这条判断就永远失效了
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
        """配置改动后重新起调度（新增/删除/改名/开关任务都会走这里）。

        两件事必须做对：

        1. **保留仍在的任务的计时**。重启后立刻把所有 ``_last_run`` 清零的话，
           用户改一个任务的名字就会让**所有**任务集体跑一遍 —— 那是真花钱的。
           所以只清理"已经不在配置里的"任务；
        2. **新任务从当下播种**（``start()`` 里做）：刚建的任务不该马上开跑，
           用户的预期是"到下一个时间点再说"，并且他多半还要先点一次"立即执行"试水。
        """
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

        # 再收拾**在跑的**自动化任务。顺序有讲究：
        # 先停调度循环（不再起新的），再取消在途的，最后等它们真的结束。
        # 不等的话 `runtime.shutdown()` 会紧接着关掉数据库与 LLM 客户端，
        # 而它们还在用 —— 结果是"数据库尚未连接"，且那一轮结果直接丢失。
        pending, self._running_tasks = list(self._running_tasks), set()
        for item in pending:
            item.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
            logger.debug("已取消 %s 个在跑的自动化任务", len(pending))

    # ------------------------------------------------------------------ #
    # 运行状态的落盘
    # ------------------------------------------------------------------ #
    def _state_path(self) -> Path | None:
        """状态文件放在数据目录里；拿不到路径就退化成"只存内存"。

        测试里的假 runtime 没有 ``paths``，那条路径下补跑自然不生效 ——
        与"没有历史就只播种"是同一条规则，不需要额外分支。
        """
        paths = getattr(self._runtime, "paths", None)
        data_dir = getattr(paths, "data_dir", None)
        if not data_dir:
            return None
        return Path(data_dir) / STATE_FILENAME

    def _load_state(self) -> None:
        """读一次运行状态（每个进程只读一次）。

        整个函数**不允许**抛异常：状态文件坏了顶多让这次启动不补跑，
        绝不能因此让调度器（以及整个应用）起不来。所以坏文件按"没有记录"处理。
        """
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
        except (OSError, ValueError) as exc:  # 坏文件不该拖垮启动，按"没有记录"处理
            logger.warning("自动化任务状态文件读不出来（本次不补跑）%s: %s", path, exc)
            return
        if not isinstance(raw, dict) or raw.get("version") != STATE_VERSION:
            # 版本不认识就整个丢掉：宁可这次不补跑，也不要把别人的字段形状
            # 猜错成"这个时间点跑过了"，那会让任务**该跑的永远不跑**
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
        """把运行状态写回磁盘（只写**当前配置里还有**的任务，文件因此不会无限长）。

        同样不抛异常：写不进去（磁盘满、目录只读）只影响"下次启动能不能补跑"，
        那次补跑的代价远小于"让用户的操作失败"。
        """
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
            # 先写临时文件再替换：中途断电也不会留下半份 JSON，
            # 而半份 JSON 的下场是"下次启动不补跑"（甚至更糟：任何任务都不补）
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning("自动化任务状态文件写不进去 %s: %s", path, exc)

    def _mark_handled(self, spec: ScheduledTaskSpec, now: float) -> None:
        """记下"这个时间点由这一轮接管了"，并立刻落盘。

        条件没满足时**同样**记 —— 与 ``_last_run`` 推进时间的道理一样：
        这一轮已经看过一眼了，重启后再看一遍等于多抓一次网页。
        """
        self._last_exec[spec.id] = now
        self._save_state()

    def _overdue_point(self, spec: ScheduledTaskSpec, now: float) -> float | None:
        """它错过的**那一个**时间点（没错过 / 错过太久 / 已经跑过 → ``None``）。"""
        if spec.id not in self._first_seen:
            # 完全没有历史记录：说不清它错过了什么，只播种。
            # 这一条保住两件事：① 首次安装（还什么都没有）不会一打开就集体跑一轮；
            # ② 刚从旧版本升上来的客户同理 —— 用户要的是"补上关着的时候错过的"，
            # 而不是"升级触发一轮全量执行"。历史从这次启动开始记，之后就正常补跑。
            return None

        if spec.trigger == "interval":
            # 间隔型的"上一次"只能推算：优先用真实的接管时刻，没有就用"第一次看见"
            anchor = self._last_exec.get(spec.id)
            if anchor is None:
                anchor = self._first_seen[spec.id]
            start = self._start_point(spec)
            if start is not None:
                # 起始时间之后的第一个点才是"该跑的时刻"：起始时间还没到时这里推出来的
                # 点必然落在未来（下面 `point > now` 挡掉），也就不会出现"刚建好的任务
                # 被当成错过了而立刻补跑"。
                anchor = max(anchor, start)
            point = anchor + spec.interval_minutes * 60
        else:
            point = self._last_occurrence(spec, now)
            if point is None:
                return None
            last = self._last_exec.get(spec.id)
            if last is not None and last >= point:
                # 这一刻在重启之前就跑过了，不能因为重启再跑一遍
                return None

        if point > now:
            return None  # 还没到点
        if now - point > CATCH_UP_WINDOW_SECONDS:
            return None  # 错过太久：等下一个周期，而不是翻旧账

        first = self._first_seen.get(spec.id)
        if first is not None and first > point:
            return None  # 任务比这个时间点还新（今天 10 点建的，不补今天 9 点那次）
        return point

    def _spawn(
        self,
        spec: ScheduledTaskSpec,
        *,
        resume: RunRecord | None = None,
        catch_up: bool = False,
    ) -> None:
        """起一个自动化任务并**登记**它。

        ``add_done_callback`` 顺带解决了另一个问题：没有强引用的 Task
        可能被 GC 回收，那会让任务在中途无声消失 —— 而且不报错。

        ``resume`` 非空表示"接着上次中断的地方跑"（断点续跑）。
        ``catch_up`` 表示这一轮是**补跑**（启动时发现错过的那次）——
        通知与留痕里必须说清，否则用户会奇怪"我刚打开它怎么自己跑起来了"。
        """
        task = asyncio.create_task(
            self._run_task(spec, resume=resume, catch_up=catch_up),
            name=f"scheduled-{spec.id}",
        )
        self._running_tasks.add(task)
        task.add_done_callback(self._running_tasks.discard)

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    def _specs(self) -> list[ScheduledTaskSpec]:
        return list(self._runtime.config.settings.agent.scheduled_tasks or [])

    def describe(self) -> list[dict[str, Any]]:
        """给界面用的状态快照。"""
        now = time.time()
        items: list[dict[str, Any]] = []
        for spec in self._specs():
            # 用落盘的那一份而不是计时游标：重启后游标被重新播种成"当下"，
            # 拿它当"上次执行"会一律显示成"刚刚"，等于骗用户
            last = self._last_exec.get(spec.id)
            items.append(
                {
                    **spec.model_dump(),
                    # 界面靠它决定"开关/编辑/删除"能不能点（产品约定）。
                    # 只下发"能不能改"，不下发判定依据 —— 判定只在服务端，见
                    # task_store.locked_for_user()。
                    "locked": locked_for_user(spec),
                    "last_run_at": last,
                    "running": spec.id in self._running,
                    # 还有多久到下一个检查点（秒）。对 daily / weekly 是**绝对时刻**
                    # 推算出来的，不是"间隔减去已过时间"。
                    "next_run_in_seconds": self._next_run_in_seconds(spec, now),
                    # 条件基线是否已经建立：界面据此显示"正在监控中 / 下次检查后生效"，
                    # 否则用户会以为"监控了却一直没触发"是坏了
                    "condition_ready": spec.id in self._fingerprints,
                }
            )
        return items

    async def run_now(self, task_id: str) -> bool:
        """立刻跑一次（用户在界面上点"立即执行"）。"""
        spec = next((item for item in self._specs() if item.id == task_id), None)
        if spec is None:
            return False
        if spec.id in self._running:
            # 已经有一轮在跑：直接拒绝而不是排队 —— 排队的语义是"跑完再跑一遍"，
            # 而用户点这个按钮的意图是"现在就看结果"
            return False
        now = time.time()
        self._last_run[spec.id] = now
        # 手动跑过也算"这一刻接管了"：落到盘上，否则用户关掉再打开，
        # 启动补跑会把刚刚手动跑过的那一次再跑一遍
        self._mark_handled(spec, now)
        self._spawn(spec)
        return True

    # ------------------------------------------------------------------ #
    # 调度
    # ------------------------------------------------------------------ #
    async def _loop(self) -> None:
        while True:
            # **先跑一轮再睡**：启动补跑的那几个任务不该再等一个 tick（默认 60 秒）
            # 才开工 —— 用户刚打开客户端，看到的是"通知说补跑，可半天没动静"。
            # 这一轮的代价可以忽略：没到点的任务在 ``_is_due`` 那一步就被挡掉了。
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 一轮调度出错不能让循环死掉
                logger.exception("自动化任务调度出错，下一轮继续")

            tick = max(
                MIN_TICK_SECONDS,
                int(self._runtime.config.settings.agent.scheduler_tick_seconds),
            )
            await asyncio.sleep(tick)

    async def _tick(self) -> None:
        now = time.time()
        # ---- 第一阶段：挑出这一轮到点的任务，并**先把时间轴推进** ---- #
        due: list[tuple[ScheduledTaskSpec, bool]] = []
        for spec in self._specs():
            if not spec.enabled or spec.id in self._running:
                continue
            # 补跑走的是**另一条**判定：它错过的那个时间点常常落在"上次执行之前"，
            # ``_is_due`` 天然看不见它（那正是补跑要解决的问题）
            catching_up = spec.id in self._catch_up
            if not catching_up and not self._is_due(spec, now):
                continue
            # 本次启动的补跑机会只有一次：不管这一轮条件满不满足都清掉，
            # 否则条件没满足时每个 tick 都会再来一遍（抓网页、烧时间）
            self._catch_up.pop(spec.id, None)
            # 先把"上次执行时间"推到当下，再起任务。
            # 顺序不能反：任务体里要 await，等它跑完再更新的话，
            # 下一次 tick 会看到"还没跑过"而再起一个 —— 同一个任务被并发执行。
            #
            # 条件检查失败 / 未满足时**同样**推进时间：间隔语义是"每隔 N 分钟看一眼"，
            # 不推进的话每个 tick（默认 60 秒）都会再抓一次网页。
            self._last_run[spec.id] = now
            self._mark_handled(spec, now)
            due.append((spec, catching_up))

        if not due:
            return

        # ---- 第二阶段：条件检查**并发**跑 ---- #
        #
        # ⚠️ 第 91 批（L-10）：原来是"挑一个、await 一个"。而 `_url_changed` 要抓网页
        # （单次超时 20 秒），所以**排在前面的任务只要连不上，同一轮里排在后面的任务
        # 就得陪着等** —— 用户看到的现象是"任务集体迟到"，而且每个 tick 都可能再来一遍。
        # 改成 gather 之后，这一轮的等待从 Σ(各条件耗时) 降到 max(其中最慢的那个)。
        #
        # 代价是同一瞬间会有几个出站请求（任务量本身很小：用户自建 + 4 条预置），
        # 而且每个任务各自 `async_client`、各自超时，互不影响。
        #
        # ⚠️ `_condition_met` 自己已经吞掉已知异常并记进 `_condition_errors`，
        # `return_exceptions=True` 只是兜住意外 —— 一个条件炸了不能带塌整轮调度。
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

    # ------------------------------------------------------------------ #
    # 时间轴
    # ------------------------------------------------------------------ #
    def _start_point(self, spec: ScheduledTaskSpec) -> float | None:
        """``start_at`` 的时间戳（本机时区）；空值 / 格式坏了 → ``None``。

        只有 ``interval`` 用它（见 ``schemas.ScheduledTaskSpec.start_at``）。
        格式坏掉时按"没有起始时间"处理：配置是用户手也改得动的文件，
        为了一行写坏的时间让整个任务彻底不跑，比"忽略它、照常按间隔跑"更糟。
        """
        raw = (spec.start_at or "").strip()
        if not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%dT%H:%M").timestamp()
        except ValueError:
            logger.warning("自动化任务 %s 的起始时间不合法（%s），按未设置处理", spec.id, raw)
            return None

    def _is_due(self, spec: ScheduledTaskSpec, now: float) -> bool:
        """按触发类型判断"这个检查点到了没有"。"""
        last = self._last_run.get(spec.id)

        if spec.trigger == "interval":
            start = self._start_point(spec)
            if start is not None and now < start:
                return False  # 起始时间还没到：一次都不该跑
            if start is not None and (last is None or last < start):
                # 起始时间已到、而"起始时间之后"还没跑过 —— 这一刻就是第一次执行。
                # ⚠️ 不能落到下面那条 `now - last >= interval`：启动时游标被播种成"当下"，
                # 若起始时间比它晚不到一个间隔，第一次执行会被推迟整整一个周期，
                # 用户看到的就是"起始时间过了却一直没动静"。
                return True
            return last is None or now - last >= spec.interval_minutes * 60

        occurrence = self._last_occurrence(spec, now)
        # 到点 = 最近一个时间点已经过去，且上次执行发生在它**之前**。
        # ⚠️ "启动时错过的那一次"不归这里管：补跑走 ``_catch_up``（见 ``_tick``），
        # 因为它的时间点常常早于 ``_last_run``，这条判断天然看不见它。
        return occurrence is not None and (last is None or last < occurrence)

    def _last_occurrence(self, spec: ScheduledTaskSpec, now: float) -> float | None:
        """最近一个**已经过去**的 daily / weekly 时间点（时间戳）。"""
        hour, minute = (int(part) for part in spec.at_time.split(":"))
        current = datetime.fromtimestamp(now)
        candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if spec.trigger == "daily":
            if candidate > current:
                candidate -= timedelta(days=1)
            return candidate.timestamp()

        # weekly：从"今天这个时刻"往回找到最近的那个指定星期几
        days_back = (current.weekday() - spec.weekday) % 7
        candidate -= timedelta(days=days_back)
        if candidate > current:
            candidate -= timedelta(days=7)
        return candidate.timestamp()

    def _next_run_in_seconds(self, spec: ScheduledTaskSpec, now: float) -> float | None:
        """到下一个检查点还有多久（秒）。界面用它显示倒计时。"""
        if spec.trigger == "interval":
            start = self._start_point(spec)
            if start is not None and now < start:
                return max(0.0, start - now)  # 起始时间还没到，倒计时指着它
            last = self._last_run.get(spec.id)
            if last is None:
                return None
            if start is not None and last < start:
                return 0.0  # 起始时间已到、这一轮马上就跑
            return max(0.0, spec.interval_minutes * 60 - (now - last))

        occurrence = self._last_occurrence(spec, now)
        if occurrence is None:
            return None
        step = timedelta(days=1 if spec.trigger == "daily" else 7)
        upcoming = occurrence
        while upcoming <= now:
            upcoming = (datetime.fromtimestamp(upcoming) + step).timestamp()
        # 若下一个时间点已经被"上次执行"覆盖过，就再往后一个周期 ——
        # 否则界面会显示"1 秒后执行"，而实际上今天那一轮已经跑完了
        last = self._last_run.get(spec.id)
        if last is not None and last >= upcoming:
            upcoming = (datetime.fromtimestamp(upcoming) + step).timestamp()
        return max(0.0, upcoming - now)

    # ------------------------------------------------------------------ #
    # 条件（"该不该真的跑"）
    # ------------------------------------------------------------------ #
    async def _condition_met(self, spec: ScheduledTaskSpec) -> bool:
        """条件满足才真执行；``none`` 直接放行。

        异常一律转成"这次不跑"：条件检查本身失败（地址写错、文件被删）
        不该让任务报成"执行失败"，但也必须让用户知道 —— 见 ``_note_condition_error``。
        """
        if spec.condition == "none":
            return True
        try:
            if spec.condition == "url_changed":
                return await self._url_changed(spec)
            if spec.condition == "file_changed":
                return self._file_changed(spec)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 条件失败不等于任务失败
            self._note_condition_error(spec, str(exc))
            return False
        return True

    async def _url_changed(self, spec: ScheduledTaskSpec) -> bool:
        """网页内容变了才算满足条件。

        ⚠️ 地址要过 ``validate_endpoint``：这条路径是**应用自己**去发请求，
        不能因为"用户配的"就跳过校验 —— 那等于给内网/元数据地址开了一个
        由模型（能自建任务）驱动的探测口。
        """
        from ..security.urls import validate_endpoint
        from ..utils.http import async_client

        target = spec.condition_target.strip()
        try:
            validate_endpoint(target, field="监控的网页地址")
        except ConfigError as exc:
            self._note_condition_error(spec, exc.message)
            return False

        # ⚠️ **边读边算、读到上限就停**（第 91 批，L-10 的第二半）：
        # 原来是 `client.get(target)` 把**整个响应体**读进内存再哈希 ——
        # 目标地址是用户填的，一个几 GB 的文件/流式页面就能把内存吃满，
        # 而这条路径是**应用自己在后台定时跑**的，出事时用户根本不在场。
        # 现在只取前 `CONDITION_MAX_BYTES` 做指纹：判定"变没变"够用，
        # 内存上限确定。超出的部分不参与比较（见常量处的说明）。
        # ⚠️ 多收 **1 个字节**再判"有没有被截断"：恰好读满上限时，"再没有内容了"
        # 与"后面还有内容"从字节数上分不开 —— 直接标成"已截断"会误导按日志排查的人
        #（日志说截断了，其实一个字都没丢）。多读一字节就能把两者分开，
        # 而参与指纹的仍然**严格是前 `CONDITION_MAX_BYTES` 字节**。
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
        # 截断与否**要如实说出来**：只看日志的人需要知道"这次比较只覆盖了前 2MB"，
        # 否则"改了但没检测到"会被当成抓取失败去查。
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
        """文件有更新（修改时间或大小变了）才算满足条件。

        只看元数据、**不读内容**：内容既没必要读（mtime 变了就是被写过），
        读了反而多一份"把用户文件带进日志/内存"的风险。
        """
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
        """条件检查失败：记日志，并且**只在原因变化时**推一次通知。

        不去重的话，一个填错的地址会按每个检查点刷一条通知 —— 用户最后
        会习惯性忽略所有通知，那比不提示更糟。
        """
        logger.warning("自动化任务 %s 的条件检查失败：%s", spec.id, reason)
        if self._condition_errors.get(spec.id) == reason:
            return
        self._condition_errors[spec.id] = reason
        # 静默任务不推通知（审计照旧写）。去重表在上面已经更新过了 ——
        # 静默的是"弹窗"，不是"记住这件事已经报过"
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
        # 补跑这件事必须说出口：用户刚打开客户端就冒出一条"任务已完成"，
        # 没有"这是补上次错过的那一轮"这句话，看起来就像任务自己乱跑
        prefix = "（补跑：客户端关闭期间错过的那一次）" if catch_up else ""
        session_id = ""
        try:
            session_id = await self._execute(spec, resume=resume)
            # 静默任务不推通知（例：四条「全员进化」——每周一次、自己跑完就行，
            # 结果在那个 [自动化] 会话里；用户要看自己进去看）。
            # ⚠️ 审计留痕在下面对谁都照写：静默的是"弹窗"，不是"记录"。
            if not spec.silent:
                self._runtime.events.publish(
                    "scheduled_task_done",
                    task_id=spec.id,
                    name=spec.name,
                    # ``session_id`` 是界面上那个「查看结果」按钮的唯一依据：
                    # 没有它，用户只能看到"结果在新会话里"却无处可去
                    session_id=session_id,
                    message=f"自动化任务「{spec.name}」已完成{prefix}，结果在新会话里。",
                )
            # 留痕：无人值守时发生的执行必须能事后查（产品要求"哪个搭子在什么时候
            # 做了什么，出了问题能查"）—— 这类动作出问题时**没有人在旁边看着**
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
        except Exception as exc:  # noqa: BLE001 - 单个任务失败不影响其它任务
            logger.exception("自动化任务 %s 执行失败", spec.id)
            # 失败对静默任务也不弹窗：四条「全员进化」每周自己跑，失败一次没必要打扰 ——
            # 审计里写着，用户在自动化任务页也能看到"上次执行"的时间
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
        """接着上次中断的位置跑，返回是否真的起了任务。

        只接 ``kind="task"``：群讨论由它自己的路由处理 —— 讨论是**流式**的，
        没法在后台悄悄续，必须由界面重新订阅那条流（见 ``routes/runs.py``）。
        """
        spec = next((item for item in self._specs() if item.id == run.ref_id), None)
        if spec is None:
            logger.warning("续跑失败：任务已不存在 id=%s", run.ref_id)
            return False
        if run.ref_id in self._running:
            # 正在跑的时候不能再并发起一个（与 run_now 是同一道闸）
            logger.info("续跑忽略：任务正在执行 id=%s", run.ref_id)
            return False
        self._spawn(spec, resume=run)
        return True

    def _resolve_runner(self, runtime: Any, spec: ScheduledTaskSpec) -> Any:
        """决定这次跑出来的会话挂在**哪个搭子**下面。

        为什么必须兜底：左侧会话列表是**按当前搭子过滤**的
        （`desktop/src/components/SessionList.tsx`），一个 ``assistant_id`` 为空串的
        会话在任何搭子被选中时都匹配不上 —— 用户看到的是"通知说结果在新会话里，
        可我翻遍列表都找不到"，而这恰恰是最容易让人以为"功能坏了"的那类现象。

        顺序：任务指定的搭子 → 默认搭子 → 第一个搭子 → 没有搭子时保持为空
        （此时列表根本不过滤，为空反而照样可见）。
        """
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
        """在一个**新会话**里跑一次，返回会话 id。

        每次都开新会话，而不是复用上一次的：自动化任务通常彼此无关
        （今天的日报和昨天的日报没有上下文关系），复用一个会话会让上下文
        无限增长，最后每轮都在为历史付费。
        """
        from ..observability.tracer import Tracer
        from ..skill.base import SkillContext
        from .context import ContextPolicy
        from .engine import Agent, AgentConfig

        runtime = self._runtime
        settings = runtime.config.settings

        # 会话标题前缀用产品名（"自动化任务"），用户才能在会话列表里一眼认出
        # 这条是自动跑出来的，而不是他自己开的对话
        if resume is not None:
            # 续跑：**接着原来那个会话**。模型因此看得到上一次已经做到哪里 ——
            # 这正是"别一次失败全白干"的关键；换一个新会话等于从零再来一遍。
            session = await runtime.sessions.get_or_create(resume.session_id)
            run_id = resume.id
        else:
            session = await runtime.sessions.create(title=f"[自动化] {spec.name}")
            # 落一条"未完成运行"：跑挂了也要留下"接着哪个会话、做到第几步"（断点续跑）。
            # 会话 id 在这里就有了，直接带上；正常跑完会把这行删掉。
            run_id = await runtime.runs.start(kind="task", ref_id=spec.id, session_id=session.id)
        # 会话必须挂在某个搭子下面，否则用户在列表里**永远看不到它**
        # （列表按当前搭子过滤，assistant_id 为空的会话谁都匹配不上）
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
            # 无人值守场景**不注入确认通道**：SkillContext 在无通道时默认拒绝，
            # 这正是我们要的 —— 后台任务不该弹出需要人点的对话框，
            # 更不该因为没人点就默认执行成功
            audit=runtime.audit.record,
            session_id=session.id,
            assistant_id=session.assistant_id,
            workspace=runtime.workspace,
            path_policy=runtime.path_policy,
            extra=runtime.skill_services_for(session.assistant_id),
            # 定时任务**一律自动批准**：产品要求"不管是使用的什么技能和工具，
            # 都默认为自动批准"，所以这里不看搭子策略、也不看全局策略，直接写死。
            #
            # 这里曾经传 `lambda: runtime.assistant_confirm_mode(...)`（与单聊/群聊
            # 同一套惰性读取，想让搭子的策略也管住后台任务）。按产品要求整体反转：
            # 后台任务不再受任何权限策略约束 —— 某个搭子即使设成「一律拒绝」，
            # 它名下的定时任务也照跑。
            confirm_mode="auto_approve",
            # 高危（admin）级也一起放开。非放开不可：后台没有确认通道，
            # 不放开就只能"拒绝执行"，而用户要的是"不管什么技能都跑"。
            # ⚠️ 代价是真实存在的：无人守看时删文件、跑命令这类操作会真的执行。
            # 走 ctx 而不是守卫上的开关 —— guard 是全局共享的，把那里打开会连
            # 前台的 admin 级一起放开（见 PermissionGuard.allow_admin）。
            allow_admin=True,
        )
        agent = Agent(
            llm=llm,
            # 后台任务同样遵循"压缩 / 规划 / 自检可指定模型"的设置
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
                # 提示词只由搭子的人格文档提供（"自定义 + 内置兜底"那条链已退役，
                # 见 agent/engine.py 的 _system_prompt）
                persona=lambda: persona_with_instructions(  # type: ignore[arg-type,return-value]
                    runtime, session.assistant_id, session.enabled_skills
                ),
                # 与单聊同一口径：展开成"内置 ∪ 自己的专属 ∪ 勾选的通用/我的"
                # （见 skill/groups.py）
                enabled_skills=runtime.skills.allowed_names(
                    assistant_id=session.assistant_id,
                    enabled_skills=session.enabled_skills,
                ),
                # 定时任务和单聊同口径：专属技能按会话所属搭子过滤
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

        # 进度：只统计**动作**（每次工具执行算一步），不按 token/字数记 ——
        # "做到哪一步了"才是续跑时要告诉模型的东西，而它不需要知道写了多少字。
        # 续跑时把"上次做到哪"讲清楚：不讲的话模型会重头再来一遍（白花钱，还可能
        # 把已经改好的东西又改一次）。
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
        # 用量表里的"轮数"取**引擎给的** iterations（与单聊同一口径，见 chat.py 的 run_stats）。
        # ⚠️ 不要拿 `step` 充当它：`step` 数的是"工具执行了几次"，而引擎的 iterations 是
        # "模型↔工具往返了几轮"（同一轮里调多个工具只算一轮），两个数**不相等**。
        # 用量页那一列两种口径混着填，用户跨来源对比时就会觉得对不上。
        iterations = 0
        try:
            async for event in agent.run_stream(prompt):
                # 后台任务没有界面可推，事件本身丢弃；但工具结果是"进度"的唯一来源
                if event.type == "done":
                    iterations = int(event.data.get("iterations") or 0)
                if event.type == "tool_result":
                    step += 1
                    last_action = str(
                        event.data.get("display_name") or event.data.get("name") or ""
                    )
                    await runtime.runs.progress(run_id, step=step, last_action=last_action)
        except asyncio.CancelledError:
            # ⚠️ **中断现场必须落盘**：原代码只在整轮跑完才 persist，中途失败什么都不留 ——
            # 用户既看不到那条会话，也无从"接着跑"（会话对象随后就被回收了）。
            # 失败才是最需要留下现场的时候。
            await runtime.persist_session(session)
            await runtime.runs.interrupt(
                run_id,
                status="cancelled",
                step=step,
                last_action=last_action,
                error="任务被中断（应用退出或主动停止）",
            )
            raise
        except Exception as exc:  # noqa: BLE001 - 记完现场再往上抛，通知由 _run_task 负责
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
        # 正常跑完就把进度删掉：没有要续跑的东西了，留着只会让界面上一直挂着「继续」
        await runtime.runs.finish(run_id)
        await runtime.usage.record(
            session_id=session.id,
            model_id=model_id,
            usage=tracer.usage,
            trace_id=tracer.trace_id,
            # ⚠️ 以前这里恒为 0（第 88 批，L-13 修）。现在传的是**引擎给的轮数**，
            # 与单聊同一口径 —— 不要退回 `step`（那是工具执行次数，见上面的说明）。
            iterations=iterations,
        )
        # ⚠️ trace 也要进留存表（第 88 批，M-25）：用量表里的 trace_id 必须能查到东西，
        # 否则界面上给出的 trace_id 对后台任务**永远是 404** —— 而"按 trace 追一次执行"
        # 恰恰是排查静默失败最直接的那条路。受同一有界上限约束（TraceStore 只留 100 条），
        # 不会带来内存增长。
        if settings.trace_enabled:
            runtime.traces.put(tracer.trace_id, tracer.export())
        logger.info("自动化任务 %s 完成，会话 %s", spec.id, session.id)
        return session.id

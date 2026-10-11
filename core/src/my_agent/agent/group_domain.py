"""群聊的**领域逻辑**：发言顺序、上下文写入与渲染、历史恢复、对话 id 解析。

## 为什么单独一层（审计 H-06 / M-22）

它们原先住在 ``server/routes/groups.py``（1500 行）里，于是**领域层只能反向依赖路由层**：
``agent/orchestrator.py`` 想在后台开一场讨论，得写
``from ..server.routes.groups import _ordered_members, _resolve_thread, _restore_history``
—— 路由文件里 `_` 开头的"内部实现"就这样成了事实上的公共 API。
后果有两层：路由一重构，agent 包跟着遭殃；而且这些规则**没法脱离 FastAPI 单测**。

现在它们住在这里：不碰 Request / HTTPException / StreamingResponse，
路由与 agent 两侧都**依赖这里**。

## 与 `group_discussion.py` 的分工

"跑一场讨论"的**执行器**（``build_group_agent`` / ``run_member`` / ``discuss_stream`` /
``emit_summary`` / ``discussion_source``）在 `agent/group_discussion.py` ——
第 100 批把它也搬了出来，于是**领域层不再 import ``server.routes.*``**。

本模块只管**纯规则与上下文**：谁能发起结束投票、投票怎么算通过、控制标记怎么解析、
群聊上下文怎么渲染与恢复。要改"讨论怎么跑"，去 `group_discussion.py`；
要改"规则是什么"，在这里。

## ⚠️ ``runtime._group_history``

它是运行时持有的**群聊上下文内存态**（下划线私有）。这里只是**保真照搬**，没有改访问方式：
更彻底的做法是抽成 ``GroupChatSession`` 之类的领域对象，两边都通过它访问 ——
但那会牵动路由里十余处读写，留作单独一步（同上一段的理由）。

## 命名

搬出来时去掉了前导下划线（理由同 ``mcp/normalize.py``）。
``routes/groups.py`` 侧保留了同名私有别名（`import ... as _xxx`），
所以那个 1500 行文件里的调用点**一行都没动** —— 搬运与改名分开做，回归面最小。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from ..protocol import parse_sse
from ..utils.timefmt import format_stamp, now_iso, parse_iso

if TYPE_CHECKING:  # pragma: no cover
    # ⚠️ 只在类型注解里用到：运行时导入会成环（runtime → orchestrator → 这里），
    # 而 `from __future__ import annotations` 让注解不求值，所以放在 TYPE_CHECKING 下最稳。
    from ..config.schemas import GroupProfile
    from ..server.runtime import AppRuntime

logger = logging.getLogger(__name__)


def ordered_members(runtime: AppRuntime, group: GroupProfile) -> list[Any]:
    """按 ``speaking_order`` 排定发言顺序（缺省用成员原顺序）。"""
    ids = list(group.member_assistant_ids)
    ordered = [item for item in group.speaking_order if item in ids]
    rest = [item for item in ids if item not in ordered]
    members: list[Any] = []
    for member_id in ordered + rest:
        member = runtime.assistants.get(member_id)
        if member is not None:
            members.append(member)
    return members


def say(
    history: list[dict[str, str]],
    *,
    role: str,
    name: str,
    content: str,
    at: str = "",
) -> None:
    """往群聊上下文里追加一条发言，并打上时间。

    ⚠️ **所有写入都必须走这里。** 群聊历史的时间维度全靠 ``at`` 这个字段：漏一处，
    搭子就会把"昨天定的口径"和"刚才说的"当成一回事 —— 而用户明确要求记忆要能分清
    现在和以前（"别把旧的当当下聊"）。时间用 ISO 字符串，与 ``group_events`` 表里
    存的是同一种形状，恢复历史时不用做格式猜测。
    """
    history.append({"role": role, "name": name, "content": content, "at": at or now_iso()})


def history_line(item: dict[str, str]) -> str:
    """把一条历史发言渲染成带时间的行：``[09-26 14:32] 甲：内容``。

    时间缺失（更早版本留下的记录）就只给发言人 —— 不补一个假时间。
    """
    who = "用户" if item.get("role") == "user" else item.get("name", "搭子")
    return f"{format_stamp(parse_iso(item.get('at')))}{who}：{item.get('content', '')}"


def render_history(history: list[dict[str, str]], group_name: str, current_name: str) -> str:
    lines = [f"这是群聊「{group_name}」，你是其中的成员「{current_name}」。前面的对话："]
    lines.extend(history_line(item) for item in history)
    lines.append(f"现在轮到你（{current_name}）发言。请自然地接着聊，不要替别人发言。")
    return "\n".join(lines)


async def restore_history(
    runtime: AppRuntime, group_id: str, thread_id: str
) -> list[dict[str, str]]:
    """从库里把**某条对话**的讨论上下文恢复到内存（重启后仍然能"接着说"）。

    只在内存里还没有这条对话的记录时做一次；重建失败就返回空列表 ——
    最多是"这一轮看不到历史"，不该让讨论起不来。

    ⚠️ 按 `thread_id` 恢复，不是按群：这是"多条对话互不串味"的**关键一步**。
    若这里读了整群的事件，用户新建一条对话后第一句话就会带着别的对话的上文。
    """
    key = (group_id, thread_id)
    existing = runtime._group_history.get(key)
    if existing is not None:
        return existing
    history: list[dict[str, str]] = []
    if runtime.db_ready:
        try:
            events = await runtime.group_event_repo.list_events(group_id, thread_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("群聊历史读取失败 group=%s thread=%s: %s", group_id, thread_id, exc)
            events = []
        for item in events:
            event, data = item.get("event"), item.get("data") or {}
            content = str(data.get("content") or "").strip()
            if not content:
                continue
            # 用**记录里原来那个时刻**，不是"恢复的此刻"：历史的时间维度不能因为
            # 重启一次就全变成今天
            at = str(item.get("created_at") or "")
            if event == "topic":
                say(history, role="user", name="用户", content=content, at=at)
            elif event in ("message", "summary"):
                say(
                    history,
                    role="assistant",
                    name=str(data.get("name") or ""),
                    content=content,
                    at=at,
                )
    runtime._group_history[key] = history
    return history


async def persisting_stream(
    runtime: AppRuntime,
    group_id: str,
    thread_id: str,
    source: AsyncIterator[str],
    *,
    background: bool = False,
) -> AsyncIterator[str]:
    """把讨论流原样转发，同时把每条事件落库（``delta`` 除外），并记录**进度**。

    ``thread_id`` 决定这批事件归到哪条对话（一个群可以有多条）。

    落库失败**绝不能**影响讨论本身：历史记录是锦上添花，正在进行的对话才是
    用户当下要的东西，为一条写库失败中断整场讨论是明显不划算的。

    进度也会落盘（``runs`` 表），这样讨论中途有搭子挂了、或用户点了「停止」，
    下次能**接着这场讨论继续**（用户要求："别一次失败全白干"）。

    ``background=True``：后台讨论**没有 HTTP 订阅者**，所以额外把每条事件经
    ``/v1/events`` 广播一次 —— 只读观察窗就是靠它实时看到讨论的。
    """
    run_id = await runtime.runs.start(
        kind="group", ref_id=group_id, session_id=f"group:{group_id}"
    )
    step = 0
    last_action = ""
    # 默认结局是"没看到 done 就结束了"：客户端断开/被取消都走这条路，
    # 那正是"讨论没完"—— 也就是要留成待续跑的那种情况
    outcome = "cancelled"
    error = ""
    try:
        async for chunk in source:
            parsed = parse_sse(chunk)
            if parsed is not None:
                name, data = parsed
                if name in ("message", "summary"):
                    step += 1
                    last_action = f"{data.get('name') or '搭子'} 发言"
                    await runtime.runs.progress(run_id, step=step, last_action=last_action)
                elif name == "done":
                    outcome = "done"
                if name != "delta" and runtime.db_ready:
                    try:
                        await runtime.group_event_repo.append(group_id, thread_id, name, data)
                    except Exception as exc:  # noqa: BLE001 - 见上面的说明
                        logger.warning("群聊事件落库失败 group=%s: %s", group_id, exc)
                if background:
                    # 后台讨论没有 HTTP 订阅者：经全局事件流广播一次，**只读观察窗**
                    # 就是靠这条常驻长连接实时看到讨论的（见 agent/orchestrator.py）。
                    #
                    # ⚠️ 广播里**必须带 `thread_id`**：一个群可以有多条对话，前端靠它
                    # 判断这批发言该画到哪条上。少了它，前端只能按群匹配 ——
                    # 用户切到另一条对话时，后台这场讨论的字会打进他正在看的那条里。
                    runtime.events.publish(
                        "group_event",
                        group_id=group_id,
                        thread_id=thread_id,
                        event=name,
                        data=data,
                    )
            yield chunk
    except Exception as exc:  # noqa: BLE001 - 记完"失败"再往上抛
        outcome = "failed"
        error = str(exc)[:500]
        raise
    finally:
        # 正常跑完 → 删掉进度（没东西要续跑了）；否则留成待续跑
        if outcome == "done":
            await runtime.runs.finish(run_id)
        else:
            await runtime.runs.interrupt(
                run_id,
                status="failed" if outcome == "failed" else "cancelled",
                step=step,
                last_action=last_action,
                error=error or "讨论还没结束就中断了",
            )
        # 留痕：一场讨论的起止要能事后查（产品要求"哪个搭子在什么时候做了什么"）。
        # 讨论是**多个搭子轮流干活**，出问题时最需要的就是"最后是谁、做到哪一步"。
        await runtime.audit.op(
            kind="group",
            action="discuss_done" if outcome == "done" else "discuss_interrupted",
            target=group_id,
            session_id=f"group:{group_id}",
            status="ok" if outcome == "done" else "error",
            detail=(
                f"讨论{'结束' if outcome == 'done' else '中断'}：共 {step} 条发言"
                + (f"，最后是 {last_action}" if last_action else "")
                + (f"；{error}" if error else "")
            )[:400],
        )


async def resolve_thread(runtime: AppRuntime, group_id: str, thread_id: str) -> str:
    """把"用户/客户端给的对话 id"落成一个**真实存在**的对话 id。

    - 给了且存在 → 就用它；
    - 没给（空串）→ 用该群**最近有动静**的那条；一条都没有 → 现建一条。

    为什么要这个兜底：老客户端不会传 `thread_id`，而"第一次进群就发消息"是
    完全正常的路径 —— 那时一条对话都还没有。与其让前端保证"先建对话再发消息"，
    不如后端把这件事做掉：漏传一次就是"消息不在任何对话里"，那种记录在界面上
    永远看不到却真实占着数据库。
    """
    wanted = thread_id.strip()
    if wanted:
        existing = await runtime.group_thread_repo.get(group_id, wanted)
        if existing is not None:
            return wanted
        # 传了一个不存在（或属于别的群）的 id：不报错，退回最近一条。
        # 报错会让"另一个窗口刚把这条对话删了"变成一个用户无法处理的失败。
        logger.info("群 %s 收到未知对话 id %s，回退到最近一条", group_id, wanted)

    threads = await runtime.group_thread_repo.list_threads(group_id)
    if threads:
        return str(threads[0]["id"])
    created = await runtime.group_thread_repo.create(group_id)
    return str(created["id"])


MAX_ROUNDS = 60
def confirm_owner(group_id: str) -> str:
    """群聊挂起确认的归属标记。

    用途只有一个但很关键：讨论被用户叫停（或整场讨论结束）时，按这个 owner
    把该群挂着的确认一起**按拒绝收掉**。没有它，那些确认要等满超时
    （默认 120 秒）才会消失，期间用户再做同一个操作会撞上"已有一项待确认"。
    """
    return f"group:{group_id}"
def parse_control(text: str) -> tuple[str, str, str]:
    """解析发言末尾的控制标记，返回 ``(干净文本, 类型, 理由)``。

    类型：``''`` / ``'end_vote'`` / ``'agree'`` / ``'disagree'``。
    """
    clean = (text or "").strip()
    if "[END_VOTE]" in clean:
        index = clean.index("[END_VOTE]")
        return clean[:index].strip(), "end_vote", clean[:index].strip()[-120:]
    if "[AGREE]" in clean:
        return clean.replace("[AGREE]", "").strip(), "agree", ""
    if "[DISAGREE]" in clean:
        return clean.replace("[DISAGREE]", "").strip(), "disagree", ""
    if "[PASS]" in clean:
        return clean.replace("[PASS]", "").strip(), "pass", ""
    if "[REJECT]" in clean:
        index = clean.index("[REJECT]")
        # 标记**之后**那段就是"具体缺什么、怎么改" —— 总管下一轮要照着它重新安排，
        # 所以它必须跟着事件传出去（截到 200 字，够写清问题又不至于刷屏）
        return clean[:index].strip(), "reject", clean[index + len("[REJECT]") :].strip()[:200]
    return clean, "", ""
def skill_owners(members: list[Any], skill: str) -> list[str]:
    """这个技能**本来该是谁的活**（按各自的白名单判断）。

    只为了把越权说得更具体：「XX 调用了 write_file，这本来是 A 的活」比一句
    "越权了"有用得多 —— 用户才知道该让谁去做，也才知道该给谁补白名单。
    """
    return [item.name for item in members if skill in set(item.enabled_skills or [])]


# --------------------------------------------------------------------------- #
# 群聊角色：总管 / 执行 / 审核
# --------------------------------------------------------------------------- #
# 产品要求是给群聊一个**团队结构**：总管做策划与分工 → 各专职执行 →
# 审核员验收，**不达标打回总管**重新安排。
#
# 角色的权威来源是搭子档案上的 ``group_role``；没写的按**发言位次**兜底：
# 首位当总管、倒数第二当优化顾问、末位当审核员、其余当执行者。兜底让"用户手建的群"
# 与"加这个字段之前建的老群"也能按分工跑，而不是退化成一群没有分工的人轮流说话。
ROLE_LABELS: dict[str, str] = {
    "coordinator": "协调者（总管）",
    "worker": "执行者",
    "advisor": "优化顾问",
    "reviewer": "审核员",
}
def effective_roles(members: list[Any]) -> dict[str, str]:
    """这场讨论里每个成员承担的角色（id → role）。"""
    roles: dict[str, str] = {}
    for index, member in enumerate(members):
        assigned = getattr(member, "group_role", "") or ""
        if assigned in ROLE_LABELS:
            roles[member.id] = assigned
        elif index == 0:
            roles[member.id] = "coordinator"
        elif index == len(members) - 1:
            roles[member.id] = "reviewer"
        elif index == len(members) - 2:
            roles[member.id] = "advisor"
        else:
            roles[member.id] = "worker"
    return roles
def can_end_vote(members: list[Any], member: Any) -> bool:
    """结束投票的发起权：**会话发起者（首位发言者）或末序发言者**（用户要求）。

    原先任何人都能发起，于是"某个人觉得差不多了"就能把所有人的讨论掐断，
    而用户要的是"由主持的人决定收尾"。
    """
    if not members:
        return False
    return member.id in {members[0].id, members[-1].id}
def role_rules(role: str, *, can_end_vote: bool) -> str:
    """该角色的职责说明（拼进群聊 system）。

    ⚠️ 越权（"不是自己的活却干了"）**只在提示层面拦**：不动工具权限
    （的选择）。所以这里要写得足够硬 —— 明确"只做自己范围内的事、
    别人的活要 @ 他"，并告诉它会**被标出来**（那份可见性见 `run_member` 的越界检测）。
    """
    common = (
        "- 只做**你自己职责范围内**的事：别人的活（写代码、做表、审核…）请用 @名字 交给"
        "对应成员，不要自己抢着做完 —— 越界调用别人的工具会在群里被标出来。\n"
    )
    if role == "coordinator":
        body = (
            "你在这场讨论里是**协调者（总管）**：\n"
            "- 开场先把任务拆成几条具体的事，明确每条交给谁（用 @名字），再往下走；\n"
            "- 有人把活退回来（审核不通过）时，你要照着反馈**重新分配**并说明改了什么；\n"
            "- 最后把大家的结论收敛成一份交付（结论 + 关键理由）。\n"
        )
    elif role == "reviewer":
        body = (
            "你在这场讨论里是**审核员**：\n"
            "- 别人给出交付后，你按能不能直接用的标准验收（完整性、有没有明显错漏）；\n"
            "- 达标：在发言最后单独一行写 [PASS]；\n"
            "- 不达标：写 [REJECT]，并在同一段里说清**具体缺什么、该怎么改**"
            "（总管会照着它重新安排）；\n"
            "- 优化顾问提出建议时**把关**：建议确实必要（不是可有可无的小改动）就批准并"
            " [REJECT] 打回完善；建议可有可无就不批准、直接按交付物本身 [PASS]/[REJECT]；\n"
            "- 不要自己动手改交付物 —— 指出问题、交回给总管。\n"
        )
    elif role == "advisor":
        body = (
            "你在这场讨论里是**优化顾问**：\n"
            "- 在交付出来后，审视它有没有**必要**的改进空间（明显更优的方案、遗漏的要点）；\n"
            "- 只提必要的、有分量的建议，可有可无的小改动一律不提；\n"
            "- 建议说清「改什么、为什么值得改、大概怎么改」，交给审核员把关；\n"
            "- 不替执行者动手改。\n"
        )
    else:
        body = (
            "你在这场讨论里是**执行者**：\n"
            "- 只做分配给你的那部分，做完把结果直接说出来；\n"
            "- 需要别人配合时 @ 他，不要越俎代庖。\n"
        )
    vote = (
        "- 你可以发起结束投票：认为讨论充分时，在发言最后单独一行写 [END_VOTE]。\n"
        if can_end_vote
        else "- 结束投票只能由**发起者或末序发言者**发起；你认为该收尾时 @ 他们提出即可。\n"
    )
    return body + common + vote
def vote_passed(votes: dict[str, bool]) -> bool:
    """投票是否通过：同意票占已投票者的多数。"""
    if not votes:
        return False
    agree = sum(1 for value in votes.values() if value)
    return agree > len(votes) / 2

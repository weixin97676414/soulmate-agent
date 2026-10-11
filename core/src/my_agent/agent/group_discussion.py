"""群聊**讨论执行器**：把"一场讨论"真正跑起来（审计 H-06 的最后一刀）。

## 为什么单独一层

这一块原先住在 `server/routes/groups.py`（1359 行）里，于是
`agent/orchestrator.py`（后台讨论的发起方）只能写：

    from ..server.routes.groups import _discussion_source

—— **领域层 import 路由层的私有函数**，而且是延迟 import（藏在函数体里）。
它一直拖着没搬，是因为这块**大**：`build_group_agent`（成员装配 + 技能上下文 +
确认通道）、`run_member`（一次发言）、`discuss_stream`（多轮 + 投票编排）、
`emit_summary`（发起者总结）、`discussion_source`（流 + 收尾清理），合计约 570 行。

## 边界

- **在这里**：讨论怎么跑 —— 谁先说、什么时候进投票、总结谁来写、收尾时怎么把
  挂起的确认收掉。
- **不在这里**：HTTP 参数 / `HTTPException` / `StreamingResponse`（仍留路由层）；
  群聊的**纯规则**（角色、投票判定、控制标记解析）在 `agent/group_domain.py`。

## ⚠️ 搬运纪律

**逐字搬运 + 只去下划线**（`_build_group_agent` → `build_group_agent`），
没有动任何一行逻辑；`routes/groups.py` 侧保留同名私有别名，
所以那边十几个调用点**一行都没改** —— 搬运与改名分开做，回归时能一眼看出是哪一步。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from ..protocol import format_sse
from ..security.confirm import ConfirmRequest
from ..security.interaction import InteractionRequest
from ..skill.custom import persona_with_instructions
from .group_domain import (
    MAX_ROUNDS,
    ROLE_LABELS,
    can_end_vote,
    confirm_owner,
    effective_roles,
    history_line,
    parse_control,
    role_rules,
    say,
    skill_owners,
    vote_passed,
)

if TYPE_CHECKING:  # pragma: no cover
    # ⚠️ 只为类型注解：运行时导入会成环（runtime → orchestrator → 这里）
    from ..config.schemas import GroupProfile
    from ..server.runtime import AppRuntime

logger = logging.getLogger(__name__)

#: 一帧 SSE 的构造器（帧格式的唯一实现在 `protocol.py`；这里保留短名，与搬运前一致）
_sse = format_sse


def build_group_agent(
    runtime: AppRuntime,
    group: GroupProfile,
    member: Any,
    history: list[Any],
    *,
    background: bool = False,
    role: str = "",
    can_end_vote: bool = False,
) -> Any:
    """为群聊里的一个搭子构造 Agent（带技能/MCP，人格与普通对话一致）。

    ``background=True``：这场讨论跑在**后台**（AI 在单聊里自己发起的，见
    ``agent/orchestrator.py``）。后台无人值守、没有确认通道，所以按定时任务
    那套口径给这个成员的 ctx 写死 ``auto_approve`` 并**按次**放开 admin 级。
    前台的群讨论一个字节都不变 —— 它有确认通道，用户能点「允许」。
    """
    from ..memory.short_term import MemoryManager
    from ..skill.base import SkillContext
    from .engine import Agent, AgentConfig

    settings = runtime.config.settings
    model_id = member.model_id or runtime.config.models.default_model
    llm = runtime.registry.get(model_id or None)

    names = "、".join(
        item.name
        for item in runtime.assistants.assistants
        if item.id in group.member_assistant_ids
    )
    persona = persona_with_instructions(runtime, member.id, list(member.enabled_skills) or None)
    role_text = ROLE_LABELS.get(role, "成员") if role else "成员"
    rules = (
        "\n\n## 你正在参加一个多搭子群聊\n"
        f"群名：「{group.name}」；成员：{names}。\n"
        f"你在这个群里的角色：**{role_text}**。\n"
        "规则：\n"
        "- 用户抛出话题后，大家**轮流发言**讨论，目标是聊到意见统一并给出结论。\n"
        "- 每次发言简短（1~3 句），像群聊一样自然，不要长篇大论。\n"
        "- 可以用 @名字 请某位成员补充发言。\n"
        "- 别人发起结束投票后，你在发言**最后**写 [AGREE] 或 [DISAGREE]（同意/不同意结束）。\n"
        "- 投票通过后，由**发起投票的人**做最终总结交付给用户。\n"
        "- 你可以使用自己的工具（技能、MCP）来核实或补充信息。\n"
        + role_rules(role, can_end_vote=can_end_vote)
    )
    # 群聊的 system = 群聊规则 + 该搭子的人格文档。「自定义提示词 / 内置兜底」
    # 那一段已整体退役（见 agent/engine.py 的 _system_prompt），所以这里不再有 base。
    system = rules.lstrip("\n")
    if persona:
        system = f"{system}\n\n{persona}"

    memory = MemoryManager()
    if history:
        # 每条历史发言都带时间：搭子们讨论可能跨很久，"谁刚才说的"与"谁昨天说的"
        # 对判断当前口径完全不同（产品要求：记忆要有时间维度）
        lines = [history_line(item) for item in history]
        memory.add_user("以下是本群到目前为止的对话记录：\n\n" + "\n".join(lines))

    # ---- 确认通道 ------------------------------------------------------ #
    #
    # 命中 confirm 级技能时，把请求推给常驻的事件流并挂起等用户点选
    # （模块说明里解释了为什么不走本群的 SSE 流）。
    #
    # 确认请求里带上"是谁、在哪个群"，弹窗上要显示来源 —— 否则用户看到
    # 一个凭空出现的确认框，第一反应是"这是什么？我点的是群聊啊"。
    async def emit_confirm(confirm: ConfirmRequest) -> None:
        runtime.events.publish(
            "permission_request",
            group_id=group.id,
            group_name=group.name,
            assistant_id=member.id,
            assistant_name=member.name,
            **confirm.to_dict(),
        )

    async def confirm_callback(confirm: ConfirmRequest) -> bool:
        # 没有任何客户端在监听事件流 → 这个确认**永远不可能被回答**。
        # 直接按拒绝返回，而不是白等一整个确认超时（默认 120 秒）——
        # 那 120 秒里用户只看到一个卡住的群。
        if runtime.events.subscriber_count == 0:
            logger.warning(
                "群聊确认无人可送达（没有客户端在监听事件流），按拒绝处理 group=%s skill=%s",
                group.id,
                confirm.skill_name,
            )
            return False
        return await runtime.request_confirm(confirm, emit_confirm, owner=confirm_owner(group.id))

    # ---- 交互通道（与确认同路：走常驻事件流，不走本群 SSE）------------- #
    #
    # 选择 / 敏感输入在群里同样要能弹：用户是在群聊页看着搭子讨论的，
    # 弹窗出现在同一屏才说得通（理由与 emit_confirm 完全一样）。
    async def emit_interaction(interaction: InteractionRequest) -> None:
        runtime.events.publish(
            "interaction_request",
            group_id=group.id,
            group_name=group.name,
            assistant_id=member.id,
            assistant_name=member.name,
            **interaction.to_dict(),
        )

    async def interaction_callback(interaction: InteractionRequest) -> dict[str, Any]:
        # 同 confirm：没有任何客户端在监听事件流 → 这个弹窗**永远不可能被回答**。
        # 直接按"没答"返回（技能会降级成按假设往下做），而不是白等一场 ——
        # 那边的用户只会看到一个卡住的群。
        if runtime.events.subscriber_count == 0:
            logger.warning(
                "群聊交互无人可送达（没有客户端在监听事件流），按未作答降级 group=%s skill=%s",
                group.id,
                interaction.skill_name,
            )
            return {"cancelled": True, "reason": "no_subscriber"}
        return await runtime.request_interaction(
            interaction, emit_interaction, owner=confirm_owner(group.id)
        )

    def live_confirm_mode() -> str | None:
        """群级策略优先于成员各自的（群里可一键"一律批准"）。

        **每次调用都重读一遍**：讨论进行到一半时用户改了群或成员的权限策略，
        后续发言要立刻按新的走，而不是等下一次讨论（用户反馈）。
        按 id 去 runtime 里查（``PATCH /v1/groups/{id}`` 会替换 ``runtime.groups``）；
        万一查不到（调用方拿的是临时对象，例如测试），就退回调用方传进来的那份，
        别把群级策略丢掉。
        """
        current = runtime.groups.get(group.id) or group
        # ⚠️⚠️ 顺序是**群设置 → 成员档案 → 全局**，且**只在群聊里用**
        # （特别强调："群聊的权限设置是管群里每个搭子在群聊当中
        # 权限的，千万不能搞混"）。单聊那份在 `routes/chat.py` 的 `SkillContext`
        # 里，只走"成员档案 → 全局"。**两条链各读各的** ——
        # 别为了"统一"把群设置写回搭子档案，那会让用户改一个群就改掉单聊。
        # 边界由 `tests/integration/test_group_confirm.py` 的
        # `test_群权限设置不会影响单聊` 守着。
        return current.confirm_mode or runtime.assistant_confirm_mode(member.id)

    ctx = SkillContext(
        settings=settings,
        paths=runtime.paths,
        confirm=confirm_callback,
        interaction=interaction_callback,
        audit=runtime.audit.record,
        session_id=f"group:{group.id}",
        assistant_id=member.id,
        # ⚠️ 群聊必须显式带上群 id：群记忆是**群内成员共享**的，
        # 检索要靠它把"这个群的库"并进来，群里说"记住这件事"也要落进群库 ——
        # 否则只有当前发言那位搭子自己记得，那就不叫共同记忆了。
        group_id=group.id,
        workspace=runtime.workspace,
        path_policy=runtime.path_policy,
        # 同理：群聊时 skills 里的 memory 绑的是**群库**，不是该成员自己的库。
        extra=runtime.skill_services_for(member.id, group_id=group.id),
        # ⚠️ 前台传**闭包**而不是取值：见 live_confirm_mode 的说明。
        # 前台：auto_approve 只放行 confirm 级，admin 级仍走确认通道。
        confirm_mode="auto_approve" if background else live_confirm_mode,
        # 后台按次放开高危级：没人能点「允许」，不放开就等于"高危技能在后台
        # 永远跑不了"。⚠️ 走 ctx 而不是守卫上的进程级开关 —— 那会把前台
        # 一起放开（见 PermissionGuard.allow_admin）。
        allow_admin=background,
    )
    config = AgentConfig(
        # 不再硬编码 6 / 50：那会让群聊里的搭子"做几步就被上限掐断"，
        # 而且与用户在设置里的调整完全脱钩。跟随全局设置（单聊也是同一套）。
        max_iterations=settings.agent.max_iterations,
        max_tool_calls_per_turn=settings.agent.max_tool_calls_per_turn,
        # 思考强度：**群级设置优先**，没有才用成员自己的；都没有就不发送该参数
        # （与单人对话里"没选档位就不发"的语义一致）。
        reasoning_effort=group.reasoning_effort or member.reasoning_effort,
        temperature=member.temperature if member.temperature is not None else 0.7,
        # 群聊的 system（群规则 + 该搭子的人格文档）现在只能走 persona 进引擎：
        # ``AgentConfig.system_prompt`` 已随"兜底提示词"一起退役，persona 是
        # system 的第 0 位唯一来源（见 engine._system_prompt）。
        # 传字符串而不是惰性提供者：一轮群聊里不会改写人格文件。
        persona=system,
        # 与单聊同一口径（见 skill/groups.py）："没勾"≠"全开"，
        # 必须展开成"内置 ∪ 自己的专属 ∪ 勾选的通用/我的"
        enabled_skills=runtime.skills.allowed_names(
            assistant_id=member.id,
            enabled_skills=member.enabled_skills,
        ),
        # 专属技能（心鉴学那套 + 搭子总管那批）只对归属搭子存在：群里每个成员
        # 各带各的，别人的专属工具连清单都不进
        target_assistant=member.id,
        token_limit=llm.token_limit,
        enable_planner=False,
        enable_reflection=False,
    )
    return Agent(
        llm=llm,
        # 群里每个成员各按自己的能力走，辅助调用同样可指定（沿用全局设置）
        utility_llm=runtime.utility_llm(llm),
        skill_manager=runtime.skills,
        memory=memory,
        config=config,
        ctx=ctx,
    )
async def run_member(
    runtime: AppRuntime,
    group: GroupProfile,
    member: Any,
    history: list[Any],
    user_input: str,
    images: list[Any] | None = None,
    *,
    background: bool = False,
    role: str = "",
    can_end_vote: bool = False,
) -> AsyncIterator[tuple[str, str]]:
    """跑一个搭子的一次发言，逐段产出 ``('delta', 文本)``，最后 ``('final', 全文)``。

    额外产出 ``('out_of_scope', 技能名)``：这个搭子调用了**不在它职责范围内**的工具
    （见下面那段说明 —— 用户选了"不动工具权限、只把越权晾出来"）。

    ``images`` 是用户这一轮附带的图片：群里每个成员都要能看到它们，
    否则"看看这张图有什么问题"只有第一个发言的搭子看得见、后面的全靠猜。

    ``background`` 只影响权限口径（见 ``build_group_agent``）。
    """
    agent = build_group_agent(
        runtime,
        group,
        member,
        history,
        background=background,
        role=role,
        can_end_vote=can_end_vote,
    )
    # 越权检测的基准 = 这个成员**实际可用**的技能（内置 ∪ 自己的专属 ∪ 勾选的通用/我的）。
    # ⚠️ 不能再用 `member.enabled_skills`：新口径下它为空只表示"没额外勾选"，
    # 而成员**至少**能用内置技能 —— 拿它当基准会把内置技能全判成越权。
    allowed = runtime.skills.allowed_names(
        assistant_id=member.id, enabled_skills=member.enabled_skills
    )
    text = ""
    started = asyncio.get_running_loop().time()
    iterations = 0
    async for event in agent.run_stream(user_input, images=list(images or [])):
        if event.type == "delta":
            piece = str(event.data.get("text") or "")
            if piece:
                text += piece
                yield "delta", piece
        elif event.type == "done":
            iterations = int(event.data.get("iterations") or 0)
        elif event.type == "tool_call":
            # ---- 越权检测（的选择：不动权限，但要"晾出来"）----
            #
            # 基准是"这个成员**实际能用**的技能"（见上面 allowed 的算法）。
            # 用了范围外的工具 → 明确标出来，让用户看得见"谁抢了谁的活"。
            # 这里**只标不拦**：拦会让讨论当场卡住，而用户要的是"可见"，
            # 不是替他把活挡住（他明确放弃了"按职责裁剪工具"那条路）。
            name = str(event.data.get("name") or "")
            if name and name not in allowed:
                yield "out_of_scope", name
        elif event.type == "error":
            yield "error", str(event.data.get("message") or "生成失败")

    # ---- 落进**群记忆库**-------------------------------- #
    #
    # 群聊天记录要成为"群内每个参与搭子的共同记忆"。在这之前群聊**完全不进向量库**
    # （消息只躺在 group_events 表里），所以群里问"我们以前说过什么"什么也查不到。
    #
    # ⚠️ 挂在这里而不是各个调用点：`run_member` 是**唯一**的发言产出地
    # （主讨论循环与最终总结都走它），挂在这儿不会漏。漏一处就是"某个成员的发言
    # 永远记不住"，而那种缺失几乎不可能被用户定位到。
    #
    # ⚠️ 剥掉控制标记再存（``[END_VOTE]`` / ``[PASS]`` 这些是给系统看的）：
    # 存进去只会污染检索结果 —— 用户问"我们当时怎么说的"，捞回来的却是标记。
    clean_text, _, _ = parse_control(text)
    if clean_text:
        await runtime.archive_group_turn(
            group_id=group.id, speaker=member.name, text=clean_text
        )

    yield "final", text

    # ---- 记录用量与费用 ------------------------------------------------ #
    #
    # ⚠️ 这里以前**什么都没有**，是实测反馈"模型计费出错"的根因：
    # 全仓用量记录原先只在 `routes/chat.py`（单聊）和 `agent/scheduler.py`
    # （后台任务）里被调用，而**群聊这条路径从来不记** —— 于是群里聊一整天，
    # 用量页一毛钱都不涨，用户会以为计费坏了。而它确实坏了，只是坏在"根本没记"。
    #
    # 数据来自 `agent.tracer`：引擎本来就给每个 Agent 建了一个 Tracer 并累加 usage
    # （见 `agent/engine.py` 的 `self.tracer.add_usage`），所以群聊不需要额外接线 ——
    # 只是从来没人去读它。被中断的那一轮同样要记：那些 token 厂商照收。
    if agent.tracer.usage.prompt_tokens or agent.tracer.usage.completion_tokens:
        # ⚠️ 用 `group.id` 当 session_id：群聊没有单聊那种会话对象，而用量表需要
        # 一个可聚合的键。按群聚合正好是用户想看的粒度（"这个群花了多少"）。
        await runtime.usage.record(
            session_id=group.id,
            # ⚠️ 必须与**实际执行用的**模型一致：`build_group_agent` 取的是
            # `member.model_id or default_model`（成员没单独配模型时用全局默认）。
            # 只传裸 `member.model_id` 的话，没配模型的那部分成员记账时
            # model_id 为空 → 查不到单价 → 费用**留空**，用户会看到
            # "这个群用了这么多 token，但费用是未配置"。
            model_id=str(getattr(member, "model_id", "") or "")
            or runtime.config.models.default_model,
            usage=agent.tracer.usage,
            trace_id=agent.tracer.trace_id,
            duration_ms=round((asyncio.get_running_loop().time() - started) * 1000, 2),
            iterations=iterations,
        )

        # ⚠️ 群聊的 trace 也要进留存表（第 88 批，M-25）：上面刚把 `trace_id` 写进用量表，
        # 而在此之前**只有单聊**会 `traces.put()` —— 于是用量页给出的 trace_id
        # 对群聊永远 404。群讨论恰恰是最容易静默失败的一条路径（成员轮流发言、
        # 中途任何一位失败都可能被吞成一句"没轮到我"），最需要能按 trace 追。
        # 与单聊同一有界上限（TraceStore 只留 100 条），无内存增长风险。
        if runtime.config.settings.trace_enabled:
            runtime.traces.put(agent.tracer.trace_id, agent.tracer.export())


# --------------------------------------------------------------------------- #
# 讨论主循环：多轮轮流发言 + 结束投票 + 发起者总结
# --------------------------------------------------------------------------- #
async def discuss_stream(
    runtime: AppRuntime,
    group: GroupProfile,
    members: list[Any],
    topic: str,
    thread_id: str,
    *,
    attachment_block: str = "",
    images: list[Any] | None = None,
    background: bool = False,
) -> AsyncIterator[str]:
    # ⚠️ 键必须是 (群, 对话)：只用群 id 的话，切到另一条对话后模型会看到**上一条
    # 对话**的发言 —— 表现为"它记得我没说过的话"（产品要求群可以有多条对话）。
    history = runtime._group_history.setdefault((group.id, thread_id), [])
    # ⚠️ 判据从"有没有文字"改成"有没有文字**或附件/图片**"（产品要求）：
    # 任务常常整份都在附件里，只发附件是合法的一次话题。原先走的是下面
    # `elif not history` 那条分支 —— 附件被当成"继续上一个话题"，既不落历史，
    # 也不告诉用户发生了什么。
    if topic.strip() or attachment_block or images:
        # 附件信息只进"给成员看的上下文"，不进 topic 事件：界面上附件是以
        # 文件名胶囊展示的，把 `[附件]…[/附件]` 再渲染成用户发言会很怪
        content = f"{attachment_block}\n\n{topic.strip()}" if attachment_block else topic.strip()
        say(history, role="user", name="用户", content=content)
        # 只发附件时给气泡一句可读的说明：空气泡会让用户以为"没发出去"
        yield _sse("topic", {"content": topic.strip() or "（只发了附件）"})
    elif not history:
        yield _sse("error", {"message": "还没有任何话题，请先抛出一个话题。"})
        yield _sse("done", {"reason": "empty"})
        return

    names = "、".join(member.name for member in members)
    # 角色：档案里写了就用它，没写按发言位次兜底（首位=总管、末位=审核员）
    roles = effective_roles(members)
    end_vote_by = ""
    votes: dict[str, bool] = {}

    for round_index in range(MAX_ROUNDS):
        for member in members:
            role = roles.get(member.id, "")
            may_end_vote = can_end_vote(members, member)
            yield _sse(
                "speaker",
                {
                    "assistant_id": member.id,
                    "name": member.name,
                    "round": round_index + 1,
                    "role": role,
                    "role_label": ROLE_LABELS.get(role, ""),
                },
            )
            if end_vote_by:
                hint = " 有人发起了结束投票：请在发言最后写 [AGREE] 或 [DISAGREE]。"
            elif may_end_vote:
                hint = " 若你认为讨论已充分、可以收尾，请在发言最后单独一行写 [END_VOTE]。"
            else:
                # 没有发起权的人也要知道该怎么做，否则他只会一遍遍试 [END_VOTE] 而没反应
                hint = " 该收尾时请 @ 发起者或末序发言者提出，由他们发起结束投票。"
            user_input = (
                f"群成员：{names}。现在轮到你（{member.name}）发言，请接着说。" + hint
            )
            text = ""
            async for kind, piece in run_member(
                runtime,
                group,
                member,
                history,
                user_input,
                images=images,
                background=background,
                role=role,
                can_end_vote=may_end_vote,
            ):
                if kind == "delta":
                    yield _sse("delta", {"assistant_id": member.id, "text": piece})
                elif kind == "error":
                    yield _sse("error", {"assistant_id": member.id, "message": piece})
                elif kind == "out_of_scope":
                    # 越权：不用它的工具，但让用户**看得见**（的选择）
                    yield _sse(
                        "out_of_scope",
                        {
                            "assistant_id": member.id,
                            "name": member.name,
                            "skill": piece,
                            "owners": skill_owners(members, piece),
                        },
                    )
                elif kind == "final":
                    text = piece

            clean, control, reason = parse_control(text)
            if clean:
                say(history, role="assistant", name=member.name, content=clean)
                yield _sse(
                    "message",
                    {"assistant_id": member.id, "name": member.name, "content": clean},
                )

            # ---- 审核员的验收结论（[PASS] / [REJECT]）----------------------- #
            #
            # 不达标**不结束讨论**：把反馈留给总管（它在下一轮会看到这条发言），
            # 由它重新安排 —— 这就是用户要的"打回给总管"。整场讨论仍在
            # MAX_ROUNDS 的安全阀内，不额外重开一场（那样成本翻倍、用户也看不到过程）。
            if control in ("pass", "reject") and role == "reviewer":
                yield _sse(
                    "review",
                    {
                        "assistant_id": member.id,
                        "name": member.name,
                        "passed": control == "pass",
                        "reason": reason,
                    },
                )
                continue

            if control == "end_vote" and not end_vote_by:
                if not may_end_vote:
                    # 没有发起权：**不静默吞掉** —— 说清规则与替代做法，
                    # 否则模型会一遍遍试（产品明确要求"只允许发起者或末序发言者发起"）
                    yield _sse(
                        "vote_denied",
                        {
                            "assistant_id": member.id,
                            "name": member.name,
                            "reason": "结束投票只能由发起者或末序发言者发起，请在发言里 @ 他们。",
                        },
                    )
                    continue
                end_vote_by = member.id
                votes = {}
                yield _sse(
                    "vote_request",
                    {"assistant_id": member.id, "name": member.name, "reason": reason},
                )
                continue

            if end_vote_by and control in ("agree", "disagree"):
                votes[member.id] = control == "agree"
                yield _sse(
                    "vote",
                    {
                        "assistant_id": member.id,
                        "name": member.name,
                        "agree": control == "agree",
                    },
                )
                others = [item.id for item in members if item.id != end_vote_by]
                all_voted = all(item in votes for item in others)
                passed = vote_passed(votes)
                if passed or all_voted:
                    yield _sse("vote_result", {"passed": passed})
                    if passed:
                        async for chunk in emit_summary(
                            runtime,
                            group,
                            members,
                            history,
                            end_vote_by,
                            background=background,
                        ):
                            yield chunk
                        yield _sse("done", {"reason": "voted"})
                        return
                    # 未通过：清空投票，继续讨论
                    end_vote_by = ""
                    votes = {}

    yield _sse(
        "done",
        {"reason": "max_rounds", "message": f"已达到安全轮数上限（{MAX_ROUNDS} 轮），讨论自动结束。"},
    )
async def emit_summary(
    runtime: AppRuntime,
    group: GroupProfile,
    members: list[Any],
    history: list[Any],
    instigator_id: str,
    *,
    images: list[Any] | None = None,
    background: bool = False,
) -> AsyncIterator[str]:
    """投票通过后，由发起者做最终总结。"""
    instigator = next((item for item in members if item.id == instigator_id), None)
    if instigator is None:
        return
    yield _sse(
        "speaker",
        {"assistant_id": instigator.id, "name": instigator.name, "summary": True},
    )
    summary = ""
    prompt = (
        "讨论已通过结束投票。请你作为发起人，给出**最终总结**："
        "把大家的结论收敛成一段清晰的交付（结论 + 关键理由），直接面向用户，"
        "不要再写 [END_VOTE]。"
    )
    # 总结也带上它自己的角色：做过总管的人写总结时会自然按"收敛交付"的语气写，
    # 而这正是我们要的（角色不该在最后一步突然消失）
    roles = effective_roles(members)
    async for kind, piece in run_member(
        runtime,
        group,
        instigator,
        history,
        prompt,
        images=images,
        background=background,
        role=roles.get(instigator.id, ""),
    ):
        if kind == "delta":
            yield _sse("delta", {"assistant_id": instigator.id, "text": piece})
        elif kind == "final":
            summary = piece
    if summary:
        say(history, role="assistant", name=instigator.name, content=summary)
        yield _sse(
            "summary",
            {"assistant_id": instigator.id, "name": instigator.name, "content": summary},
        )
async def discussion_source(
    runtime: AppRuntime,
    group: GroupProfile,
    members: list[Any],
    topic: str,
    thread_id: str,
    *,
    attachment_block: str = "",
    images: list[Any] | None = None,
    background: bool = False,
) -> AsyncIterator[str]:
    """讨论流 + **收尾清理**。

    HTTP 路由与后台运行器（``agent/orchestrator.py``）共用这一条 —— 两条各写一份的
    话，落库/进度/收尾迟早会长歪（而"同一场讨论有两种记录口径"是最难查的一类问题）。

    收尾那一步不能省：用户点「停止」时前端只是断开连接，服务端这个生成器随即被
    取消 —— 如果此刻正好有一个搭子卡在"等确认"上，那个 future 会一直悬着到超时
    （默认 120 秒）。期间用户再触发同一个操作，会撞上"已经有一项待确认"，
    而界面上完全看不出为什么没反应。
    """
    try:
        async for chunk in discuss_stream(
            runtime,
            group,
            members,
            topic,
            thread_id,
            attachment_block=attachment_block,
            images=images,
            background=background,
        ):
            yield chunk
    finally:
        pending = runtime.reject_pending(owner=confirm_owner(group.id))
        if pending:
            logger.info("群讨论收尾：已按拒绝收起 %s 个挂起的确认 group=%s", pending, group.id)

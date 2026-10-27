










































from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ...assistants import evolution
from ...assistants.persona import ALLOWED_FILES, read_file
from ...errors import SkillExecutionError
from ...skill.base import BaseSkill, SkillContext
from ...skill.decorator import skill





class TeamListParams(BaseModel):
    include_groups: bool = Field(True, description="是否连现有的群一起列出来")
    assistant_id: str = Field(
        "",
        description=(
            "只看某一个搭子的完整设定时填它（来自上一次清单的结果）；"
            "留空 = 列出全部。判断它能不能担这件事时，指定一个更省事。"
        ),
    )


@skill(
    name="team_list_assistants",
    display_name="查看现有搭子与群",
    description=(
        "列出**现有**搭子的 id、名称、简介、已装技能、**它当前的群角色（group_role）**，"
        "以及它的**身份 / 规则 / 语气**三份设定全文；还列出已有的群"
        "（群的成员带 id、它是**工作群还是讨论群**，以及该群**优化员 / 审核员**确认了没有）。\n"
        "三个用途：① 新建之前先看有没有能复用的（**建搭子、建群之前必须先调它**，"
        "用户明确要求「有功能相同的就复用现有的」）；"
        "② 判断某个搭子适不适合承担本次任务、还差什么能力（差什么可以用 "
        "team_update_assistant 给它补上）；"
        "③ 给群提交审核员 / 优化顾问之前，用它拿到真搭子的 id、看清谁已经是这个角色。"
    ),
    params_model=TeamListParams,
    category="system",
    permission_level="safe",
    tags=["搭子团队", "群聊"],
)
class TeamListSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = TeamListParams(**params)
        team = ctx.service("team")
        assistants = team.list_assistants(assistant_id=args.assistant_id)
        result: dict[str, Any] = {
            "count": len(assistants),
            "assistants": assistants,
            "message": (
                "现在是空的：确实需要新建时再建。"
                if not assistants
                else "**先看这份清单**：有功能相同的就直接用它的 id，不要重复建；"
                "要看某人能不能担事，读它的 identity / abilities 与 rules。"
            ),
        }
        if args.include_groups:
            result["groups"] = await team.list_groups()
        return result


class AssistantCreateParams(BaseModel):
    name: str = Field(..., min_length=1, max_length=48, description="搭子名称（要具体，例如「周报助手」）")
    description: str = Field(
        ...,
        min_length=1,
        description=(
            "**简介**，一两句话，必须写清这个搭子的**全部能力**（界面列表里只显示它）。"
            "例如「把聊天记录、会议纪要整理成结构化周报，能读 Excel 与 Word」。"
        ),
    )
    identity: str = Field(
        ...,
        min_length=1,
        description=(
            "**身份**：它是谁、负责哪一块、服务的对象是谁（写进 IDENTITY.md）。"
            "一句话说清职责范围，别写成「我是个乐于助人的助手」这种没有信息量的。"
        ),
    )
    abilities: str = Field(
        ...,
        min_length=1,
        description=(
            "**能力清单**（写进 IDENTITY.md 的「我能做什么」）：它实际会做的几件事，"
            "逐条列出来，并说明各自用在什么场景。这是别人判断它能不能担事的依据。"
        ),
    )
    rules: str = Field(
        ...,
        min_length=1,
        description=(
            "**工作规则与边界**（写进 RULES.md）：先做什么后做什么、什么情况必须先问、"
            "拿不准时怎么办、明确不做什么。这里要能约束住它的行为。"
        ),
    )
    tone: str = Field(
        ...,
        min_length=1,
        description=(
            "**语气风格**（写进 SOUL.md）：按它的职责与任务来定，不是泛泛的"
            "「友好专业」。例如「像交付清单一样简洁，每条给依据，不寒暄」。"
        ),
    )
    emoji: str = Field("🤖", description="头像 emoji（一个字符即可）")
    group_role: Literal["", "coordinator", "worker", "advisor", "reviewer"] = Field(
        "",
        description=(
            "群聊里的角色：coordinator=协调者（总管，做策划与分工）、worker=执行者、"
            "advisor=优化顾问（交付后只提必要的建设性建议）、reviewer=审核员（验收交付、"
            "把关建议、不达标打回）。只给要拉进群做分工的搭子填；单独的助手留空即可。"
        ),
    )
    skills: list[str] = Field(
        default_factory=list,
        description=(
            "要开放给它的技能名（留空 = 开放全部已启用技能）。"
            "只能填真实存在的技能名，不确定就留空。"
            "⚠️ 每个搭子只该专精一个领域：能列出它真正需要的技能就列出来，"
            "别因为省事就留空。"
        ),
    )


@skill(
    name="team_create_assistant",
    display_name="新建搭子",
    description=(
        "新建一个搭子（助手预设），并写全它的设定：身份、能力清单、工作规则、语气风格。\n"
        "**调用前必须先 team_list_assistants**：已经有功能相同的搭子时，直接用现有的 id"
        "（甚至可以先用 team_update_assistant 给它补能力），别建重复的（同名会被拒绝）。\n"
        "⚠️ 每个搭子只专精一个领域，不要造全能搭子 —— 需要更多角色就多建几个。"
    ),
    params_model=AssistantCreateParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队"],
)
class TeamCreateAssistantSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = AssistantCreateParams(**params)
        team = ctx.service("team")
        try:
            created = await team.create_assistant(
                name=args.name,
                description=args.description,
                identity=args.identity,
                abilities=args.abilities,
                rules=args.rules,
                tone=args.tone,
                emoji=args.emoji,
                skills=args.skills,
                group_role=args.group_role,
                actor_id=ctx.assistant_id,
            )
        except ValueError as exc:
            
            raise SkillExecutionError(str(exc)) from exc
        return {
            "created": created,
            "message": (
                f"已新建搭子「{created['name']}」（id={created['id']}），"
                "身份 / 能力 / 规则 / 语气都已写入它的设定，也已经出现在左侧搭子栏里。"
                "要让它和别人讨论，用 team_create_group 把成员拉进群；"
                "如果它是给某个群建的审核员 / 优化顾问，建好后还要用 team_assign_group_roles "
                "把它（以及另一个角色）的 id 提交给那个群 —— 这一步不做，讨论开不了。"
            ),
        }


class AssistantSetupParams(BaseModel):
    assistant_id: str = Field(
        ..., min_length=1, description="要修改设定的搭子 id（来自 team_list_assistants 的结果）"
    )
    identity_append: str = Field(
        "", description="追加到 IDENTITY.md 的内容（新增的能力 / 职责范围）"
    )
    rules_append: str = Field(
        "",
        description=(
            "追加到 RULES.md 的内容（新增的规则与边界）。"
            "只追加：**不要**去删改它已有的规则，尤其那段「全员进化」的原始规则"
        ),
    )
    tone_append: str = Field("", description="追加到 SOUL.md 的内容（语气风格的补充）")
    memory_append: str = Field(
        "",
        description=(
            "追加到对方 MEMORY.md 的内容（例如「全员进化月度复盘」给每个人定的下月重点）。"
            "只追加，不要动他已经写下的东西"
        ),
    )
    description_append: str = Field(
        "", description="追加到简介末尾的内容（新增能力时同步更新简介，界面才看得到）"
    )
    identity_replace: str = Field(
        "",
        description=(
            "**覆盖** IDENTITY.md（整份替换为这段文本）。用于「身份写错了要重写」，"
            "会丢掉原有内容，慎用；与 identity_append 不能同时传"
        ),
    )
    rules_replace: str = Field(
        "",
        description=(
            "**覆盖** RULES.md（整份替换）。用于「规则要重写」，会丢掉原有内容，慎用；"
            "与 rules_append 不能同时传"
        ),
    )
    tone_replace: str = Field(
        "",
        description=(
            "**覆盖** SOUL.md（整份替换）。用于「语气风格要重写」，会丢掉原有内容，慎用；"
            "与 tone_append 不能同时传"
        ),
    )
    description_replace: str = Field(
        "",
        description=(
            "**覆盖**简介（整份替换）。用于简介写错了要重写；与 description_append 不能同时传"
        ),
    )


@skill(
    name="team_update_assistant",
    display_name="修改搭子设定",
    description=(
        "修改**现有**搭子的设定：既能**追加**（`*_append`），也能**覆盖**（`*_replace`）。\n"
        "「这个搭子还差点什么」用 append；「这段写错了 / 要重写」用 replace（会让原文丢掉，慎用）。\n"
        "调用前先 team_list_assistants 看它现在有哪些设定，避免重复补充。\n"
        "memory_append 是给「全员进化月度复盘」回写各人下月重点用的，平时别用它（且只支持追加）。\n"
        + evolution.APPEND_ONLY_CLAUSE
    ),
    params_model=AssistantSetupParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队"],
)
class TeamUpdateAssistantSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = AssistantSetupParams(**params)
        provided = [
            args.identity_append.strip(),
            args.rules_append.strip(),
            args.tone_append.strip(),
            args.memory_append.strip(),
            args.description_append.strip(),
            args.identity_replace.strip(),
            args.rules_replace.strip(),
            args.tone_replace.strip(),
            args.description_replace.strip(),
        ]
        if not any(provided):
            raise SkillExecutionError(
                "至少要给一段要写的内容（identity/rules/tone/description 的 _append 或 _replace 之一，"
                "或 memory_append）。"
            )
        team = ctx.service("team")
        try:
            result = await team.append_assistant_setup(
                assistant_id=args.assistant_id,
                identity_append=args.identity_append,
                rules_append=args.rules_append,
                tone_append=args.tone_append,
                memory_append=args.memory_append,
                description_append=args.description_append,
                identity_replace=args.identity_replace,
                rules_replace=args.rules_replace,
                tone_replace=args.tone_replace,
                description_replace=args.description_replace,
                actor_id=ctx.assistant_id,
            )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc
        replaced = bool(result.get("replaced"))
        detail = "、".join(result.get("changed") or []) or "简介"
        return {
            "updated": result,
            "message": (
                f"已{'覆盖' if replaced else '补充'}「{args.assistant_id}」的设定：{detail}。"
                + ("（覆盖会丢掉原文，已在 updated.replaced 里标明）" if replaced else "")
            ),
        }





class TeamReadFileParams(BaseModel):
    assistant_id: str = Field(
        ..., min_length=1, description="要看的搭子 id（来自 team_list_assistants 的结果）"
    )
    file: str = Field(
        "进化日志.md",
        description=(
            f"要读哪个文件，只能是：{' / '.join(ALLOWED_FILES)}。"
            "「全员进化月度复盘」读的是各个搭子的 进化日志.md"
        ),
    )


@skill(
    name="team_read_assistant_file",
    display_name="查看搭子的文件",
    description=(
        "读取**另一个**搭子的人格文件（身份 / 人格 / 规则 / 记忆 / 进化日志）。\n"
        "什么时候用：你要评判或协助别的搭子时 —— 最典型的是「全员进化月度复盘」："
        "总管必须看得到每个人的 进化日志.md，否则只能凭印象说话。\n"
        "只读，不改任何东西；全文返回、不做截断。"
    ),
    params_model=TeamReadFileParams,
    category="system",
    
    permission_level="safe",
    tags=["搭子团队"],
)
class TeamReadAssistantFileSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = TeamReadFileParams(**params)
        team = ctx.service("team")
        
        
        if not team.list_assistants(assistant_id=args.assistant_id):
            raise SkillExecutionError(
                f"没有 id 为「{args.assistant_id}」的搭子（先用 team_list_assistants 看清单）。"
            )
        try:
            content = read_file(ctx.paths, args.assistant_id, args.file)
        except ValueError as exc:  
            raise SkillExecutionError(str(exc)) from exc
        return {
            "ok": True,
            "assistant_id": args.assistant_id,
            "file": args.file,
            "content": content,
            
            "empty": not content.strip(),
        }


class ConfirmationItem(BaseModel):
    check: str = Field(..., min_length=1, description="要核对什么（一句话，用户看得懂）")
    expect: str = Field("", description="期望看到什么（用户对照着看）")
    pass_if: str = Field("", description="怎么算通过（判据）")


class TeamAddConfirmationParams(BaseModel):
    assistant_id: str = Field(
        ..., min_length=1, description="哪个搭子的待确认清单（来自 team_list_assistants 的结果）"
    )
    items: list[ConfirmationItem] = Field(..., min_length=1, description="要追加的核对条目")


@skill(
    name="team_add_confirmation",
    display_name="写待确认清单",
    description=(
        "把「需要用户**亲眼核对**的事」写进某个搭子的 `待确认.md`（结构化条目，用户逐条勾选）。\n"
        "**你看不到客户端界面**（截图内容进不了你的上下文；UI 自动化对 Electron 自绘窗口也失效），\n"
        "所以**不要写**「点右上角齿轮」这类操作脚本 —— 只写「核对项 / 期望 / 判据」三件事，"
        "由用户自己去对照画面确认。"
    ),
    params_model=TeamAddConfirmationParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队"],
)
class TeamAddConfirmationSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        from ...assistants.persona import CONFIRM_FILE, read_file, write_file

        args = TeamAddConfirmationParams(**params)
        team = ctx.service("team")
        if not team.list_assistants(assistant_id=args.assistant_id):
            raise SkillExecutionError(
                f"没有 id 为「{args.assistant_id}」的搭子（先用 team_list_assistants 看清单）。"
            )
        try:
            current = read_file(ctx.paths, args.assistant_id, CONFIRM_FILE)
        except (OSError, ValueError):
            current = ""
        
        existing = current.count("\n## ") + (1 if current.strip().startswith("## ") else 0)
        blocks: list[str] = []
        for offset, item in enumerate(args.items, start=existing + 1):
            blocks.append(
                f"## {offset}\n"
                f"- 核对项：{item.check.strip()}\n"
                f"- 期望：{item.expect.strip() or '（未写）'}\n"
                f"- 判据：{item.pass_if.strip() or '（未写）'}\n"
                f"- 结论：待定\n"
            )
        addition = "\n".join(blocks)
        merged = (
            f"{current.rstrip()}\n\n{addition}\n"
            if current.strip()
            else f"# 待确认清单\n\n{addition}\n"
        )
        try:
            write_file(ctx.paths, args.assistant_id, CONFIRM_FILE, merged)
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc
        return {
            "assistant_id": args.assistant_id,
            "added": len(args.items),
            "content": merged,
            "message": (
                f"已写入 {len(args.items)} 条待确认项；用户可在设置页逐条勾选「通过 / 不通过 / 待定」。"
            ),
        }


class ContextPlanItem(BaseModel):
    member_id: str = Field(..., min_length=1, description="成员搭子 id（必须在群里）")
    brief: str = Field(..., min_length=1, description="该成员这次只需要读的内容（摘要 / 要点）")


class TeamDistributeContextParams(BaseModel):
    group_id: str = Field(..., min_length=1, description="群 id")
    thread_id: str = Field(..., min_length=1, description="当前对话 id（这条讨论的 thread_id）")
    items: list[ContextPlanItem] = Field(..., min_length=1, description="每个成员该读什么")


@skill(
    name="team_distribute_context",
    display_name="分配群聊上下文",
    description=(
        "把「每个成员这次该读什么」分配给一场群讨论（**取代全量广播**）。\n"
        "用法：在开讨论之前先想清楚每个人只需要知道哪部分，用这个工具写下来；"
        "讨论时每个成员**只收到分配给它那份**，没有分配的人才读摘要 + 最近几条。\n"
        "这样多个执行者也能各看各的，不用每人读全量。\n"
        "⚠️ 分配太窄会让成员漏掉必要背景；不确定时宁可给摘要、别硬裁。"
    ),
    params_model=TeamDistributeContextParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队", "群聊"],
)
class TeamDistributeContextSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = TeamDistributeContextParams(**params)
        team = ctx.service("team")
        try:
            result = await team.distribute_context(
                group_id=args.group_id,
                thread_id=args.thread_id,
                items=[item.model_dump() for item in args.items],
                actor_id=ctx.assistant_id,
            )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc
        return {
            "result": result,
            "message": (
                f"已为 {result['assigned']} 个成员分配上下文；本次讨论里他们会只读分配到的部分"
                "（未分配的人读摘要 + 最近几条）。"
            ),
        }


class AssistantDeleteParams(BaseModel):
    assistant_id: str = Field(
        ..., min_length=1, description="要删除的搭子 id（**必须来自 team_list_assistants 的结果**）"
    )
    reason: str = Field("", description="一句话说明为什么删，会显示在确认框里给用户看")


@skill(
    name="team_delete_assistant",
    display_name="删除搭子",
    description=(
        "删除一个搭子。**调用时会弹确认框，用户点头才真的删** —— 所以别把它当成"
        "「先调了再说」的技能，用户可能直接点拒绝。\n"
        "什么时候用：用户明确说「把 XX 删了 / 这个搭子不要了」，且"
        "team_list_assistants 确认过确实是这个 id。**不要**因为「它好像没用」就主动删。\n"
        "⚠️ 删除会连带处理：把它从所有群里移出、清掉它担任的审核员/优化顾问角色、"
        "删掉它的人格文件；如果某个群因此只剩不到两个成员，那个群也会被一并删除"
        "（返回体里会逐条说明做了什么，要如实转告用户）。\n"
        "它原本是默认搭子时，默认位会自动移交给清单里的第一位。"
    ),
    params_model=AssistantDeleteParams,
    category="system",
    
    
    
    permission_level="confirm",
    tags=["搭子团队"],
)
class TeamDeleteAssistantSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = AssistantDeleteParams(**params)
        team = ctx.service("team")
        try:
            result = await team.delete_assistant(
                assistant_id=args.assistant_id, actor_id=ctx.assistant_id
            )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc
        return {
            "deleted": result,
            
            
            "message": result["message"] + " 请如实把上面的连带影响告诉用户。",
        }


class GroupCreateParams(BaseModel):
    name: str = Field(..., min_length=1, max_length=48, description="群名称，例如「学习计划讨论组」")
    group_type: Literal["work", "discussion"] = Field(
        "discussion",
        description=(
            "**群类型，建群前先想清楚选哪种**：\n"
            "· `work` = **工作群**（流水线）：你分发任务 → 执行者**并行**各干各的 → "
            "优化员挑改进 → 审核员验收 → 你总结。**除你之外谁也看不到全量对话**"
            "（每人只拿到自己那一段），适合「一份活拆给几个人干」。必须配齐优化员 + 审核员。\n"
            "· `discussion` = **讨论群**（圆桌）：所有人共享全部对话、轮流发言，"
            "适合头脑风暴 / 多人评议。不强制要优化员、审核员。\n"
            "拿不准就用 `discussion`（默认值，也是老行为）。"
        ),
    )
    member_ids: list[str] = Field(
        ...,
        min_length=2,
        description="成员搭子的 id 列表（**必须来自 team_list_assistants 的结果**，至少两个）",
    )
    coordinator_id: str = Field(
        "",
        description=(
            "**已固定为 Buddy Manager，不用传**（群总管恒为它，且会自动把它写进成员）。"
            "保留这个参数只为兼容老调用；传了别的 id 会被忽略。"
        ),
    )
    speaking_order: list[str] = Field(
        default_factory=list,
        description=(
            "发言顺序（成员 id 的子集）；留空按上面给的顺序。"
            "**只对讨论群有意义**（工作群按流水线阶段走，不看这个）"
        ),
    )
    advisor_id: str = Field(
        "",
        description=(
            "**只有工作群用**：优化员的搭子 id（会自动加进成员）。"
            "建群时给了就一步到位；不给就紧接着调 team_assign_group_roles 补。"
        ),
    )
    reviewer_id: str = Field(
        "",
        description=(
            "**只有工作群用**：审核员的搭子 id（会自动加进成员）。"
            "建群时给了就一步到位；不给就紧接着调 team_assign_group_roles 补。"
        ),
    )


@skill(
    name="team_create_group",
    display_name="建群（拉搭子进群）",
    description=(
        "把几个搭子拉进一个群。成员 id 必须来自 team_list_assistants 的结果。\n"
        "\n"
        "**第一件要想清楚的事：这是工作群还是讨论群**（`group_type`）——\n"
        "· `work`（工作群，流水线）：你把任务拆开分派给每个执行者，他们**并行**各干各的，"
        "**彼此看不到对方做了什么、也看不到群聊历史**；成品出来后优化员只看交付物提改进、"
        "审核员只看交付物验收，最后由你统一总结交付。适合「一份活拆给几个人干」。\n"
        "  必须配齐四类角色：总管（恒为你，自动进群）+ 执行者（至少 1 个）+ 优化员 + 审核员。"
        "优化员 / 审核员可以直接传 `advisor_id` / `reviewer_id` 一步到位，"
        "没传就紧接着调 team_assign_group_roles 补 —— **没配齐之前 team_start_discussion 会被拒绝**。\n"
        "· `discussion`（讨论群，圆桌）：所有人共享全部对话、轮流发言，"
        "适合头脑风暴 / 多人评议。**不强制配优化员 / 审核员，建完直接开讨论。**\n"
        "拿不准就用 `discussion`（默认值，也是老行为）。\n"
        "\n"
        "怎么选人：有合适的现有搭子就直接复用 id；没有就用 team_create_assistant 建一个"
        "带具体规则的（group_role 填 reviewer / advisor，规则里写清「这个任务怎么算达标」）。\n"
        "返回体里会带上现有搭子清单与下一步指引，方便确认有没有该复用却漏掉的。"
    ),
    params_model=GroupCreateParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队", "群聊"],
)
class TeamCreateGroupSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = GroupCreateParams(**params)
        team = ctx.service("team")
        try:
            created = await team.create_group(
                name=args.name,
                member_ids=args.member_ids,
                coordinator_id=args.coordinator_id,
                speaking_order=args.speaking_order,
                actor_id=ctx.assistant_id,
                group_type=args.group_type,
                advisor_id=args.advisor_id,
                reviewer_id=args.reviewer_id,
            )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc
        return {
            "created": created,
            
            
            "message": (
                f"已建{'工作群' if created.get('group_type') == 'work' else '讨论群'}"
                f"「{created['name']}」（id={created['id']}）。" + (created.get("next_step") or "")
            ),
        }


class GroupRolesParams(BaseModel):
    group_id: str = Field(
        ..., min_length=1, description="要确认角色的群 id（team_create_group 或群清单里的 id）"
    )
    reviewer_id: str = Field(
        ...,
        min_length=1,
        description=(
            "**审核员**的搭子 id：交付出来后按「能不能直接用」的标准验收，达标写 [PASS]、"
            "不达标写 [REJECT] 打回总管。必须是群成员（不在群里会自动拉进来）。"
        ),
    )
    advisor_id: str = Field(
        ...,
        min_length=1,
        description=(
            "**优化顾问**的搭子 id：在交付成型后只提**必要**的建设性建议，交给审核员把关。"
            "必须与 reviewer_id 是两个不同的搭子。"
        ),
    )


@skill(
    name="team_assign_group_roles",
    display_name="提交群角色（审核员 / 优化顾问）",
    description=(
        "把一个群的「审核员」与「优化顾问」的搭子 id 提交给系统确认。\n"
        "⚠️ **只有工作群需要这一步**：工作群是流水线（分发 → 执行 → 优化 → 审核 → 总结），"
        "优化员与审核员是流水线上的**固定站点**，缺一个整条流程就断，**没有「不需要」"
        "这个选项**；讨论群不强制（用户明确：讨论群不强制有优化员与审核员），"
        "不调它也能直接开讨论。\n"
        "怎么选人：\n"
        "1. 先 team_list_assistants 看清楚现有搭子的 id、简介与**它当前的角色"
        "（group_role）**：已经是审核员 / 优化顾问的，直接复用；\n"
        "2. 没有合适的就用 team_create_assistant 建一个（group_role 填 reviewer / advisor，"
        "规则里写清这个任务的具体判据）；\n"
        "3. 再用这个技能把两个 id 提交上来。\n"
        "提交成功后系统会记住；工作群没配齐之前 team_start_discussion 会被拒绝。\n"
        "另外：不在群里的搭子会被自动拉进群（返回体里会说明）；已经是**别的**角色"
        "（例如总管）的搭子不能顶成审核员，会被拒绝 —— 换一个搭子。"
    ),
    params_model=GroupRolesParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队", "群聊"],
)
class TeamAssignGroupRolesSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = GroupRolesParams(**params)
        team = ctx.service("team")
        try:
            confirmed = await team.assign_group_roles(
                group_id=args.group_id,
                reviewer_id=args.reviewer_id,
                advisor_id=args.advisor_id,
                actor_id=ctx.assistant_id,
            )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc
        roles = confirmed["roles"]
        added = [item["name"] for item in confirmed.get("added_members", [])]
        return {
            "confirmed": confirmed,
            "message": (
                f"已确认「{confirmed['name']}」的角色：审核员 = {roles['reviewer']['name']}、"
                f"优化顾问 = {roles['advisor']['name']}。"
                + (f"（顺手把 {'、'.join(added)} 拉进了群。）" if added else "")
                + "现在可以用 team_start_discussion 把话题抛进去了。"
            ),
        }


class GroupUpdateParams(BaseModel):
    group_id: str = Field(..., min_length=1, description="要改的群 id（来自群清单）")
    name: str = Field("", max_length=48, description="新群名；留空表示不改名")
    add_member_ids: list[str] = Field(
        default_factory=list,
        description="要**加进**群的搭子 id（来自 team_list_assistants 的结果）",
    )
    remove_member_ids: list[str] = Field(
        default_factory=list, description="要**移出**群的搭子 id"
    )
    speaking_order: list[str] = Field(
        default_factory=list,
        description="想要的发言顺序（成员 id 列表，可只列前几位）；留空表示不动",
    )
    avatar_source: str = Field(
        "",
        description=(
            "换成新头像。三种来源都行：**图片链接**、**本机文件路径**、"
            "或**工作区里上传件的 id**（用户在对话里发过的图）。"
            "留空 = 不动头像。⚠️ 你自己没有图片，所以只在这个信息确实来自用户时用它 —— "
            "想「随便换个头像」的话，用 clear_avatar 让系统重新分配。"
        ),
    )
    clear_avatar: bool = Field(
        False,
        description=(
            "清掉这个群的头像，由系统重新分配一张（会优先选与现有群不重复的）。"
            "用户说「换个群头像」但没给图时用它。"
        ),
    )


@skill(
    name="team_update_group",
    display_name="调整群（改名 / 加减成员 / 调顺序 / 换头像）",
    description=(
        "改一个**已经存在**的群：改群名、加人或减人、调整发言顺序、换群头像。\n"
        "用户说「这个群再加个懂设计的」「把某某移出去」「群名改成 XX」「让谁先说」"
        "「换个群头像」时用它。\n"
        "⚠️ 加人只需给要加的 id（不用交完整名单）；群里至少要留两个搭子，不然会被拒绝。\n"
        "⚠️ 换头像：用户给了图片（链接 / 文件 / 他刚发的那张）就填 avatar_source；"
        "只是说「换一张」而没给图，就填 clear_avatar=true —— "
        "群头像库在你这边是看不到的，**不要自己编一个图片地址**。"
    ),
    params_model=GroupUpdateParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队", "群聊"],
)
class TeamUpdateGroupSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = GroupUpdateParams(**params)
        if not any(
            [
                args.name.strip(),
                args.add_member_ids,
                args.remove_member_ids,
                args.speaking_order,
                args.avatar_source.strip(),
                args.clear_avatar,
            ]
        ):
            raise SkillExecutionError(
                "至少要给一项要改的东西（群名 / 加人 / 减人 / 发言顺序 / 头像）。"
            )
        team = ctx.service("team")
        try:
            result = await team.update_group(
                group_id=args.group_id,
                name=args.name,
                add_member_ids=args.add_member_ids,
                remove_member_ids=args.remove_member_ids,
                speaking_order=args.speaking_order,
                avatar_source=args.avatar_source,
                clear_avatar=args.clear_avatar,
                actor_id=ctx.assistant_id,
            )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc
        note = ""
        if result.get("roles_cleared"):
            
            note = (
                f"⚠️ 被移出群的人里包含已确认的{'、'.join(result['roles_cleared'])}，"
                "该角色已作废 —— 要开讨论必须先用 team_assign_group_roles 重新提交一个 id。"
            )
        return {
            "group": result,
            "message": (
                f"已更新群「{result['name']}」：现有成员 "
                + "、".join(item["name"] for item in result["members"])
                + "。"
                + note
            ),
        }


class GroupOrderParams(BaseModel):
    group_id: str = Field(..., min_length=1, description="群 id（来自 team_list_assistants 的 groups）")
    order: list[str] = Field(..., min_length=1, description="想要的发言顺序（成员 id 列表）")


@skill(
    name="team_set_speaking_order",
    display_name="调整群发言顺序",
    description=(
        "调整群里谁先说、谁后说。先说的人往往定基调，所以用户说"
        "「让某某先讲」时用它。没列到的成员会按原顺序排在后面。"
    ),
    params_model=GroupOrderParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队", "群聊"],
)
class TeamSetOrderSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = GroupOrderParams(**params)
        team = ctx.service("team")
        try:
            result = await team.set_speaking_order(
                group_id=args.group_id, order=args.order, actor_id=ctx.assistant_id
            )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc
        return result


class StartDiscussionParams(BaseModel):
    topic: str = Field(
        ...,
        min_length=1,
        description=(
            "要讨论的话题，要写清楚**目标**（例如「定一下这周的学习计划，"
            "给出每天的任务与时间安排」），而不是「你俩聊聊」这种没有交付物的说法。"
        ),
    )
    group_id: str = Field(
        ...,
        min_length=1,
        description=(
            "要讨论的群 id。**工作群**必须已经配齐优化员与审核员；**讨论群**建好即可。"
        ),
    )


@skill(
    name="team_start_discussion",
    display_name="让搭子们讨论（后台）",
    description=(
        "把话题交给一个群，让它们在里面**后台讨论**。调用后**立即返回**：用户可以接着"
        "做别的，讨论结束时结论会自动发回当前这条对话。用户说「你们讨论一下」"
        "「找几个人研究一下」「先议一议再告诉我」时用它。\n"
        "⚠️ **前置条件按群类型不同**（会被拒绝，别抱着试一下的心态调）：\n"
        "· **工作群**：必须先配齐「优化员」与「审核员」—— 顺序是 team_create_group 建群 → "
        "team_assign_group_roles 提交这两个角色的搭子 id → 才能调本技能；\n"
        "· **讨论群**：建好就能直接调，不需要配任何角色。\n"
        "没满足条件时本技能会直接报错并把缺什么告诉你。\n"
        "（本技能不负责建群：没有合适的群就先准备好，别把建群和开讨论挤在一步里。）"
    ),
    params_model=StartDiscussionParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队", "群聊"],
)
class TeamStartDiscussionSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = StartDiscussionParams(**params)
        team = ctx.service("team")

        try:
            started = await team.start_discussion(
                group_id=args.group_id.strip(),
                topic=args.topic,
                origin_session_id=ctx.session_id or "",
                origin_assistant_id=ctx.assistant_id,
            )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc

        return {
            "started": started,
            "group_id": started["group_id"],
            "message": (
                f"已经在后台开始讨论「{started['group_name']}」。"
                "你现在可以继续做别的事 —— 讨论结束后我会把结论发回这条对话。"
            ),
        }





class RestructureUpdateItem(BaseModel):
    assistant_id: str = Field(..., min_length=1, description="要改设定的搭子 id（来自 team_list_assistants）")
    identity_append: str = Field("", description="追加到 IDENTITY.md 的职责/能力")
    rules_append: str = Field(
        "",
        description="追加到 RULES.md 的规则与边界（只追加；不要动它已有的规则，尤其那段「全员进化」的原始规则）",
    )
    tone_append: str = Field("", description="追加到 SOUL.md 的语气")


class RestructureCreateItem(BaseModel):
    name: str = Field(..., min_length=1, description="新搭子名字")
    description: str = Field(..., min_length=1, description="简介（写清它负责什么、有什么能力）")
    identity: str = Field("", description="身份（它是谁、定位是什么）")
    abilities: str = Field("", description="能力清单（它具体会做什么）")
    rules: str = Field("", description="工作规则与边界")
    tone: str = Field("", description="语气风格")
    emoji: str = Field("🤖", description="头像 emoji")
    group_role: Literal["", "coordinator", "worker", "advisor", "reviewer"] = Field(
        "", description="群角色；拉进群做分工才填，单独助手留空"
    )
    skills: list[str] = Field(default_factory=list, description="技能子集（留空=全部技能）")


class TeamRestructureParams(BaseModel):
    group_id: str = Field(..., min_length=1, description="要重塑的群 id（来自 team_list_assistants 的 groups）")
    update: list[RestructureUpdateItem] = Field(default_factory=list, description="要改设定的现有成员")
    create: list[RestructureCreateItem] = Field(default_factory=list, description="要新建并拉进群的搭子")
    add_member_ids: list[str] = Field(default_factory=list, description="额外要拉进群的已有搭子 id")
    speaking_order: list[str] = Field(
        default_factory=list, description="最终发言顺序（含新老成员 id；留空=原顺序 + 新成员追加到末尾）"
    )


@skill(
    name="team_restructure",
    display_name="重塑团队",
    description=(
        "**总管（协调者）专用**：策划完成后**立刻**重新规划团队，把整个团队围绕任务核心"
        "调整为最佳配置——改现有成员的职责/规则、新建搭子并拉进群、把成员调整到正确的"
        "发言序列位置。\n"
        "用法：先 team_list_assistants 查看现有群成员的设定与技能配置，判断「围绕这个任务"
        "团队还差什么、谁该多担什么、顺序对不对」，再据此调整。一次调用可同时做这三类"
        "调整，每个动作都可选、按需传。改/建都是**追加**语义，不删减。\n"
        + evolution.APPEND_ONLY_CLAUSE
    ),
    params_model=TeamRestructureParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队", "群聊"],
)
class TeamRestructureSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = TeamRestructureParams(**params)
        if not any([args.update, args.create, args.add_member_ids, args.speaking_order]):
            raise SkillExecutionError(
                "至少要给一项要调整的（改成员设定 / 建新搭子 / 拉人进群 / 发言顺序）。"
            )
        team = ctx.service("team")
        updated: list[dict[str, Any]] = []
        created_ids: list[str] = []
        add_ids: list[str] = []
        try:
            for item in args.update:
                
                
                
                
                
                res = await team.append_assistant_setup(
                    assistant_id=item.assistant_id,
                    identity_append=item.identity_append,
                    rules_append=item.rules_append,
                    tone_append=item.tone_append,
                    actor_id=ctx.assistant_id,
                )
                updated.append({"assistant_id": item.assistant_id, "appended": res.get("appended", [])})

            for item in args.create:
                res = await team.create_assistant(
                    name=item.name,
                    description=item.description,
                    identity=item.identity,
                    abilities=item.abilities,
                    rules=item.rules,
                    tone=item.tone,
                    emoji=item.emoji,
                    skills=item.skills,
                    group_role=item.group_role,
                    actor_id=ctx.assistant_id,
                )
                created_ids.append(res["id"])

            add_ids = [*created_ids, *args.add_member_ids]
            if add_ids or args.speaking_order:
                await team.update_group(
                    group_id=args.group_id,
                    add_member_ids=add_ids or None,
                    speaking_order=args.speaking_order or None,
                    actor_id=ctx.assistant_id,
                )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc

        return {
            "ok": True,
            "group_id": args.group_id,
            "updated": updated,
            "created": created_ids,
            "message": (
                f"团队重塑完成：改了 {len(updated)} 个成员的设定、新建 {len(created_ids)} 个搭子"
                + ("，并拉进群调好了顺序。" if (add_ids or args.speaking_order) else "。")
            ),
        }


class EnsureRequiredSkillsParams(BaseModel):
    assistant_ids: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "要统一补装必装技能 / 强加策划类规则的搭子 id 列表（来自 team_list_assistants 的结果）。"
        ),
    )


@skill(
    name="team_ensure_required_skills",
    display_name="补装必装技能",
    description=(
        "把策划类搭子的**必装技能**与**策划类规则**交给系统统一确保（事后兜底）。\n"
        "当你不确定自己建的那些搭子有没有装齐必装技能（self_growth / ai_thinking_mode / "
        "team_restructure）、或规则里缺了「策划前用 ai_thinking_mode、策划后用 team_restructure "
        "重塑团队」时，把它们的 id 传进来，系统统一补装 + 强加规则条款。\n"
        + evolution.APPEND_ONLY_CLAUSE
    ),
    params_model=EnsureRequiredSkillsParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队"],
)
class TeamEnsureRequiredSkillsSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = EnsureRequiredSkillsParams(**params)
        team = ctx.service("team")
        try:
            result = await team.ensure_required_skills(
                assistant_ids=args.assistant_ids,
                actor_id=ctx.assistant_id,
            )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc
        return {
            "result": result,
            "message": (
                f"已对 {len(result['assistants'])} 个搭子统一确保必装技能与策划类规则。"
                "必装技能（self_growth / ai_thinking_mode）属「内置技能」——"
                "每个搭子创建时就自带，不需要、也不能靠可用能力清单去添加。"
            ),
        }

















class GroupThreadCreateParams(BaseModel):
    group_id: str = Field(
        ...,
        min_length=1,
        description="给哪个群开新对话（id 来自 team_list_assistants 的 groups[].id）",
    )
    title: str = Field(
        "",
        description=(
            "这条对话叫什么。**起一个一眼能看出聊的是什么的名字**（例如「这周的学习计划」"
            "「预算复盘」）—— 一个群里会有多条对话，名字是用户唯一的区分依据，"
            "叫成「新对话」等于没起。留空则自动叫「新对话」。"
        ),
    )


@skill(
    name="team_create_group_thread",
    display_name="新建群对话",
    description=(
        "在一个**已有的群**里开一条新对话（一个群可以有多条互不相干的对话流）。\n"
        "⚠️ 开出来的是**空对话**：里面没有任何上下文，不会接着上一轮聊。\n"
        "什么时候用：上一件事已经聊完、现在要开一件**不相干**的新事；"
        "或者用户明确说「开个新对话」。\n"
        "什么时候**不要**用：只是接着刚才的话题往下说 —— 那直接在原来那条里说就行，"
        "另开一条会把上下文切断。\n"
        "group_id 必须来自 team_list_assistants 的结果。"
    ),
    params_model=GroupThreadCreateParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队", "群聊"],
)
class TeamCreateGroupThreadSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = GroupThreadCreateParams(**params)
        team = ctx.service("team")
        try:
            return await team.create_group_thread(
                group_id=args.group_id,
                title=args.title.strip(),
                actor_id=ctx.assistant_id,
            )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc


class GroupThreadRenameParams(BaseModel):
    group_id: str = Field(..., min_length=1, description="对话所属的群 id")
    thread_id: str = Field(
        ...,
        min_length=1,
        description=(
            "要改名的对话 id —— 必须来自 team_list_assistants 的 groups[].threads，"
            "**不要靠「最近一条」猜**"
        ),
    )
    title: str = Field(
        ...,
        min_length=1,
        description="新名字（要具体，能看出这条对话聊的是什么）",
    )


@skill(
    name="team_rename_group_thread",
    display_name="修改群对话名",
    description=(
        "改一条群对话的名字。\n"
        "⚠️ 要改哪条**由 `thread_id` 决定**，所以必须先从 team_list_assistants 的"
        " groups[].threads 里拿到它 —— 猜错一条就是把用户另一条对话改了名，"
        "而且界面上不会有任何提示。\n"
        "名字是用户在一个群里区分多条对话的唯一依据，起得具体一点。"
    ),
    params_model=GroupThreadRenameParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队", "群聊"],
)
class TeamRenameGroupThreadSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = GroupThreadRenameParams(**params)
        team = ctx.service("team")
        try:
            return await team.rename_group_thread(
                group_id=args.group_id,
                thread_id=args.thread_id,
                title=args.title,
                actor_id=ctx.assistant_id,
            )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc


class GroupThreadClearParams(BaseModel):
    group_id: str = Field(..., min_length=1, description="对话所属的群 id")
    thread_id: str = Field(
        ...,
        min_length=1,
        description="要清空的对话 id（来自 team_list_assistants 的 groups[].threads）",
    )


@skill(
    name="team_clear_group_thread",
    display_name="清空群对话内容",
    description=(
        "把一条群对话的**记录清空**，对话本身还在（可以接着往下聊）。\n"
        "⚠️ **不可逆**，删掉的记录找不回来。做之前先跟用户确认一次 —— "
        "除非他明确说了「清空/清掉」。\n"
        "⚠️ 与 team_delete_group_thread 的区别：这个是**清内容、留对话**，"
        "那个是**连对话一起删掉**。目的只是「清掉记录」时用这个。"
    ),
    params_model=GroupThreadClearParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队", "群聊"],
)
class TeamClearGroupThreadSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = GroupThreadClearParams(**params)
        team = ctx.service("team")
        try:
            return await team.clear_group_thread(
                group_id=args.group_id,
                thread_id=args.thread_id,
                actor_id=ctx.assistant_id,
            )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc


class GroupThreadDeleteParams(BaseModel):
    group_id: str = Field(..., min_length=1, description="对话所属的群 id")
    thread_id: str = Field(
        ...,
        min_length=1,
        description="要删除的对话 id（来自 team_list_assistants 的 groups[].threads）",
    )


@skill(
    name="team_delete_group_thread",
    display_name="删除群对话",
    description=(
        "删掉一条群对话，**连带它的全部记录**（不可恢复）。\n"
        "⚠️ 做之前先跟用户确认一次 —— 除非他明确说了「删掉那条对话」。\n"
        "⚠️ 只删对话，**不删群**：群本身和它其余对话都不受影响。"
        "要动整个群请用 team_restructure 那一组。\n"
        "⚠️ 一个群的**最后一条**对话删不掉（删了群就空了，用户点进去一片空白）—— "
        "只想清掉内容的话用 team_clear_group_thread。"
    ),
    params_model=GroupThreadDeleteParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队", "群聊"],
)
class TeamDeleteGroupThreadSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = GroupThreadDeleteParams(**params)
        team = ctx.service("team")
        try:
            return await team.delete_group_thread(
                group_id=args.group_id,
                thread_id=args.thread_id,
                actor_id=ctx.assistant_id,
            )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc

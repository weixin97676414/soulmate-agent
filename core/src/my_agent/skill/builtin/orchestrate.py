"""搭子团队技能：AI 自己组队，并把群讨论挪到后台跑。

## 为什么要有它们

用户的原话是「让 AI 自己建搭子、自己组群」。没有这些技能时，用户说"你们几个
讨论一下"，模型只能回"请你自己到左侧新建搭子、再建一个群" —— 而这恰恰是零基础
用户最卡的一步。有了它，一句"帮我找几个搭子讨论下这周的学习计划"就够了。

## ⚠️ 建之前必须先查（用户明确要求）

> 需要在确认之前拉取现有搭子的名称列表与简介列表，如果有功能相同的则使用现有的，
> 没有合适的需要补充的时候才进行创建

这条**不能**只写在描述里 —— 光提醒的话，模型照样会建出第三个「资料整理助手」。
所以规则同时落在三处：

1. ``team_list_assistants`` 这个技能本身（模型得先调它才看得到清单）；
2. ``team_create_group`` 的**返回体**里带上现有搭子清单（清单会出现在它眼前）；
3. ``Orchestrator.create_assistant`` 里**同名直接拒绝**（硬约束，绕不过去）。

## ⚠️ 审核员 / 优化顾问：少了就走不动（产品要求加的那一环）

以前"要不要审核员"是 ``team_create_group`` 上的一个布尔参数，模型一句
``require_reviewer=false`` 就带过去了。现在这一步被拆成**独立的、绕不过去的工具**：

    ① team_create_group          建群
    ② team_assign_group_roles    提交审核员 + 优化顾问的搭子 id（没有"不需要"这个选项）
    ③ team_start_discussion      才能开讨论

系统**不再替你补通用角色**：确实没有合适的搭子时，自己用 ``team_create_assistant``
建（``group_role`` 填 reviewer / advisor），再提交 id。闸门在
``Orchestrator.start_discussion`` 上 —— 没配齐一律拒绝，并把缺什么说清楚。

## 权限分级

- 查（``team_list_assistants`` / 群清单）：safe，只读；
- 建搭子 / 建群 / 提交群角色 / 排顺序 / 起讨论：**confirm** 级。

写操作标 confirm 是本项目的本分（它真的会改配置），而**出厂默认已经是
「自动批准」**，所以日常使用**不会**被弹框打断 —— 只有用户主动把确认模式切回
「每次确认」时才会问一句，那时他本来就希望被问。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ...assistants import evolution
from ...errors import SkillExecutionError
from ...skill.base import BaseSkill, SkillContext
from ...skill.decorator import skill

# 起讨论是"后台跑、立刻返回"，所以不带任何轮数/时长参数：
# 成本闸由群讨论自己的安全阀负责（见 routes/groups.py 的 MAX_ROUNDS）。


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
        "（群的成员带 id，以及该群**审核员 / 优化顾问**确认了没有）。\n"
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
            # 把规则原文带回去，模型下一次就知道该怎么做了（而不是只看到"失败了"）
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
        ..., min_length=1, description="要补充设定的搭子 id（来自 team_list_assistants 的结果）"
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
    description_append: str = Field(
        "", description="追加到简介末尾的内容（新增能力时同步更新简介，界面才看得到）"
    )


@skill(
    name="team_update_assistant",
    display_name="补充搭子设定",
    description=(
        "在**现有**搭子的设定上补充能力与规则（用于「这个搭子还差点什么，给它加上」）。\n"
        "只能**追加**，不能删改原有内容 —— 要删除只能由用户自己在设置页操作。\n"
        "调用前先 team_list_assistants 看它现在有哪些设定，避免重复补充。\n"
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
        if not any(
            [
                args.identity_append.strip(),
                args.rules_append.strip(),
                args.tone_append.strip(),
                args.description_append.strip(),
            ]
        ):
            raise SkillExecutionError(
                "至少要给一段要补充的内容（identity_append / rules_append / "
                "tone_append / description_append 之一）。"
            )
        team = ctx.service("team")
        try:
            result = await team.append_assistant_setup(
                assistant_id=args.assistant_id,
                identity_append=args.identity_append,
                rules_append=args.rules_append,
                tone_append=args.tone_append,
                description_append=args.description_append,
                actor_id=ctx.assistant_id,
            )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc
        return {
            "updated": result,
            "message": (
                f"已给「{args.assistant_id}」补上设定（原有内容一个字都没动）："
                f"{'、'.join(result['appended']) or '简介'}。"
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
    # confirm：产品约定是「总管建与改可以直接做，**删除要你点头**」。
    # 落在这个既有的确认机制上，而不是另造一套"删除前先问一句"的流程 ——
    # 那种靠模型自觉的问法，模型一步就能带过去（本项目为此吃过教训）。
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
            # 连带影响原样带上（**不替它总结成"删好了"**）：顺手删了一个群这件事，
            # 比"删了那个搭子"本身更需要被说出来
            "message": result["message"] + " 请如实把上面的连带影响告诉用户。",
        }


class GroupCreateParams(BaseModel):
    name: str = Field(..., min_length=1, max_length=48, description="群名称，例如「学习计划讨论组」")
    member_ids: list[str] = Field(
        ...,
        min_length=2,
        description="成员搭子的 id 列表（**必须来自 team_list_assistants 的结果**，至少两个）",
    )
    coordinator_id: str = Field(
        ...,
        min_length=1,
        description=(
            "**这个群的总管（协调者）搭子 id**：必须是 member_ids 里的一个，不能空着。"
            "**想自己当总管，就得先把你自己也写进 member_ids** —— 你不能在群里没有席位，"
            "却以总管自居（分工会被系统按成员名单判定，你说的和实际不一致时算你错）。"
            "id 必须来自 team_list_assistants 的结果。"
        ),
    )
    speaking_order: list[str] = Field(
        default_factory=list, description="发言顺序（成员 id 的子集）；留空按上面给的顺序"
    )


@skill(
    name="team_create_group",
    display_name="建群（拉搭子进群）",
    description=(
        "把几个搭子拉进一个群。成员 id 必须来自 team_list_assistants 的结果。\n"
        "⚠️ **总管必须指名道姓**：coordinator_id 要填一个真实的搭子 id，而且它必须也在"
        " member_ids 里 —— 想自己当总管，就得把**你自己**也写进 member_ids（一个群可以"
        "把你也算作成员）。不能空着，也不能嘴上自称总管却不在群里。\n"
        "⚠️ **建群只是第一步，建完必须接着做第二步**：调 team_assign_group_roles 把"
        "「审核员」与「优化顾问」的搭子 id 提交上来 —— 这一步**没有「不需要」这个选项**，"
        "而且**没提交之前 team_start_discussion 一定会被拒绝**。\n"
        "第二步怎么选人：有合适的现有搭子就直接复用它的 id；没有就用 team_create_assistant "
        "建一个带具体规则的（group_role 分别填 reviewer / advisor，规则里写清「这个任务"
        "怎么算达标」这类具体判据），再把新搭子的 id 提交上去。\n"
        "⚠️ 团队角色要齐：总管（coordinator，做策划与分工）、执行者（worker）、"
        "优化顾问（advisor）、审核员（reviewer）。顺序上优化顾问在审核员之前（倒数第二）、"
        "审核员在最后。\n"
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
            )
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc
        coordinator = created.get("coordinator") or {}
        return {
            "created": created,
            "message": (
                f"已建群「{created['name']}」（id={created['id']}）。"
                + (
                    f"本群总管是「{coordinator.get('name')}」"
                    "（讨论时按这个分工走，别把自己当总管）。"
                    if coordinator
                    else ""
                )
                + "**下一步必须调 team_assign_group_roles**，把这个群的审核员与优化顾问的"
                "搭子 id 提交上来（没有合适的搭子就先建一个再提交）；提交之后才能用 "
                "team_start_discussion 把话题抛进去。"
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
        "⚠️ **这是建群之后绕不过去的一步**：任务群必须配齐这两个角色，**没有「不需要」"
        "这个选项**，系统也不会替你补通用角色 —— 你只能指一个真实的搭子出来：\n"
        "1. 先 team_list_assistants 看清楚现有搭子的 id、简介与**它当前的角色"
        "（group_role）**：已经是审核员 / 优化顾问的，直接复用；\n"
        "2. 没有合适的就用 team_create_assistant 建一个（group_role 填 reviewer / advisor，"
        "规则里写清这个任务的具体判据）；\n"
        "3. 再用这个技能把两个 id 提交上来。\n"
        "提交成功后系统会记住，你才能用 team_start_discussion 开讨论。\n"
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
            # **不静默**：角色跟着人一起走了，模型必须知道开讨论前得重新提交 id
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
        description="要讨论的群 id。群必须已经建好**并且配齐了审核员与优化顾问**。",
    )


@skill(
    name="team_start_discussion",
    display_name="让搭子们讨论（后台）",
    description=(
        "把话题交给一个群，让它们在里面**后台讨论**。调用后**立即返回**：用户可以接着"
        "做别的，讨论结束时结论会自动发回当前这条对话。用户说「你们讨论一下」"
        "「找几个人研究一下」「先议一议再告诉我」时用它。\n"
        "⚠️ **前置条件（会被拒绝，别抱着试一下的心态调）**：群里必须先配齐「审核员」与"
        "「优化顾问」—— 顺序是 team_create_group 建群 → team_assign_group_roles 提交这两个"
        "角色的搭子 id → 才有资格调用本技能。没配齐时本技能会直接报错并把缺什么告诉你。\n"
        "（本技能不负责建群：没有合适的群就先按上面三步准备好，别把建群和开讨论挤在一步里。）"
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


# --------------------------------------------------------------------------- #
# 重塑团队（总管专用）：改成员设定 + 建新搭子 + 拉进群调序列，一次调用按需组合
# --------------------------------------------------------------------------- #
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
                # ⚠️ 方法名必须是 `append_assistant_setup` —— `Orchestrator` 上
                # **没有** `update_assistant`（那个名字是路由层的 HTTP 端点）。
                # 2026-10-06 实测：名字写错时这一整条技能每次调用都 AttributeError
                # 失败，而审计日志里只留一行"工具 team_restructure 执行出错"，
                # 看起来像"模型用错了工具"，查起来要一路翻到 Orchestrator 才发现。
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


# --------------------------------------------------------------------------- #
# 群对话（AI 也要能管一个群里的多条对话）
# --------------------------------------------------------------------------- #
#
# ⚠️ 这一组**只动「对话」，不动「群」**（用户划的边界："对话名右键的功能是管这
# 一个对话"）。要动整个群，用 team_restructure 那一组。
#
# ⚠️ 四个技能一律同时要 `group_id` 与 `thread_id`，而且都在描述里写明
# "id 必须来自 team_list_assistants 的结果" —— 模型编一个 id 的代价是当场报错，
# 而**用错一条**的代价是它安静地改了另一条对话，用户回头才发现。
#
# ⚠️ "清空"与"删除"的区别必须写在描述里：两者都不可逆，但清空之后那条对话还在
# （能接着聊），删除之后它就没了。模型混用这两个词时，用户的损失是不一样的。


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

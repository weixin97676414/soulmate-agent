"""搭子团队：AI 自己组队 + 后台把讨论跑完，结论送回发起它的那条对话。

## 为什么要有它

用户对着一个搭子说「你们讨论一下」时，如果讨论只能在前台流式跑，他就必须
**盯着群聊页**看完整个过程 —— 而他真正要的只是结论。所以：

- 单聊里的搭子可以自己**建搭子、建群**（编排技能见 ``skill/builtin/orchestrate.py``）；
- 讨论挪到**后台**跑：单聊立刻回一句"已经在后台开始"，用户接着做别的事；
- 讨论的每条事件仍然**落库**（重开页面还能看到完整过程），并经全局事件流
  **广播**（只读观察窗靠它实时看到讨论）；
- 跑完把结论**写回发起它的那条会话**，并推 ``group_task_done`` 让界面刷新或提示。

## 权限口径

后台无人值守，理由与定时任务完全相同（见 ``agent/scheduler.py``）：没有确认通道，
不放开 admin 级就只能"拒绝执行"。所以后台那一场把成员 ctx 建成
``auto_approve`` + ``allow_admin=True``（见 ``routes/groups.py::_build_group_agent``）。
⚠️ 那是**按次**放开，绝不动 ``PermissionGuard`` 上的进程级开关。

## 为什么讨论引擎是"按需导入"

引擎住在 ``server/routes/groups.py`` —— 它当初只为 HTTP 流式而生。要彻底理顺得把
引擎搬到 ``agent/`` 下，那会牵动确认通道、进度落库、事件广播三处，属于独立的一轮
重构，不夹在本次里做。这里用函数内导入，同时避开 ``runtime ↔ 路由`` 的环形依赖
（``server/runtime.py`` 要构造本类，而路由要 ``runtime``）。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from ..assistants import evolution, lifecycle, locked_builtins
from ..assistants.persona import IDENTITY_FILE, RULES_FILE, SOUL_FILE, read_file
from ..config.schemas import AssistantProfile, GroupProfile
from ..skill import groups
from ..skill.builtin import xjx
from ..skill.custom import known_skill_names
from ..storage import images

logger = logging.getLogger(__name__)


# 策划类搭子的强制规则条款（系统强加，不依赖 AI 写）：
# 产品要求「策划类的规则里必须有」这些条款，且"必须有"。
_THINKING_RULE = (
    "开始策划前必须先调用 ai_thinking_mode 技能（AI 思考模式·道家做局思维）进行分析梳理。"
)
_RESTRUCTURE_RULE = (
    "策划完成后必须调用 team_restructure 技能重塑团队：先查看现有群成员的设定与技能配置，"
    "再围绕任务核心把团队调整为最佳配置。"
)

# ---- 档案字段的边界（昵称 / 图标 / 头像 / 温度）------------------------ #
#
# 昵称上限。名字会被拼进 system prompt（``persona.build_persona_section`` 的
# nickname），所以这不是单纯的长度限制：**限长 + 不许换行**是防"把一长串指令
# 塞进名字里"最便宜的那道闸。超了直接拒绝、不截断 —— 截出来的名字用户认不出
# 是自己起的哪一个。
MAX_NICKNAME_CHARS = 24
# 图标允许的码点数。有的表情是组合出来的（👨‍👩‍👧 要 5 个码点），
# 卡到"一个字符"会把完全正常的表情判成非法。
MAX_EMOJI_CHARS = 8
# 头像大小上限。它是要**写进 assistants.json** 的 data URL（前端每次启动都读它），
# 所以刻意比"发给模型的图片"（8MB）小得多。
#
# ⚠️ 核心不做图像缩放（不引 Pillow、也不去拉外部解释器，理由见 storage/images），
# 所以超过这个数的图**只能明确报错**，由模型如实转告用户"换张小图或先压缩"。
AVATAR_MAX_BYTES = 512 * 1024

# 群角色的中文名（工具返回体、报错、留痕都用它 —— 别在代码里各写一份）。
_ROLE_NAMES: dict[str, str] = {
    "coordinator": "协调者（总管）",
    "worker": "执行者",
    "reviewer": "审核员",
    "advisor": "优化顾问",
}


class Orchestrator:
    """组队与后台讨论。

    技能只认这一层门面（与 ``tasks`` / ``calendar`` 是同一个套路）：技能拿不到
    runtime，也不该拿到 —— 它一旦能改任意配置，"这个技能刚才到底干了什么"就再也
    说不清了。这里只暴露六件事：看现有搭子/群、建搭子、建群、**提交群角色确认**
    （审核员 / 优化顾问）、排发言顺序、起讨论。
    """

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        # 在跑的后台讨论：group_id → 任务。留着它们只为一件事 ——
        # 应用退出时能收干净，不留悬挂的协程。
        self._tasks: dict[str, asyncio.Task[None]] = {}

    # ------------------------------------------------------------------ #
    # 看
    # ------------------------------------------------------------------ #
    @property
    def running(self) -> list[str]:
        """正在后台跑讨论的群 id（界面与排查都用得到）。"""
        return [group_id for group_id, task in self._tasks.items() if not task.done()]

    def list_assistants(self, *, assistant_id: str = "") -> list[dict[str, Any]]:
        """现有搭子的**完整设定**：名称、简介、技能，以及身份 / 规则 / 语气三份全文。

        这是用户两条要求的落点：

        1. **建之前先查**（没有它，模型只能凭想象建新的，"资料整理小助手"会被重复建五份）；
        2. **判断谁适合这次任务**（用户原话）：光看一句简介判断不了能不能担事，
           要能看到它的身份、能力与规则，也才知道该"在原有设定上增补"什么。

        全文返回、不做截断：单文件本来就有 32KB 上限（见 persona.MAX_FILE_BYTES），
        搭子数量是个位数，成本可控 —— 而"给 AI 的东西不能被省略"是本项目的硬口径。
        """
        runtime = self._runtime
        wanted = assistant_id.strip()
        result: list[dict[str, Any]] = []
        for item in runtime.assistants.sorted():
            if wanted and item.id != wanted:
                continue
            entry: dict[str, Any] = {
                "id": item.id,
                "name": item.nickname or item.name,
                "description": item.description,
                "skills": list(item.enabled_skills),
                # 角色要看得见：AI 得据此判断"谁已经是审核员/优化顾问、可以直接复用"，
                # 也得知道"这个人已经是总管了，不能再顶别的角色"（提交时会拒绝）
                "group_role": item.group_role,
            }
            for label, file_name in (
                ("identity", IDENTITY_FILE),
                ("rules", RULES_FILE),
                ("tone", SOUL_FILE),
            ):
                try:
                    entry[label] = read_file(runtime.paths, item.id, file_name).strip()
                except (OSError, ValueError) as exc:
                    # 读不出来时如实说明，而不是给个空串让模型以为"这个搭子没设定"
                    entry[label] = ""
                    entry.setdefault("read_errors", []).append(f"{file_name}: {exc}")
            result.append(entry)
        return result

    async def list_groups(self) -> list[dict[str, Any]]:
        """群清单（含每个群的**对话**列表）。

        ⚠️ 这是 async 的：对话要从库里读（`group_thread_repo.list_threads`）。
        在此之前它只读内存里的 ``runtime.groups``，所以是同步的。

        **为什么必须带上对话**：AI 现在能改名 / 清空 / 删除
        群对话，而这三个操作都要 ``thread_id``。清单里没有的话，它只能靠"最近一条"
        去猜 —— 而"改群对话名"改错一条，用户回头看到的是**另一条对话被改了名**，
        那种错没有任何提示。
        """
        runtime = self._runtime
        groups: list[dict[str, Any]] = []
        for item in runtime.groups.groups:
            threads: list[dict[str, Any]] = []
            if runtime.db_ready:
                try:
                    rows = await runtime.group_thread_repo.list_threads(item.id)
                except Exception as exc:  # noqa: BLE001 - 读不到对话不该让整份清单失败
                    logger.warning("读取群对话列表失败 group=%s: %s", item.id, exc)
                    rows = []
                threads = [
                    {"id": row["id"], "title": row["title"], "updated_at": row["updated_at"]}
                    for row in rows
                ]
            groups.append(
                {
                    "id": item.id,
                    "name": item.name,
                    # 成员**同时**给 id 与名字：提交角色时（team_assign_group_roles）要的是 id，
                    # 只给名字的话模型只能靠猜，猜错就是一次白跑
                    "members": [
                        {"id": member_id, "name": self._display_name(member_id)}
                        for member_id in item.member_assistant_ids
                    ],
                    # 角色配齐没有：没配齐的群开不了讨论，先列出来免得模型来回试
                    "roles": {
                        "reviewer": self._role_brief(item.reviewer_id),
                        "advisor": self._role_brief(item.advisor_id),
                    },
                    # 该群的对话（最近有动静的排前面）。要改/删/清某条对话时，
                    # `thread_id` 从这里的 id 取，**不要自己编、也不要靠"最近一条"猜**
                    "threads": threads,
                }
            )
        return groups

    def _role_brief(self, assistant_id: str) -> dict[str, Any] | None:
        """群角色（审核员 / 优化顾问）的简报：未提交返回 None，提交过给出 id 与名字。"""
        cleaned = (assistant_id or "").strip()
        if not cleaned:
            return None
        return {"id": cleaned, "name": self._display_name(cleaned)}

    def _display_name(self, assistant_id: str) -> str:
        profile = self._runtime.assistants.get(assistant_id)
        if profile is None:
            # 成员被删掉了但群定义还留着：如实显示 id，不假装它还在
            return f"{assistant_id}（已删除）"
        return profile.nickname or profile.name

    # ------------------------------------------------------------------ #
    # 组队
    # ------------------------------------------------------------------ #
    def _ensure_library_checked(self, from_import: bool) -> None:
        """新建搭子 / 建群之前必须**先查过官网搭子库**（产品约定）。

        为什么做成抛错而不是写进工具描述：写描述里模型照样会直接建
        （与"必须先提交审核员 id"是同一个教训）。

        两个刻意的放宽：

        - ``from_import`` 时放行 —— 导入这条路本身就是"已经用上现成的了"
          （用户上传的包、或从官网拉下来的包），再要求先查一遍没有意义；
        - **只要求"查过"，不要求"查到"** —— 官网连不上时不该把用户的手脚也绑住。
          代价是要求 AI 如实说明"官网未查到（原因），将自行创建"，不许假装查过。
        """
        if from_import:
            return
        library = getattr(self._runtime, "buddy_library", None)
        if library is None or library.checked:
            return
        raise ValueError(
            "新建之前必须先**查一遍官网搭子库**：先调 buddy_library_list，"
            "看官网有没有现成的搭子 —— 有合适的就用 buddy_import 直接导进来"
            "（技能包会一起装好），一个合适的都没有再自己建。"
            "如果读取官网失败，也要在回复里说明「官网未查到（附原因），我将自行创建」，"
            "不要跳过这一步。"
        )

    async def create_assistant(
        self,
        *,
        name: str,
        description: str = "",
        identity: str = "",
        abilities: str = "",
        rules: str = "",
        tone: str = "",
        emoji: str = "🤖",
        skills: list[str] | None = None,
        group_role: str = "",
        actor_id: str | None = None,
        from_import: bool = False,
    ) -> dict[str, Any]:
        """新建一个搭子，并把它**完整的设定**写进人格文件。

        ⚠️ 这里改过（2026-09-26 用户明确）：原先是"写一句 `你是 X` 就完事"，
        用户的评价是「仅给了一个简单的 soul 说明一句身份你是谁，再没有别的，这是不对的。
        AI 创建的搭子是要处理一定任务的，所以必须有完整的身份、功能、以及规则」。
        现在四块分开落：

        - ``IDENTITY.md``：身份 + **能力清单**（它到底会做什么）
        - ``RULES.md``：工作规则与边界
        - ``SOUL.md``：语气风格（按它的功能与任务来定，不是泛泛的"友好专业"）
        - ``assistants.json`` 的 ``description``：给**界面列表**看的能力摘要

        同名直接拒绝并让模型去看 ``list_assistants`` 的结果 —— 这不是"防呆"，
        而是把用户要求的那条规则（能复用就复用）变成**执行不动的硬约束**：
        光写在工具描述里，模型照样会建第二个「资料整理助手」。
        """
        runtime = self._runtime
        from ..skill.package import slugify

        self._ensure_library_checked(from_import)

        clean_name = name.strip()
        if not clean_name:
            raise ValueError("搭子得有个名字。")
        existing = [item for item in runtime.assistants.sorted() if item.name == clean_name]
        if existing:
            raise ValueError(
                f"已经有一个叫「{clean_name}」的搭子（id={existing[0].id}），"
                "直接用那个就好 —— 请先看一遍现有搭子清单，别建重复的。"
            )

        # 心鉴学专属技能**不允许**写进任何搭子的技能清单（
        # "非归属搭子不可见、不可用、无法添加"）。这里**明确报错**，而不是走下面
        # "未知技能进 ignored_skills"那条路 —— 后者会让模型以为自己只是写错了名字，
        # 于是换个写法再试一次；而真实原因是"这东西不该由你指定"。
        xjx.reject_reserved_skill_names(skills or [])

        wanted: list[str] = []
        dropped: list[str] = []
        # 与搭子保存校验同一个口径（含**指导型技能**）：模型给搭子配技能时
        # 随手写上一个已装的指导型技能是很自然的，用工具表判定会把它归进
        # dropped（"这些技能本机没有"）→ 模型收到一句错误的反馈后开始瞎改。
        known = known_skill_names(runtime)
        for item in skills or []:
            (wanted if item in known else dropped).append(item)

        # **别人的专属技能**同样不该写进新搭子的清单（补）。
        #
        # ⚠️ 这条路原先没做这件事：用户保存搭子那条会拒绝，但"AI 自己建搭子"
        # 不走那里 —— 于是模型顺手写上 `team_restructure` / `pmaster` 之类，
        # 名字会被静默落进档案，装配时又被归属过滤排除（不生效），
        # 而回报里写着"已配置"，模型与用户都以为配上了。
        #
        # ⚠️ 静默剔除、**不**报"本机没有"：这些名字都是真实存在的技能，
        # 说"没有"是在给模型一个错误的反馈（它会换个写法再试）。
        wanted = groups.without_exclusive(wanted)

        # ---- 策划类规则（硬约束，不是只写在描述里）----------------------- #
        #
        # ⚠️ 起**这里不再补任何"必装技能"**，两个原因：
        #
        # 1. 必装的那两个（`self_growth` / `ai_thinking_mode`）现在都划在「内置技能」里，
        #    而内置技能是**每个搭子恒有的**（不靠白名单勾选，见 `skill/groups.py`）——
        #    再"补"一遍是多余的。
        # 2. 旧写法的前提（"skills 为空 = 全部技能，必装已含在内"）已经作废：
        #    现在"没勾" = 只有内置技能（"以后没有默认加载全部技能的搭子了"）。
        #
        # 原先第三个必装 `team_restructure` 也一并去掉：它是搭子总管的**专属技能**
        # （`team_` 前缀，见 `skill/groups.py`），自定义搭子即便被写进白名单也拿不到
        # （装配时会被归属过滤排除）。留着只会造成"补了却没生效"的困惑。
        is_analysis = group_role in ("coordinator", "advisor") or any(
            keyword in (description + identity)
            for keyword in ("策划", "规划", "分析", "策略", "咨询", "顾问")
        )
        is_coordinator = group_role == "coordinator"

        # ---- 策划类规则条款（系统强加，不依赖 AI 写）--------------------- #
        #
        # 产品要求「策划类的规则里必须有」这些条款，且"必须有"。
        # 落点在 RULES.md：coordinator（总管）两条都有；advisor / 含策划关键词的
        # 搭子只强加 ai_thinking_mode 那一条。
        imposed_rules: list[str] = []
        if is_analysis:
            imposed_rules.append(_THINKING_RULE)
        if is_coordinator:
            imposed_rules.append(_RESTRUCTURE_RULE)
        # 「全员进化」的初始规则：自建搭子没有预置的进化任务，
        # 靠这一段让它自己主动问用户要不要建。与用户手工新建那条路共用同一份正文
        # （见 assistants/evolution.py），否则两条路会写出不一样的话。
        imposed_rules.append(evolution.evolution_rule(clean_name))
        if imposed_rules:
            rules = _merge_rules(rules, imposed_rules)

        profile = AssistantProfile(
            id=f"{slugify(clean_name, fallback='group')}-{uuid.uuid4().hex[:6]}",
            name=clean_name,
            description=description.strip(),
            emoji=emoji or "🤖",
            enabled_skills=wanted,
            # 角色只认白名单里的四个值（pydantic 的 Literal 也会挡，这里提前归一化，
            # 免得模型写个 "manager" 之类直接抛校验错误）
            group_role=group_role if group_role in ("coordinator", "worker", "reviewer", "advisor") else "",
            builtin=False,
        )
        config = runtime.assistants.model_copy(deep=True)
        config.upsert(profile)
        runtime.save_assistants(config)

        written, failed = self._write_setup_files(
            profile.id,
            profile.name,
            {
                IDENTITY_FILE: _identity_document(profile.name, identity, abilities),
                RULES_FILE: _rules_document(profile.name, rules),
                SOUL_FILE: _soul_document(profile.name, tone, description),
            },
        )

        await runtime.audit.op(
            kind="assistant",
            action="create",
            actor_id=actor_id,
            target=profile.id,
            detail=f"AI 新建搭子「{clean_name}」：{profile.description[:80] or '（没写简介）'}",
        )
        # 告诉所有窗口"搭子清单变了" —— 少了这条，新搭子要等用户手动刷新
        # 或者重启才会出现在左侧搭子栏与设置里（实测反馈正是这个：
        # "不是没放进去，而是没有自动刷新"）
        runtime.events.publish("assistants_changed", assistant_id=profile.id, action="create")

        result: dict[str, Any] = {
            "id": profile.id,
            "name": profile.name,
            "description": profile.description,
            "setup_files": written,
            # 必装技能状态：起必装那几个（self_growth / ai_thinking_mode）
            # 都划进「内置技能」，而内置技能是每个搭子**恒有**的 —— 不再有"补装"这一步。
            "required_skills": "已包含在内置技能中（每个搭子都有）",
        }
        if imposed_rules:
            result["imposed_rules"] = imposed_rules
        if dropped:
            # **不静默丢弃**：模型写了个不存在的技能名时，它得知道自己被忽略了什么，
            # 否则它会以为"技能装上了"，然后一直依赖一个不会生效的能力
            result["ignored_skills"] = dropped
        if failed:
            result["setup_errors"] = failed
        return result

    async def append_assistant_setup(
        self,
        *,
        assistant_id: str,
        identity_append: str = "",
        rules_append: str = "",
        tone_append: str = "",
        description_append: str = "",
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """在**现有设定上补充**能力与规则（用户要求：只能加、不能删）。

        「不能删减」不是靠提示词约束，而是**结构上做不到**：这个方法只接受"要追加的
        内容"，接口里根本没有"整份新文本"这个入口。要真删东西只能由用户自己在设置页改
        （那里有确认框，且是他自己的决定）。

        返回体里带上追加后的全文：模型据此确认"我要补的确实补上了"，
        用户也能在设置页看到同样的内容。
        """
        runtime = self._runtime
        from ..assistants.persona import write_file

        profile = runtime.assistants.get(assistant_id)
        if profile is None:
            raise ValueError(f"搭子「{assistant_id}」不存在（请先用 team_list_assistants 看清单）。")

        # 内置搭子的人设**写死**："追加"也算改，一并拒绝。
        # 在动手写之前**先全部判一遍**，而不是写一份判一份 —— 后者会在被锁的搭子上
        # 留下"第一份已经写进去了、第二份才报错"的半截状态。
        docs = (
            (IDENTITY_FILE, identity_append),
            (RULES_FILE, rules_append),
            (SOUL_FILE, tone_append),
        )
        for file_name, extra in docs:
            if extra.strip():
                locked_builtins.ensure_persona_writable(assistant_id, file_name)
        if description_append.strip():
            # 简介也是被锁的那一项（``LOCKED_FIELD_LABELS``）
            locked_builtins.ensure_mutable(assistant_id, changes=("description",))

        appended: list[str] = []
        failed: list[str] = []
        for file_name, extra in docs:
            text = extra.strip()
            if not text:
                continue
            try:
                current = read_file(runtime.paths, profile.id, file_name)
            except (OSError, ValueError):
                current = ""
            # 追加而不是覆盖：原内容一个字节都不动，新内容另起一段接在后面
            merged = f"{current.rstrip()}\n\n{text}\n" if current.strip() else f"{text}\n"
            try:
                write_file(runtime.paths, profile.id, file_name, merged)
                appended.append(file_name)
            except ValueError as exc:  # 超过 MAX_FILE_BYTES 之类的边界
                failed.append(f"{file_name}: {exc}")

        if description_append.strip():
            merged_description = f"{profile.description.rstrip()} {description_append.strip()}".strip()
            updated = profile.model_copy(update={"description": merged_description})
            config = runtime.assistants.model_copy(deep=True)
            config.upsert(updated)
            runtime.save_assistants(config)

        if appended or description_append.strip():
            await runtime.audit.op(
                kind="assistant",
                action="update",
                actor_id=actor_id,
                target=profile.id,
                detail=f"AI 补充搭子设定：{'、'.join(appended) or '简介'}",
            )
            runtime.events.publish("assistants_changed", assistant_id=profile.id, action="update")

        result: dict[str, Any] = {
            "id": profile.id,
            "appended": appended,
            "assistants": self.list_assistants(assistant_id=profile.id),
        }
        if failed:
            result["setup_errors"] = failed
        return result

    # ------------------------------------------------------------------ #
    # 档案字段：昵称 / 图标 / 头像 / 温度
    # ------------------------------------------------------------------ #
    # 实测反馈问题：AI 给自己"改了昵称"，但对话里显示的仍是旧名 ——
    # 因为它走的是 ``self_persona_update``，那条路只写人格 md 文件；而**界面上
    # 那个名字**来自这里（``assistants.json`` 的 nickname / emoji / avatar /
    # temperature）。所以档案字段必须有自己的一条路，并且写完要**通知界面刷新**。
    #
    # ⚠️ 与 ``append_assistant_setup`` 的分工要分清，**不要合并**：那边改的是人设
    # 文本（且只追加），这里改的是档案字段。合起来会变成"改个昵称顺手重写了人设"，
    # 那是用户明确不想看到的。

    async def update_assistant_profile(
        self,
        *,
        assistant_id: str,
        nickname: str | None = None,
        emoji: str | None = None,
        avatar_source: str = "",
        clear_avatar: bool = False,
        temperature: float | None = None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """改一个搭子的档案字段（至少要给一个；一个都没给就明确报错）。"""
        runtime = self._runtime
        profile = runtime.assistants.get(assistant_id)
        if profile is None:
            raise ValueError(
                f"搭子「{assistant_id}」不存在。要看现有清单请先调 team_list_assistants。"
            )

        changes: dict[str, Any] = {}
        done: list[str] = []

        if nickname is not None:
            clean = nickname.strip()
            if not clean:
                raise ValueError("昵称不能为空。想换名字就给一个新名字。")
            if len(clean) > MAX_NICKNAME_CHARS or "\n" in clean:
                raise ValueError(
                    f"昵称最多 {MAX_NICKNAME_CHARS} 个字且不能换行"
                    f"（当前给了 {len(clean)} 个字）。"
                )
            changes["nickname"] = clean
            done.append(f"昵称改为「{clean}」")

        if emoji is not None:
            clean = emoji.strip()
            if not clean or len(clean) > MAX_EMOJI_CHARS:
                raise ValueError(f"图标要是一个表情符号（最多 {MAX_EMOJI_CHARS} 个字符）。")
            changes["emoji"] = clean
            done.append(f"图标改为 {clean}")

        if temperature is not None:
            if not 0 <= temperature <= 2:
                raise ValueError(f"温度必须在 0 到 2 之间（当前给了 {temperature}）。")
            changes["temperature"] = temperature
            done.append(f"温度改为 {temperature}")

        if clear_avatar:
            changes["avatar"] = ""
            done.append("头像已清掉（回到用图标显示）")
        elif avatar_source.strip():
            # 三种来源（图片链接 / 本机路径 / 上传件的 id）统一交给 ``storage.images``，
            # 它只做"校验格式 + 限大小 + base64"（核心不引图像库，理由见该模块）
            try:
                _, data_url = await images.to_data_url(
                    avatar_source, max_bytes=AVATAR_MAX_BYTES, workspace=runtime.workspace
                )
            except images.ImageSourceError as exc:
                # 原样抛出去：模型需要把"为什么不行"如实转告用户，而不是含糊地重试
                raise ValueError(f"设置头像失败：{exc}") from exc
            # ⚠️ 只报**大小**，绝不把 data_url / base64 写进日志或错误信息
            # （几 MB 的 base64 一次就能把日志撑爆，见 storage/images 的说明）
            changes["avatar"] = data_url
            done.append(f"头像已换成这张图（{len(data_url) // 1024}KB）")

        if not changes:
            raise ValueError(
                "至少要给一个要改的字段：nickname / emoji / avatar_source / temperature。"
            )

        config = runtime.assistants.model_copy(deep=True)
        config.upsert(profile.model_copy(update=changes))
        runtime.save_assistants(config)
        await runtime.audit.op(
            kind="assistant",
            action="update",
            actor_id=actor_id,
            target=assistant_id,
            detail="AI 修改搭子档案：" + "、".join(done),
        )
        # 少了这条，用户切回对话时看到的还是旧名字 —— 他报的正是这个
        runtime.events.publish("assistants_changed", assistant_id=assistant_id, action="update")

        saved = runtime.assistants.get(assistant_id)
        return {
            "id": assistant_id,
            "changed": done,
            "nickname": saved.nickname if saved else "",
            "emoji": saved.emoji if saved else "",
            "temperature": saved.temperature if saved else None,
            "has_avatar": bool(saved.avatar) if saved else False,
        }

    async def delete_assistant(
        self, *, assistant_id: str, actor_id: str | None = None
    ) -> dict[str, Any]:
        """删除一个搭子（连带群成员 / 群角色 / 人格目录 / 默认位）。

        四位内置搭子删不掉：裁决在 ``lifecycle.delete_assistant``（三条删除路径的
        唯一汇合点），抛出的 ``LockedBuiltinError`` 是 ``ValueError`` 的子类，
        会被技能外壳原样转成给模型/用户看的一句话。


        用户口径（2026-09-28）：「总管」建与改可以直接做，**删除要先经过用户确认**
        —— 这条由技能侧的 ``confirm`` 权限保证（会弹确认框），不靠这里再判断一次。
        所以本方法只负责"确认之后干净地删掉"。

        实现落在 ``assistants/lifecycle.delete_assistant``：与设置页那个删除按钮
        是**同一份**实现（各写一遍的话，两条路迟早会长成两种行为）。
        """
        runtime = self._runtime
        try:
            report = lifecycle.delete_assistant(runtime, assistant_id)
        except KeyError:
            raise ValueError(
                f"搭子「{assistant_id}」不存在。要看现有清单请先调 team_list_assistants。"
            ) from None
        message = lifecycle.describe_report(report)
        await runtime.audit.op(
            kind="assistant",
            action="delete",
            actor_id=actor_id,
            target=assistant_id,
            detail=message,
        )
        # 连带影响**必须出现在返回体里**：模型只会照着自己拿到的结果说话，
        # 不给它"顺手删了一个群"，它就会报成"只删了一个搭子"
        return {**report, "message": message}

    async def ensure_required_skills(
        self,
        *,
        assistant_ids: list[str],
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """系统统一确保策划类搭子的必装技能 + 强加规则条款（事后兜底）。

        AI 建搭子时若不确定必装是否装上，可把搭子 id 交给系统，
        由系统统一补装必装技能、并把策划类规则条款写进 RULES。对每个搭子：
        - enabled_skills 非空 → 追加缺失的必装技能；
        - enabled_skills 空 → 保持空（= 全部技能，必装已含），但规则条款照强加。
        """
        from ..assistants.persona import write_file

        runtime = self._runtime
        # 同上：这个"事后兜底"要判断某技能在不在（already_have），口径必须与
        # 保存校验一致，否则会出现"校验时算存在、补装时算不存在"——
        # 于是每轮都在补装同一个技能，用户看到技能列表反复抖动。
        known = known_skill_names(runtime)
        results: list[dict[str, Any]] = []
        for assistant_id in assistant_ids:
            profile = runtime.assistants.get(assistant_id)
            if profile is None:
                results.append({"id": assistant_id, "error": "搭子不存在"})
                continue
            # 四位内置搭子的能力与人设**写死**（``locked_builtins``）：这个方法
            # 是"事后兜底"，恰恰是最容易被顺手绕过去的一条路 —— 它既会往
            # enabled_skills 里追技能，也会往 RULES.md 追规则条款。
            # 整个跳过并**如实报出来**：模型需要知道"这个搭子不用你补"，
            # 否则它会以为补装失败了、反复重试。
            if locked_builtins.is_locked(profile.id):
                results.append(
                    {
                        "id": assistant_id,
                        "name": profile.nickname or profile.name,
                        "skipped": True,
                        "error": locked_builtins.locked_persona_message(RULES_FILE),
                    }
                )
                continue
            is_analysis = profile.group_role in ("coordinator", "advisor") or any(
                keyword in (profile.description or "")
                for keyword in ("策划", "规划", "分析", "策略", "咨询", "顾问")
            )
            is_coordinator = profile.group_role == "coordinator"
            required: list[str] = ["self_growth"]
            if is_analysis:
                required.append("ai_thinking_mode")
            if is_coordinator:
                required.append("team_restructure")

            added: list[str] = []
            current = list(profile.enabled_skills)
            # ⚠️ 口径 变过：空**不等于**"全部技能"了（空 = 只有内置技能）。
            # 而必装的那两个本来就在内置技能里，所以"补装"其实已无必要 ——
            # 保留这段只是为了老配置（白名单非空）也能被补齐。
            # 另外 `team_restructure` 是搭子总管的**专属技能**，自定义搭子补了也拿不到
            # （装配时会被归属过滤排除，见 skill/groups.py）。
            if current:
                for name in required:
                    if name in known and name not in current:
                        current.append(name)
                        added.append(name)
                updated = profile.model_copy(update={"enabled_skills": current})
                config = runtime.assistants.model_copy(deep=True)
                config.upsert(updated)
                runtime.save_assistants(config)

            imposed: list[str] = []
            if is_analysis:
                imposed.append(_THINKING_RULE)
            if is_coordinator:
                imposed.append(_RESTRUCTURE_RULE)
            appended_rules: list[str] = []
            if imposed:
                try:
                    current_rules = read_file(runtime.paths, profile.id, RULES_FILE)
                except (OSError, ValueError):
                    current_rules = ""
                merged = _merge_rules(current_rules, imposed)
                if merged != current_rules:
                    try:
                        write_file(runtime.paths, profile.id, RULES_FILE, merged)
                        appended_rules = imposed
                    except ValueError as exc:
                        results.append({"id": assistant_id, "error": f"规则写失败：{exc}"})
                        continue

            results.append(
                {
                    "id": assistant_id,
                    "name": profile.nickname or profile.name,
                    "required_skills": required,
                    "added_skills": added,
                    "imposed_rules": appended_rules,
                }
            )

        if any(item.get("added_skills") or item.get("imposed_rules") for item in results):
            await runtime.audit.op(
                kind="assistant",
                action="update",
                actor_id=actor_id,
                target=",".join(assistant_ids),
                detail=f"系统统一补装必装技能/规则（{len(results)} 个搭子）",
            )
            runtime.events.publish("assistants_changed", action="update")
        return {"ok": True, "assistants": results}

    def _write_setup_files(
        self, assistant_id: str, name: str, documents: dict[str, str]
    ) -> tuple[list[str], list[str]]:
        """把设定写进人格文件；返回（写成功的、失败的）。

        失败**不抛**：文件写不进去（超长、磁盘只读）不该让"建搭子"这一步整体失败，
        但也不能装作没事 —— 失败清单会跟着返回值回到模型眼前。
        """
        from ..assistants.persona import write_file

        written: list[str] = []
        failed: list[str] = []
        for file_name, content in documents.items():
            try:
                write_file(self._runtime.paths, assistant_id, file_name, content)
                written.append(file_name)
            except (OSError, ValueError) as exc:
                logger.warning("写入搭子设定失败 %s/%s: %s", assistant_id, file_name, exc)
                failed.append(f"{file_name}: {exc}")
        return written, failed

    async def create_group(
        self,
        *,
        name: str,
        member_ids: list[str],
        coordinator_id: str = "",
        speaking_order: list[str] | None = None,
        actor_id: str | None = None,
        from_import: bool = False,
    ) -> dict[str, Any]:
        """建一个群，并把**现有搭子清单**一起返回。

        返回清单是关键：用户要求"建之前先拉取现有搭子的名称与简介，有合适的就复用"。
        把清单放进**返回体**而不只是写在描述里，"先查"这一步才会真的发生。

        ⚠️ 这里**不再有"要不要审核员/优化顾问"的参数**（产品约定）：
        以前是 AI 传 ``require_reviewer=False`` 一句就带过，现在改成建群后必须调
        ``assign_group_roles`` 把两个角色的搭子 id 交上来（见 ``start_discussion`` 的闸门）。

        ⚠️ 总管必须**指名道姓**：``coordinator_id`` 要给一个 id，而且
        它必须在这批 ``member_ids`` 里 —— 想自己当总管，就先把自己也写进成员。在这之前
        谁当总管是按发言位次（首位）兜底算的，模型嘴上自称总管、人却不在群里，用户看到的
        分工跟它说的不是一回事。空串只留给"用户手建的群 / 导入的群包"这类**没有模型在场**
        的路径，那时才回到位次兜底。
        """
        runtime = self._runtime
        from ..skill.package import slugify

        self._ensure_library_checked(from_import)

        clean_name = name.strip()
        if not clean_name:
            raise ValueError("群得有个名字。")

        members: list[str] = []
        missing: list[str] = []
        for member_id in member_ids:
            if runtime.assistants.get(member_id) is None:
                missing.append(member_id)
            elif member_id not in members:
                members.append(member_id)
        if len(members) < 2:
            raise ValueError(
                "一个群至少要两个搭子才讨论得起来。"
                f"（收到 {len(member_ids)} 个成员，其中可用 {len(members)} 个；"
                "搭子 id 请用 list_assistants 的结果，不要自己编。）"
            )

        # 指名道姓的总管：给了就必须是这批成员里的一个（见方法头部的说明）。
        if coordinator_id and not coordinator_id.strip():
            raise ValueError(
                "群总管不能是空白 id：给一个真实搭子的 id，或者（只有用户手建群那种场景）"
                "整个字段留空。"
            )
        coordinator = coordinator_id.strip()
        if coordinator and coordinator not in members:
            if actor_id and coordinator == actor_id:
                raise ValueError(
                    "你说自己是这个群的总管，但成员名单里没有你。要自己当总管就把"
                    f"**你自己也写进 member_ids**（现在群里只有"
                    f"{'、'.join(self._display_name(item) for item in members)}）。"
                    "自称总管却不在群里，用户看到的分工就是假的。"
                )
            raise ValueError(
                f"指名的群总管「{coordinator}」不在成员名单里（id 要用 list_assistants 的结果）："
                "总管必须是这次一起拉进群的人之一。"
            )
        if coordinator:
            # 与 assign_group_roles 同一条规矩：一个人的角色不能被这样顶掉（否则他在
            # 别的群里的审核员 / 优化顾问职责会被静默改写）。这里在建群**之前**判，
            # 免得群已经落盘了才报错。
            target = runtime.assistants.get(coordinator)
            current_role = (target.group_role or "").strip() if target is not None else ""
            if current_role and current_role != "coordinator":
                raise ValueError(
                    f"「{self._display_name(coordinator)}」现在的角色是"
                    f"「{_ROLE_NAMES.get(current_role, current_role)}」，不能同时当这个群的"
                    "总管（一个人的角色不能这样顶掉）。换一个成员当总管。"
                )

        group = GroupProfile(
            id=f"{slugify(clean_name, fallback='group')}-{uuid.uuid4().hex[:6]}",
            name=clean_name,
            member_assistant_ids=members,
            speaking_order=[item for item in (speaking_order or []) if item in members],
            coordinator_id=coordinator,
        )
        config = runtime.groups.model_copy(deep=True)
        config.upsert(group)
        runtime.groups = runtime.config_store.save_groups(config)
        logger.info("AI 新建群 %s（成员 %s，总管 %s）", group.id, members, coordinator or "位次兜底")
        # 与搭子同理：不推这条事件，群聊列表要等用户手动刷新才看得到新群
        runtime.events.publish("groups_changed", group_id=group.id, action="create")

        # 指名即任命：把总管写进搭子档案，讨论时 ``_effective_roles`` 才照它分工，
        # 而不是按发言位次给首位兜底（与 assign_group_roles 对另外两个角色的做法一致）。
        if coordinator:
            profile = runtime.assistants.get(coordinator)
            if profile is not None and (profile.group_role or "").strip() != "coordinator":
                assistant_config = runtime.assistants.model_copy(deep=True)
                assistant_config.upsert(profile.model_copy(update={"group_role": "coordinator"}))
                runtime.save_assistants(assistant_config)
                await runtime.audit.op(
                    kind="assistant",
                    action="update",
                    actor_id=actor_id,
                    target=coordinator,
                    detail=f"群角色任命：{self._display_name(coordinator)} → 协调者（总管）",
                )
                runtime.events.publish(
                    "assistants_changed", assistant_id=coordinator, action="update"
                )

        await runtime.audit.op(
            kind="group",
            action="create",
            actor_id=actor_id,
            target=group.id,
            detail=(
                f"AI 新建群「{clean_name}」（成员："
                f"{'、'.join(self._display_name(item) for item in members)}）"
            ),
        )
        result: dict[str, Any] = {
            "id": group.id,
            "name": group.name,
            "members": [
                {"id": item, "name": self._display_name(item)} for item in members
            ],
            # 这个群的总管是谁（指名道姓；空 = 按发言位次兜底）。写进返回体，模型才不会
            # 照着自己的身份想当然地"以总管自居"。
            "coordinator": (
                {"id": coordinator, "name": self._display_name(coordinator)}
                if coordinator
                else None
            ),
            # 建之前该看的清单（见上面的说明）
            "existing_assistants": self.list_assistants(),
            # **不静默**：建群不是终点，下一步是绕不过去的（没提交角色 id 就开不了讨论）。
            # 写进返回体而不是只写在工具描述里，模型才会真的去做这一步。
            "next_step": (
                (
                    f"这个群的总管是「{self._display_name(coordinator)}」——"
                    "讨论时按这个分工走，别把自己当总管。"
                    if coordinator
                    else "这个群没指定总管，会按发言位次（首位）兜底。"
                )
                + "接着调 team_assign_group_roles 提交这个群的「审核员」与「优化顾问」搭子 id"
                "（没有「不需要」这个选项；有合适的现有搭子就复用，没有就先用 "
                "team_create_assistant 建一个 group_role 为 reviewer / advisor 的）。"
                "没提交之前 team_start_discussion 会被拒绝。"
            ),
        }
        if missing:
            result["ignored_members"] = missing
        if len(members) < len(member_ids):
            result["note"] = "部分成员 id 不存在，已跳过（见 ignored_members）。"
        return result

    # ------------------------------------------------------------------ #
    # 群对话（AI 也要能管）
    # ------------------------------------------------------------------ #
    #
    # ⚠️ 这一组**只动「对话」，不动「群」**。用户把边界划得很清楚："群右键的功能
    # 是管整个群，对话名右键的功能是管这一个对话" —— AI 这边同理。所以这里没有
    # "删掉群"这类方法，删群是用户自己的动作。
    #
    # ⚠️ 一律同时要 `group_id` 与 `thread_id`，理由见 `_require_thread`。

    def _require_group(self, group_id: str) -> GroupProfile:
        group = self._runtime.groups.get(group_id)
        if group is None:
            raise ValueError(
                f"群「{group_id}」不存在（先用 team_list_assistants 看群清单，"
                "或者 team_create_group 建一个）。"
            )
        return group

    async def _require_thread(self, group_id: str, thread_id: str) -> dict[str, Any]:
        """按 **(群, 对话)** 两个键取对话；对不上就报错。

        两个键一起用，而不是只按 `thread_id` 找：**"这条对话属于哪个群"就是它的
        身份**。只按 id 找的话，模型把两个 id 搞混（A 群的 group_id + B 群的
        thread_id）时依然能改到 B 群那条，而它以为自己在改 A 群 ——
        用户看到的是**另一条对话被改了名/清空了**，且没有任何提示。
        """
        thread = await self._runtime.group_thread_repo.get(group_id, thread_id)
        if thread is None:
            raise ValueError(
                f"群「{group_id}」下没有 id 为「{thread_id}」的对话。"
                "对话 id 必须来自 team_list_assistants 返回的 groups[].threads —— "
                "不要自己编，也不要用别的那条。"
            )
        return thread

    async def create_group_thread(
        self, *, group_id: str, title: str = "", actor_id: str | None = None
    ) -> dict[str, Any]:
        """给一个群新开一条**空**对话。

        新对话里一句话都没有 —— 这是它和"接着上一轮聊"的区别，所以返回体里
        明说，免得模型以为可以接着上面的上下文。
        """
        group = self._require_group(group_id)
        thread = await self._runtime.group_thread_repo.create(group.id, title)
        await self._runtime.audit.op(
            kind="group",
            action="update",
            actor_id=actor_id,
            target=group.id,
            detail=f"新建群对话「{thread['title']}」（群「{group.name}」）",
        )
        self._notify_threads_changed(group.id)
        return {
            "group": {"id": group.id, "name": group.name},
            "thread": thread,
            "message": (
                f"已在群「{group.name}」里新建对话「{thread['title']}」"
                f"（thread_id={thread['id']}）。**它现在是空的** —— "
                "话题要接着抛给它才行（用 team_start_discussion 时把 group_id 传这个群）。"
            ),
        }

    async def rename_group_thread(
        self, *, group_id: str, thread_id: str, title: str, actor_id: str | None = None
    ) -> dict[str, Any]:
        """改一条对话的名字。"""
        group = self._require_group(group_id)
        thread = await self._require_thread(group.id, thread_id)
        clean = title.strip()
        if not clean:
            raise ValueError("对话名字不能为空 —— 空名字在列表里是一条说不清是什么的记录。")
        if clean == thread["title"]:
            # 不算错，但也没做事：明确回一句，免得模型以为失败了又试一遍
            return {"thread": thread, "message": f"「{clean}」本来就是它的名字，没有改动。"}
        renamed = await self._runtime.group_thread_repo.rename(group.id, thread["id"], clean)
        if not renamed:
            raise ValueError(f"改名失败：群「{group.name}」下找不到那条对话。")
        await self._runtime.audit.op(
            kind="group",
            action="update",
            actor_id=actor_id,
            target=group.id,
            detail=f"群对话改名：「{thread['title']}」→「{clean}」",
        )
        self._notify_threads_changed(group.id)
        return {
            "group": {"id": group.id, "name": group.name},
            "thread_id": thread["id"],
            "before": thread["title"],
            "after": clean,
            "message": f"已把群「{group.name}」里的对话「{thread['title']}」改名为「{clean}」。",
        }

    async def clear_group_thread(
        self, *, group_id: str, thread_id: str, actor_id: str | None = None
    ) -> dict[str, Any]:
        """清空一条对话的**记录**（对话本身还在，可以接着聊）。

        ⚠️ 与 `delete_group_thread` 的区别要在这个返回体里说清 —— 两者都不可逆，
        但"清空"之后还能接着聊，"删除"之后这条对话就没了。
        """
        group = self._require_group(group_id)
        thread = await self._require_thread(group.id, thread_id)
        removed = await self._runtime.group_event_repo.clear(group.id, thread["id"])
        await self._runtime.audit.op(
            kind="group",
            action="update",
            actor_id=actor_id,
            target=group.id,
            detail=f"清空群对话「{thread['title']}」的 {removed} 条记录",
        )
        self._notify_threads_changed(group.id)
        return {
            "group": {"id": group.id, "name": group.name},
            "thread_id": thread["id"],
            "removed": removed,
            "message": (
                f"已清空群「{group.name}」里对话「{thread['title']}」的 {removed} 条记录。"
                "**这条对话还在**，可以接着往下聊。"
            ),
        }

    async def delete_group_thread(
        self, *, group_id: str, thread_id: str, actor_id: str | None = None
    ) -> dict[str, Any]:
        """删掉一条对话（连带它的记录）。

        ⚠️ **不让删最后一条**：一个群至少要有一条对话，否则用户点进去是一片空白，
        而界面上没有任何"再建一条"的线索（群列表里那条还在，点开却什么都没有）。
        要"清掉全部内容"用 `clear_group_thread`，别用连续删除来表达。
        """
        group = self._require_group(group_id)
        thread = await self._require_thread(group.id, thread_id)
        remaining = await self._runtime.group_thread_repo.list_threads(group.id)
        if len(remaining) <= 1:
            raise ValueError(
                f"群「{group.name}」只剩这一条对话了，不能删 —— 删掉之后这个群会是空的。"
                "如果目的是清掉内容，用 team_clear_group_thread（对话还在，可以接着聊）。"
            )
        deleted = await self._runtime.group_thread_repo.delete(group.id, thread["id"])
        if not deleted:
            raise ValueError(f"删除失败：群「{group.name}」下找不到那条对话。")
        await self._runtime.audit.op(
            kind="group",
            action="update",
            actor_id=actor_id,
            target=group.id,
            detail=f"删除群对话「{thread['title']}」",
        )
        self._notify_threads_changed(group.id)
        return {
            "group": {"id": group.id, "name": group.name},
            "thread_id": thread["id"],
            "deleted_title": thread["title"],
            "remaining": len(remaining) - 1,
            "message": (
                f"已删除群「{group.name}」里的对话「{thread['title']}」（连带它的记录，"
                f"无法恢复）。该群还剩 {len(remaining) - 1} 条对话。"
            ),
        }

    def _notify_threads_changed(self, group_id: str) -> None:
        """告诉所有窗口"这个群的对话列表变了"。

        ⚠️ 不能复用 `groups_changed`：那条事件在界面上的动作是 `loadGroups()`
        （重拉**群**清单），而对话列表是"选中某个群之后"才去拉的 ——
        AI 新建/改名/删除一条对话之后，用户正开着的那个群不会跟着刷新，
        他会以为 AI 什么都没做。
        """
        self._runtime.events.publish("group_threads_changed", group_id=group_id)

    # ------------------------------------------------------------------ #
    # 群角色确认：审核员 / 优化顾问的 id 必须由 AI 交上来
    # ------------------------------------------------------------------ #
    def _roles_gap(self, group: GroupProfile) -> str:
        """这个群的角色还差什么（配齐返回空串）。

        两个判据缺一不可：① **提交过**（字段非空）；② 提交的人此刻**还在群里、还在**。
        只看字段会放行一个"已经不在群里的审核员"—— 那是假齐全。
        """
        runtime = self._runtime
        for role, label in (("reviewer", "审核员"), ("advisor", "优化顾问")):
            assistant_id = self._confirmed_role(group, role)
            if not assistant_id:
                return f"还没提交{label}的搭子 id"
            if assistant_id not in group.member_assistant_ids:
                return f"已确认的{label}「{self._display_name(assistant_id)}」已经不在群里了"
            if runtime.assistants.get(assistant_id) is None:
                return f"已确认的{label}「{assistant_id}」已经被删掉了"
        return ""

    @staticmethod
    def _confirmed_role(group: GroupProfile, role: str) -> str:
        """取这个群已确认的某个角色 id（去空白；未提交为空串）。"""
        value = group.reviewer_id if role == "reviewer" else group.advisor_id
        return (value or "").strip()

    async def assign_group_roles(
        self,
        *,
        group_id: str,
        reviewer_id: str,
        advisor_id: str,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """提交并确认这个群的「审核员」与「优化顾问」（产品要求加的那一环）。

        为什么要有这一步：以前"要不要审核员"是建群时的一个布尔参数，模型一句
        ``require_reviewer=false`` 就带过去了。改成**必须交出搭子 id** 之后，它要么
        指一个真实的搭子出来、要么被拒绝；而且没交之前 ``start_discussion`` 直接拒绝，
        步骤上绕不过去。系统**不再兜底补通用角色**（用户明确取消：必须自己建或复用）。

        提交即任命：档案上没有角色的补写成该角色；已经是**别的**角色则拒绝
        （那是把团队的总管抢去当审核员，属于不可逆的分工破坏）。
        """
        runtime = self._runtime
        group = runtime.groups.get(group_id)
        if group is None:
            raise ValueError(
                f"群「{group_id}」不存在（先用 team_list_assistants 看群清单，"
                "或者 team_create_group 建一个）。"
            )

        reviewer = reviewer_id.strip()
        advisor = advisor_id.strip()
        if not reviewer or not advisor:
            raise ValueError(
                "审核员与优化顾问都要给 id —— 这一步没有「不需要」："
                "确实没有合适的现有搭子时，先用 team_create_assistant 建一个"
                "（group_role 分别填 reviewer / advisor，并在规则里写清这个任务怎么算达标），"
                "再把它们的 id 提交上来。"
            )
        if reviewer == advisor:
            raise ValueError(
                "审核员和优化顾问不能是同一个搭子：一个按标准验收、一个提必要建议，"
                "分开才互相把关。请各指一个。"
            )
        # 与群里**已确认的另一个**角色也不能撞（例如把现任优化顾问提成审核员）
        if reviewer == self._confirmed_role(group, "advisor") or advisor == self._confirmed_role(
            group, "reviewer"
        ):
            raise ValueError("同一个搭子不能同时担任审核员与优化顾问，请各指一个。")

        members = list(group.member_assistant_ids)
        added: list[str] = []
        roles: dict[str, dict[str, Any]] = {}
        for role, assistant_id in (("reviewer", reviewer), ("advisor", advisor)):
            label = _ROLE_NAMES[role]
            profile = runtime.assistants.get(assistant_id)
            if profile is None:
                raise ValueError(
                    f"搭子「{assistant_id}」不存在 —— id 必须来自 team_list_assistants 的结果，"
                    "不要自己编。"
                )
            current = (profile.group_role or "").strip()
            if current and current != role:
                raise ValueError(
                    f"「{profile.nickname or profile.name}」现在的角色是"
                    f"「{_ROLE_NAMES.get(current, current)}」，不能再当{label}"
                    "（一个人的角色不能这样顶掉）。请另外指一个搭子。"
                )
            if assistant_id not in members:
                # AI 的常见失误：建了搭子忘了拉进群。这里直接拉进来并**如实报出**，
                # 而不是让它再兜一圈白跑一次工具调用
                members.append(assistant_id)
                added.append(assistant_id)
            roles[role] = {
                "id": assistant_id,
                "name": profile.nickname or profile.name,
                "role_written": current == role,
            }

        order = [item for item in group.speaking_order if item in members]
        order += [item for item in members if item not in order]
        updated = group.model_copy(
            update={
                "member_assistant_ids": members,
                "speaking_order": order,
                "reviewer_id": reviewer,
                "advisor_id": advisor,
            }
        )
        config = runtime.groups.model_copy(deep=True)
        config.upsert(updated)
        runtime.groups = runtime.config_store.save_groups(config)
        runtime.events.publish("groups_changed", group_id=group.id, action="update")

        # 档案上的 group_role 也落下来：讨论时按它分工（不写就只能按发言位次兜底，
        # 顺序一变角色就飘了），界面上也才看得到谁担任什么角色。
        appointed: list[str] = []
        for role in ("reviewer", "advisor"):
            assistant_id = roles[role]["id"]
            profile = runtime.assistants.get(assistant_id)
            if profile is None or (profile.group_role or "").strip() == role:
                continue
            assistant_config = runtime.assistants.model_copy(deep=True)
            assistant_config.upsert(profile.model_copy(update={"group_role": role}))
            runtime.save_assistants(assistant_config)
            await runtime.audit.op(
                kind="assistant",
                action="update",
                actor_id=actor_id,
                target=assistant_id,
                detail=f"群角色任命：{profile.nickname or profile.name} → {_ROLE_NAMES[role]}",
            )
            runtime.events.publish("assistants_changed", assistant_id=assistant_id, action="update")
            appointed.append(assistant_id)

        await runtime.audit.op(
            kind="group",
            action="update",
            actor_id=actor_id,
            target=group.id,
            detail=(
                f"确认群角色「{group.name}」：审核员={roles['reviewer']['name']}、"
                f"优化顾问={roles['advisor']['name']}"
                + (
                    "；顺带拉进群：" + "、".join(self._display_name(item) for item in added)
                    if added
                    else ""
                )
            ),
        )
        result: dict[str, Any] = {
            "id": group.id,
            "name": group.name,
            "roles": roles,
            "members": [{"id": item, "name": self._display_name(item)} for item in members],
            "roles_ready": True,
            "next_step": "角色已配齐，现在可以用 team_start_discussion 把话题抛进去。",
        }
        if added:
            result["added_members"] = [
                {"id": item, "name": self._display_name(item)} for item in added
            ]
        if appointed:
            result["role_written_to_profile"] = appointed
        return result

    async def update_group(
        self,
        *,
        group_id: str,
        name: str = "",
        add_member_ids: list[str] | None = None,
        remove_member_ids: list[str] | None = None,
        speaking_order: list[str] | None = None,
        avatar_source: str = "",
        clear_avatar: bool = False,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """改群名 / 加减成员 / 调发言顺序 / 换头像（用户要求：建好之后也要能改，AI 也要能做）。

        加减成员是**按方向给**（``add_*`` / ``remove_*``）而不是让模型交一份完整名单：
        模型很难知道当前完整成员是谁，交整份名单极易把没提到的成员"顺手删掉"
        （那是不可逆的破坏）。按方向给，最坏情况只是加错人，用户一眼能改回来。
        """
        runtime = self._runtime
        existing = runtime.groups.get(group_id)
        if existing is None:
            raise ValueError(f"群「{group_id}」不存在（先用 team_list_assistants 看群清单）。")

        members = list(existing.member_assistant_ids)
        added: list[str] = []
        dropped: list[str] = []
        missing: list[str] = []
        for assistant_id in add_member_ids or []:
            if runtime.assistants.get(assistant_id) is None:
                missing.append(assistant_id)
                continue
            if assistant_id not in members:
                members.append(assistant_id)
                added.append(assistant_id)
        for assistant_id in remove_member_ids or []:
            if assistant_id in members:
                members.remove(assistant_id)
                dropped.append(assistant_id)
            else:
                missing.append(assistant_id)
        if len(members) < 2:
            raise ValueError(
                "一个群至少要两个搭子才讨论得起来"
                f"（按你要的改动，群里只剩 {len(members)} 个了，已拒绝这次修改）。"
            )

        order = [item for item in existing.speaking_order if item in members]
        order += [item for item in members if item not in order]
        if speaking_order:
            picked = [item for item in speaking_order if item in members]
            order = picked + [item for item in order if item not in picked]

        # 角色确认跟着成员走：被移出群的审核员 / 优化顾问不能再算"已确认"，
        # 否则闸门会放行一个**已经不在群里**的角色（讨论时他根本不发言）。
        kept_roles: dict[str, str] = {}
        cleared: list[str] = []
        for role, label in (("reviewer", "审核员"), ("advisor", "优化顾问")):
            confirmed = self._confirmed_role(existing, role)
            if confirmed and confirmed not in members:
                cleared.append(label)
                kept_roles[f"{role}_id"] = ""
            else:
                kept_roles[f"{role}_id"] = (
                    existing.reviewer_id if role == "reviewer" else existing.advisor_id
                )

        # 总管同理：被移出群的总管不能再挂着"本群总管"的名（他已经不发言了）。
        coordinator_kept = (existing.coordinator_id or "").strip()
        if coordinator_kept and coordinator_kept not in members:
            cleared.append("总管")
            coordinator_kept = ""

        # 头像：`clear_avatar` 优先（"换个头像但没给图"走它 → 置空，由前端重新分配）。
        # `avatar_source` 走 `storage.images` 那套统一校验（与搭子那边同一个上限），
        # 失败时**原样抛出** —— 模型要把"为什么不行"如实转告用户，而不是含糊重试。
        avatar = existing.avatar
        avatar_note = ""
        if clear_avatar:
            avatar = ""
            avatar_note = "换头像（交给系统重新分配）"
        elif avatar_source.strip():
            try:
                _, avatar = await images.to_data_url(
                    avatar_source, max_bytes=AVATAR_MAX_BYTES, workspace=runtime.workspace
                )
            except images.ImageSourceError as exc:
                raise ValueError(f"设置群头像失败：{exc}") from exc
            # ⚠️ 只报大小，绝不把 data_url / base64 写进日志（见 storage/images 的说明）
            avatar_note = f"换头像（{len(avatar) // 1024}KB）"

        group = existing.model_copy(
            update={
                "name": name.strip() or existing.name,
                "member_assistant_ids": members,
                "speaking_order": order,
                "coordinator_id": coordinator_kept,
                "avatar": avatar,
                **kept_roles,
            }
        )
        config = runtime.groups.model_copy(deep=True)
        config.upsert(group)
        runtime.groups = runtime.config_store.save_groups(config)
        runtime.events.publish("groups_changed", group_id=group.id, action="update")
        await runtime.audit.op(
            kind="group",
            action="update",
            actor_id=actor_id,
            target=group_id,
            detail=(
                f"AI 调整群「{group.name}」："
                + "、".join(
                    item
                    for item in (
                        "改名" if name.strip() and name.strip() != existing.name else "",
                        f"加人（{'、'.join(self._display_name(i) for i in added)}）" if added else "",
                        f"减人（{'、'.join(self._display_name(i) for i in dropped)}）" if dropped else "",
                        "调整发言顺序" if speaking_order else "",
                        avatar_note,
                        f"角色失效（{'、'.join(cleared)}，需重新提交 id）" if cleared else "",
                    )
                    if item
                )
                or "提交后无实际变化"
            ),
        )
        result: dict[str, Any] = {
            "id": group.id,
            "name": group.name,
            "members": [
                {"id": item, "name": self._display_name(item)} for item in members
            ],
            "speaking_order": [self._display_name(item) for item in order],
        }
        if added:
            result["added"] = [self._display_name(item) for item in added]
        if dropped:
            result["removed"] = [self._display_name(item) for item in dropped]
        if missing:
            result["ignored_ids"] = missing
        if cleared:
            # **不静默**：角色被带走了，模型必须知道下一步得重新提交
            result["roles_cleared"] = cleared
            result["next_step"] = (
                f"被移出群的人里包含已确认的{'、'.join(cleared)}，该角色已作废："
                "开讨论前要用 team_assign_group_roles 重新提交一个 id。"
            )
        return result

    async def set_speaking_order(
        self, *, group_id: str, order: list[str], actor_id: str | None = None
    ) -> dict[str, Any]:
        """调整发言顺序（谁先说，往往决定谁定基调）。"""
        runtime = self._runtime
        existing = runtime.groups.get(group_id)
        if existing is None:
            raise ValueError(f"群「{group_id}」不存在。")
        members = list(existing.member_assistant_ids)
        cleaned = [item for item in order if item in members]
        rest = [item for item in members if item not in cleaned]
        group = existing.model_copy(update={"speaking_order": cleaned + rest})
        config = runtime.groups.model_copy(deep=True)
        config.upsert(group)
        runtime.groups = runtime.config_store.save_groups(config)
        await runtime.audit.op(
            kind="group",
            action="update",
            actor_id=actor_id,
            target=group_id,
            detail=f"调整发言顺序：{' → '.join(self._display_name(item) for item in cleaned + rest)}",
        )
        return {
            "id": group.id,
            "order": [
                {"id": item, "name": self._display_name(item)} for item in cleaned + rest
            ],
        }

    # ------------------------------------------------------------------ #
    # 派活：起一场后台讨论
    # ------------------------------------------------------------------ #
    async def start_discussion(
        self,
        *,
        group_id: str,
        topic: str,
        origin_session_id: str = "",
        origin_assistant_id: str | None = None,
    ) -> dict[str, Any]:
        """起一场**后台**讨论，**立即返回**（不等它跑完）。

        返回体里带 group_id：界面据此把「群聊入口」挂到结果消息上。
        """
        runtime = self._runtime
        from .group_domain import ordered_members, resolve_thread, restore_history

        group = runtime.groups.get(group_id)
        if group is None:
            raise ValueError(
                f"群「{group_id}」不存在。可以先看一遍现有的群，或者建一个。"
            )
        # ---- 闸门：角色没配齐就不许开讨论（产品要求的那一环）---- #
        #
        # 放在这里而不是建群时校验：建群是第一步，提交角色是**另一步**，
        # 只有把闸门放在"开讨论"上，"必须提交 id 才能进行下一步"才真的成立
        # （否则模型建完群直接开讨论，中间那一步照样可以不做）。
        # 注意这个方法只有 AI 技能会走 —— 用户在前台手点讨论走的是 server/routes/groups.py
        # 的 SSE 流，不会被这道闸门拦住。
        gap = self._roles_gap(group)
        if gap:
            raise ValueError(
                f"「{group.name}」还没配齐「审核员 / 优化顾问」：{gap}。"
                "先用 team_assign_group_roles 把这两个角色的搭子 id 提交上来"
                "（这一步没有「不需要」；没有合适的搭子就先用 team_create_assistant 建一个），"
                "再发起讨论。"
            )
        clean_topic = topic.strip()
        if not clean_topic:
            raise ValueError("得给一个讨论话题，否则搭子们不知道要聊什么。")
        if group_id in self.running:
            raise ValueError(f"「{group.name}」里已经有一场讨论在跑了，等它结束。")
        members = ordered_members(runtime, group)
        if not members:
            raise ValueError(f"群「{group.name}」里没有可用的成员（搭子可能被删掉了）。")

        # 后台这场讨论归到该群**最近有动静**的那条对话（一条都没有就现建一条）。
        # 后台讨论是搭子自己发起的，用户没有"选一条对话"的机会，落在最近那条
        # 是唯一不会让他意外的地方 —— 讨论开始后他能在自己刚看过的地方找到它。
        thread_id = await resolve_thread(runtime, group_id, "")
        # 历史要先恢复：后台这一场也必须"看得到前面聊过什么"
        await restore_history(runtime, group_id, thread_id)

        task = asyncio.create_task(
            self._run(
                group, members, clean_topic, origin_session_id, origin_assistant_id, thread_id
            ),
            name=f"group-discussion-{group_id}",
        )
        self._tasks[group_id] = task
        task.add_done_callback(lambda _task, gid=group_id: self._tasks.pop(gid, None))

        # 让界面知道"后台开跑了"：只读观察窗据此自动弹出（受设置里的开关控制）
        runtime.events.publish(
            "group_task_started",
            group_id=group_id,
            group_name=group.name,
            topic=clean_topic,
            session_id=origin_session_id,
        )
        await runtime.audit.op(
            kind="group",
            action="background_start",
            actor_id=origin_assistant_id,
            target=group_id,
            session_id=origin_session_id or None,
            detail=f"在后台发起讨论「{group.name}」：{clean_topic[:120]}",
        )
        return {
            "group_id": group_id,
            "group_name": group.name,
            "topic": clean_topic,
            "members": [item.name for item in members],
            "started": True,
        }

    async def _run(
        self,
        group: GroupProfile,
        members: list[Any],
        topic: str,
        origin_session_id: str,
        origin_assistant_id: str | None,
        thread_id: str,
    ) -> None:
        """后台真正跑讨论的那一段（消费与前台**同一条**流）。"""
        runtime = self._runtime
        # ⚠️ 这三样**都不再来自路由层**（审计 H-06 的最后一刀）：帧解析在中立层
        # `protocol`、落库转发在 `group_domain`、讨论执行器（讨论流 + 收尾清理）
        # 整体搬到了 `group_discussion` —— 至此领域层不再 import `server.routes.*`。
        from ..protocol import parse_sse
        from .group_discussion import discussion_source
        from .group_domain import persisting_stream

        summary = ""
        last_speech = ""
        outcome = "done"
        error = ""
        try:
            source = persisting_stream(
                runtime,
                group.id,
                thread_id,
                discussion_source(runtime, group, members, topic, thread_id, background=True),
                background=True,
            )
            async for chunk in source:
                parsed = parse_sse(chunk)
                if parsed is None:
                    continue
                name, data = parsed
                if name == "summary":
                    summary = str(data.get("content") or "")
                elif name == "message":
                    last_speech = str(data.get("content") or "")
                elif name == "done" and str(data.get("reason") or "") == "max_rounds":
                    # 安全阀触发：讨论**没有收敛**。如实回传，不假装有结论。
                    outcome = "incomplete"
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except Exception as exc:  # noqa: BLE001 - 后台任务失败也要留下可读原因
            outcome = "failed"
            error = str(exc)[:300]
            logger.exception("后台群讨论失败 group=%s", group.id)
        finally:
            await self._deliver(
                group,
                topic,
                outcome,
                summary or last_speech,
                error,
                origin_session_id,
                origin_assistant_id,
            )

    async def _deliver(
        self,
        group: GroupProfile,
        topic: str,
        outcome: str,
        body: str,
        error: str,
        origin_session_id: str,
        origin_assistant_id: str | None,
    ) -> None:
        """把结论写回**发起它的那条会话**，并推事件让界面跟上。

        文案一律如实：没收敛就说没收敛，失败了就说失败和原因 —— 后台跑完不吭声
        是这类功能最招人恨的地方（用户以为它还在跑）。
        """
        runtime = self._runtime
        if outcome == "done":
            head = f"【{group.name}】的讨论有结论了："
        elif outcome == "incomplete":
            head = (
                f"【{group.name}】的讨论聊到安全轮数上限就停了，"
                "没有投票收敛出结论。最后聊到："
            )
        elif outcome == "cancelled":
            head = f"【{group.name}】的讨论被中断了（应用退出或主动停止）。最后聊到："
        else:
            head = f"【{group.name}】的讨论出错了：{error or '原因未知'}。"

        text = head + ("\n\n" + body if body else "\n\n（没有拿到任何发言。）")

        if origin_session_id:
            try:
                session = await runtime.sessions.get(origin_session_id)
                session.memory.add_assistant(text)
                session.touch()
                await runtime.persist_session(session)
            except Exception as exc:  # noqa: BLE001 - 写不回会话也不该把事件吞掉
                logger.warning("群聊结果写回会话失败 session=%s: %s", origin_session_id, exc)

        runtime.events.publish(
            "group_task_done",
            group_id=group.id,
            group_name=group.name,
            topic=topic,
            session_id=origin_session_id,
            outcome=outcome,
            content=text,
        )
        await runtime.audit.op(
            kind="group",
            action="background_done" if outcome == "done" else "background_failed",
            actor_id=origin_assistant_id,
            target=group.id,
            session_id=origin_session_id or None,
            status="ok" if outcome == "done" else "error",
            detail=f"后台讨论结束（{outcome}）：{topic[:80]}" + (f"；{error}" if error else ""),
        )

    async def stop_discussion(self, group_id: str) -> dict[str, Any]:
        """停止某个群正在跑的后台讨论（用户点「暂停任务」）。

        从 ``_tasks`` 里取出对应 task 并 ``cancel()``：``_run`` 里已有
        ``CancelledError → outcome="cancelled"`` 的处理，会自动走 ``_deliver``
        把「讨论被中断」写回发起会话并推 ``group_task_done``。task 不存在（没在跑、
        或已经结束）返回 ``stopped=False``。
        """
        task = self._tasks.get(group_id)
        if task is None or task.done():
            return {"group_id": group_id, "stopped": False}
        task.cancel()
        logger.info("已停止群后台讨论 group=%s", group_id)
        return {"group_id": group_id, "stopped": True}

    async def shutdown(self) -> None:
        """应用退出时收干净：不留悬挂的后台协程。

        取消而不是等待：一场讨论可能还要跑几分钟，等它跑完用户会以为应用卡住了。
        """
        pending = [task for task in self._tasks.values() if not task.done()]
        for task in pending:
            task.cancel()
        for task in pending:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - 退出路径不挑错
                pass
        self._tasks.clear()


def _merge_rules(rules: str, imposed: list[str]) -> str:
    """把系统强加的规则条款拼进 RULES（已含则跳过，避免重复）。

    「策划类规则必须有 ai_thinking_mode / team_restructure 条款」是
    明确的硬要求，落在 RULES.md 里。这里按行去重：AI 自己已经写了同样的意思
    就不重复塞。
    """
    body = rules.strip()
    parts = [body] if body else []
    for clause in imposed:
        if clause not in body:
            parts.append(clause)
    return "\n".join(parts)


def _identity_document(name: str, identity: str, abilities: str) -> str:
    """IDENTITY.md：它是谁 + 它会做什么。

    ⚠️ 能力清单必须落在**文件里**，不能只写进 ``description``：判断"它能不能担这件事"
    的人（用户，以及下一个要拉它进群的搭子）看的就是这几份文件；简介只是列表页上的一行。
    """
    return (
        f"# IDENTITY · {name}\n\n"
        "## 我是谁\n\n"
        f"{identity.strip()}\n\n"
        "## 我能做什么\n\n"
        f"{abilities.strip()}\n"
    )


def _rules_document(name: str, rules: str) -> str:
    """RULES.md：工作规则与边界（先做什么、什么必须确认、做不到时怎么办）。"""
    return f"# RULES · {name} 的工作规则\n\n{rules.strip()}\n"


def _soul_document(name: str, tone: str, description: str) -> str:
    """SOUL.md：语气与风格。

    刻意**不重复身份与职责**（那些在 IDENTITY.md），只留"怎么说话、在意什么" ——
    用户原话是「soul 里应该是根据这个搭子的功能和任务给予具体的语气风格等说明」。
    语气留空时给一句兜底，但不说"你是某某助手"那种身份话（那是 IDENTITY 的事）。
    """
    body = tone.strip() or "语气自然、直接，始终围绕你自己那份职责说话。"
    return f"# SOUL\n\n你是 {name}。{body}\n"

"""技能分组：四分类 + "谁能用哪些技能"的唯一判定中心。

## 四类是什么（产品约定）

| 分类 | 谁属于它 | 能不能关 |
|---|---|---|
| **我的技能** | 用户上传 / AI 创建 / AI 下载安装的技能（`source == "custom"`） | 能 |
| **通用技能** | 客户端预设里"按需挑选"的能力 + MCP 外部工具（`source == "mcp"`） | 能 |
| **内置技能** | 每个搭子**创建时即自带**的基础能力（时间、文件、HTTP、记忆、人格、计划…） | **不能** |
| **专属技能** | 内置四个搭子各自专属（BuddyManager 的团队管理 + 电脑操作那批、心鉴学两条） | **不能** |

## 为什么名单集中在这一个文件

要么给 40 多个 `@skill` 各加一个参数，要么写一份集中名单。选后者：

- **改一处就能调整口径**。用户明确说了「通用/内置先按你的想法划分，**之后还要做调整**」——
  散在 40 多个文件里的话，每次调整都要动一大片，迟早漏掉几个。
- **能校验**。`validate_registry()` 会指出名单里"指向不存在技能"的名字 ——
  写错一个字不会报错、只会让那一个技能静静地待错分类，而这种错没人会发现。

## 搭子能用哪些技能（本次最关键的口径）

```
内置搭子   → 全部内置技能 ∪ 自己的专属技能            （忽略 enabled_skills，且**不可添加**）
自定义搭子 → 全部内置技能 ∪ 勾选的「通用技能 + 我的技能」（不勾 = 只有内置技能）
```

⚠️ 这里**推翻了旧语义**：以前 `enabled_skills` 为空 = **不限制**（全开），
现在是"空 = 只有内置技能"。**没有"默认加载全部技能"的搭子**了（原话）。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

# --------------------------------------------------------------------------- #
# 四分类
# --------------------------------------------------------------------------- #
BUCKET_MINE = "mine"
BUCKET_COMMON = "common"
BUCKET_BUILTIN = "builtin"
BUCKET_EXCLUSIVE = "exclusive"

#: 展示顺序（技能页那四个子页也按这个顺序）
BUCKETS: tuple[str, ...] = (BUCKET_MINE, BUCKET_COMMON, BUCKET_BUILTIN, BUCKET_EXCLUSIVE)

BUCKET_LABELS: dict[str, str] = {
    BUCKET_MINE: "我的技能",
    BUCKET_COMMON: "通用技能",
    BUCKET_BUILTIN: "内置技能",
    BUCKET_EXCLUSIVE: "专属技能",
}


#: **通用技能**：客户端预设里"按需挑选"的能力 —— 有开关、可以被搭子勾选。
#:
#: ⚠️ 判定方向是**"显式列通用，其余都算内置"**，不是反过来。两条理由：
#:
#: 1. **保守优先**：漏登记的后果是"这个技能变成关不掉的内置技能"，
#:    而不是"一个本该常开的技能被用户随手关掉"。后者会让搭子悄悄失去基础能力，
#:    前者的表现只是"这一项开关不见了"，用户一问就能发现。
#: 2. **新增技能不必逐个登记**：绝大多数新技能要么是基础能力、要么是某个搭子的专属，
#:    真正"可自选"的是少数。
#:
#: ⚠️ 名字必须是 `@skill(name=...)` 里的**技能 id**，不是显示名 ——
#: 写错一个字不会报错，只会让那一个技能静静地变成内置技能，所以有 `validate_registry()` 兜着。
#:
#: ⚠️ **这份名单已经过两轮调整**。要调只改这里，**不要**去动那些 `@skill(...)` 文件：
#:
#: 1. **第一版**：按能力域粗分（用户："先按你的想法划分，之后还要做调整"）。
#: 2. **第二版（，用户逐条点名）**：把 **27 项转成内置技能**（浏览器 5 /
#:    自动化任务 5 / 剪贴板 3 / 日程 4 / 提醒 3 / 图表·报告·SVG 3 / 屏幕截图 1 /
#:    结构化笔记·苏格拉底式追问·技能创作指南 3），再把 **2 项转成专属技能**
#:    （产品经理方法论、商业诊断工具箱 → `EXCLUSIVE_EXACT`）。
#:    用户的口径是"这些属于基础能力，每个搭子都该有，不必让用户挑"。
#:    注意：**MCP 工具（`source="mcp"`）不在本名单的管辖范围**，它们由 `bucket_of`
#:    单独判为通用 —— 明确"MCP 是用户自己连进来的，保持通用"。
#:    两轮合计：49 → 20 项。
COMMON_NAMES: frozenset[str] = frozenset(
    {
        # 系统小工具：音量 / 亮度 / 锁屏（截图 已转为内置）
        "system_volume",
        "system_volume_get",
        "system_brightness_get",
        "system_brightness_set",
        "system_lock_screen",
        # 文档转换（5）
        "doc_word_to_markdown",
        "doc_markdown_to_word",
        "doc_to_pdf",
        "doc_pdf_to_text",
        "doc_parse",
        # 办公（3）：只剩 Excel 那三项（图表 / 报告 已转为内置）
        "excel_read",
        "excel_write",
        "excel_analyze",
        # 生活（3）：天气与记账（日程 / 提醒 已转为内置）
        "weather_query",
        "expense_record",
        "expense_analyze",
        # 知识与领域（4）：内容加工与专业领域能力，按需挑
        # （结构化笔记 / 苏格拉底式追问 / 技能创作指南 已转为内置；
        #   产品经理方法论 / 商业诊断工具箱 同日已转为专属）
        "paper_deweight",
        "humanizer",
        "pro_legal_strategist",
        "nihaixia",
    }
)
#: 真正"用户与 AI 都**关不掉**、也改不了权限"的内置技能（用户原话：
#: "这部分技能用户与ai无法关闭和删除"）。
#:
#: ⚠️ 它比"bucket 是内置"**窄**，两者别混：
#: - `bucket == builtin` 的含义是"每个搭子**默认就带**"（装配时用）；
#: - 这份名单的含义是"连开关都不给"（界面不画开关 + 后端 409）。
#:
#: 分开的理由很实在：`bucket` 是"没登记就算内置"的**宽松兜底**，
#: 而"关不掉"必须**显式声明** —— 否则一个忘了归类的新技能会莫名其妙地变成
#: "默认永久开启"，用户既关不掉、也找不到原因（这是最难解释的一类问题）。
LOCKED_BUILTIN_NAMES: frozenset[str] = frozenset(
    {
        # ---- ----
        # 时间 / 计算
        "system_time",
        "calc",
        # 文件读写
        "file_read",
        "file_write",
        # 网络
        "http_request",
        "http_fetch",
        # 长内容分段读取
        "read_tool_output",
        # 记忆与历史
        "history_search",
        "kb_add",
        "kb_search",
        "kb_stats",
        "kb_forget",
        # 自我认知与成长
        "self_persona_read",
        "self_persona_update",
        "self_growth",
        # 计划回报
        "plan_update",
        # 思考模式
        "ai_thinking_mode",
        # 防骗
        "anti_fraud",
        # 压缩包只看不解压
        "archive_list",
        "archive_read",
        # ---- ----
        # ⚠️ 这 27 项**必须**与 `COMMON_NAMES` 里删掉的那 27 项逐字对应：
        # 只从 COMMON 删、忘了往这里加，会得到一个"bucket 是内置、却还能被关掉"的
        # 中间态（测试 `test_每个内置技能都真的关不掉` 专门拦这种漏改）。
        # 浏览器（5）
        "browser_read",
        "browser_act",
        "browser_screenshot",
        "browser_snapshot",
        "browser_tabs",
        # 自动化任务（5）
        "scheduled_task_create",
        "scheduled_task_delete",
        "scheduled_task_list",
        "scheduled_task_run",
        "scheduled_task_update",
        # 剪贴板（3）
        "clipboard_read_text",
        "clipboard_read_image",
        "clipboard_write",
        # 日程（4）
        "calendar_create",
        "calendar_update",
        "calendar_list",
        "calendar_delete",
        # 提醒（3）
        "reminder_create",
        "reminder_list",
        "reminder_cancel",
        # 办公里的图表 / 报告 / SVG（3）
        "chart_generate",
        "report_generate",
        "svg_create",
        # 屏幕截图（1）
        "system_screenshot",
        # 知识与内容（3）
        "excerpo",
        "grill_me",
        "skill_creator",
    }
)


#: **专属技能**：用"前缀 + 精确名"两条规则，不手工罗列 31 个名字
#: （罗列的坏处是新增一个 `team_xxx` 时必然忘加）。
#:
#: ⚠️ 前缀是有意放宽的：`team_` / `buddy_` / `computer_` 目前**只有**搭子总管那一批在用。
#: 将来若要加一个以它们开头的通用技能，得先把它从这里排除掉。
EXCLUSIVE_PREFIXES: tuple[str, ...] = ("team_", "buddy_", "computer_")
EXCLUSIVE_EXACT: frozenset[str] = frozenset(
    {
        "custom_skill_install",
        "skill_package_install",
        "update_assistant_profile",
        # ：用户点名把这两个从「通用技能」改成搭子总管专用 ——
        # 它们是"做策划时才用得上"的方法论，别的搭子拿着也没有使用场景。
        "pmaster",
        "dbskill",
    }
)

#: 上面这批专属技能归谁（内置搭子 id）
EXCLUSIVE_OWNER = "BuddyManager"

#: 归属搭子的**界面叫法**（只用于文案）。心鉴学那三个在 `builtin/xjx.py` 里，
#: 这里只补搭子总管 —— 两边各存一份会"改了一边忘了另一边"，所以下面用合并而不是复制。
#:
#: ⚠️ 用英文「Buddy Manager」是产品要求（"仅 Buddy Manager 可用"）。
#: 它**只影响技能页**：`owner_label()` 的产物只经 `SkillMeta.to_dict` 下发成
#: `owner_label` 字段，而读它的只有技能页（专属栏分组标题 + 心鉴学那条徽标）。
#: 操作被拒的提示走 `skill/locked.py::locked_message()` —— 那个按**技能名**给理由、
#: 不读本字段，所以拒绝文案不受影响（产品明确要求"其它地方不动"）。
_OWNER_LABEL_EXTRA: dict[str, str] = {"BuddyManager": "Buddy Manager"}


# --------------------------------------------------------------------------- #
# 指导型技能的专属 / 常驻名单（新增，**独立于上面两个集合**）
# --------------------------------------------------------------------------- #
# ⚠️ 为什么不能并进 `EXCLUSIVE_EXACT` / `COMMON_NAMES`：
# `validate_registry`（本文件末尾）只扫这两个集合、拿它们跟**工具注册表**比对，
# 而下面这些是**指导型技能**（`kind == "instruction"`，正文在 `custom_skills.json`
# 里，**不注册成工具**）—— 塞进去会被判成"名单里有不存在的技能"，启动日志刷满假
# 告警，`tests/unit/test_skill_groups.py` 里那条 `validate_registry(...) == []` 也会红。
# 所以给它们**单独两份常量**，并在 `is_exclusive` / `owners_of` / `bucket_of` 里显式接入。
#
# ⚠️ 为什么需要这两份常量（而不是靠改 `bucket_of` 的分支顺序）：
# `bucket_of` 的第一条分支是 `source == "custom"`，而指导型技能的 source 正是
# `"custom"` 且带 domain ⇒ 原来它**永远**走那条分支返回「通用技能」，
# 后面那些判定对它一次都不会被调用。见 `bucket_of` 里新加的两条短路。

#: **指导型技能里的专属技能** → 归属搭子。
#:
#: 「品牌策略与提案 / 活动会议策划与运营 / 漏斗分析 / 营销 Playbook 库 /
#: ab-test-setup / marketing-ideas / pricing-strategy / referral-program」这八个
#: 从「通用技能」改为**搭子总管专属** —— 它们是"做策划时才用得上"的方法论，
#: 别的搭子拿着也没有使用场景。转过去之后：只有 BuddyManager 能用、关不掉、
#: 其它搭子**连看都看不到**（不只是不能勾）。
#:
#: ⚠️ 键是**技能 id**（`custom_skills.json` 里的 `id`，不是显示名）。
#: 写错一个字不会报错、只会让那一个静静地待错分类 —— 改名前先跟数据核一遍。
INSTRUCTION_EXCLUSIVE_OWNERS: dict[str, tuple[str, ...]] = {
    "brand-strategy": (EXCLUSIVE_OWNER,),
    "event-planning": (EXCLUSIVE_OWNER,),
    "funnel-analysis": (EXCLUSIVE_OWNER,),
    "marketing-playbooks": (EXCLUSIVE_OWNER,),
    "ab-test-setup": (EXCLUSIVE_OWNER,),
    "marketing-ideas": (EXCLUSIVE_OWNER,),
    "pricing-strategy": (EXCLUSIVE_OWNER,),
    "referral-program": (EXCLUSIVE_OWNER,),
}

#: **指导型技能里的常驻技能**（每个搭子创建时自带、关不掉）。
#:
#: 「敏感信息脱敏与文件预检 / copy-editing」改为内置技能口径。
#: 这两条与真·内置技能（代码里 `@skill` 注册的那批）**行为一致、来源不同** ——
#: 它们仍不注册成工具，正文照旧靠 `persona_with_instructions` 注入，
#: 但注入集合里**恒有它们**（见 `allowed_skill_names`：无条件并集）。
#:
#: ⚠️ 它们的"关不掉"是**注入层面**的：`collect_instructions` 只认"集合里有没有这个名字"，
#: 名字恒在集合里 ⇒ 勾不勾都生效。注意 `is_locked` 对它们**无效**
#: （那个函数第一句就是"source 不是 builtin 就返回 False"），所以技能页的"关不掉"
#: 表现（不画开关）要另走 `routes/skills.py::_instruction_entries` 把 `locked` 下发成 True。
ALWAYS_ON_INSTRUCTION_NAMES: frozenset[str] = frozenset(
    {"sensitive-data-precheck", "copy-editing"}
)


def is_locked_instruction(name: str) -> bool:
    """是不是**关不掉的指导型技能**（上面那两份名单合起来）。

    ⚠️ 与 `is_locked`（本文件另一处）**不是一回事**，别混：
    `is_locked` 读的是"技能自己的 source"，而它第一句就是"source 不是 builtin 就返回 False"——
    指导型技能永远过不了那一关。所以专属于指导型的"关不掉"必须走这个函数。

    ⚠️ 拿到 True 之后，调用方要**自己**把 `locked` 下发 / 拒绝掉：
    这两批技能的"关不掉"只体现在两处 —— 注入集合恒含它们（`allowed_skill_names`）、
    以及接口拒绝关闭（`routes/skills.py::patch_skill` 返回 409）。落盘里没有可改的状态，
    所以不存在"漏拦某个入口"的问题。
    """
    return name in INSTRUCTION_EXCLUSIVE_OWNERS or name in ALWAYS_ON_INSTRUCTION_NAMES

#: **曾经**是通用技能、现在已失效的名字（转为专属 / 内置的那批）。
#:
#: ⚠️ 它**不参与任何分类判定**（判定看 `EXCLUSIVE_EXACT` 与上面那两份名单），
#: 只回答一个问题："用户档案里残留的这个名字，是'他以前合法勾过的'，还是'他现在硬塞的'？"
#: 前者要**静默剔除**（否则老档案一保存就撞 422，用户什么都没改却报错），
#: 后者要**明确拒绝**（那是越权企图，见 `routes/assistants.py::_validate_skills`）。
#:
#: ⚠️ 上面那 10 个指导型技能**必须并进来**：它们原本是可以被搭子勾选的「通用技能」，
#: 用户在老档案里很可能真勾过 —— 转类之后那些残留一律静默剔除，不能让用户
#: "什么都没改却保存失败"。
RETIRED_COMMON_NAMES: frozenset[str] = frozenset(
    {"pmaster", "dbskill"}
    | set(INSTRUCTION_EXCLUSIVE_OWNERS)
    | ALWAYS_ON_INSTRUCTION_NAMES
)


# --------------------------------------------------------------------------- #
# 技能小分类（技能页「通用技能」栏那排分类按钮按它分组）
# --------------------------------------------------------------------------- #
# ⚠️ 与 `SkillMeta.category` 是**两个维度**，别混：
#   - `category`（10 个固定值）说"这个技能干什么" —— 办公 / 生活 / 系统 / 知识…
#   - `domain`（下面这 14 个）说"它属于哪个行业 / 领域" —— 电商 / 金融 / 医疗…
# 用户导入 236 个第三方技能时要求按行业分类浏览，才有了这一层。
#
# 前 13 个直接取自素材库 `Skills岸单体` 的分类文件夹名（产品约定："用源目录分类"）；
# 最后补一个「系统」—— 客户端自带的音量 / 亮度 / 锁屏那几项没有对应行业，
# 但产品明确要求"原有的通用技能也要分类"，不能让它们无处可去。
#
# ⚠️ 「玄学」整分类删除（产品约定："删除玄学分类以及其中的 16 个技能"）——
# 这里少一项就够，但**前端 `SkillSettings.tsx` 的 `DOMAIN_ORDER` 必须同步**
# （那里有注释要求两边逐字一致），打包闸也钉着"前后端域清单一致"。
DOMAIN_ORDER: tuple[str, ...] = (
    "系统",
    "办公",
    "生活",
    "学术",
    "媒体",
    "法律",
    "医疗",
    "电商",
    "金融",
    "营销",
    "教育",
    "科技",
    "设计",
    "人力",
)

#: 客户端**自带**的通用技能归到哪个小分类（第三方技能包的 domain 随包带进来，不在这里）。
#: 产品约定：音量亮度锁屏→系统，文档转换/Excel→办公，
#: 天气记账→生活，论文降重→学术，去 AI 味→媒体，诉讼分析→法律，倪海厦经方→医疗。
BUILTIN_DOMAINS: dict[str, str] = {
    # 系统小工具
    "system_volume": "系统",
    "system_volume_get": "系统",
    "system_brightness_get": "系统",
    "system_brightness_set": "系统",
    "system_lock_screen": "系统",
    # 文档转换（5）
    "doc_word_to_markdown": "办公",
    "doc_markdown_to_word": "办公",
    "doc_to_pdf": "办公",
    "doc_pdf_to_text": "办公",
    "doc_parse": "办公",
    # Excel（3）
    "excel_read": "办公",
    "excel_write": "办公",
    "excel_analyze": "办公",
    # 生活（3）
    "weather_query": "生活",
    "expense_record": "生活",
    "expense_analyze": "生活",
    # 领域（4）
    "paper_deweight": "学术",
    "humanizer": "媒体",
    "pro_legal_strategist": "法律",
    "nihaixia": "医疗",
}


def domain_of(name: str, explicit: str = "") -> str:
    """这个技能属于哪个小分类（空 = 没归类，界面归到「其它」）。

    ``explicit`` 是技能自己声明的 domain（第三方技能包导入时从源目录写进去的）——
    它**优先**于下面那张内置映射表：那个是"包作者说的"，这张只是我们给自带技能补的。
    """
    return explicit or BUILTIN_DOMAINS.get(name, "")


def owner_label(owners: Iterable[str]) -> str:
    """把归属搭子 id 拼成给用户看的一句话（如「Soulmate」/「搭子总管」）。"""
    from .builtin import xjx  # 函数内导入：见文件末尾的说明

    labels = {**xjx.OWNER_LABELS, **_OWNER_LABEL_EXTRA}
    return "、".join(labels.get(item, item) for item in owners)


# --------------------------------------------------------------------------- #
# 判定：某个技能属于哪一类
# --------------------------------------------------------------------------- #
def is_exclusive(name: str) -> bool:
    """是不是**专属技能**（只有归属的那个搭子能用）。"""
    if name in EXCLUSIVE_EXACT or name.startswith(EXCLUSIVE_PREFIXES):
        return True
    # 指导型技能里的专属那批（见 `INSTRUCTION_EXCLUSIVE_OWNERS`）。
    # ⚠️ 接入这里的意义是**自动获得三条落盘入口的净化**：`without_exclusive` 会用它，
    # 于是老档案里"以前合法勾过、现在成了别人的专属"的残留会被静默剔除，
    # `routes/assistants.py` 那条则会**明确拒绝**别的搭子硬塞。
    if name in INSTRUCTION_EXCLUSIVE_OWNERS:
        return True
    from .builtin import xjx

    # 心鉴学：四条技能本身 + **两个配套工具**都算。
    # ⚠️ 配套工具必须算进来：它们不注册进技能页（用户看不见），但归属搭子得能调。
    # 漏掉的表现很隐蔽 —— 归属搭子的工具清单里少两个工具，"没有"而不是"报错"。
    return xjx.is_xjx_skill(name) or xjx.is_xjx_tool(name)


def without_exclusive(names: Iterable[str]) -> list[str]:
    """去掉**专属技能**的名字（也就是"写了也不会生效"的那些）。

    用在"落盘前"的净化上：专属技能按搭子归属自动生效、不靠白名单 ——
    写在档案里既不生效（装配时会被归属过滤排除），又会让人（或模型）
    以为"勾了就有用"。2026-10-07 起有三条落盘入口共用它：
    `routes/assistants.py`（用户保存，那条走的是"拒绝"而非静默剔除）、
    `assistants/transfer.py`（导入搭子包）、`agent/orchestrator.py`（AI 自建搭子）。

    ⚠️ **内置技能的名字不在过滤范围内**：它们写在档案里是无害的（装配时恒被并入），
    而且"档案里留着内置技能名"是既有行为，动它属于扩大改动面。
    """
    return [name for name in names if not is_exclusive(name)]


def bucket_of(name: str, source: str, domain: str = "") -> str:
    """这个技能属于四类里的哪一类。

    ``source`` 来自 `SkillMeta.source`（``builtin`` / ``mcp`` / ``custom``）；
    ``domain`` 是技能小分类（只有"展示归类"用得上，见下）。

    ⚠️ ``domain`` **默认空**：绝大多数调用点（装配、归属过滤、老档案净化）不需要它 ——
    那些地方只关心"这个技能能不能被搭子勾选"，而「通用技能」与「我的技能」在这一点上
    完全一样（`allowed_skill_names` 对两者一视同仁）。只有 `SkillMeta.to_dict`
    （下发展示）才需要它。
    """
    # ⚠️ 这两条短路必须放在**最前面**（新增）。
    # 原因：指导型技能的 source 也是 `"custom"` 且带 domain ⇒ 下面那条 `source == "custom"`
    # 分支会把它们一律判成「通用技能」，后面所有判定对它们**一次都不会被调用**。
    # ⇒ 想改它们的分类，只能在这里先拦下来。
    # ⚠️ 用"特定名字优先"而不是重排整个函数：其余 240 多个技能的归类因此**一个字都没变**。
    if name in INSTRUCTION_EXCLUSIVE_OWNERS:
        return BUCKET_EXCLUSIVE
    if name in ALWAYS_ON_INSTRUCTION_NAMES:
        return BUCKET_BUILTIN
    if source == "custom":
        # **带小分类的自定义技能归「通用技能」**。
        # 判据是 `domain` 而不是"是不是导入的"——用户手动建的技能没有 domain，
        # 仍留在「我的技能」（那里能单独删 / 停 / 改权限）；从素材库导入的都带 domain，
        # 进「通用技能」栏按分类浏览。
        return BUCKET_COMMON if domain else BUCKET_MINE
    if source == "mcp":
        # 产品约定：MCP 是"用户在 MCP 页自己连进来的"，归通用技能（可自选）
        return BUCKET_COMMON
    if is_exclusive(name):
        return BUCKET_EXCLUSIVE
    if name in COMMON_NAMES:
        return BUCKET_COMMON
    # 其余（含所有"忘了归类"的新技能）一律算内置 —— 理由见 COMMON_NAMES 上面的说明
    return BUCKET_BUILTIN


def owners_of(name: str) -> tuple[str, ...]:
    """专属技能的归属搭子 id；非专属返回空元组。"""
    from .builtin import xjx

    if xjx.is_xjx_skill(name):
        skill = xjx.skill_by_name(name)
        return skill.owners if skill is not None else ()
    if xjx.is_xjx_tool(name):
        # 两个配套工具是**两组共用**的（Soulmate 与 Love/Relation Buddy 都要用），
        # 所以归属是两组并集 —— 与 `xjx.may_use_tools` 的判定保持一致。
        return tuple(sorted(xjx.XJX_OWNER_IDS))
    # 指导型技能里的专属那批（见 `INSTRUCTION_EXCLUSIVE_OWNERS`）。
    # ⚠️ 不接这里的话，「每个专属技能都要有归属」那条单测会红，而且技能页的
    # `owner_label` 会是空串 —— 专属栏的分组标题会变成光秃秃的「专属」。
    if name in INSTRUCTION_EXCLUSIVE_OWNERS:
        return INSTRUCTION_EXCLUSIVE_OWNERS[name]
    if name in EXCLUSIVE_EXACT or name.startswith(EXCLUSIVE_PREFIXES):
        return (EXCLUSIVE_OWNER,)
    return ()


def may_use_exclusive(name: str, assistant_id: str | None) -> bool:
    """这个搭子**有没有资格**用这个专属技能（非专属技能恒为 True）。"""
    owners = owners_of(name)
    if not owners:
        return True
    return bool(assistant_id) and assistant_id in owners


def is_locked(name: str, source: str) -> bool:
    """内置技能与专属技能 → 用户与 AI 都**关不掉、也改不了权限**。

    ⚠️ 只对内置技能生效：MCP 工具的权限本来就由用户在 MCP 页里管；
    自定义技能是用户自己建的，当然要能删能关。

    ⚠️ 还要**并上既有那份硬锁名单**（`skill/locked.py::ALWAYS_ON_SKILLS`）：
    里面有两个心鉴学的**配套工具**（`xjx_place_lookup` / `xjx_fetch_report`），
    它们不算"专属技能"（专属判定只认那四条 `xjx-*` 技能），但同样必须常开 ——
    这一段漏掉的话，它们会掉进「通用技能」变成用户可以随手关掉的。
    """
    if source != "builtin":
        return False
    from .locked import ALWAYS_ON_SKILLS

    if name in ALWAYS_ON_SKILLS:
        return True
    if is_exclusive(name):
        return True
    # ⚠️ 这里用**显式名单**，不是"bucket 是不是内置" —— 见 LOCKED_BUILTIN_NAMES 的说明。
    return name in LOCKED_BUILTIN_NAMES


# --------------------------------------------------------------------------- #
# 装配：某个搭子能用哪些技能
# --------------------------------------------------------------------------- #
def forbidden_names(registered: Iterable[str], for_assistant: str | None) -> frozenset[str]:
    """该搭子**不该看见**的技能名。合并两处来源：

    1. 心鉴学的两个配套工具（既有机制，只管"是不是那两个的归属搭子"）；
    2. 归属别人的专属技能 —— 对非归属搭子应当**压根不存在**，而不是"调了会报错"：
       模型把"看得见"直接理解成"可以用"，留一个多余的工具只会诱导它去调。

    ``registered`` 传当前注册表的全部技能名。
    """
    from .builtin import xjx

    blocked = set(xjx.forbidden_tool_names(for_assistant))
    # ⚠️ 专属名单里那几条**固定名字**要查，且**不依赖注册表**：某个专属技能这一刻还没注册
    # （启动中途、或将来被摘掉）时，光遍历 `registered` 会漏掉它 —— 而搭子档案里的白名单是
    # 先用后装配的，中间恰好有这个时间差。漏拦的后果是"别的搭子拿到了不属于它的工具"。
    for name in EXCLUSIVE_EXACT:
        if not may_use_exclusive(name, for_assistant):
            blocked.add(name)
    for name in registered:
        if is_exclusive(name) and not may_use_exclusive(name, for_assistant):
            blocked.add(name)
    return frozenset(blocked)


def allowed_skill_names(
    sources: Mapping[str, str],
    *,
    assistant_id: str | None,
    enabled_skills: Iterable[str] | None,
    builtin_assistant: bool,
) -> set[str]:
    """这个搭子**实际可用**的技能名集合（**永不为空、永不返回 None**）。

    ``sources`` 是 ``{技能名: source}`` 的映射（来自 `SkillManager`）。
    语义见文件头：内置搭子 = 内置 ∪ 自己的专属；自定义搭子 = 内置 ∪ 勾选的通用/我的。

    ⚠️ **一定要返回显式集合**：旧实现用 ``None`` 表示"不限制（全开）"，
    于是"没有勾任何技能"与"想开全部"是同一个值 —— 而新口径要求它们是两件事。
    """
    allowed = {
        name
        for name, source in sources.items()
        if bucket_of(name, source) == BUCKET_BUILTIN
    }

    # ⚠️ 下面两处并集**必须放在 `if builtin_assistant` 之前**：
    # 指导型技能不在上面的遍历范围里（那个循环只走**工具注册表** `sources`，
    # 而它们不注册成工具），所以"每个搭子自带"这条口径只能在这里兑现。
    #
    # ⚠️ 这也是那两条"关不掉"的实现方式：`collect_instructions`（skill/custom.py）
    # 只认"传入的集合里有没有这个名字"，名字**恒在集合里** ⇒ 用户勾不勾它都生效。
    # 所以本函数是"关不掉"的唯一开关，别把这两行挪进某个分支 ——
    # 挪进去就等于"只有某类搭子关不掉"，而用户的口径是每个搭子都关不掉。
    allowed |= ALWAYS_ON_INSTRUCTION_NAMES

    # 指导型技能里的**专属**那批：只并给归属搭子。
    # ⚠️ 不写死在内置搭子分支里：归属判定（`may_use_exclusive` 内部查 `owners_of`）
    # 本身就是"这个搭子 id 在不在 owners 里"，对自定义搭子同样成立；
    # 写死在内置分支反而会让"将来某个自定义搭子被授权"变成要改两处。
    allowed |= {
        name
        for name in INSTRUCTION_EXCLUSIVE_OWNERS
        if may_use_exclusive(name, assistant_id)
    }

    if builtin_assistant:
        # 内置搭子：恒等于「全部内置 ∪ 自己的专属」，**忽略 enabled_skills**
        # （它的那个字段本来就被 locked_builtins 锁着，用户与 AI 都改不了）
        allowed |= {
            name
            for name, source in sources.items()
            if bucket_of(name, source) == BUCKET_EXCLUSIVE
            and may_use_exclusive(name, assistant_id)
        }
        return allowed

    # 自定义搭子：只认「通用 + 我的」两类；内置与专属**不能**靠勾选加上去
    # （前者本来就自带，后者是别人的专属）
    for name in set(enabled_skills or ()):
        source = sources.get(name)
        if source is None:
            # 不在工具注册表里 —— 多半是**指导型技能**：`kind == "instruction"` 的自定义
            # 技能不注册成工具（它的正文靠 `persona_with_instructions` 注入，见 skill/custom.py），
            # 所以在这里查不到。它们属「我的技能」，勾了就该生效 ⇒ **保留**。
            # 真正不存在的名字无害：下游（工具装配只认注册表、正文注入只认 custom_skills）
            # 各自会忽略它。
            #
            # ⚠️ 例外：**指导型技能里的专属那批**不能靠"档案里写了"就生效。
            # 上面那两处并集已经按归属把它们发了 —— 该拿到的搭子**不看白名单也有**
            # （所以这里丢掉的绝不会让归属搭子变少）；不该拿到的搭子，档案里写了也得丢，
            # 否则一句"我勾了它"就能绕过归属隔离 —— 而这条路径**不经过 `is_exclusive`**
            # （因为是注册表外的名字），是归属隔离唯一的漏洞口。
            if name in INSTRUCTION_EXCLUSIVE_OWNERS:
                continue
            allowed.add(name)
            continue
        if bucket_of(name, source) in (BUCKET_COMMON, BUCKET_MINE):
            allowed.add(name)
    return allowed


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #
def validate_registry(registered: Iterable[str]) -> list[str]:
    """名单里**指向不存在技能**的名字（返回空列表 = 全部对得上）。

    意义：技能 id 写错一个字不会报错，只会让那一个静静地待错分类 ——
    而"它为什么是可关的 / 为什么只有总管能用"这种问题没人查得出来。
    所以启动时跑一次，把这类错变成一条明确的日志。

    ``registered`` 必须是**完整注册表**（`SkillManager.all_names()`）——
    注意 `custom_skill_install` / `skill_package_install` 是在 `skill/custom.py`
    里注册的，不在 `discover_builtin_skills()` 的那一份里。
    """
    known = set(registered)
    missing = [name for name in sorted(COMMON_NAMES) if name not in known]
    missing += [name for name in sorted(EXCLUSIVE_EXACT) if name not in known]
    return missing


# ⚠️ 关于上面那些 `from .builtin import xjx` 的函数内导入：
# ``skill/manager.py`` 在启动早期就被 import（server/runtime.py），而它要 import 本模块；
# 本模块又需要 xjx 的归属数据。放模块顶层会让"谁先谁后"变成一条隐性约束 ——
# 将来任何一边加一行 import 都可能成环。函数内导入把这件事摊平成"用到时才解析"。

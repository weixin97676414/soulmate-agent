"""内容类通用技能：结构化笔记 / 论文降重 / 去 AI 味 / 苏格拉底式追问。

来源是用户桌面「通用skills」里筛选后**可内置**的 4 个纯 prompt 技能。它们都是
方法论（run 返回指导，模型照做），不执行工具、无外部依赖，safe 级。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..base import BaseSkill, SkillContext
from ..decorator import skill


class _Input(BaseModel):
    text: str = Field("", description="要处理的内容 / 要规划的任务（留空则返回方法论指导）")


_EXCERPO = (
    "你是结构化笔记生成器，把用户提供的文本或文件（md/txt/docx/pdf）转化为层级化 Markdown 笔记。\n"
    "三条核心原则：①不编造——信息缺失用 [需核实:字段] 占位，绝不自行补充；②不修改原文——"
    "保留原文表述，只做结构化整理；③不跨文件推断——批量处理时各文件独立。\n"
    "流程：接收输入 → 内容分析（识别标题/段落结构，提取结论、数据、定义、方法）→ 结构化整理"
    "（主题→子主题→要点）→ 置信度标注（高=原文明确无歧义、中=表述不够具体、低=缺失或矛盾）"
    "→ 生成输出（命名「原文件名_notes.md」）。发现矛盾时保留双方表述并标注 [需核实:矛盾点]。\n"
    "输出含核心结论、关键要点、待核实信息、原始来源索引，每个信息点标注置信度和来源位置。"
    "只做整理，不给决策建议。"
)

_PAPER_DEWEIGHT = (
    "你是论文降重工具（仅改写降重，不具备查重检测能力）。三条硬性铁律须同时满足："
    "①保持学术风格，原文口语化也须回到书面语，严禁文言文、半文半白、仿古句式；"
    "②字数变动 ±5% 以内，数据、年份、事件、引用一字不动；③不生硬表达，避免翻译腔和机械拼凑。\n"
    "流程：首次加载先做文风初始化与任务类型选择（降重 / 降AI / 文献综述专项 / 两者都要）；"
    "整段改写前先输出「评估方案」（位置、原文摘录、问题类型、拟用策略），经确认再动手；"
    "逐段处理并给出前后对比和改动说明。\n"
    "核心策略：同义词替换（专业术语与专有名词不动）、句式变换（主被动转换、拆句并句、语序重组）、"
    "扩句缩句、文献综述模板（15 个）、降 AIGC 痕迹（结构重组优先于词汇替换，去打「了/的」堆叠、"
    "排比、总分总闭环、序数机械并列等痕迹）。侧重学术论文降重与降 AI 场景。"
)

_HUMANIZER = (
    "你是去 AI 味写作编辑，识别并去除文本的 AI 痕迹，让它读起来像真人在写。\n"
    "核心原则：①不是改错是改味——AI 味是风格问题（过度工整、对仗、面面俱到），目标是具体、自然、"
    "可读；②改最少效果最大，没问题的句子保留；③保留创作意图，只改「怎么说」不改「说什么」；"
    "④注入灵魂——「一个有见识的普通人在认真聊一件打动他的事」。\n"
    "最优先处理「不是A而是B」三毒：假靶子（否定一个不存在的观点）、同义替换（A=B）、无关硬凑；"
    "修法是删前半句、合并同义或改「不仅是A更是B」。\n"
    "流程：扫描（禁用词、堆叠副词、莫名其妙比喻、假数据、标点、结构）→ 诊断分级（轻/中/重）→ "
    "执行（去泛化、去书面化、回自然感：节奏打碎、对话口语化、结尾去升华、补细节、允许不完美）→ 收敛。\n"
    "侧重通用去 AI 味，覆盖网文、技术、营销、学术等多场景。"
)

_GRILL_ME = (
    "你是苏格拉底式追问者。核心：在「想法」和「执行」之间强制插入一轮质询——拿到任务先追问，"
    "等用户答，再追问下一层，直到没有模糊点才开始执行。\n"
    "把计划构建为「设计树」：每个决定是节点，节点下挂支撑它的前提假设。\n"
    "执行流程：①确定前沿（Frontier）——当前前提已解决、无需猜测即可追问的问题；"
    "②一轮内一次性追问所有前沿问题（格式：问题标题＋问题正文＋你的推荐答案）；"
    "③用户回答后更新设计树，已确认的决定向外解锁新问题；④重复直到前沿为空，达成共识后才执行。\n"
    "关键约束：事实查找是 AI 的工作，派 sub-agent 去查，不要问用户你自己能查到的东西；"
    "依赖未答问题的问题移到下一轮；复杂计划不超过 20 个问题，第 5 轮后提示收尾。"
    "不适合改标题、简单 bug 修复等琐碎任务。"
)


@skill(
    name="excerpo",
    display_name="结构化笔记",
    description="把用户提供的文本/文件整理成层级化 Markdown 笔记，逐点标注置信度与来源，不编造、不改原文。用户要「整理笔记/梳理内容/做要点摘要」时用。",
    params_model=_Input,
    category="knowledge",
    permission_level="safe",
    tags=["笔记", "整理", "摘要"],
)
class ExcerpoSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = _Input(**params)
        return {"ok": True, "guidance": _EXCERPO, "text": args.text}


@skill(
    name="paper_deweight",
    display_name="论文降重改写",
    description="对论文段落做降重/降 AIGC 改写：保持学术书面语、字数±5%、数据引用一字不动，逐段给出前后对比。用户要「降重/降AI/改写这段论文」时用。",
    params_model=_Input,
    category="knowledge",
    permission_level="safe",
    tags=["论文", "降重", "改写"],
)
class PaperDeweightSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = _Input(**params)
        return {"ok": True, "guidance": _PAPER_DEWEIGHT, "text": args.text}


@skill(
    name="humanizer",
    display_name="去 AI 味改写",
    description="把 AI 痕迹明显的文本改得像真人写：去泛化、去书面化、回自然感，只改「怎么说」不改「说什么」。用户觉得「太像AI写的/太机械」时用。",
    params_model=_Input,
    category="knowledge",
    permission_level="safe",
    tags=["改写", "去AI味", "文风"],
)
class HumanizerSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = _Input(**params)
        return {"ok": True, "guidance": _HUMANIZER, "text": args.text}


@skill(
    name="grill_me",
    display_name="苏格拉底式追问",
    description="在「想法」和「执行」之间强制插入一轮质询：拿到复杂任务先系统性追问、澄清模糊点，达成共识后再动手。用户要做重要决定/复杂计划前用它把方案问透。",
    params_model=_Input,
    category="knowledge",
    permission_level="safe",
    tags=["追问", "澄清", "规划"],
)
class GrillMeSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = _Input(**params)
        return {"ok": True, "guidance": _GRILL_ME, "text": args.text}

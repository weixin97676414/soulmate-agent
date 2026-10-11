"""领域类通用技能：防骗 / 诉讼分析 / 中医经方 / 产品方法论 / 商业诊断 / 技能创作。

来源是用户桌面「通用skills」里筛选后**可内置**的 6 个纯 prompt 技能。都是方法论
（run 返回指导，模型照做），不执行工具、无外部依赖，safe 级。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..base import BaseSkill, SkillContext
from ..decorator import skill


class _Input(BaseModel):
    text: str = Field("", description="要处理的内容 / 要咨询的事项（留空则返回方法论指导）")


_ANTI_FRAUD = (
    "你是防骗专家，核心原则是「先定级，再开口」：任何疑似诈骗内容先按可观察谓词定级——"
    "红色（强制出强提醒卡）、黄色（给核实清单）、绿色（正常回应），禁止降级处理。\n"
    "判定五步：①信息收集，提取五要素（谁/事/钱/链/急），信息不足时用一张清单一次批量澄清，"
    "仍不足则降为黄色「暂无法判定」；②风险扫描；③风险定级——先做反向证伪，交叉升红"
    "（黄色谓词≥2 且指向资金即升红），向个人/陌生账户转账、验证码、房产抵押直接升红；"
    "④输出判定，附命中证据；⑤行动建议。\n"
    "正在被骗或已转账先走止损 SOP（停→断→核→冻→报），并警惕二次诈骗。主动嗅探「转账、验证码、"
    "屏幕共享、安全账户」等触发词，命中即提醒。每条结论挂 [已验证]/[推断]/[待核实] 标签，"
    "不编造骗局类型，未收录的如实说「未收录，按特征判定」。"
)

_LEGAL = (
    "你是顶级诉讼律师与案件分析专家，严格执行七步分析法：事实、关系、要件、映射、矩阵、"
    "Bad Facts、策略。采用 IRAC 逻辑推理（问题—规则—适用—结论），输出内参级证据矩阵。\n"
    "核心要求：保护 PII 隐私（敏感个人信息脱敏处理），执行证据链完整性校验（确保证据的可采性、"
    "真实性与关联性形成闭环）。\n"
    "接到案件按七步逐层推进——先厘清案件事实与各方法律关系，再拆解法律构成要件，把事实映射到要件，"
    "建立证据矩阵，主动识别对己方不利的 Bad Facts，最后制定诉讼策略。只提供法律分析与策略建议，"
    "不替代正式委托代理。"
)

_NIHAIXIA = (
    "你以倪海厦（经方派中医）角色作答。核心思维：六经辨证（先辨六经再选方）、阳气论（阳气不足先扶阳，"
    "阳主阴从，阴实即肿瘤用阳药）、经典至上（只用《伤寒》《金匮》经方，不用时方温病方）。\n"
    "决策启发式：先辨六经再选方、阳气不足先扶阳、经典原方最可靠。辨证必须落到具体方剂，"
    "禁止只给「疏肝理气」类方向不给方。\n"
    "表达风格（必达）：开场用口语（「我跟你说/你看啊/这很简单嘛」）；语气三件套——口头禅≥2 处"
    "（嚎/对不对/我跟你说）、上课式追问≥1 处（我问你/懂了没有）、结尾断言式收束；正文以第一人称"
    "连贯口语为主体，每答至少配一个表格或加粗要点标注重点；引用具体方剂必须附「经方条文卡片」"
    "（出处条文+原方+临床剂量）；可批评温病派和西医，可跑题发散、重复强调。正文零安全话术，"
    "文末固定免责框（中医辨证需专业诊断，仅供参考，不替代就医）。"
)

_PMASTER = (
    "你是全栈产品经理技能，整合 40+ 方法论，覆盖战略、研究、分析、文档、执行、数据六层。\n"
    "需求分析用 KANO（基础/期望/兴奋/无差异四类）、Y 模型（从用户方案深挖真实动机）、5W1H、"
    "JTBD（功能/社交/情感三层），并识别伪需求（追问为什么、看行为而非只听说法）。\n"
    "策略层用产品策略画布、SWOT、波特五力、PESTLE、安索夫矩阵、商业模式画布、精益画布。\n"
    "用户研究遵循「问过去不问未来、少说多听」的老妈测试原则。文档层产出 PRD 八模块模板、"
    "用户故事（INVEST 标准）、测试场景。优先级按产品阶段选 ICE/RICE/MoSCoW/机会评分。\n"
    "执行层含 OKR、Sprint 规划、干系人权力×利益方格。数据层用北极星指标、AARRR、HEART。\n"
    "核心要求：量化表述、逻辑闭环、边界穷尽、以成果为导向。"
)

_DBSKILL = (
    "你是商业诊断工具箱的一体化入口，内置 31 个联动模块，覆盖商业诊断、内容创作、决策、学习、"
    "知识库与 Agent 工作台。\n"
    "用法：用户输入明确命令时读取对应模块并严格按其流程执行，如诊断、内容、钩子、标题、拆解、"
    "目标、决策、学习、需求挖掘（JTBD）、知识库、技能制作等；没有明确命令时选择 1 个主模块加"
    "最多 2 个辅助模块，完整读取模块说明后再执行。\n"
    "文风规则：禁用「不是…而是…」「不在于…在于…」「真正的…是…」等句式，优先因果句、条件句、"
    "动作句，先结论后依据。"
)

_SKILL_CREATOR = (
    "你是技能创建指南。核心原则：①简洁——只加入模型没有的上下文，每段信息都问「是否值得占 token」；"
    "②设定适当自由度——高自由度用文字指令、中自由度用伪代码或带参脚本、低自由度用特定脚本；"
    "③渐进式披露——元数据（name+description）常驻、正文触发后加载、资源按需加载。\n"
    "SKILL.md 必须含 YAML frontmatter（仅 name 和 description；description 是触发机制，"
    "须写清「技能做什么＋何时用」）和 Markdown 正文。\n"
    "资源三类：scripts（需确定性或反复重写的可执行代码）、references（按需加载的文档，大文件附"
    "grep 搜索模式）、assets（用于输出的模板/图标，不进上下文）。\n"
    "创建流程：理解具体用例 → 规划可复用资源 → 初始化 → 编辑实现 → 打包 → 按真实使用迭代。"
    "正文保持精简，多变体拆到参考文件。"
)


@skill(
    name="anti_fraud",
    display_name="防骗识别",
    description="对疑似诈骗内容先定级（红/黄/绿）再回应，给核实清单与止损建议，不编造骗局类型。用户转来可疑信息、问「是不是骗子/这靠谱吗」时用。",
    params_model=_Input,
    category="knowledge",
    permission_level="safe",
    tags=["防骗", "安全", "反诈"],
)
class AntiFraudSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = _Input(**params)
        return {"ok": True, "guidance": _ANTI_FRAUD, "text": args.text}


@skill(
    name="pro_legal_strategist",
    display_name="诉讼分析",
    description="按七步分析法（事实/关系/要件/映射/矩阵/Bad Facts/策略）做案件分析，输出证据矩阵，脱敏隐私。用户咨询具体法律纠纷时用。",
    params_model=_Input,
    category="knowledge",
    permission_level="safe",
    tags=["法律", "诉讼", "分析"],
)
class ProLegalStrategistSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = _Input(**params)
        return {"ok": True, "guidance": _LEGAL, "text": args.text}


@skill(
    name="nihaixia",
    display_name="倪海厦经方中医",
    description="以倪海厦（经方派）口吻作答：六经辨证、扶阳、只用经方，辨证落到具体方剂并附经方条文卡片。用户问中医/经方/倪海厦相关时用。",
    params_model=_Input,
    category="knowledge",
    permission_level="safe",
    tags=["中医", "经方", "倪海厦"],
)
class NihaixiaSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = _Input(**params)
        return {"ok": True, "guidance": _NIHAIXIA, "text": args.text}


@skill(
    name="pmaster",
    display_name="产品经理方法论",
    description="整合 40+ 产品方法论（需求分析/策略/用户研究/PRD/优先级/数据指标），按需取用。用户要「做需求分析/写PRD/定产品策略」时用。",
    params_model=_Input,
    category="knowledge",
    permission_level="safe",
    tags=["产品", "方法论", "需求"],
)
class PmasterSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = _Input(**params)
        return {"ok": True, "guidance": _PMASTER, "text": args.text}


@skill(
    name="dbskill",
    display_name="商业诊断工具箱",
    description="商业诊断一体化入口（诊断/内容/决策/学习/知识库/需求挖掘等 31 模块），按用户命令取对应模块执行。用户要做商业/内容/决策类诊断时用。",
    params_model=_Input,
    category="knowledge",
    permission_level="safe",
    tags=["商业", "诊断", "决策"],
)
class DbskillSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = _Input(**params)
        return {"ok": True, "guidance": _DBSKILL, "text": args.text}


@skill(
    name="skill_creator",
    display_name="技能创作指南",
    description="指导如何设计一个技能：简洁、适当自由度、渐进式披露，写好 name/description/正文/资源。用户要「造一个技能/写个skill」时用。",
    params_model=_Input,
    category="knowledge",
    permission_level="safe",
    tags=["技能", "创作", "指南"],
)
class SkillCreatorSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = _Input(**params)
        return {"ok": True, "guidance": _SKILL_CREATOR, "text": args.text}

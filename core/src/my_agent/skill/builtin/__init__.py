"""内置 Skill 注册入口。

**显式导入**而非自动扫描：这样"哪些 Skill 会被加载"在代码里一眼可见，
也不会因为某处忘记 import 而导致 Skill 静默消失。
新增 Skill 模块后，把模块路径加进 ``_MODULES`` 即可。
"""

from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

# 显式列出要加载的模块。新增技能文件后必须在这里登记，
# 否则技能会因为"没被导入"而静默消失 —— 这是刻意的取舍：
# 宁可多写一行、也要让"加载了哪些技能"在代码里一眼可见。
_MODULES: list[str] = [
    # 系统类小工具
    "my_agent.skill.builtin.system",
    # 通用 HTTP 请求（等价 curl）与本地文件读写 —— 有了它们，模型才不必为
    # "访问一个没被封装成技能的接口""读写一个用户指定的文件"而回答"我做不到"。
    # 两类都是**读写分开两个技能**：只读的走 safe 直接执行，会改东西的走 confirm。
    "my_agent.skill.builtin.http_tools",
    "my_agent.skill.builtin.file_tools",
    # 分段读取超长内容：它是"无损外置"的另一半 —— 没有它，那条
    # "完整内容已保存到 XXX" 的提示就只是指向空气，等于换了个方式的省略。
    "my_agent.skill.builtin.output_read",
    # 浏览器自动化（用系统 Edge/Chrome，读写分级；browser_act 需确认）
    "my_agent.skill.builtin.browser",
    # 定时任务：搭子自己建 / 查 / 改 / 删 / 立刻跑（写操作是 confirm 级，
    # 因为它们会落盘配置、并且每一轮都真的调用模型、真的花钱）
    "my_agent.skill.builtin.task_tools",
    # 桌面能力（Windows）：剪贴板读写、音量/亮度/锁屏/截图。
    # 它们之所以归在"系统类"，是因为调的是本机能力而不是外部服务 ——
    # 读的后端是 ctypes 与系统自带 PowerShell（见 utils/windows_api.py）
    "my_agent.skill.builtin.clipboard",
    "my_agent.skill.builtin.system_control",
    # 文档转换（Word / Markdown / PDF 互转；PDF 用已打包的浏览器离线渲染）
    "my_agent.skill.builtin.doc_convert",
    # 办公
    "my_agent.skill.builtin.office.excel",
    "my_agent.skill.builtin.office.document",
    "my_agent.skill.builtin.office.report",
    "my_agent.skill.builtin.office.chart",
    # 自由创作 SVG：`office.chart` 只能画标准图表，用户要的是"照着做个封面/示意图"，
    # 所以补一个"把模型写好的 SVG 落成产物"的入口（用户 2026-09-28 报的缺口）
    "my_agent.skill.builtin.svg_tools",
    # 生活
    "my_agent.skill.builtin.life.weather",
    "my_agent.skill.builtin.life.expense",
    "my_agent.skill.builtin.life.reminder",
    # 日历（本地 .ics 或 CalDAV，读写分级：看日程 safe，增删改 confirm）
    "my_agent.skill.builtin.calendar",
    # 长期记忆（依赖可选的 chromadb；没装时技能会给出启用说明而不是报 ImportError）
    "my_agent.skill.builtin.knowledge",
    # 助手自己维护人格与记忆（改的那条是 confirm 级，不能降到 safe）
    "my_agent.skill.builtin.self_persona",
    # 档案字段（昵称 / 图标 / 头像 / 温度）：与 self_persona 是**两件事** ——
    # 界面上显示的名字读的是档案，不是人格 md（用户 2026-09-28 报的正是这个）
    "my_agent.skill.builtin.profile_tools",
    # 官网搭子库：先查官网有没有合适的搭子（用户要求"先查再建"），
    # 以及从官网把搭子包/搭子群包导进来（与前端导入共用 transfer.py）
    "my_agent.skill.builtin.buddy_tools",
    # 搭子团队：AI 自己建搭子 / 建群 / 排发言顺序，并把群讨论挪到**后台**跑
    # （结论发回发起它的那条对话）。"建之前先查现有搭子"的规则在这三处一起兜：
    # 技能描述、建群返回体、以及门面里的同名拒绝（见 skill/builtin/orchestrate.py）
    "my_agent.skill.builtin.orchestrate",
    # 跨来源检索：群聊记录 + 单聊历史 + 长期记忆一个入口查完（见 agent/history.py）
    "my_agent.skill.builtin.history_search",
    # 计划进度回报：单聊计划模式下，AI 每完成一步就汇报（见 agent/planner.py）。
    # 技能本身不判断真伪 —— 步号对不对由引擎按真实计划裁决（agent/engine.py）
    "my_agent.skill.builtin.plan_tools",
    # 压缩包：**只看内容、不解压**（用户 2026-09-26 的口径），只用标准库
    "my_agent.skill.builtin.archive",
    # AI 思考模式（道家做局思维）：策划/分析类搭子必装（见 orchestrator.create_assistant）
    "my_agent.skill.builtin.ai_thinking_mode",
    # 自我成长（记录踩坑/纠正）：每个搭子必装
    "my_agent.skill.builtin.self_growth",
    # 内容类通用技能（结构化笔记 / 论文降重 / 去 AI 味 / 苏格拉底追问）—— 桌面通用skills 筛选后内置
    "my_agent.skill.builtin.content_skills",
    # 领域类通用技能（防骗 / 诉讼 / 中医 / 产品 / 商业诊断 / 技能创作）
    "my_agent.skill.builtin.domain_skills",
    # 心鉴学（Soulmate / 人际关系运营）专属能力的**配套工具**：
    # 地点核对 + 报告代取。技能的"正文"（SKILL.md）不在注册表里，它是指导型内容，
    # 由 skill/custom.py 按搭子与线路注入提示词（见 skill/builtin/xjx.py）。
    # 只有一个真的"动作"，才值得在这里占一个工具位。
    "my_agent.skill.builtin.geo_lookup",
    "my_agent.skill.builtin.xjx_report",
    # 电脑操作（鼠标 / 键盘 / 窗口 / 启动程序 / 读界面元素）：**会真的操作用户
    # 电脑**，所以里面的技能**全部**是 confirm 级（用户 2026-10-06 定的口径
    # "每一步都先问"）。底座在 utils/windows_api.py（SendInput + .NET UI
    # Automation），零新增依赖。⚠️ 不登记在这里 = 技能静默消失。
    "my_agent.skill.builtin.computer",
    # 向用户发起的两个交互能力（用户 2026-10-07）：不确定意图时让他做选择、
    # 需要私钥这类敏感信息时弹输入框。它们**关不掉**（见 skill/locked.py）——
    # 用户的原话是"要不然我怎么不放通用技能呢"，所以别把它们挪去通用栏。
    # ⚠️ 顺序也有讲究：`ask_choice` 在前 —— 两个工具的描述都会进 system，
    # 而"先问清楚"比"先要东西"更该被模型看到（它更容易在这上面出错）。
    "my_agent.skill.builtin.ask_choice",
    "my_agent.skill.builtin.request_secret",
]


def discover_builtin_skills() -> list[type]:
    """导入全部内置 Skill 模块，返回被注册的 Skill 类列表。"""
    from ..base import BaseSkill

    found: list[type] = []
    for module_path in _MODULES:
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            logger.error("内置 Skill 模块导入失败 %s: %s", module_path, exc)
            continue
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseSkill)
                and attr is not BaseSkill
                and getattr(attr, "meta", None) is not None
            ):
                found.append(attr)
                logger.debug("发现内置 Skill: %s", attr.meta.name)
    return found

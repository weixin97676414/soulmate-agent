"""长期记忆技能：把资料存进本地长期记忆，需要时按语义检索出来。

对应《智能体框架开发文档》5.4 的 ``kb_search`` 与 8.3 的长期记忆。

## 为什么把「写入」和「检索」分成两个技能

它们的权限级别**完全不同**：

- ``kb_search`` 只读，``safe`` 级，模型可以自由调用；
- ``kb_add`` 会往本地库里写数据（且写进去的内容以后会出现在别的对话的上下文里），
  属 ``confirm`` 级，必须经过用户确认。

合成一个技能会让"只想查一下"也弹确认框，用户很快就会把确认设成自动批准——
那就连写入也一起放行了。

## 依赖缺失时要说人话

长期记忆依赖 chromadb，而它是本项目体积最大的一块（实测裸装约 265 MB），
所以做成了可选依赖。未安装时这里返回的是**怎么启用**，
而不是一个 ``ModuleNotFoundError``。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ...memory.long_term import LongTermMemory
from ...utils.timefmt import day_range
from ..base import BaseSkill, SkillContext
from ..decorator import skill

INSTALL_HINT = (
    "长期记忆当前不可用，两个可能的原因：\n"
    "1. **没有打开开关** —— 设置 → 安全与通用 → 长期记忆；\n"
    "2. **没装依赖** —— 长期记忆依赖 chromadb，它是本项目体积最大的一块"
    "（裸装约 265 MB），所以做成了可选依赖："
    "pip install \"my-agent-core[memory]\""
)


def require_memory(ctx: SkillContext) -> LongTermMemory:
    """取出长期记忆实例；不可用时给出可操作的说明。"""
    try:
        memory = ctx.service("memory")
    except SkillExecutionError as exc:
        raise SkillExecutionError(INSTALL_HINT) from exc
    if not isinstance(memory, LongTermMemory) or not memory.available:
        # ⚠️ **已经初始化失败过**的话，真正的原因就在 `init_error` 里（磁盘不可写、
        # 库名非法……）。这时再只列"开关 / 依赖"两条会把人**带偏**：用户查完那两条
        # 都好端端的，却不知道该往哪走 —— 实测踩过：搭子名带中文 → chromadb 拒收库名，
        # 界面上只说"长期记忆当前不可用"，查半天查不出。
        reason = memory.init_error if isinstance(memory, LongTermMemory) else None
        if reason:
            raise SkillExecutionError(f"{INSTALL_HINT}\n\n⚠️ 具体原因：{reason}")
        raise SkillExecutionError(INSTALL_HINT)
    return memory


# --------------------------------------------------------------------------- #
# 写入
# --------------------------------------------------------------------------- #
class KbAddParams(BaseModel):
    content: str = Field(..., min_length=1, description="要记住的内容（完整的一段话，不要只写关键词）")
    tags: list[str] = Field(
        default_factory=list, description="便于分类的标签，例如 [\"项目\", \"接口文档\"]"
    )
    source: str | None = Field(None, description="内容出处，例如文件名或网址")


@skill(
    name="kb_add",
    display_name="存入长期记忆",
    description=(
        "把一段资料存入本地长期记忆，之后可以用 kb_search 按语义检索到。"
        "当用户说「记住这个」「把这个存进长期记忆」「以后可能会用到」时使用。"
        "写入会持久化到本地，**直接执行，无需用户确认**。"
    ),
    params_model=KbAddParams,
    category="memory",
    # safe（免批准）：**产品要求**"存入长期记忆"这类技能
    # 由 AI 直接用、不弹确认，且永久开启（见 skill/locked.py）。
    #
    # 改回 confirm 的代价要清楚：这条写的是本地长期记忆，是搭子"记得住"的入口；
    # 每次弹确认就等于"用户不在电脑前时它什么也记不住"。它只写本机文件，
    # 没有任何外部副作用，所以免批准是合适的。
    #
    # 注意 kb_forget（从长期记忆删除）**保持 confirm**：删除不可逆，值得看一眼。
    permission_level="safe",
    tags=["长期记忆", "长期记忆"],
)
class KbAddSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = KbAddParams(**params)
        memory = require_memory(ctx)

        metadata: dict[str, Any] = {}
        if args.tags:
            # chromadb 的 metadata 只接受标量，列表要转成字符串
            metadata["tags"] = "、".join(args.tags)
        if args.source:
            metadata["source"] = args.source

        ids = await memory.add([args.content], metadatas=[metadata] if metadata else None)
        if not ids:
            raise SkillExecutionError("内容为空，没有写入任何记忆。")
        return {
            "ok": True,
            "id": ids[0],
            "message": f"已存入长期记忆（目前共 {await memory.count()} 条）。",
        }


# --------------------------------------------------------------------------- #
# 检索
# --------------------------------------------------------------------------- #
class KbSearchParams(BaseModel):
    query: str = Field(..., min_length=1, description="要检索的问题或关键词")
    # ⚠️ 不给（None）就用**设置页那个「默认检索条数」**（LongTermMemory.default_top_k）。
    # 以前这里写死 5，模型不填就永远 5 条 —— 用户在设置里把条数改成 8，
    # 知识库检索照样只给 5 条，看起来就是"设置不生效"。
    # 上限从 20 放宽到 2000：20 条对"把这一类资料都找出来"这种诉求是硬伤，
    # 而它原本只是个防手滑的数。真正要控制成本的话，用户/模型自己填小一点就行。
    top_k: int | None = Field(
        None, ge=1, le=2000, description="返回条数上限；不填就用设置里的默认检索条数"
    )
    since: str = Field("", description="只看这个日期之后的记忆（含当天），格式 YYYY-MM-DD；留空不限")
    until: str = Field("", description="只看这个日期之前的记忆（含当天），格式 YYYY-MM-DD；留空不限")


@skill(
    name="kb_search",
    display_name="检索长期记忆",
    description=(
        "按语义在本地长期记忆里检索相关资料。当用户提到「我之前说过」「上次那个」"
        "「查一下长期记忆」，或需要引用以前存过的资料时使用。"
        "返回的是相关资料片段，不是最终答案——需要据此组织回答。"
        "**每条结果都带时间**（when 字段）；用户问「上周/上个月我们定的什么」时，"
        "把 since / until 填上（YYYY-MM-DD）只取那个时间段，别把更早的旧结论当现在的口径。"
    ),
    params_model=KbSearchParams,
    category="memory",
    permission_level="safe",
    tags=["长期记忆", "长期记忆"],
)
class KbSearchSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = KbSearchParams(**params)
        memory = require_memory(ctx)

        # 日期 → epoch 区间。解析不出来的日期会被忽略（`day_range` 返回 None），
        # 而不是让整次检索报错：模型写日期的方式千奇百怪，宁可范围宽一点。
        since, until = day_range(args.since, args.until)
        hits = await memory.search(args.query, top_k=args.top_k, since=since, until=until)
        if not hits:
            total = await memory.count()
            return {
                "results": [],
                "message": (
                    "长期记忆里没有相关内容。"
                    if total > 0
                    else "长期记忆还是空的，可以先用 kb_add 存入一些资料。"
                ),
            }
        return {
            "results": [hit.to_dict() for hit in hits],
            "message": f"找到 {len(hits)} 条相关资料。",
        }


# --------------------------------------------------------------------------- #
# 遗忘与统计
# --------------------------------------------------------------------------- #
class KbForgetParams(BaseModel):
    ids: list[str] = Field(..., min_length=1, description="要删除的记忆 id（来自 kb_search 的结果）")


@skill(
    name="kb_forget",
    display_name="从长期记忆删除",
    description=(
        "按 id 从长期记忆里删除内容。仅在用户明确要求「忘掉这个」「删掉那条」时使用，"
        "删除不可恢复，需要用户确认。"
    ),
    params_model=KbForgetParams,
    category="memory",
    permission_level="confirm",
    tags=["长期记忆", "长期记忆"],
)
class KbForgetSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = KbForgetParams(**params)
        memory = require_memory(ctx)
        removed = await memory.forget(args.ids)
        return {"removed": removed, "message": f"已删除 {removed} 条记忆。"}


class KbStatsParams(BaseModel):
    pass


@skill(
    name="kb_stats",
    display_name="长期记忆概况",
    description="查看本地长期记忆里存了多少条内容。只读操作。",
    params_model=KbStatsParams,
    category="memory",
    permission_level="safe",
    tags=["长期记忆", "长期记忆"],
)
class KbStatsSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        memory = require_memory(ctx)
        return {"count": await memory.count()}

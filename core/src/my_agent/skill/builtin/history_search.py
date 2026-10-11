"""检索历史记录：群聊记录 / 单聊历史 / 长期记忆，一个入口。

## 为什么要有它

这三份数据住在三个地方，而用户问的是同一件事：「上周我们定的那个方案是怎么说的」。
没有它，模型只能挨个技能试（群聊用 group 的技能、记忆用 kb_search），试到哪算哪，
而且很容易只翻到一半就回答 —— 那正是用户说的"别把旧的当当下聊"。

真正的检索逻辑在 ``agent/history.py`` 的 ``HistorySearch`` 门面里（技能拿不到
runtime，也不该拿到）：这里只负责把参数翻成"时间区间"，并把结果原样交回模型。

## 时间

- ``since`` / ``until`` 用 ``YYYY-MM-DD``，**结束日含当天**（与 kb_search、
  审计页同一套口径 —— ``utils.timefmt.day_range`` 统一处理，不在这里另算一次）；
- 每条结果都带**可读时间**（``when``）：模型据此判断新旧，epoch 它算不明白；
- 没有时间戳的老记录**不补假时间**，被跳过多少条会写在 ``notes`` 里。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ...utils.timefmt import day_range
from ..base import BaseSkill, SkillContext
from ..decorator import skill


class HistorySearchParams(BaseModel):
    query: str = Field(
        ..., min_length=1, description="检索关键词（一句话或几个词都行，按字面匹配）"
    )
    scope: Literal["all", "group", "chat", "memory"] = Field(
        "all",
        description="all=三处都查；group=只查群聊记录；chat=只查单聊历史；memory=只查长期记忆",
    )
    group_id: str = Field("", description="只在某个群里查时填它（来自群清单）")
    author: str = Field(
        "", description="只看某个人/某个搭子说过的话：填名字的一部分即可，例如「我」或搭子名"
    )
    since: str = Field("", description="起始日期 YYYY-MM-DD（含当天）；留空不限")
    until: str = Field("", description="结束日期 YYYY-MM-DD（含当天）；留空不限")
    limit: int = Field(50, ge=1, le=200, description="最多返回多少条")


@skill(
    name="history_search",
    display_name="检索历史记录",
    description=(
        "跨**群聊记录 / 单聊历史 / 长期记忆**检索以前聊过的内容。"
        "当用户提到「我们之前说的」「上次那个方案」「前几天讨论的结论」"
        "「把以前相关的内容找出来」时使用。\n"
        "**每条结果都带时间**（when）。用户问「上周/上个月」时把 since / until 填上"
        "（YYYY-MM-DD，结束日含当天）—— 别把更早的旧结论当成现在的口径。"
    ),
    params_model=HistorySearchParams,
    category="memory",
    permission_level="safe",
    tags=["检索", "历史记录", "长期记忆"],
)
class HistorySearchSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = HistorySearchParams(**params)
        search = ctx.service("history")

        # 日期 → epoch 区间。解析不出来的日期会被忽略（`day_range` 返回 None），
        # 而不是让整次检索报错：模型写日期的方式千奇百怪，宁可范围宽一点。
        since, until = day_range(args.since, args.until)
        return await search.search(
            query=args.query,
            scope=args.scope,
            # ⚠️ 模型没指定群时，用**当前所在的群**：群记忆是群内
            # 成员共享的，在群里问"我们以前说过什么"就该翻到这个群的历史。
            # 单聊时 ctx.group_id 为空，行为与改动前完全一样（不碰群库）。
            group_id=args.group_id or ctx.group_id,
            author=args.author,
            since=since,
            until=until,
            limit=args.limit,
            # 长期记忆是按搭子分库的：不带这个，就查不到当前搭子那份
            assistant_id=ctx.assistant_id,
        )

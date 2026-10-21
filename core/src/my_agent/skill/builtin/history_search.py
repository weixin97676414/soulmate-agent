


















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

        
        
        since, until = day_range(args.since, args.until)
        return await search.search(
            query=args.query,
            scope=args.scope,
            
            
            
            group_id=args.group_id or ctx.group_id,
            author=args.author,
            since=since,
            until=until,
            limit=args.limit,
            
            assistant_id=ctx.assistant_id,
        )

"""改搭子的**档案字段**：昵称 / 图标 / 头像 / 温度。

## 为什么必须单独一条路，而不是塞进 ``self_persona_update``

实测反馈问题原话："让 AI 自己修改昵称时，只会修改 md，而不能修改搭子
中的昵称配置，这导致了昵称设置后，对话中搭子仍然显示的搭子名。"

根因很直白：界面上那个名字读的是 ``assistants.json`` 的 ``nickname`` 字段，
而 ``self_persona_update`` 改的是 ``IDENTITY.md`` 这类**人格文件** —— 两个地方。
所以这两件事要分开、并且各自说清楚：

- 人设文本（我是谁、我的规则）→ ``self_persona_update``（confirm 级）；
- 档案字段（叫什么、什么图标、什么头像、温度多少）→ **本技能**。

## 权限为什么是 ``safe`` 而不是 ``confirm``

``self_persona_update`` 是 confirm 级，理由写在它自己的模块注释里：那等于"让模型写
自己的系统提示词"，提示词注入的风险是真实的。而本技能改的四样东西**装不下指令**：

- 昵称有长度上限、不许换行（``orchestrator.MAX_NICKNAME_CHARS``）；
- 图标只收一个短表情；
- 头像是一张图（按魔数校验格式 + 限大小）；
- 温度限定在 0~2。

用户要的正是"我说一句它就改掉，别再让我点确认"，所以这里是 ``safe``。
⚠️ 哪天想给它加"直接改 rules / identity 文本"这类字段，**那一条必须留在 confirm**，
不要顺手把本技能整体降级。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ..base import BaseSkill, SkillContext
from ..decorator import skill


class ProfileUpdateParams(BaseModel):
    assistant_id: str = Field(
        "",
        description=(
            "要改哪个搭子（id 来自 team_list_assistants）。**留空 = 改你自己** —— "
            "用户说「你以后叫 XX」「把你自己的头像换成这张图」时留空就行。"
        ),
    )
    nickname: str = Field("", description="新昵称。不改就留空。最多 24 个字，不能换行。")
    emoji: str = Field("", description="新图标（一个表情符号）。不改就留空。")
    avatar_source: str = Field(
        "",
        description=(
            "新头像的图片来源，三种都支持：① 用户上传的图片（填附件的文件 id）；"
            "② 图片链接（http/https）；③ 本机图片的完整路径。不改就留空。"
            "⚠️ 图片要小于 512KB（它会被存进配置里），太大请让用户换一张或先压缩。"
        ),
    )
    clear_avatar: bool = Field(
        False, description="填 true 表示**清掉头像**、回到用图标显示。要清才填。"
    )
    temperature: float | None = Field(
        None, description="新温度（0~2，越大越随机）。不改就留空。"
    )


@skill(
    name="update_assistant_profile",
    display_name="改搭子的昵称 / 图标 / 头像 / 温度",
    description=(
        "改一个搭子的**档案**：昵称、图标（emoji）、头像、温度，四样都能改。\n"
        "用户说「你以后叫 XX」「把你的头像换成我发的这张图」「温度调低一点」时用它；"
        "**留空 assistant_id 就是改你自己**。\n"
        "⚠️ 与 self_persona_update 是两件事：那个改的是人格文本（我是谁、我的规则），"
        "这个改的是档案字段，而**界面上显示的名字/图标/头像读的是档案**。"
        "所以「只是给自己改个名字」也必须调本技能，光调 self_persona_update 界面上不会变。\n"
        "头像支持三种来源：用户上传的图片（填附件 id）、图片链接、本机路径。"
        "要改**别的**搭子时，先用 team_list_assistants 拿到它的 id。"
    ),
    params_model=ProfileUpdateParams,
    category="persona",
    permission_level="safe",
    tags=["人格", "自我", "搭子团队"],
)
class UpdateAssistantProfileSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ProfileUpdateParams(**params)
        # 留空 = 改自己。用 ctx 里的助手 id（**不让模型自己填"我是谁"**：
        # 它可能猜，猜错就改到别人身上了）
        target = args.assistant_id.strip() or (ctx.assistant_id or "").strip()
        if not target:
            raise SkillExecutionError(
                "不知道该改哪个搭子：当前会话没有绑定搭子。"
                "请在参数里给出 assistant_id（先用 team_list_assistants 查）。"
            )
        team = ctx.service("team")
        try:
            result = await team.update_assistant_profile(
                assistant_id=target,
                nickname=args.nickname or None,
                emoji=args.emoji or None,
                avatar_source=args.avatar_source,
                clear_avatar=args.clear_avatar,
                temperature=args.temperature,
                actor_id=ctx.assistant_id,
            )
        except ValueError as exc:
            # 原样转出去：措辞就是"给用户看的"，模型不该自己另编一套
            raise SkillExecutionError(str(exc)) from exc
        return {
            "updated": result,
            "message": (
                f"已更新「{result['nickname'] or target}」的：{'、'.join(result['changed'])}。"
                "界面上立刻生效，不需要重启。"
            ),
        }


__all__ = ["UpdateAssistantProfileSkill"]

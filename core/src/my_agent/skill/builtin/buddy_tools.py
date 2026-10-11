"""官网搭子库：先查、再从官网导入。

## 用户定的流程（2026-09-28）

> AI 要新建搭子 / 建群之前，**先看官网有没有合适的**：有就下载导入并装技能包；
> 没有才自己建。

三个技能分工：

- ``buddy_library_list`` —— 按**当前线路**打开官网搭子库，列出可导入的搭子；
- ``buddy_import`` —— 把一个搭子导进来（给它 json 地址或本地路径，技能包会自动跟上）；
- ``buddy_group_import`` —— 把一个搭子群包导进来。

## 闸门不在描述里，在 orchestrator

"先查再建"如果只写在工具描述里，模型照样会直接建。所以真正的约束在
``agent/orchestrator.py``：没查过官网就调 ``team_create_assistant`` /
``team_create_group`` 会被**拒绝**并被告知先去查（与项目既有的
"独立步骤 + 闸门 + 不静默"同一套路）。

查不到、连不上**不阻断**建 —— 但要求 AI 在回复里说明"官网未查到/查询失败，将自行创建"，
不许假装查过。
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ..base import BaseSkill, SkillContext
from ..decorator import skill


def _library(ctx: SkillContext) -> Any:
    return ctx.service("buddy")


class LibraryListParams(BaseModel):
    pass


@skill(
    name="buddy_library_list",
    display_name="查官网搭子库",
    description=(
        "打开**官网搭子库**（按你当前的线路）并列出上面可导入的搭子与搭子群："
        "名字、简介、包地址（page 上是什么就列什么，导入时以包内文件为准）。\n"
        "**新建搭子或建群之前必须先调它** —— 用户明确要求「先看官网有没有合适的，"
        "有就用现成的，没有才自己建」。没调它就调 team_create_assistant / "
        "team_create_group 会被拒绝。\n"
        "返回里会说明有没有查到；**如果读取失败，要如实告诉用户「官网未查到"
        "（附原因），我将自行创建」，不要假装查过。**"
    ),
    params_model=LibraryListParams,
    category="system",
    permission_level="safe",
    tags=["搭子团队", "官网"],
)
class BuddyLibraryListSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        library = _library(ctx)
        # 联网抓页面是同步 IO，丢线程里做，别占住事件循环
        return await asyncio.to_thread(library.list_available)


class BuddyImportParams(BaseModel):
    source: str = Field(
        ...,
        description=(
            "要导入的搭子的地址或本地路径：官网清单里的 package_url，"
            "或用户给你的 .zip / .json 文件路径。"
        ),
    )


@skill(
    name="buddy_import",
    display_name="从官网导入搭子",
    description=(
        "把一个搭子导入本机（人设、人格三件套、技能都一起落好）。\n"
        "参数 source 给**官网清单里的 package_url**（zip 包），或本地 .zip / .json "
        "的完整路径 —— 包里自带技能，一个文件就够；给旧版裸 json 时技能包也会按 "
        "skill_pack 字段自动下载安装。\n"
        "技能已存在时**不会重复导入**，只会把它配给这个搭子；导入后如果某个技能"
        "在本机找不到，返回体会逐条列出来。"
    ),
    params_model=BuddyImportParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队", "官网"],
)
class BuddyImportSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = BuddyImportParams(**params)
        library = _library(ctx)
        try:
            outcome = await library.import_buddy(args.source, actor_id=ctx.assistant_id)
        except SkillExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 - 要把它变成人话，不是堆栈
            raise SkillExecutionError(f"导入失败：{exc}") from exc
        missing = outcome.get("skills_missing") or []
        return {
            "imported": outcome,
            "message": (
                f"已{'更新' if outcome.get('action') == 'update' else '导入'}搭子"
                f"「{outcome['assistant']['name']}」（id={outcome['assistant']['id']}）。"
                + (
                    f"⚠️ 这些技能在本机找不到，已跳过：{'、'.join(missing)}。"
                    if missing
                    else ""
                )
            ),
        }


class BuddyGroupImportParams(BaseModel):
    source: str = Field(..., description="搭子群包的地址或本地路径（.zip）")


@skill(
    name="buddy_group_import",
    display_name="从官网导入搭子群",
    description=(
        "把一个**搭子群包**导入本机：包里是一份群配置 + 多个搭子包，"
        "导入后群与成员搭子一起建好。\n"
        "⚠️ 群里**不含优化顾问与审核员** —— 导入不会替你决定，"
        "建完仍要用 team_assign_group_roles 提交这两个角色的搭子 id。"
    ),
    params_model=BuddyGroupImportParams,
    category="system",
    permission_level="confirm",
    tags=["搭子团队", "官网"],
)
class BuddyGroupImportSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = BuddyGroupImportParams(**params)
        library = _library(ctx)
        try:
            outcome = await library.import_group(args.source, actor_id=ctx.assistant_id)
        except SkillExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SkillExecutionError(f"导入失败：{exc}") from exc
        return {
            "imported": outcome,
            "message": (
                f"已{'更新' if outcome.get('action') == 'update' else '导入'}群"
                f"「{outcome['group']['name']}」（id={outcome['group']['id']}）。"
                "**下一步必须用 team_assign_group_roles 提交审核员与优化顾问的搭子 id**，"
                "提交后才能用 team_start_discussion 开讨论。"
            ),
        }

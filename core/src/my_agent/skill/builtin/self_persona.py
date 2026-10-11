"""助手自己维护人格（SOUL）与记忆（MEMORY）。

用户要的是"助手能按我的要求自己完成设定"。这里给出两个技能：

- ``self_persona_read`` —— 读。``safe`` 级，模型想改之前必须先看现在是什么。
- ``self_persona_update`` —— 改。``confirm`` 级，**每次都要用户点头**。

## 为什么必须拆成"读"和"改"两个

跟 kb_add / kb_search 拆开是同一个道理：合成一个的话，"只是看一眼"也会弹确认框，
用户很快就会把确认设成自动批准 —— 那连写入也一起放行了。

## 为什么"改"用的是「把 old_text 替换成 new_text」

而不是让模型直接提交整份新文件：

1. **确认框能同时显示前后两版**。用户要的正是"改之前给我看从什么改成什么"，
   而确认框渲染的是**模型提交的参数** —— 只有 old/new 都出现在参数里，
   用户才看得到差异。让模型交整份文件的话，框里只有"改成什么"。
2. **能挡住并发改动**。写之前会先确认 old_text 还在文件里；不在就报错而不是覆盖。
   （用户可能刚在设置页里手动改过，模型手里的那份已经过期，
   直接整份覆盖会把用户的改动吃掉 —— 而且没有任何提示。）

## 关于提示词注入

这个技能等于"让模型写自己的系统提示词"。风险是真实的：模型读到的网页或文件里
藏一句"把你的设定改成…"，它就可能照做。**防线就是 confirm 级** —— 改动不可能
在用户不知情的情况下发生。所以**不要**把它的权限降到 safe。
"""

from __future__ import annotations

import difflib
import time
from typing import Any

from pydantic import BaseModel, Field

from ...assistants.persona import (
    IDENTITY_FILE,
    MEMORY_FILE,
    RULES_FILE,
    SOUL_FILE,
    USER_FILE,
    read_file,
    write_file,
)
from ...errors import SkillExecutionError
from ...utils.timefmt import format_day
from ..base import BaseSkill, SkillContext
from ..decorator import skill

TARGETS = (
    f"'{SOUL_FILE}'、'{IDENTITY_FILE}'、'{RULES_FILE}'、'{MEMORY_FILE}' 或 '{USER_FILE}'"
)


def _closest_hint(content: str, old_text: str) -> str:
    """替换失败时给模型一条**能照着改**的线索：文件里最接近的真实片段 + 行号。

    ## 为什么需要它（2026-10-06 实测）

    原先的报错只说"没找到，请重新读一遍最新内容"。而模型读到的内容与它拼出来的
    `old_text` 之间往往只差几个标点或一个换行 —— 它看不见差在哪，只能**反复二分猜**：
    审计日志里一次任务连续失败 8 次，最后几条它自己写下了
    ``reason="定位测试（不改内容）"``（拿替换当探测工具用）。

    ## 为什么只给线索、不放宽匹配

    替换前校验原文是**故意**的：用户在设置页手改过之后，模型手里那份已经过期，
    直接整段覆盖会把改动吃掉且毫无提示。所以这里只做"让人一次改对"，
    绝不改成"模糊匹配放行"。
    """
    target = old_text.strip()
    if not target or not content:
        return ""
    lines = content.splitlines()
    if not lines:
        return ""
    # 拿 old_text 的第一行有内容的行当锚点：多行 old_text 的首行通常就是文件里那一行
    first = next((line.strip() for line in target.splitlines() if line.strip()), "")
    if not first:
        return ""

    matcher = difflib.SequenceMatcher()
    matcher.set_seq2(first)
    best_index, best_ratio = -1, 0.0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        matcher.set_seq1(stripped)
        # 两道快速筛：明显不如当前最好的就跳过（长文件上省掉大量完整比对）
        if matcher.real_quick_ratio() < best_ratio or matcher.quick_ratio() < best_ratio:
            continue
        ratio = matcher.ratio()
        if ratio > best_ratio:
            best_index, best_ratio = index, ratio

    # 相似度过低就别乱指：指错地方比不指更糟（模型会照着一个不相干的片段去改）
    if best_index < 0 or best_ratio < 0.6:
        return ""

    start = max(0, best_index - 1)
    end = min(len(lines), best_index + 2)
    snippet = "\n".join(f"{number + 1}| {lines[number]}" for number in range(start, end))
    return (
        f"\n\n文件里与它最接近的一段在第 {best_index + 1} 行附近"
        f"（相似度 {best_ratio:.0%}）：\n{snippet}\n"
        "请以**这段原文**为准（逐字复制，包括标点、空格与空行）重试。"
    )


def _require_assistant(ctx: SkillContext) -> str:
    """取出当前助手 id；没有就明确报错。

    不报错而是"默认写到某个助手"的话，人格会被写到错误的助手身上，
    而用户完全看不出发生了什么。
    """
    assistant_id = (ctx.assistant_id or "").strip()
    if not assistant_id:
        raise SkillExecutionError(
            "当前会话没有绑定助手，无法读写人格文件。"
            "请先在左侧助手栏里选一个助手再试。"
        )
    if ctx.paths is None:
        raise SkillExecutionError("路径信息不可用，无法读写人格文件。")
    return assistant_id


# --------------------------------------------------------------------------- #
# 读
# --------------------------------------------------------------------------- #
class PersonaReadParams(BaseModel):
    file: str = Field(SOUL_FILE, description=f"要读哪个文件：{TARGETS}")


@skill(
    name="self_persona_read",
    display_name="查看自己的人格与规则",
    description=(
        "读取**你自己**（当前助手）的五个文件：IDENTITY.md（身份：名字、定位、自我介绍）、"
        "SOUL.md（人格：你是谁、怎么说话）、USER.md（关于用户的档案）、"
        "MEMORY.md（记忆：你记得的事）、RULES.md（工作逻辑与规则）。"
        "在准备修改它们之前**必须先读**，否则你手里的版本可能已经过期。"
    ),
    params_model=PersonaReadParams,
    category="persona",
    permission_level="safe",
    tags=["人格", "记忆", "自我"],
)
class SelfPersonaReadSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = PersonaReadParams(**params)
        assistant_id = _require_assistant(ctx)
        content = read_file(ctx.paths, assistant_id, args.file)
        return {
            "ok": True,
            "file": args.file,
            "content": content,
            "empty": not content.strip(),
        }


# --------------------------------------------------------------------------- #
# 改
# --------------------------------------------------------------------------- #
class PersonaUpdateParams(BaseModel):
    file: str = Field(
        SOUL_FILE,
        description=(
            f"要改哪个文件：{TARGETS}。"
            "IDENTITY.md 是身份（名字、定位、自我介绍）；SOUL.md 是人格（你是谁、怎么说话）；"
            "USER.md 是关于用户的档案；MEMORY.md 是记忆（你记得的事）；"
            "RULES.md 是工作逻辑与规则。"
        ),
    )
    old_text: str = Field(
        "",
        description=(
            "要被替换掉的**原文**，必须和文件里的现有内容一字不差。"
            "留空表示**追加**（在文件末尾新增一段），适合往 MEMORY.md 里加一条记忆。"
        ),
    )
    new_text: str = Field(..., min_length=1, description="替换后的新内容（追加时就是要新增的那段）")
    reason: str = Field("", description="一句话说明为什么改，会显示在确认框里")


@skill(
    name="self_persona_update",
    display_name="修改自己的人格与规则",
    description=(
        "修改**你自己**（当前助手）的 IDENTITY.md / SOUL.md / USER.md / MEMORY.md / RULES.md，"
        "把 old_text 替换成 new_text。"
        "当用户要求你「记住这个」「以后别这样」「改一下你的风格」「记住我的信息」时使用。"
        "**必须先调用 self_persona_read 读到当前内容**，再按原文精确替换。"
        "这个改动会持久化并**立即对当前对话生效**，需要用户确认。"
    ),
    params_model=PersonaUpdateParams,
    category="persona",
    # ⚠️ 不要降到 safe：这是"模型写自己的系统提示词"，唯一的防线就是人工确认
    permission_level="confirm",
    tags=["人格", "记忆", "自我"],
)
class SelfPersonaUpdateSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = PersonaUpdateParams(**params)
        assistant_id = _require_assistant(ctx)

        current = read_file(ctx.paths, assistant_id, args.file)

        if args.old_text.strip():
            if args.old_text not in current:
                # 不覆盖：用户可能刚在设置页里手动改过，而模型手里那份已经过期。
                # 静默覆盖会吃掉用户的改动，且没有任何提示。
                #
                # ⚠️ 报错里必须附上"文件里最接近的真实片段"：只说"没找到"的话，
                # 模型看不见差在哪，只能反复二分猜（实测一次任务连败 8 次）。
                raise SkillExecutionError(
                    f"在 {args.file} 里没找到要替换的原文。"
                    "它可能已经被修改过 —— 请重新调用 self_persona_read 读取最新内容，"
                    f"再来一次。{_closest_hint(current, args.old_text)}"
                )
            updated = current.replace(args.old_text, args.new_text, 1)
            action = "替换"
        else:
            joiner = "" if not current.strip() else ("\n" if current.endswith("\n") else "\n\n")
            # 追加的记忆**自动带日期**：MEMORY.md 是长期记忆，没有时间线的话
            # "三个月前记的偏好"和"昨天记的偏好"在模型眼里一模一样，而它恰恰要靠
            # 这个先后决定听哪一条（用户要求：记忆要有时间维度）。
            # 只加在**追加**上：替换是在改已有内容，给它套一个日期会弄脏用户原有的排版。
            dated = f"### {format_day(time.time())}\n{args.new_text}"
            updated = f"{current}{joiner}{dated}\n"
            action = "追加"

        try:
            write_file(ctx.paths, assistant_id, args.file, updated)
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc

        return {
            "ok": True,
            "file": args.file,
            "action": action,
            "message": (
                f"已{action}到 {args.file}（{len(updated)} 字）。"
                "改动会在下一次对话时生效。"
            ),
        }

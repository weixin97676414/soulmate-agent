





























from __future__ import annotations

import difflib
import time
from typing import Any

from pydantic import BaseModel, Field

from ...assistants.persona import (
    EVOLUTION_LOG_FILE,
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
    f"'{SOUL_FILE}'、'{IDENTITY_FILE}'、'{RULES_FILE}'、'{MEMORY_FILE}'、'{USER_FILE}' "
    f"或 '{EVOLUTION_LOG_FILE}'"
)


def _closest_hint(content: str, old_text: str) -> str:















    target = old_text.strip()
    if not target or not content:
        return ""
    lines = content.splitlines()
    if not lines:
        return ""
    
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
        
        if matcher.real_quick_ratio() < best_ratio or matcher.quick_ratio() < best_ratio:
            continue
        ratio = matcher.ratio()
        if ratio > best_ratio:
            best_index, best_ratio = index, ratio

    
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





    assistant_id = (ctx.assistant_id or "").strip()
    if not assistant_id:
        raise SkillExecutionError(
            "当前会话没有绑定助手，无法读写人格文件。"
            "请先在左侧助手栏里选一个助手再试。"
        )
    if ctx.paths is None:
        raise SkillExecutionError("路径信息不可用，无法读写人格文件。")
    return assistant_id





class PersonaReadParams(BaseModel):
    file: str = Field(SOUL_FILE, description=f"要读哪个文件：{TARGETS}")


@skill(
    name="self_persona_read",
    display_name="查看自己的人格与规则",
    description=(
        "读取**你自己**（当前助手）的六个文件：IDENTITY.md（身份：名字、定位、自我介绍）、"
        "SOUL.md（人格：你是谁、怎么说话）、USER.md（关于用户的档案）、"
        "MEMORY.md（记忆：你记得的事）、RULES.md（工作逻辑与规则）、"
        f"{EVOLUTION_LOG_FILE}（你的进化日志：每周那轮改了什么、为什么、下轮要验证什么）。"
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
        "修改**你自己**（当前助手）的 IDENTITY.md / SOUL.md / USER.md / MEMORY.md / "
        f"RULES.md / {EVOLUTION_LOG_FILE}，把 old_text 替换成 new_text。"
        "当用户要求你「记住这个」「以后别这样」「改一下你的风格」「记住我的信息」时使用；"
        f"每周的「全员进化」那轮也用它读写 {EVOLUTION_LOG_FILE}"
        "（old_text 留空 = 在末尾追加，并自动带上日期标题）。"
        "**必须先调用 self_persona_read 读到当前内容**，再按原文精确替换。"
        "这个改动会持久化并**立即对当前对话生效**，需要用户确认。"
    ),
    params_model=PersonaUpdateParams,
    category="persona",
    
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
                
                
                
                
                
                raise SkillExecutionError(
                    f"在 {args.file} 里没找到要替换的原文。"
                    "它可能已经被修改过 —— 请重新调用 self_persona_read 读取最新内容，"
                    f"再来一次。{_closest_hint(current, args.old_text)}"
                )
            updated = current.replace(args.old_text, args.new_text, 1)
            action = "替换"
        else:
            joiner = "" if not current.strip() else ("\n" if current.endswith("\n") else "\n\n")
            
            
            
            
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

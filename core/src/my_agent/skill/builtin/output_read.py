


























from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ...memory.spill import skip_chars
from ...skill.base import BaseSkill, SkillContext
from ...skill.decorator import skill






MAX_WINDOW_CHARS = 2_000_000


class ReadToolOutputParams(BaseModel):
    path: str = Field(..., description="要读取的文件路径。取自上一条工具结果里的「完整内容已保存到」")
    offset: int = Field(0, ge=0, description="从第几个字符开始读（0 表示开头）")
    limit: int = Field(
        12_000,
        ge=1,
        le=MAX_WINDOW_CHARS,
        description=(
            "这一次最多读多少个字符（上限 2000000）。想看更多就填更大的数，"
            "或按返回的 next_offset 连续读几段 —— 内容不会少，只是分几次给"
        ),
    )


@skill(
    name="read_tool_output",
    display_name="分段读取超长内容",
    description=(
        "读取一个文件的指定字符区间，用于把上一条工具结果里"
        "「完整内容已保存到 XXX」的那份全文全部读完；也可用于分段阅读任何大文件。"
        "返回值里会带上 next_offset 与 eof：eof 为 false 说明后面还有内容，"
        "把 offset 设成 next_offset 再调一次即可继续。"
        "只要一直读下去就能拿到全部内容 —— 不会丢、不会被省略。"
    ),
    params_model=ReadToolOutputParams,
    category="system",
    permission_level="safe",
    tags=["文件", "分段读取", "无损"],
)
class ReadToolOutputSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ReadToolOutputParams(**params)
        
        
        

        
        
        path = ctx.resolve_path(args.path.strip(), mode="read")
        if path.is_dir():
            raise SkillExecutionError(f"「{path}」是目录，不是文件。")

        try:
            size_bytes = path.stat().st_size
            
            
            
            with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                skip_chars(handle, args.offset)
                chunk = handle.read(args.limit)
                
                
                has_more = bool(handle.read(1))
        except OSError as exc:
            raise SkillExecutionError(f"读取失败：{exc}") from exc

        next_offset = args.offset + len(chunk)
        
        if not chunk and not has_more and args.offset > 0:
            raise SkillExecutionError(
                "offset 已经超过文件末尾了（这次没读到任何字符）。"
                "如果内容已经读完就可以停；要继续读请把 offset 设在文件长度以内。"
            )

        return {
            "path": str(path),
            "offset": args.offset,
            "limit": args.limit,
            "content": chunk,
            "chars_returned": len(chunk),
            "size_bytes": size_bytes,
            "next_offset": next_offset,
            "eof": not has_more,
            "hint": (
                "已读到文件末尾，内容完整。"
                if not has_more
                else f"后面还有内容。用 offset={next_offset} 继续读，"
                "直到 eof 为 true 即可拿到全文。"
            ),
        }

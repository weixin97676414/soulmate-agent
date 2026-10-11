"""分段读取超长内容（工具结果全文 / 大文件）。

## 为什么必须有这个技能

模型单次请求能装下多少 token 是厂商的物理限制。当一份工具结果（或一个大文件）
超过这个容量时，``memory/spill.py`` 会把**全文原样**写到磁盘，并告诉模型
"完整内容在这个文件里，从第 N 个字符继续读"。

如果只有前半句、没有这个技能，那个路径就只是"一个指向空气的提示"——
模型知道内容存在却拿不到，等于换了个方式的省略。所以这个技能是
**"内容可以不在上下文里，但绝不可以不可达"**这条原则的另一半。

## 为什么按字符而不是按行/字节

- 按**字节**切片会在多字节字符中间劈开，读回来是乱码 —— 而乱码与
  "丢内容"在用户眼里是同一件事；
- 按**行**需要一个"这一行有多长"的上界，遇到没有换行的 JSON 单行文件就失效了，
  而超长工具结果恰恰经常就是单行 JSON。

## 为什么窗口大小由模型自己给

窗口是"这一次读多少"，不是"内容有多少"。默认 12000 字符；模型想要更多就填更大，
想要精确定位就带上 offset。返回值里始终带 ``next_offset`` / ``eof`` / ``total_chars``，
所以模型可以一直读到自己确认读完为止 —— 这一点是刻意的：**任何"没读完"都必须
由模型自己看得见**（``eof: false``），而不是由我们替它决定"差不多了"。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ...memory.spill import skip_chars
from ...skill.base import BaseSkill, SkillContext
from ...skill.decorator import skill

# 单次读取的**窗口**上限。
#
# 它约束的是"这一次调用返回多少"，不是"能读到多少内容"：文件里剩下的部分
# 一直都在，模型用 next_offset 接着读就行。给这个数是为了避免"模型手滑填了
# 十亿"时把进程内存打满 —— 那种崩溃会让用户连错误都看不到。
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
        # ``limit`` 的上界由 schema（``le=MAX_WINDOW_CHARS``）负责，框架会把
        # 校验失败转成一条"参数不合法，请修正后重试"的工具错误交给模型 ——
        # 所以这里不再重复判断（那样会是一段永远走不到的死代码）。

        # 走白名单校验：这里的文件既可能是我们外置的工具结果
        # （artifacts 目录，永远放行），也可能是用户工作区里的文件。
        path = ctx.resolve_path(args.path.strip(), mode="read")
        if path.is_dir():
            raise SkillExecutionError(f"「{path}」是目录，不是文件。")

        try:
            size_bytes = path.stat().st_size
            # ⚠️ 只读"这一段"，不把整个文件读进内存：
            # 这个技能存在的意义就是处理"大到读不完"的文件，
            # 若它自己先整体读一遍就自相矛盾了。
            with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                skip_chars(handle, args.offset)
                chunk = handle.read(args.limit)
                # 探一个字符判断是否到末尾。**不把它交给模型** ——
                # 它只是用来回答"后面还有没有内容"这个问题的。
                has_more = bool(handle.read(1))
        except OSError as exc:
            raise SkillExecutionError(f"读取失败：{exc}") from exc

        next_offset = args.offset + len(chunk)
        # 空结果 + 有剩余 = 偏移落在文件末尾之外（例如把 next_offset 又加了一次）
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

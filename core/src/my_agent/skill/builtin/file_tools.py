



































from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ...skill.base import BaseSkill, SkillContext
from ...skill.decorator import skill











WHOLE_READ_LIMIT_BYTES = 32 * 1024 * 1024


def _decode(raw: bytes) -> tuple[str, str]:






    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    
    return raw.decode("utf-8", errors="replace"), "utf-8(容错)"


class FileReadParams(BaseModel):
    path: str = Field(..., description="要读取的文件或目录路径，可以是绝对路径")


@skill(
    name="file_read",
    display_name="读取本地文件",
    description=(
        "读取本机上的文本文件内容，或列出一个目录里有哪些文件。"
        "当用户说「读一下这个文件」「看看那个目录里有什么」并给出路径时使用。"
        "只读，不会修改任何文件。**内容完整返回，不做截断**；"
        "文件特别大（超过 32MB）时会给出提示，请改用 read_tool_output 分段读取，"
        "分几次即可读完，内容不会少。"
    ),
    params_model=FileReadParams,
    category="system",
    permission_level="safe",
    tags=["文件", "本地", "只读"],
)
class FileReadSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = FileReadParams(**params)
        
        path = ctx.resolve_path(args.path.strip(), mode="read")

        if path.is_dir():
            
            
            entries: list[dict[str, Any]] = []
            for item in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                try:
                    size = item.stat().st_size if item.is_file() else None
                except OSError:
                    size = None
                entries.append({"name": item.name, "is_dir": item.is_dir(), "size": size})
            return {
                "path": str(path),
                "kind": "directory",
                "count": len(entries),
                "entries": entries,
            }

        if not path.is_file():
            raise SkillExecutionError(f"「{path}」既不是文件也不是目录。")

        size = path.stat().st_size
        if size > WHOLE_READ_LIMIT_BYTES:
            
            
            
            
            return {
                "path": str(path),
                "kind": "file",
                "size_bytes": size,
                "too_large_to_read_at_once": True,
                "hint": (
                    f"这个文件有 {size} 字节，一次性整体读回会占满内存。"
                    "请改用 read_tool_output 分段读取，例如："
                    f'read_tool_output(path="{path}", offset=0, limit=20000)，'
                    "然后按返回值的 next_offset 继续，直到 eof 为 true —— "
                    "这样能把全文完整读完，内容不会缺少。"
                ),
            }

        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise SkillExecutionError(f"读取失败：{exc}") from exc

        text, encoding = _decode(raw)
        return {
            "path": str(path),
            "kind": "file",
            "size_bytes": len(raw),
            "encoding": encoding,
            "content": text,
        }


class FileWriteParams(BaseModel):
    path: str = Field(..., description="要写入的文件路径，可以是绝对路径")
    content: str = Field(..., description="要写入的内容")
    mode: str = Field(
        "overwrite",
        description="overwrite = 覆盖整个文件；append = 追加到末尾",
    )
    create_dirs: bool = Field(True, description="父目录不存在时是否自动创建")


@skill(
    name="file_write",
    display_name="写入本地文件",
    description=(
        "把内容写入本机文件，可以覆盖整个文件或追加到末尾，父目录不存在会自动创建。"
        "当用户说「把这段内容存到某个文件」「追加到那个文件里」时使用。"
        "会修改磁盘上的真实内容，执行前会请用户确认。"
    ),
    params_model=FileWriteParams,
    category="system",
    
    permission_level="confirm",
    tags=["文件", "本地", "写入"],
)
class FileWriteSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = FileWriteParams(**params)
        if args.mode not in ("overwrite", "append"):
            raise SkillExecutionError("mode 只能是 overwrite 或 append。")

        
        path: Path = ctx.resolve_path(args.path.strip(), mode="write")

        if args.create_dirs:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise SkillExecutionError(f"创建目录失败：{exc}") from exc

        existed = path.exists()
        try:
            
            
            
            
            
            
            with path.open("a" if args.mode == "append" else "w", encoding="utf-8", newline="") as handle:
                handle.write(args.content)
        except OSError as exc:
            raise SkillExecutionError(f"写入失败：{exc}") from exc

        return {
            "path": str(path),
            "mode": args.mode,
            "action": "已覆盖" if (existed and args.mode == "overwrite") else (
                "已创建" if args.mode == "overwrite" else "已追加"
            ),
            "chars_written": len(args.content),
            "size_bytes": path.stat().st_size,
        }

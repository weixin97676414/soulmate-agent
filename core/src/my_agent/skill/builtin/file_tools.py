"""通用本地文件读写能力。

## 为什么需要它

在此之前，模型能碰的只有"上传的附件"和"产物目录"（office 那几个技能各自的入口）。
用户说"把这段内容存到 D 盘那个文件里""读一下我桌面上的这个配置"时，
模型没有通用的手段——只能绕着走，或者干脆说做不到。

## 安全：一切路径都必须过 ``ctx.resolve_path``

这是**唯一**的入口。它背后是 ``PathPolicy``：

- 工作区与产物目录**永远放行**；
- 用户在设置里配的白名单之外一律拒绝；
- 白名单为空时表示"不限制"（用户的选择，不是我们的默认）。

**不要**在这里直接用 ``Path(...)`` —— 那等于把白名单彻底绕过去。

## 读写分开的权限

- ``file_read``（**safe**）：读文本、列目录。只读动作直接执行。
- ``file_write``（**confirm**）：写文件、追加、建目录。会覆盖磁盘上的真实内容，
  必须让用户看一眼。

## 关于"读大文件"

以前这里有一个 200000 字符的读取上限，还有 500 条的列目录上限。它们已经被**删除**：

- 读的上限会真的丢掉内容，而用户的原话是"不要做任何截断/省略"；
- 需要控制"这一次读多少"时，正确做法是**由调用方指定区间** ——
  也就是 ``read_tool_output`` 那个按 offset 分段读的能力，读完为止，
  而不是由我们替用户决定"后面不用看了"。

列目录同理：文件多就该如实列出全部，用户要的是"有哪些文件"，不是"前 500 个"。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ...skill.base import BaseSkill, SkillContext
from ...skill.decorator import skill

# 单次整体读回的**内存护栏**（字节）。
#
# ⚠️ 这**不是**内容上限，两者必须分清：
# - 内容上限：砍掉内容、丢掉用户的东西 —— 已被彻底删除，不再有；
# - 内存护栏：文件大到不能一次性读进内存时，**不读、也不切**，而是
#   把请求转交给 ``read_tool_output`` 按区间读（见下面 ``run`` 里的处理）。
#   模型因此仍然能拿到**全部**内容，只是分几次拿。
#
# 取 32MB：远超任何"文本类工具结果"的量级（用户遇到的那条是 23KB），
# 又远低于会把进程撑坏的量级。真踩到这条线的基本只有日志/镜像/数据库文件。
WHOLE_READ_LIMIT_BYTES = 32 * 1024 * 1024


def _decode(raw: bytes) -> tuple[str, str]:
    """按 UTF-8 → GBK 的顺序尝试解码，返回 (文本, 实际用的编码)。

    国内用户的纯文本文件很常见是 GBK/GB18030（Excel 导出的 csv、
    老编辑器存的 txt）。只试 UTF-8 的话这些文件会整篇变成问号，
    而用户看到的解释是"文件读出来是乱码"。
    """
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    # 两种都不行：容错解码，至少把能认的部分给出去
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
        # mode="read"：PathPolicy 会要求文件已存在、且在白名单内
        path = ctx.resolve_path(args.path.strip(), mode="read")

        if path.is_dir():
            # 列目录**不做数量上限**：用户问的是"这里有哪些文件"，
            # 给他前 500 个等于让他以为这就是全部（而且不会察觉少了什么）。
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
            # **不读、也不切**：一次性读进内存会把进程撑坏（那种崩溃让用户连错误
            # 都看不到）。这里把请求**转交**给分段读取 —— 模型按区间把文件读完即可，
            # 内容一条都不少。这与"截断"的区别在于：我们既没有丢内容，也没有替
            # 用户决定"看到哪就够了"。
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
    # confirm：会覆盖磁盘上的真实内容，不能默默做
    permission_level="confirm",
    tags=["文件", "本地", "写入"],
)
class FileWriteSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = FileWriteParams(**params)
        if args.mode not in ("overwrite", "append"):
            raise SkillExecutionError("mode 只能是 overwrite 或 append。")

        # mode="write"：PathPolicy 允许文件还不存在（否则新建文件永远被拒）
        path: Path = ctx.resolve_path(args.path.strip(), mode="write")

        if args.create_dirs:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise SkillExecutionError(f"创建目录失败：{exc}") from exc

        existed = path.exists()
        try:
            # ⚠️ 必须显式 `newline=""`：默认的文本模式会把 `\n` 翻译成 Windows 的
            # `\r\n`，于是"写入的内容"和用户给的内容**不是同一份字节** ——
            # 模型按要求写一段代码/配置，用户打开却多了看不见的回车
            # （对 shell 脚本、Makefile 这类文件是实打实的破坏）。
            # 追加模式也用 UTF-8：目标若是 GBK，混写会把原有内容读坏，
            # 而"先整体解码再整体重写"对一个"追加一段文字"的动作失败面太大。
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

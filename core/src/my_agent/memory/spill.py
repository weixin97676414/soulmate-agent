"""超长内容的**无损外置**（spill）。

## 为什么需要它

模型单次请求能装下多少 token，是**厂商的物理限制**，不是我们能改的东西。
但"这一次装不下"和"看不到"是两件完全不同的事：

- **以前**：超过 4000 字符的工具结果被砍成"头 2000 + ``…（中间省略 N 字符）…`` + 尾 2000"。
  中间那段**被销毁**，模型永远拿不回来。而紧挨着的注释写着"完整内容已落产物目录"
  —— 那句话是**错的**：对 ``http_fetch``、长期记忆检索、MCP 工具这些没有产物目录的
  调用，内容就是真的没了，而且服务端明明完整发来了（用户实测 ``truncated: false`` /
  ``bytes: 23006``，却在正文里看到"中间省略 5745 字符"）。
- **现在**：完整内容**一个字节不少**地写进磁盘，投递给模型的是"开头一段 + 明确的
  续读指引"（文件在哪、总长多少、从哪个偏移继续）。模型随时能把剩下的读完。

一句话：**内容可以不在这一次的上下文里，但绝不可以不可达。**

## 为什么写盘是同步的

``MemoryManager.get_context()`` 是同步方法（它在每轮请求构造上下文时被调用），
而这里只在"某条内容确实超出单次容量"时才会触发 —— 那是低频路径，且同一份内容
只会写一次（调用方按 tool_call_id 缓存）。为此引入一套异步落盘管线，
换来的是每次对话都多一层 await 与一次调度，不划算。

写入用"先写临时文件再替换"：中途失败或进程被杀时，读者要么看到旧文件、
要么看到完整的新文件，不会读到半截内容 —— 而"半截内容"正是这个模块要消灭的东西。
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 外置文件存放的目录名（挂在 artifacts_dir 下）。
#
# 为什么放 artifacts_dir：它本来就在路径白名单的"永远放行"列表里
# （见 security/paths.py），所以模型可以用统一的读文件能力读回来，
# 不需要为这个目录再开一条豁免。
SPILL_DIRNAME = "tool-output"

# 单次投递给模型的**起点**默认值（字符）。它**不是**内容上限 ——
# 超出部分原样躺在文件里，模型按指引就能继续读。
#
# 取 12000：约 6k token，对任何还在正常工作的上下文预算都留足了余量，
# 同时又足够装下绝大多数真实工具结果（用户实测那条 23KB 的 JSON 会走外置，
# 但读两段即可看全）。
DEFAULT_DELIVER_CHARS = 12_000

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(part: str, *, fallback: str) -> str:
    """把 id 变成安全的文件名片段。

    会话 id / tool_call_id 来自外部（前端与模型），可能含路径分隔符或 Windows
    保留字符。直接拼进路径会写到别的地方去，所以一律白名单化。
    """
    cleaned = _UNSAFE.sub("_", (part or "").strip())[:64].strip("._-")
    return cleaned or fallback


def spill_filename(session_id: str, call_id: str) -> str:
    """给一份外置内容生成文件名。

    名字里带上原始 id 的短哈希：可读性靠前缀，**唯一性靠哈希** ——
    只用清理后的前缀的话，``a/b`` 与 ``a?b`` 会撞成同一个文件，
    后写的那份会静默覆盖先写的。
    """
    digest = hashlib.sha1(f"{session_id}\x00{call_id}".encode()).hexdigest()[:12]
    return f"{_safe_name(call_id, fallback='call')}-{digest}.txt"


def write_spill(root: Path, session_id: str, call_id: str, text: str) -> Path:
    """把完整内容原样写到 ``root`` 下，返回文件路径。

    写失败时**抛出** —— 调用方必须知道"这次没能无损外置"，从而选择
    "宁可多给内容也不要给一个指向空气的路径"。
    """
    root.mkdir(parents=True, exist_ok=True)
    target = root / spill_filename(session_id, call_id)
    tmp = target.with_suffix(target.suffix + ".part")
    # newline="" 保持字节原样：工具结果里的 \n 被翻译成 \r\n 会让
    # 偏移量与实际不符，模型按偏移续读就会读到错位的内容。
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    os.replace(tmp, target)
    return target


def skip_chars(handle: Any, count: int, *, chunk: int = 65536) -> None:
    """按块丢弃 ``count`` 个字符。

    为什么不用 ``handle.seek()``：文本模式下 ``seek`` 只接受 ``tell()`` 返回过的值，
    而我们要的是"从第 N 个**字符**开始"，二者不是一回事。

    为什么按块而不是 ``handle.read(count)``：后者会先构造一个 count 长的字符串 ——
    对大文件的靠后偏移，峰值内存就等于偏移量本身。而"读大文件"恰恰是这个模块
    存在的理由，用它会自相矛盾。
    """
    remaining = count
    while remaining > 0:
        got = handle.read(min(chunk, remaining))
        if not got:
            return
        remaining -= len(got)


def read_range(
    path: Path, *, offset: int = 0, limit: int = DEFAULT_DELIVER_CHARS
) -> dict[str, Any]:
    """读取文件的字符区间，返回内容与续读所需的全部信息。

    刻意按**字符**而不是字节分片：模型看到的、``offset`` 里填的都是字符位置，
    按字节切片会在多字节字符中间劈开（读回来是乱码），而"乱码"和"丢内容"
    在用户眼里是同一件事。
    """
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        skip_chars(handle, offset)
        text = handle.read(limit)
        has_more = bool(handle.read(1))
    return {
        "path": str(path),
        "offset": offset,
        "content": text,
        "chars_returned": len(text),
        "next_offset": offset + len(text),
        "eof": not has_more,
        "size_bytes": path.stat().st_size,
    }


def deliver_pointer(path: Path, *, total_chars: int, delivered_chars: int) -> str:
    """生成投递给模型的"续读指引"。

    写法上有三个刻意的选择：

    1. **明说"没有删改"**。以前那句``（中间省略 N 字符）``让模型以为内容就是这样，
       于是它拿着半个 JSON 硬解，还得出了一个"网络丢了数据"的错误结论。
    2. **给出偏移量的具体数值**，而不是"你可以继续读" —— 后者模型还得自己算，
       而它算不出来（它不知道自己刚才收到多少字符）。
    3. **给出可直接照抄的调用示例**，降低"知道该读但写不对参数"的概率。
    """
    remaining = max(0, total_chars - delivered_chars)
    lines = [
        "",
        f"[完整内容共 {total_chars} 字符，此处先给出前 {delivered_chars} 字符。",
        f"剩余 {remaining} 字符**没有丢失** —— 全文已原样保存到本机文件：",
        f"  {path}",
        "要继续读取，请调用 read_tool_output：",
        f'  read_tool_output(path="{path}", offset={delivered_chars})',
        "该文件内容与本说明无关，未被删改、未被省略。]",
    ]
    return "\n".join(lines)

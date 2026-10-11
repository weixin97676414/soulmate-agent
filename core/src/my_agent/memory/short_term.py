"""短期记忆（会话上下文管理）。

对应《智能体框架开发文档》8.2 节。

## 一条贯穿本模块的原则：**内容可以不在这，但不可以不可达**

上下文窗口是厂商的物理限制，装不下就是装不下。但"装不下"只能带来两个后果，
**不能**带来"内容被销毁"或"内容里出现省略标记"：

1. 装得下 → 完整投递。这是默认路径，绝大部分情况都走这里。
2. 装不下 → 全文**无损外置**到磁盘，投递"开头 + 续读指引"
   （见 ``memory/spill.py`` 与下面的 ``_externalize``）。模型随时能读完全部。

历史教训：这里曾经用 4000 字符做"头尾保留 + 中间省略"，而紧随其后的注释
声称"完整内容已落产物目录" —— 那句话对不产出文件的工具（http 取回、
记忆检索、MCP）**是错的**，中间那段是真的没了。用户是拿着证据找上来的：
服务端完整发了 23006 字节、``truncated: false``，模型却看到"中间省略 5745 字符"。

## 另一个关键细节

``_trim`` 丢弃消息时必须保证序列对 OpenAI 协议仍然合法 ——
``tool`` 消息不能出现在其对应的 ``assistant(tool_calls)`` 之前。
因此裁剪后会跳过开头孤立的 tool 消息。
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..llm.base import ImagePart, Message, ToolCall
from ..security.injection import UNTRUSTED_CLOSE, annotate
from ..utils.timefmt import format_message_time, format_now
from . import spill as spill_mod
from .spill import DEFAULT_DELIVER_CHARS

logger = logging.getLogger(__name__)

# 每张图片的保守 token 估算。
#
# **按张数而不是按体积**：厂商对图片的计费与文件大小无关，而是按分辨率切块
# （patch）计算，常见区间约 256~1600 token/张。拿 data URL 的字符数去估会离谱 ——
# 一张 8MB 的照片能算出上百万 token，反而把压缩策略彻底带偏。
#
# 取偏大的 1200：低估图片开销会让"看着还很空"的会话在厂商侧直接超限，
# 而那条路的自愈（压缩后重试）恰恰依赖这个估算先触发。
IMAGE_TOKEN_ESTIMATE = 1200

# ⚠️ **这里故意没有"工具结果字符上限"这个常量。**
#
# 历史：它曾经存在，取值 4000，行为是把超长结果砍成"头 2000 + ``…（中间省略 N 字符）…``
# + 尾 2000"。实测反馈"AI 拿到的内容被省略了"，而我们当时的注释还写着
# "完整内容已落产物目录" —— 那句话是错的：对 http_fetch、长期记忆检索、MCP
# 工具这些不产出文件的能力，中间那段内容**被真正销毁**，模型永远拿不回来。
# 用户的原话是"很多用户的外部服务是花钱买的，我们没有资格给别人截掉或者省略"。
#
# 现在的规则：工具结果**一个字节都不改**地进 ``_messages``。唯一与"容量"有关的
# 事发生在**出站视图**（``get_context``）：单条内容确实超出模型单次容量时，
# 把全文无损外置到磁盘并给出续读指引（见 memory/spill.py）——
# 内容可以不在这一次的上下文里，但绝不可以不可达。

# --------------------------------------------------------------------------- #
# 内部提示消息
# --------------------------------------------------------------------------- #
# 引擎为了让模型继续作答而合成的内容（例如"模型返回了空回复"时的催促语）
# 会以 user 角色的身份混进消息列表。它不是用户真实输入，展示层必须能识别
# 并过滤掉 —— 否则用户会在对话记录里看到自己从没发过的话。
#
# 用**内容标记**而不是 Message 上的布尔字段：消息要经 SQLite 往返，
# 布尔字段不会持久化、重新载入后就丢了标记，而这些消息会一直留在库里。
INTERNAL_OPEN = "⟪internal⟫"
INTERNAL_CLOSE = "⟪/internal⟫"


def internal_hint(text: str) -> str:
    """把一段引擎合成的内容标记为内部提示。"""
    return f"{INTERNAL_OPEN}{text}{INTERNAL_CLOSE}"


def is_internal(content: str) -> bool:
    """判断一条消息是否是引擎合成的内部提示。"""
    return content.startswith(INTERNAL_OPEN)


# --------------------------------------------------------------------------- #
# 上下文摘要
# --------------------------------------------------------------------------- #
# 超长对话的早期内容压缩成一段摘要后，作为**第二条 system 消息**插在最前面。
#
# 为什么不用 user 角色：摘要不是用户说的话，模型不该把它当作用户的新指示；
# 也不该被展示层当成一条真实消息（万一将来有人放宽 history() 的过滤条件）。
#
# 为什么不做成"把摘要拼进第一条 system"：``ensure_system()`` 每轮都会用
# ``Agent._system_prompt()`` 的返回值覆盖内容，拼进去的部分会被下一轮直接抹掉。
SUMMARY_PREFIX = (
    "以下是与你更早对话的**摘要**（不是原文，用于保持连续性，不必逐字复述）。\n"
    "更早的完整对话记录**没有被删除**：它仍然保存在用户的会话里、用户随时能看到，"
    "只是没有再随本次请求发送。\n"
    "如果摘要没有覆盖到你需要的具体细节，请**直接说明你需要什么或询问用户**，"
    "不要凭猜测补全被省略的部分。\n"
    "摘要如下：\n"
)


def dropped_notice(count: int) -> str:
    """告知模型"这一轮你看到的不是全部"。

    为什么必须说出来：模型在**不知道**自己缺信息的时候，最危险的行为不是拒绝回答，
    而是用现有材料编一个自洽的答案 —— 用户完全看不出来哪些是事实、哪些是补的。
    明确告知之后，它的正确动作变成"问一句"或"说明需要什么"，代价小得多。

    同样要说清"内容没丢"：否则模型可能反过来告诉用户"你的历史记录被删了"。
    """
    return (
        f"[说明：为腾出上下文容量，更早的 {count} 条消息这一次没有随请求发送。"
        "这些内容**没有被删除** —— 用户在自己的对话记录里仍能看到完整历史。"
        "如果你需要其中的具体细节，请明确说明你需要什么，或直接询问用户；"
        "不要凭猜测补上被省略的部分。]"
    )


def summary_message(summary: str) -> Message:
    """把摘要包装成可直接放进上下文的消息。"""
    return Message(role="system", content=f"{SUMMARY_PREFIX}{summary}")


# --------------------------------------------------------------------------- #
# 消息时间（长期记忆的时间维度）
# --------------------------------------------------------------------------- #
# 用户的要求：「每个聊天记录的每句话，都有一个准确的时间戳，记忆要有时间维度，
# 让 AI 能分清'现在'和'以前'，别把旧的当当下聊」。落地方式是**只在发给模型的那份
# 视图里**给消息加时间前缀（见 ``with_time_prefixes``）。
#
# ⚠️ 为什么不写进 content：content 是落盘内容、摘要的输入、界面回显的原文。时间混进去
# 之后摘要会被噪声淹没、界面上的前缀越滚越长，而"这条消息原本说了什么"再也还原不出来。
#
# ⚠️ 为什么不把日期塞回 system：system 在第 0 位，任何按分钟变化的内容都会让厂商的
# 前缀缓存整段失效（命中价通常只有 1/10）。所以"现在"挂在**最后一条用户消息**上 ——
# 它本来就在末尾、每轮都在变，动它不影响前面的缓存前缀。
def with_time_prefixes(messages: list[Message]) -> list[Message]:
    """给**发给模型**的消息加时间前缀，返回新列表（不改原对象）。

    - 历史消息：``[09-26 14:32] 内容``；
    - **最后一条用户消息**：``现在：2026-09-26 14:32（周六）`` —— 它代表"此刻"，
      而每轮工具往返都会重新渲染一次，所以模型在整轮任务里始终看得到当下时间；
    - 时间不知道的（更早版本落盘的老消息、system、摘要、引擎合成的提示）**不加前缀**：
      给一个假时间比没有时间糟糕得多（那正是"把三个月前的旧事按刚才讲"的来源）。

    ⚠️ ``tool`` 消息**刻意不加**：它的内容以不可信边界的起始标记
    （``<<<UNTRUSTED_TOOL_OUTPUT``）开头，在它之前插入我们自己的文字会让模型分不清
    "数据区从哪开始"，而那道边界是防注入的第三层。工具结果与它的 assistant 消息在同一轮，
    时间信息已由那条 assistant 带上。
    """
    if not messages:
        return messages
    last_user = max(
        (index for index, item in enumerate(messages) if item.role == "user"),
        default=-1,
    )
    out: list[Message] = []
    for index, message in enumerate(messages):
        if message.created_at is None or message.role not in ("user", "assistant"):
            out.append(message)
            continue
        if index == last_user:
            prefix = f"现在：{format_now(message.created_at)}\n"
        else:
            prefix = f"[{format_message_time(message.created_at)}] "
        # replace 生成副本而不是就地改：``_messages`` 里那一条是用户看到的聊天记录，
        # 也是落盘内容，必须始终是原文
        out.append(replace(message, content=f"{prefix}{message.content}"))
    return out


class MemoryManager:
    """维护单个会话的消息列表、上下文摘要与截断策略。"""

    def __init__(
        self,
        *,
        max_context_tokens: int = 32000,
        spill_root: Path | None = None,
        spill_session: str = "",
        deliver_chars: int = DEFAULT_DELIVER_CHARS,
    ) -> None:
        self._messages: list[Message] = []
        self._max_tokens = max_context_tokens
        # 无损外置的落点与归属会话。**为 None 时不做任何外置** ——
        # 没有地方放内容时，宁可把全文交给模型，也不能给一个指向空气的路径。
        self._spill_root = spill_root
        self._spill_session = spill_session
        # 单次投递的**起点长度**（不是上限，超出部分在文件里，可续读）
        self._deliver_chars = deliver_chars
        # 已外置过的内容：``tool_call_id -> (路径, 总字符数)``。
        # ``get_context`` 每轮都会跑，有这张表才不会对同一份内容反复写盘。
        self._spilled: dict[str, tuple[Path, int]] = {}
        # 早期对话的摘要，以及它覆盖到第几条消息（含 system，从 0 数）。
        #
        # 摘要**不删除**原消息：``_messages`` 仍然完整保留，用于界面回显与落盘。
        # 它只影响 ``get_context()`` 发给模型的内容 —— 用户不该因为模型上下文
        # 紧张就发现自己的聊天记录少了一截。
        self._summary = ""
        self._summary_upto = 0

    def configure(
        self,
        *,
        max_context_tokens: int | None = None,
        spill_root: Path | None = None,
        spill_session: str | None = None,
    ) -> None:
        """运行时调整上下文预算与无损外置位置。

        **这里没有"工具结果字符上限"这个参数**，而且不该再加回来 ——
        见文件顶部关于那 4000 字符截断的说明。容量的约束只体现为
        ``max_context_tokens``，且它只影响"这一次投递多少"，不影响"内容是否还存在"。
        """
        if max_context_tokens is not None:
            self._max_tokens = max_context_tokens
        if spill_root is not None:
            self._spill_root = spill_root
        if spill_session is not None:
            self._spill_session = spill_session

    # ------------------------------------------------------------------ #
    # 写入
    # ------------------------------------------------------------------ #
    def ensure_system(self, prompt: str) -> None:
        """确保 system 消息位于列表首位且内容最新。

        ``prompt`` 为空时**不留 system 消息**：提示词现在只由搭子的人格文档组成
        （兜底那段已退役），而人格文件可能被用户清空，也可能遇到更早版本建出来、
        还没有归属搭子的会话。这时宁可整条请求不带 system，也不发一条空内容的
        —— 空文本在部分厂商那里直接判为非法请求。列表没有 system 时
        ``_split_head`` / ``_truncate`` / ``get_context`` 都已能正确处理。
        """
        if not prompt:
            if self._has_system:
                del self._messages[0]
                # 摘要覆盖范围是**含 system** 数的（见 summary_upto 的说明），
                # 删掉首位就得跟着减一，否则 get_context 会把摘要边界算错一条。
                self._summary_upto = max(0, self._summary_upto - 1)
            return
        if self._messages and self._messages[0].role == "system":
            if self._messages[0].content != prompt:
                self._messages[0] = Message(role="system", content=prompt)
            return
        self._messages.insert(0, Message(role="system", content=prompt))

    def add_user(self, text: str, *, images: list[ImagePart] | None = None) -> Message:
        # created_at 在**产生的这一刻**打上：落盘与投递给模型的时间都以它为准
        msg = Message(role="user", content=text, images=list(images or []), created_at=time.time())
        self._messages.append(msg)
        return msg

    def add_assistant(
        self,
        content: str,
        tool_calls: list[ToolCall] | None = None,
        reasoning_content: str = "",
        plan: dict[str, Any] | None = None,
    ) -> Message:
        msg = Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls or None,
            reasoning_content=reasoning_content,
            created_at=time.time(),
            plan=plan,
        )
        self._messages.append(msg)
        return msg

    def add_tool(self, tool_call_id: str, name: str, result: str) -> Message:
        """把工具结果**原样**记进上下文。

        ⚠️ **这里不做任何截断、也不做任何省略。** 这条规则是硬的：

        - 用户的原话是"很多用户的外部服务是花钱买的，我们没有资格给别人截掉或者省略"；
        - 以前的 4000 字符头尾截断让模型拿着半个 JSON 硬解，还因此得出
          "服务端把数据丢了"的错误结论（服务端其实完整发了 23006 字节）；
        - 更坏的是"截断"与"协议"无关，纯粹是我们自己拍的数，属于无理由的信息损失。

        需要为容量做取舍时，**只能**发生在 ``get_context()`` 的出站视图：
        把全文无损外置并给出续读指引。``_messages`` 里永远是完整内容，
        界面回显与落盘也照旧完整。

        ``annotate`` 仍在此处调用，且**必须包在完整内容之外** ——
        它是工具结果进入模型上下文的唯一入口，防护放这里才不会漏掉新增技能；
        而如果哪天在它之前又插进了"切一刀"，就可能留下一个永远闭合不上的
        ``<<<UNTRUSTED_TOOL_OUTPUT``，那正是我们要让模型识别为"数据区"的标记。
        """
        text = str(result)
        annotated, hits = annotate(text, source=name)
        # ⚠️ **这里不再预判式外置**。
        #
        # 上一版在这里对超过 `_deliver_chars`(12000) 的结果做外置 + "开头 12000 +
        # 续读指引"。用户看到的就是那句"完整内容共 23728 字符，此处先给出前 12000
        # 字符" —— 它仍然是一个**我们拍的固定数**，正是用户明确拒绝的东西。
        #
        # 现在的规则：**能装下就整段给**。内容原样进 `_messages`（界面回显与落库
        # 也是完整），`get_context()` 默认也原样投递。只有厂商**真的**因为超出上下文
        # 而拒绝时，才由 `externalize_oversized()` 做一次事后兜底（见 engine 的超限重试）。

        msg = Message(
            role="tool",
            content=annotated,
            tool_call_id=tool_call_id,
            name=name,
            injection_hits=[hit.label for hit in hits],
            created_at=time.time(),
        )
        self._messages.append(msg)
        return msg

    def pop_last_assistant(self) -> Message | None:
        """回滚最后一条 assistant 消息（用于工具调用参数非法时重试）。"""
        for i in range(len(self._messages) - 1, -1, -1):
            if self._messages[i].role == "assistant":
                return self._messages.pop(i)
        return None

    # ------------------------------------------------------------------ #
    # 摘要
    # ------------------------------------------------------------------ #
    @property
    def summary(self) -> str:
        return self._summary

    @property
    def summary_upto(self) -> int:
        """摘要覆盖到第几条消息（含 system，从 0 数）。"""
        return self._summary_upto

    def set_summary(self, summary: str, upto: int) -> None:
        """记录一段摘要，以及它覆盖到哪一条消息为止。

        ``upto`` 是 ``_messages`` 中的索引：``[:upto]`` 已经被摘要代表，
        发送给模型时不再重复出现。
        """
        self._summary = summary.strip()
        self._summary_upto = max(0, min(upto, len(self._messages)))

    def clear_summary(self) -> None:
        self._summary = ""
        self._summary_upto = 0

    def compressible_range(self, *, keep_recent: int) -> tuple[int, int]:
        """返回"这次可以拿去压缩"的消息下标区间 ``[start, end)``。

        - ``start`` 是已覆盖位置之后的第一条 —— 已经进过摘要的内容不重复压；
        - ``end`` 留出最近 ``keep_recent`` 条不动，它们是当前任务的直接上下文，
          压掉会让模型丢掉"刚才在做什么"。

        ## ``end`` 为什么要往前退（重要，别去掉）

        ``end`` 是按**条数**算出来的，但消息之间是有配对的：``tool`` 消息必须紧跟在
        它对应的 ``assistant(tool_calls)`` 之后。如果 ``end`` 正好落在这两者之间，
        摘要就会覆盖那条 assistant，却把孤立的 ``tool`` 留在正文里。

        后果不是"少一点上下文"，而是**这个会话开始永久报错**：发给厂商的序列以
        ``tool`` 开头，OpenAI / DeepSeek 一律直接 400。更麻烦的是此时内容远小于
        预算，``_trim`` 根本不会走到"跳过开头孤立 tool"那段代码 —— 那道防线在这里
        是失效的，而引擎的上下文超限自愈也救不了（它只认上下文超限的文案）。

        把边界退到配对完整的位置，代价只是少压几条消息。
        """
        start = max(self._summary_upto, 1 if self._has_system else 0)
        end = len(self._messages) - max(keep_recent, 0)
        # 只要 ``end`` 指着一条 tool 消息，它的 assistant 就在摘要里，得一起退出来
        while start < end < len(self._messages) and self._messages[end].role == "tool":
            end -= 1
        return (start, end) if end > start else (start, start)

    @property
    def _has_system(self) -> bool:
        return bool(self._messages) and self._messages[0].role == "system"

    # ------------------------------------------------------------------ #
    # 读取
    # ------------------------------------------------------------------ #
    def get_context(self) -> list[Message]:
        """返回给 LLM 的消息列表（已应用摘要，并在必要时裁剪）。

        与旧实现的区别：早期消息**优先用摘要代表**而不是直接丢弃。
        裁剪只处理摘要之后的部分，所以摘要本身永远不会被裁掉。
        """
        head, body = self._split_head()
        prefix = list(head)
        if self._summary:
            prefix.append(summary_message(self._summary))

        # ``_summary_upto`` 里已经数进了 system，转成 body 的下标要减掉
        covered = max(0, min(self._summary_upto - len(head), len(body)))
        # 兜底再挡一次孤立 tool 消息：``compressible_range`` 已经保证自己给的边界
        # 是对齐的，但 ``_summary_upto`` 也可能来自旧版状态或序列化数据。
        # 一条孤立 tool 就能让整条请求被厂商拒掉，代价太大，不值得只信任上游一处。
        while covered < len(body) and body[covered].role == "tool":
            covered += 1
        budget = max(self._max_tokens - self._estimate_tokens(prefix), 0)
        # 先做无损外置（把装不下的换成"开头 + 续读指引"），再按预算裁剪。
        # 顺序不能反：先裁的话，被裁掉的整条消息连指引都不会留下。
        body = self._externalize(body[covered:])
        kept = self._trim(body, budget)

        # 裁掉整条消息时**必须说出来**（见 dropped_notice 的说明）：
        # 静默的"少几条"和"内容被删了"在模型眼里前者更危险 ——
        # 它不知道自己缺信息，就会用一个自洽的答案把缺口填上。
        #
        # 插在最前面是安全的：``_trim`` 已经跳过了开头孤立的 tool 消息，
        # 所以 ``kept[0]`` 一定不是 tool（system 插在 assistant(tool_calls)
        # 之前也不会破坏配对）。
        dropped = len(body) - len(kept)
        if dropped > 0:
            kept = [Message(role="system", content=dropped_notice(dropped)), *kept]
        # 时间前缀加在**最后一步**：前面所有环节（摘要、外置、裁剪）处理的都是原文，
        # 只有要交给模型的那一份才带上时间。顺序反了会把前缀算进 token 预算、
        # 也会让外置的边界判断跟着错位。
        return with_time_prefixes(prefix + kept)

    # ------------------------------------------------------------------ #
    # 无损外置
    # ------------------------------------------------------------------ #
    def externalize_oversized(self) -> int:
        """**事后兜底**：把超长的工具结果无损外置，返回外置了几条。

        只在厂商**真的**因为超出上下文而拒绝、且压缩也没救回来时才调用
        （见 ``agent/engine.py`` 的超限重试）。这**不是**预判式截断：
        正常路径下一条都不会走到这里，内容始终整段投递给模型。

        外置之后 ``get_context()`` 才把这几个换成"开头 + 续读指引"；全文仍在磁盘上，
        模型可以用 ``read_tool_output`` 读完全部 —— 内容不丢，只是分次取。

        ⚠️ 投递视图要**重新闭合**不可信边界：直接截取带标记的内容会留下一个永远
        闭合不上的 ``<<<UNTRUSTED_TOOL_OUTPUT`` —— 那正是要让模型识别为"数据区"
        的标记，闭合不上等于这道防护失效。而续读指引属于**我们的指令**，
        所以放在闭合标记**之后**（放在里面会被模型当成待处理的数据）。
        """
        if self._spill_root is None:
            return 0
        count = 0
        for message in self._messages:
            key = message.tool_call_id or ""
            if message.role != "tool" or not key or key in self._spilled:
                continue
            if len(message.content) <= self._deliver_chars:
                continue
            try:
                path = spill_mod.write_spill(
                    self._spill_root, self._spill_session, key, message.content
                )
            except OSError as exc:
                # 外置失败就跳过这一条：宁可让它按原文投递（用户会看到明确的超限
                # 报错并知道该调大窗口），也不能给一个指向空气的路径。
                logger.warning("工具结果无损外置失败，将按原样投递：%s", exc)
                continue
            head = message.content[: self._deliver_chars]
            if not head.rstrip().endswith(UNTRUSTED_CLOSE):
                head = f"{head}\n{UNTRUSTED_CLOSE}"
            pointer = spill_mod.deliver_pointer(
                path,
                total_chars=len(message.content),
                delivered_chars=self._deliver_chars,
            )
            self._spilled[key] = f"{head}\n{pointer}"
            count += 1
        if count:
            logger.info("上下文超限：已无损外置 %s 条超长工具结果并重试", count)
        return count

    def _externalize(self, messages: list[Message]) -> list[Message]:
        """把有外置副本的 tool 消息换成"开头 + 续读指引"。

        ⚠️ 用 ``dataclasses.replace`` 生成**新对象**，绝不改 ``_messages`` 里那一条：
        后者是用户看到的聊天记录与落库内容，必须始终完整。
        """
        if not self._spilled:
            return messages
        out: list[Message] = []
        for message in messages:
            key = message.tool_call_id or ""
            view = self._spilled.get(key) if key else None
            # 内容没超过投递起点就照原样给（说明它本来就不该被外置）
            if view is None or len(message.content) <= self._deliver_chars:
                out.append(message)
                continue
            out.append(replace(message, content=view))
        return out

    def _split_head(self) -> tuple[list[Message], list[Message]]:
        if self._has_system:
            return [self._messages[0]], list(self._messages[1:])
        return [], list(self._messages)

    @property
    def messages(self) -> list[Message]:
        """完整消息列表（未截断），供持久化与前端回显。"""
        return self._messages

    @property
    def last_message(self) -> Message | None:
        return self._messages[-1] if self._messages else None

    def __len__(self) -> int:
        return len(self._messages)

    # ------------------------------------------------------------------ #
    # 截断
    # ------------------------------------------------------------------ #
    def _trim(self, messages: list[Message], budget: int) -> list[Message]:
        """按 token 预算裁掉列表**开头**的消息。

        裁完还要跳过开头孤立的 ``tool`` 消息：``tool`` 不能出现在它对应的
        ``assistant(tool_calls)`` 之前，否则厂商直接返回协议错误。
        这个"跳过"不是可选项——它决定了裁剪后的序列是否合法。
        """
        if not messages:
            return messages

        # 先算每条的 token，再用**累减**找切点：原实现每轮都重新估算
        # ``messages[cut:]``，是 O(n²)。消息上百条时会变成几千次重复计算，
        # 而它跑在事件循环里。
        sizes = [self._estimate_tokens([message]) for message in messages]
        total = sum(sizes)
        if total <= budget:
            return messages

        cut = 0
        while cut < len(messages) and total > budget:
            total -= sizes[cut]
            cut += 1
        while cut < len(messages) and messages[cut].role == "tool":
            cut += 1

        return messages[cut:]

    def _truncate(self, messages: list[Message]) -> list[Message]:
        """整表截断，system 永远保留。保留此入口供既有调用方与测试使用。"""
        system = [m for m in messages[:1] if m.role == "system"]
        rest = messages[len(system) :]
        budget = self._max_tokens - self._estimate_tokens(system)
        return system + self._trim(rest, max(budget, 0))

    @staticmethod
    def _estimate_tokens(messages: list[Message]) -> int:
        """保守估算：中文约 1 字 ≈ 0.5~0.7 token，此处按 0.5 估算并加消息开销。"""
        total = 0
        for m in messages:
            total += len(m.content) // 2
            total += 4  # 角色与结构开销
            # 图片按**张数**计，不按体积计 —— 见 IMAGE_TOKEN_ESTIMATE 的说明。
            # 不记这一笔的话，带图会话会"看起来还很空"却已经把窗口塞满，
            # 压缩与裁剪都不会触发，最后直接吃厂商的超限报错。
            total += len(m.images) * IMAGE_TOKEN_ESTIMATE
            for tc in m.tool_calls or []:
                total += len(tc.name) // 2 + len(tc.raw_arguments) // 2 + 4
        return total

    def estimated_tokens(self) -> int:
        """**完整历史**的估算值（含已进摘要的部分），用于展示与诊断。"""
        return self._estimate_tokens(self._messages)

    def context_tokens(self) -> int:
        """**实际会发给模型**的估算值。

        决策要看这个值，不能看 ``estimated_tokens()``：压缩之后完整历史仍然很长
        （消息不删除），但真正发送的内容已经短了很多。拿完整历史去判断会得到
        "一直超限"的错误结论。
        """
        return self._estimate_tokens(self.get_context())

    # ------------------------------------------------------------------ #
    # 序列化（供 SQLite 持久化）
    # ------------------------------------------------------------------ #
    def to_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for m in self._messages:
            records.append(
                {
                    "role": m.role,
                    "content": m.content,
                    "tool_call_id": m.tool_call_id,
                    "name": m.name,
                    "tool_calls": [tc.to_openai() for tc in m.tool_calls] if m.tool_calls else None,
                    "created_at": m.created_at,
                    # 计划只在有值时带上（绝大多数消息没有）：落库多一列 JSON，
                    # 但重开对话时能原样恢复计划卡片（见 llm/base.py 的 Message.plan）
                    "plan": m.plan,
                }
            )
        return records

    def clear(self, *, keep_system: bool = True) -> None:
        # 只在"第 0 位真的是 system"时才留下它。提示词兜底退役后，一个搭子可能
        # 没有任何 system（人格文件全空、或更早版本建出来的无归属会话），这时
        # 盲取 ``[:1]`` 会把**第一条用户消息**当成 system 留下来 ——
        # 用户看到的现象是"清空了，却还剩一句没清掉"。
        keep = keep_system and self._has_system
        self._messages = self._messages[:1] if keep else []
        # 摘要必须一起清掉：它描述的是刚刚被删掉的那批消息，
        # 留着会让模型"记得"用户已经明确清空的内容。
        self.clear_summary()

    def replace(
        self,
        messages: list[Message],
        *,
        summary: str = "",
        summary_upto: int = 0,
    ) -> None:
        """用外部消息列表整体替换当前记忆（会话懒加载时使用）。

        会做一次浅拷贝，避免调用方后续改动列表时影响到记忆内部状态。
        摘要一并恢复：否则重开一个长会话会退回到"模型只能看到最近几条"，
        而用户看到的是完整历史 —— 这种不一致会让模型的表现莫名其妙。
        """
        self._messages = list(messages)
        self.clear_summary()
        if summary:
            self.set_summary(summary, summary_upto or len(self._messages))

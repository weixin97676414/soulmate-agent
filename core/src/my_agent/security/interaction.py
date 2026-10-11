"""向用户发起一次交互请求（选择 / 敏感输入）的数据结构与回调类型。

## 与 `confirm.py` 的关系

两者都放在 ``security`` 包、都用来打断
``skill.manager -> security.permission -> skill.base`` 的循环导入。但**语义完全不同**，
所以刻意分成两个模块、两套挂起表（见 ``runtime.PendingConfirm`` /
``PendingInteraction`` 的注释）：

- ``ConfirmRequest`` 承载的是**权限**语义 —— "要不要允许这个动作"，答案是布尔；
- ``InteractionRequest`` 承载的是**交互**语义 —— "你指的是哪个" / "把你那串东西给我"，
  答案是任意结构。

## 为什么要有它（而不是让技能自己想办法问）

在这之前，技能想让用户回答一个问题**没有渠道**：
``grill_me``（苏格拉底式追问）只能返回一段"你去问用户"的提示词，靠模型在**下一轮**开口，
用户答不答、答得准不准全看运气。而"请用户提供一串密钥"更是完全做不到 ——
模型只能开口要，用户把私钥**打进对话框**，于是明文就进了消息表、上下文、
还会发给模型厂商（详见 ``security/secret_ref.py`` 的模块注释）。

有了这条通道，这两件事才第一次成为**结构化的、有回报的**动作：
问出去、等到一个明确的答复、再继续。

## ⚠️ 一个必须记住的边界

这条通道**只负责"问"与"收"**。它不认识"敏感"两个字 ——
``kind == "secret"`` 的那条路上，**值根本不会经过这里**：
用户在弹窗里粘贴的内容由渲染层直接写进本地加密文件，
回传给核心的只有名字（见 ``kind`` 字段的说明）。所以：
**不要把任何敏感值塞进 ``payload``**，那个字段会被审计与日志看到。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

#: 交互类型。前端据此决定渲染哪种弹窗。
#:
#: - ``"choice"``：多选项 + 可自定义输入。``payload`` 里是 ``question`` / ``options`` /
#:   ``allow_custom``，**不含任何敏感内容**。
#: - ``"secret"``：逐字段的密码型输入。``payload`` 里只有 ``fields``（名字与提示）
#:   与 ``reason`` —— **值从来不在这里**，由渲染层写进本地加密文件后只回传名字。
KIND_CHOICE = "choice"
KIND_SECRET = "secret"
INTERACTION_KINDS: frozenset[str] = frozenset({KIND_CHOICE, KIND_SECRET})


@dataclass
class InteractionRequest:
    """一次交互请求，由服务层转成 SSE 事件发给客户端弹窗。"""

    request_id: str
    skill_name: str
    display_name: str
    kind: str
    #: 给前端渲染弹窗用的内容。⚠️ **绝不许放敏感值**（它会被审计与日志看到）。
    payload: dict[str, Any] = field(default_factory=dict)
    #: 给用户看的一句话：为什么要问他。
    prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "skill_name": self.skill_name,
            "display_name": self.display_name,
            "kind": self.kind,
            "payload": self.payload,
            "prompt": self.prompt,
        }


#: 交互回调：服务层实现，返回用户的答复（结构由 ``kind`` 决定）。
#:
#: ⚠️ 返回 ``{"cancelled": True}`` 表示"没有拿到答复"—— 它同时覆盖
#: "用户点了取消 / 关了弹窗"与"这条任务被打断"两种情况。
#: 再带 ``interrupted=True`` 时是后者（同 ``PendingConfirm.interrupted`` 的区分方式）：
#: 对用户来说"我不想答"和"我走开了一下它就没了"是完全不同的两件事。
InteractionCallback = Callable[[InteractionRequest], Awaitable[dict[str, Any]]]

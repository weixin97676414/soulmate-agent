"""请求级上下文。

## 为什么需要 ContextVar

有些事件是在**适配器内部**产生的，那里拿不到任何请求级信息 ——
最典型的就是模型降级：``FallbackLLM`` 只知道"哪个模型挂了、换成了哪个"，
它并不知道这属于哪个会话。

把会话 id 做成 ``ContextVar`` 之后，路由里设一次，任务内部随时能读到。
关键在于 **asyncio 的任务会继承创建它的上下文**：Agent 任务是在请求
处理过程中 ``create_task`` 出来的，所以它和它派生的协程都看得到这个值，
不需要把它一路当参数传下去（那会污染一大串本来与请求无关的签名）。

注意它**不是**全局变量：不同请求各自有自己的值，并发时不会串。
"""

from __future__ import annotations

from contextvars import ContextVar

# 当前正在处理的会话 id（不在请求上下文中时是 None）
current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)


def bind_session(session_id: str):
    """绑定当前会话，返回一个 token 供调用方在 finally 里恢复。

    用 ``set`` 返回的 token 去 ``reset``，而不是再 ``set(None)``：
    后者在嵌套调用时会把外层的值也清掉。
    """
    return current_session_id.set(session_id)

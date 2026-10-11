"""改「默认检索条数」之后，设置必须真的作用到**对话里那条检索路**上。

## 背景（这是修掉的一个真缺陷）

``apply_settings`` 里原本只重建了全局那份 ``long_term``，而对话中检索长期记忆走的是
``memory_for(assistant_id)`` 那份**每搭子实例**（见 ``agent/history.py`` 的
``_from_memory``）—— 它们各自缓存着旧的 ``default_top_k``。

更隐蔽的是嵌入器：``_embedder_cache()`` 把嵌入器对缓存在 ``_embedder_pair`` 里，
换嵌入后端时不清缓存的话，新建的实例拿到的还是旧嵌入器 —— 连向量维度都不会变，
用户"换了个模型"却什么都没发生。

所以这里同时钉住两条：条数要传到每搭子实例，嵌入器缓存要被丢掉。
"""

from __future__ import annotations


async def test_改检索条数会连每搭子实例一起重建(runtime):
    per = runtime.memory_for("某个搭子")
    assert per.default_top_k == 5

    settings = runtime.config.settings.model_copy(deep=True)
    settings.memory.vector_top_k = 9
    runtime.apply_settings(settings)

    assert runtime.long_term.default_top_k == 9
    # 关键：**每搭子那份**也必须跟着变 —— 对话里检索用的就是它
    assert runtime.memory_for("某个搭子").default_top_k == 9
    # 是**换掉**而不是原地改值：旧实例手里还攥着旧嵌入器
    assert runtime.memory_for("某个搭子") is not per


async def test_改嵌入方式会丢掉嵌入器缓存(runtime):
    """不丢缓存的话，换后端等于白换（拿到的还是旧嵌入器）。"""
    # 手工塞一个哨兵当缓存：真去构建一次要加载内置模型（几百 MB），而这里要验的
    # 只是"apply_settings 有没有把这个缓存丢掉"。
    runtime._embedder_pair = ("旧嵌入器", "旧查询嵌入器")  # type: ignore[assignment]

    settings = runtime.config.settings.model_copy(deep=True)
    settings.memory.embedding_backend = "ollama"
    runtime.apply_settings(settings)

    assert runtime._embedder_pair != (
        "旧嵌入器",
        "旧查询嵌入器",
    ), "嵌入器缓存没被丢掉，换了后端也不会生效"

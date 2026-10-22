














from __future__ import annotations


async def test_改检索条数会连每搭子实例一起重建(runtime):
    per = runtime.memory_for("某个搭子")
    assert per.default_top_k == 5

    settings = runtime.config.settings.model_copy(deep=True)
    settings.memory.vector_top_k = 9
    runtime.apply_settings(settings)

    assert runtime.long_term.default_top_k == 9
    
    assert runtime.memory_for("某个搭子").default_top_k == 9
    
    assert runtime.memory_for("某个搭子") is not per


async def test_改嵌入方式会丢掉嵌入器缓存(runtime):

    
    
    runtime._embedder_pair = ("旧嵌入器", "旧查询嵌入器")  

    settings = runtime.config.settings.model_copy(deep=True)
    settings.memory.embedding_backend = "ollama"
    runtime.apply_settings(settings)

    assert runtime._embedder_pair != (
        "旧嵌入器",
        "旧查询嵌入器",
    ), "嵌入器缓存没被丢掉，换了后端也不会生效"

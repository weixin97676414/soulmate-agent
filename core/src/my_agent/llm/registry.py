"""模型注册表：按 id 查找适配器实例。

对应《智能体框架开发文档》4.4 节。相比文档原始版本，这里额外承担两件职责：

1. **配置热更新**：设置中心改完模型后调用 ``rebuild`` 即可生效，无需重启客户端。
2. **安全回收（租约）**：见下面 ``LlmLease`` 的说明 —— 这是被一个线上问题逼出来的。

## 为什么要"租约"

``reload_models()`` 重建注册表后会关掉旧的（``aclose()`` 会把每个适配器的 httpx
客户端一起关掉）。如果此刻**有一个流式请求正在用旧注册表里的适配器**，那个请求
会当场断掉：httpx 抛 ``RemoteProtocolError`` / ``ReadError``，适配器把它包成
``LLMError("模型流式调用网络异常: ...")``。

用户看到的现象因此非常反直觉：**"搭子正在回答时我切到设置页，它就被打断了。"**
原因是切到设置页会触发一次自动保存 → ``PUT /v1/models`` → ``reload_models()``
→ 关旧客户端。上一轮只修了"切搭子"那条路径，这条一直留着。

所以"关掉旧注册表"必须**等到没有人正在用它**：请求开始时借一个租约，结束时还回来，
最后一个租约释放时才真正关闭。
"""

from __future__ import annotations

import logging

from ..errors import LLMError
from .base import BaseLLM

logger = logging.getLogger(__name__)


class LlmLease:
    """一次"我正在使用这个注册表"的声明。

    用法::

        async with registry.lease():
            ...  # 这期间注册表不会被关掉

    它只影响**回收时机**，不影响任何请求内容。异常路径也会走 ``__aexit__``，
    所以不会因为中途出错就把租约永久占住。
    """

    __slots__ = ("_registry", "_released")

    def __init__(self, registry: LlmRegistry) -> None:
        self._registry = registry
        self._released = False

    async def __aenter__(self) -> LlmLease:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.release()

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._registry.release_lease()


class LlmRegistry:
    def __init__(self) -> None:
        self._models: dict[str, BaseLLM] = {}
        self._default: str = ""
        # ---- 租约状态 ---- #
        self._leases = 0
        #: 已经请求回收、但还有租约在身（等最后一个租约释放）
        self._retire_pending = False
        #: 已经关掉了。重复关闭是安全的（幂等），但记一笔便于排查
        self._closed = False

    # ------------------------------------------------------------------ #
    # 注册与查询
    # ------------------------------------------------------------------ #
    def register(self, model_id: str, llm: BaseLLM, *, is_default: bool = False) -> None:
        self._models[model_id] = llm
        # 把租约工厂交给适配器，让**每一次流式调用**都能声明"我在用"。
        # 放在这里而不是每个调用方：调用方有 chat / 群聊 / 定时任务 / 命令行四条，
        # 逐个加迟早会漏；而"谁在用这个适配器"只有适配器自己最清楚。
        llm.set_lease_factory(self.lease)
        if is_default or not self._default:
            self._default = model_id

    def get(self, model_id: str | None) -> BaseLLM:
        """按 id 取适配器；``None`` 时返回默认模型。"""
        key = model_id or self._default
        if not key or key not in self._models:
            raise LLMError(f"未知模型: {model_id or '(默认)'}，请在设置中检查模型配置。")
        return self._models[key]

    def has(self, model_id: str) -> bool:
        return model_id in self._models

    def ids(self) -> list[str]:
        return list(self._models)

    def default(self) -> BaseLLM:
        return self.get(None)

    @property
    def default_id(self) -> str:
        return self._default

    def __len__(self) -> int:
        return len(self._models)

    # ------------------------------------------------------------------ #
    # 租约
    # ------------------------------------------------------------------ #
    def lease(self) -> LlmLease:
        """借出一个租约。调用方**必须**在 ``async with`` 里用，保证异常时也归还。"""
        self._leases += 1
        return LlmLease(self)

    async def release_lease(self) -> None:
        self._leases = max(0, self._leases - 1)
        if self._leases == 0 and self._retire_pending:
            logger.debug("最后一个在途请求已结束，回收旧模型注册表")
            await self._close_now()

    @property
    def active_leases(self) -> int:
        """当前在途的流式调用数（仅用于诊断与测试）。"""
        return self._leases

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    async def retire(self) -> None:
        """请求回收这个注册表（它已经被新注册表取代）。

        **没有在途请求时立刻关**（绝大多数情况）；有在途请求时只做标记，
        等最后一个租约还回来再关 —— 那正是"搭子回答到一半时切页面"的场景。
        """
        if self._leases == 0:
            await self._close_now()
            return
        self._retire_pending = True
        logger.info(
            "旧模型注册表仍有 %s 个在途请求，等它们结束后再回收（避免打断正在进行的回答）",
            self._leases,
        )

    async def _close_now(self) -> None:
        self._retire_pending = False
        if self._closed:
            return
        self._closed = True
        await self.aclose()

    async def aclose(self) -> None:
        for llm in self._models.values():
            try:
                await llm.aclose()
            except Exception as exc:  # noqa: BLE001 - 关闭失败不应阻塞退出
                logger.warning("关闭模型适配器失败: %s", exc)
        self._models.clear()
        self._default = ""

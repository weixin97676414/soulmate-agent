"""``@skill`` 装饰器 —— Skill 易用性的关键。

对应《智能体框架开发文档》5.2 节。

**与文档原始实现的一处偏差**：文档版本在装饰器里直接调用
``SkillManager.instance().register()`` 完成自动注册，但这会让
「导入顺序」变成隐式依赖（模块没被 import 就静默不注册）。
这里改为装饰器只负责**挂载元数据**，由 ``discover_builtin_skills()``
显式导入并注册，行为可预测、可测试。
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from .base import BaseSkill, SkillMeta

T = TypeVar("T", bound=type[BaseSkill])

_EMPTY_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


def skill(
    name: str,
    description: str,
    *,
    params_model: type[BaseModel] | None = None,
    category: str = "general",
    permission_level: str = "safe",
    timeout: float = 30.0,
    requires: list[str] | None = None,
    tags: list[str] | None = None,
    display_name: str = "",
) -> Any:
    """把一个 ``BaseSkill`` 子类登记为可被模型调用的能力。

    参数
    ----
    name:           全局唯一标识，命名规范 ``领域_动作``（如 ``excel_read``）。
    description:    **必填且必须写清「何时使用、输入什么、输出什么」**，
                    这是 LLM 决定是否调用的唯一依据。
    params_model:   Pydantic 模型，自动生成 JSON Schema 并用于参数校验。
    category:       office / life / system / mcp。
    permission_level: safe（只读）/ confirm（有副作用）/ admin（高危）。
    """

    def decorator(cls: T) -> T:
        schema = (
            params_model.model_json_schema()
            if params_model is not None
            else dict(_EMPTY_SCHEMA)
        )
        # Pydantic 生成的 schema 顶层会带 title，工具参数里不需要，反而干扰模型
        schema.pop("title", None)

        cls.meta = SkillMeta(  # type: ignore[attr-defined]
            name=name,
            description=description,
            parameters=schema,
            category=category,
            permission_level=permission_level,
            timeout=timeout,
            requires=list(requires or []),
            tags=list(tags or []),
            display_name=display_name or name,
        )
        cls.params_model = params_model  # type: ignore[attr-defined]
        if not getattr(cls, "__doc__", None):
            cls.__doc__ = description
        return cls

    return decorator

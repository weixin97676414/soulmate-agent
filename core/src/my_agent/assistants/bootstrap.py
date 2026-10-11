"""内置搭子的**数据源门面**（审计 M-20）。

## 为什么单独一层

``config/loader.py`` 原先直接 import 这个包（模块级 1 处 + 函数内 6 处），
于是**基础设施层依赖业务包**：``config → assistants → config.schemas``
（目前只因 ``schemas`` 是叶子模块才没炸）。

现在改成：``ConfigStore`` 接收一个数据源（由组合根 ``AppRuntime`` 注入），
``config`` 里出现的一律是 ``self._builtin.xxx`` —— **它不再 import ``assistants``**。

## ⚠️ 这一步只解依赖方向，**不动流程**

"首启播种 + 四条迁移 + 人格对齐 + 锁定回写"的**流程**仍写在
``loader._load_assistants`` 里 —— 顺序与条件一个字没动，这里只提供数据与工具。
把流程也搬过来能让 loader 只剩纯 I/O，但那会同时改动四组测试的时序断言；
**搬运与解耦分成两步做，回归时能一眼看出是哪一步引起的**。

## 为什么是转发，而不是搬实现

``persona`` / ``locked_builtins`` / ``evolution`` 里的函数**就是这个包的业务**，
搬到这里等于原地换个文件名。门面只做两件事：

1. 暴露数据表（内置搭子是谁、改过哪些名字/id、出厂人格正文在哪）；
2. 按**原签名**转发那几个工具函数。

第 2 点刻意保持原签名（连位置参数都不动）：这样 loader 侧的改动是**纯机械换名**
（`persona.read_file(` → `self._builtin.read_file(`），实参一个都不用改 ——
凡是要"顺手调整调用"的重构，错误都藏在那些手改的地方。
"""

from __future__ import annotations

from typing import Any

from . import evolution, locked_builtins, persona
from .presets import (
    BUILTIN_ASSISTANTS,
    BUILTIN_IDENTITIES,
    BUILTIN_RULES,
    BUILTIN_SOULS,
    BUILTIN_USERS,
    DEFAULT_ASSISTANT_ID,
    LEGACY_DEFAULT_ASSISTANT_IDS,
    REMOVED_BUILTIN_IDS,
    RENAMED_BUILTIN_IDS,
    RENAMED_BUILTINS,
    builtin_config,
)


class BuiltinAssistants:
    """内置搭子的数据与工具。

    ⚠️ 这些名字与 ``presets`` / ``persona`` 里**逐字相同**：loader 侧的替换是
    机械换名，名字对不上就会变成两套叫法（下一个读代码的人得来回查）。
    """

    # ---- 数据表 ---------------------------------------------------------- #
    DEFAULT_ASSISTANT_ID = DEFAULT_ASSISTANT_ID
    REMOVED_BUILTIN_IDS = REMOVED_BUILTIN_IDS
    RENAMED_BUILTIN_IDS = RENAMED_BUILTIN_IDS
    RENAMED_BUILTINS = RENAMED_BUILTINS
    LEGACY_DEFAULT_ASSISTANT_IDS = LEGACY_DEFAULT_ASSISTANT_IDS
    BUILTIN_ASSISTANTS = BUILTIN_ASSISTANTS
    BUILTIN_SOULS = BUILTIN_SOULS
    BUILTIN_IDENTITIES = BUILTIN_IDENTITIES
    BUILTIN_RULES = BUILTIN_RULES
    BUILTIN_USERS = BUILTIN_USERS

    # 人格文件的文件名常量（loader 拿它们拼"文件 × 出厂正文"的播种表）
    SOUL_FILE = persona.SOUL_FILE
    IDENTITY_FILE = persona.IDENTITY_FILE
    RULES_FILE = persona.RULES_FILE
    USER_FILE = persona.USER_FILE

    # ---- 默认配置 -------------------------------------------------------- #
    def build_default_config(self) -> Any:
        """首次启动写入的完整默认配置（= ``presets.builtin_config()``）。"""
        return builtin_config()

    # ---- persona 工具（原签名转发）--------------------------------------- #
    def read_file(self, *args: Any, **kwargs: Any) -> Any:
        return persona.read_file(*args, **kwargs)

    def write_file(self, *args: Any, **kwargs: Any) -> Any:
        return persona.write_file(*args, **kwargs)

    def assistant_dir(self, *args: Any, **kwargs: Any) -> Any:
        return persona.assistant_dir(*args, **kwargs)

    # ---- 锁定与出厂回写（原签名转发）------------------------------------- #
    def is_locked(self, *args: Any, **kwargs: Any) -> Any:
        return locked_builtins.is_locked(*args, **kwargs)

    def factory_text(self, *args: Any, **kwargs: Any) -> Any:
        return locked_builtins.factory_text(*args, **kwargs)

    def restore_factory_fields(self, *args: Any, **kwargs: Any) -> Any:
        return locked_builtins.restore_factory_fields(*args, **kwargs)

    @property
    def FACTORY_TEXTS(self) -> Any:  # noqa: N802 - 与 locked_builtins 同名，见类 docstring
        return locked_builtins.FACTORY_TEXTS

    @property
    def LOCKED_PERSONA_FILES(self) -> Any:  # noqa: N802 - 同上
        return locked_builtins.LOCKED_PERSONA_FILES

    # ---- 进化规则（原签名转发）------------------------------------------- #
    def with_evolution_rule(self, *args: Any, **kwargs: Any) -> Any:
        return evolution.with_evolution_rule(*args, **kwargs)

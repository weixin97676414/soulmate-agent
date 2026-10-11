"""配置加载 / 保存 / 校验。

设计要点：
- 首次启动若配置文件不存在，自动写入默认值（含 DeepSeek 示例模型），
  用户只需在图形界面填入 API Key 即可使用；
- 保存时先经 Pydantic 校验，避免写入非法配置；
- 加载失败给出明确的 ``ConfigError``，不静默降级（对齐开发文档 9.4 节）。
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any

from ..errors import ConfigError
from . import keystore
from .paths import AppPaths
from .schemas import (
    AppConfig,
    AppSettings,
    AssistantsConfig,
    CustomSkillsConfig,
    GroupsConfig,
    McpConfig,
    ModelsConfig,
)

if TYPE_CHECKING:  # pragma: no cover
    # ⚠️ 只在类型注解里用到：`config` **不许**在运行时 import `assistants`（审计 M-20）。
    # 运行时拿到的是组合根注入的实例（见 `assistants/bootstrap.py` 的说明）。
    from ..assistants.bootstrap import BuiltinAssistants

logger = logging.getLogger(__name__)


def _default_models() -> ModelsConfig:
    """初始模型清单：**空**。

    曾经这里硬编码塞了 deepseek-chat 与本地 qwen3:8b 两条 —— 用户第一次打开
    设置就看到两个自己从没配置过的"幽灵模型"，而且那个 deepseek 的模型名
    已经不在供应商的在售清单里。**首次配置走界面上的接入向导**，没有配置
    就是空的；界面已有"没有可用模型"的明确引导（对话区顶栏标红 + 向导入口）。
    """
    return ModelsConfig(default_model="", models=[])


class ConfigStore:
    """负责配置文件的读写，并缓存最近一次加载结果。"""

    def __init__(
        self,
        paths: AppPaths,
        *,
        manage_secrets: bool = False,
        builtin: BuiltinAssistants | None = None,
    ) -> None:
        self._paths = paths
        self._config: AppConfig | None = None
        # 密钥是否由外部（Electron safeStorage）托管。只有托管时才在落盘时剥离，
        # 否则独立运行后端会让用户填过的 Key 在下次保存时悄悄消失。
        self._strip_secrets_on_save = manage_secrets
        # 内置搭子的数据源（审计 M-20）。
        #
        # ⚠️ **为什么是注入而不是 import**：`config` 是基础设施层，却要 import
        # `assistants.presets` 才知道"内置搭子长什么样"，于是两个包互相依赖
        # （`config → assistants → config.schemas`，只因 schemas 是叶子模块才没炸）。
        # 现在由组合根 `AppRuntime` 注入，实现在 `assistants/bootstrap.py`。
        #
        # ⚠️ `None` 表示"**不接管**内置搭子这一摊"：不播种、不迁移、不锁定回写，
        # 加载出来的就是文件里原样的内容。它只用于"只关心别的配置"的场合
        # （例如只读模型密钥的测试）；生产路径永远有值。
        self._builtin = builtin

    # ------------------------------------------------------------------ #
    # 加载
    # ------------------------------------------------------------------ #
    def load(self, *, reload: bool = False) -> AppConfig:
        if self._config is not None and not reload:
            return self._config

        self._paths.ensure()
        settings = self._load_settings()
        models = self._load_models()
        mcp = self._load_mcp()
        assistants = self._load_assistants()

        # **没有配置模型不再是启动失败**：新装用户的清单本来就是空的，
        # 引导页自己就要调 /v1/models、/v1/assistants —— 在这里拒绝加载等于
        # 把用户锁死在"还没配模型"的第一步之外。发消息时没有模型，
        # 由 chat 路由给出引导性的错误（那才是这个提示该出现的地方）。
        if models.resolve_default() is None:
            logger.warning("尚未配置任何模型；发消息前请先在「设置 → 模型服务商」里添加。")

        self._config = AppConfig(
            settings=settings, models=models, mcp=mcp, assistants=assistants
        )
        return self._config

    def _load_settings(self) -> AppSettings:
        path = self._paths.settings_file
        if not path.exists():
            settings = AppSettings()
            self._write_json(path, settings.model_dump(mode="json"))
            logger.info("已生成默认配置文件: %s", path)
            return settings
        raw = self._read_json(path)
        try:
            settings = AppSettings.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 - 统一转为 ConfigError
            raise ConfigError(f"settings.json 校验失败: {exc}", detail=str(path)) from exc

        # 内置搭子改过 id（见 presets.RENAMED_BUILTIN_IDS）：定时任务里存的是旧 id，
        # 不改的话任务会指向一个不存在的搭子（表现为"任务到点了却什么都没发生"）。
        # ⚠️ 这一步**很容易被漏**：它既不在 assistants.json 里，也不在数据库里，
        # 而是躺在 settings.json 的 scheduled_tasks 里。
        changed = False
        for spec in settings.agent.scheduled_tasks:
            new_id = self._builtin.RENAMED_BUILTIN_IDS.get(spec.assistant_id)
            if new_id:
                spec.assistant_id = new_id
                changed = True
        if changed:
            self._write_json(path, settings.model_dump(mode="json"))
            logger.info("已把定时任务的搭子 id 迁到新值: %s", path)
        return settings

    def _load_models(self) -> ModelsConfig:
        path = self._paths.models_file
        if not path.exists():
            models = _default_models()
            self._write_json(path, models.model_dump(mode="json"))
            logger.info("已生成默认模型配置: %s", path)
            return models
        raw = self._read_json(path)
        try:
            models = ModelsConfig.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(f"models.json 校验失败: {exc}", detail=str(path)) from exc

        if not self._strip_secrets_on_save:
            # 独立模式：Key 不在 models.json 里，而是单独加密存放在 secrets.enc
            # （见 config/keystore.py）。后者读不出来也不能让应用起不来 ——
            # 换机器解不开是需要用户重填 Key，不是需要他面对一个启动失败。
            self._apply_encrypted_keys(models)
        return models

    # ------------------------------------------------------------------ #
    # 独立模式的密钥存储
    # ------------------------------------------------------------------ #
    def _secrets_path(self):
        """加密密钥文件的位置。与 models.json 同目录，便于整体拷贝/备份。"""
        return self._paths.models_file.parent / "secrets.enc"

    def _remove_secrets_file(self) -> None:
        path = self._secrets_path()
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            # 删不掉要说出来：不说的话下次启动 Key 会"复活"，
            # 而用户完全没法把这两件事联系起来
            logger.warning("旧密钥文件删除失败（%s），已删除的 API Key 可能在重启后复现。", exc)

    def _apply_encrypted_keys(self, models: ModelsConfig) -> None:
        path = self._secrets_path()
        if not path.exists():
            return

        if not keystore.is_available():
            logger.warning(
                "发现加密密钥文件 %s，但本机无法使用系统加密（DPAPI 仅 Windows 可用），"
                "该文件将被忽略，请重新填写 API Key。",
                path,
            )
            return

        try:
            blob = path.read_bytes()
        except OSError as exc:
            logger.warning("密钥文件读取失败（%s），请重新填写 API Key。", exc)
            return

        keys = keystore.load_keys(blob)
        if not keys:
            # 解不开最常见的原因是**换了 Windows 账户或换了机器** ——
            # DPAPI 的密钥由用户配置文件派生，绑定之后就搬不走。
            # 必须说清"为什么"和"怎么办"，否则用户只会看到"模型全都不见了"。
            logger.warning(
                "密钥文件 %s 无法解密。DPAPI 的密钥与当前 Windows 用户账户绑定，"
                "换账户、换机器或重装系统后都会解不开。请重新填写 API Key。",
                path,
            )
            return

        applied = 0
        for spec in models.models:
            key = keys.get(spec.id)
            if key:
                spec.api_key = key
                applied += 1
        logger.info("已从加密文件恢复 %s 个模型的 API Key", applied)

    def _save_keys_encrypted_or_warn(self, validated: ModelsConfig, payload: dict[str, Any]) -> None:
        """把 Key 加密后单独存，并把 payload 里的明文清空。

        **只在确认写入成功后才清空 payload** —— 加密不可用、或文件写失败时
        如果照样清了空，用户的 Key 就真的没了，而且他不会知道。
        那种"保存成功但密钥消失"比不加密糟糕得多。
        """
        keys = {spec.id: spec.api_key for spec in validated.models if spec.api_key}
        if not keys:
            # 用户把 Key 全删了 —— 必须**同步删掉**已有的加密文件。
            #
            # 只是"什么都不做"的话旧文件会留在盘上，下次启动
            # ``_apply_encrypted_keys`` 又把它读回来按 id 塞回去，
            # 用户看到的是"我明明删掉了，重启它又回来了"，而且界面不提示任何异常。
            # 删除动作没能持久化，比明文落盘更难发现。
            self._remove_secrets_file()
            return

        blob = keystore.dump_keys(keys) if keystore.is_available() else None
        if blob is None:
            # 沿用既有行为：明文 + 明确告警。用户得知道这里**没有**加密，
            # 而不是以为它已经像桌面客户端那样受保护了。
            logger.warning(
                "当前以独立模式运行，且本机无法使用系统加密（DPAPI 仅 Windows 可用），"
                "API Key 将以**明文**写入 %s。若需要加密保护，请通过桌面客户端运行。",
                self._paths.models_file,
            )
            return

        path = self._secrets_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # 与 _write_json 同理：用 os.open 而不是 open()，只有前者能在
            # **创建时**就带上权限位，中间没有"先 644 再 chmod"的窗口期
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, self._FILE_MODE)
            with os.fdopen(fd, "wb") as fh:
                fh.write(blob)
        except OSError as exc:
            logger.error("密钥加密文件写入失败（%s），本次保留明文以免丢失 Key。", exc)
            return

        for spec in payload.get("models", []):
            spec["api_key"] = ""
        logger.info("API Key 已用 Windows DPAPI 加密保存到 %s", path)

    def _load_mcp(self) -> McpConfig:
        path = self._paths.mcp_file
        if not path.exists():
            # 首次生成时**播种自带的 SQLite 只读查询服务** —— 
            # 它随应用分发（标准库实现，不需要 uv / Node），应该开箱就在、
            # 并且随应用自动开启（`auto_start` 见 build_sqlite_server）。
            #
            # ⚠️ **只在"文件不存在"时写，之后只读不补** —— 与助手播种同一取舍
            # （见 `_load_assistants` 的说明）：用户删掉它是明确的意图，每次启动都
            # 补回来会让人没法真正删掉它（真想删还得去翻配置文件）。想加回来，
            # 「MCP 服务」页的快速添加里一直有它。
            #
            # ⚠️ 函数内 import：`mcp` 包会反向依赖 config，放模块顶部会绕成环。
            from ..mcp.presets import build_sqlite_server

            config = McpConfig(servers=[build_sqlite_server(self._paths)])
            self._write_json(path, config.model_dump(mode="json"))
            logger.info("已生成默认 MCP 配置（含自带的 SQLite 只读查询）: %s", path)
            return config
        raw = self._read_json(path)
        try:
            return McpConfig.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(f"mcp.json 校验失败: {exc}", detail=str(path)) from exc

    def _load_assistants(self) -> AssistantsConfig:
        """载入助手配置；首次启动时写入内置预设。

        注意后续启动**只读不补**：用户删掉某个内置助手是明确的意图，
        每次启动都补回来会让人没法真正删掉它。补种走显式的「恢复默认助手」。

        唯一的例外是 ``self._builtin.REMOVED_BUILTIN_IDS``：这些 id 已经从预设表里移除，
        是**产品决策**而不是用户操作 —— 旧配置里残留的条目要在启动时清掉，
        否则升级用户会一直看到两个预设表里已不存在的幽灵助手。
        只清 ``builtin=True`` 的：用户拿同名 id 自建的助手不受影响。
        """
        path = self._paths.assistants_file
        if not path.exists():
            if self._builtin is None:
                # 没有数据源：写一份**空**配置并返回（见构造里的说明）。
                config = AssistantsConfig()
                self._write_json(path, config.model_dump(mode="json"))
                logger.info("已生成空的助手配置（未注入内置搭子数据源）: %s", path)
                return config
            config = self._builtin.build_default_config()
            self._write_json(path, config.model_dump(mode="json"))
            logger.info("已生成内置助手预设: %s", path)
            # ⚠️ 这里必须**也**播一次初始 SOUL，不能直接 return。
            # 内置搭子的出厂人设现在**只**来自 SOUL.md（提示词兜底已退役，
            # 见 agent/engine.py 的 _system_prompt），漏播的直接后果是：
            # 全新安装的首启那一次会话，五个人格文件全空 → 一条 system 都没有，
            # 用户一上来就会遇到"搭子不知道自己是谁"。第二次启动才补上是不可接受的。
            self._seed_builtin_souls(config)
            # ⚠️ 人格包对齐也必须在这里跑掉（并写 marker）：否则首启不跑、
            # 第二次启动才跑 —— 用户在这两次启动之间改过的 SOUL 会被覆盖掉，
            # "对齐后解锁"就破了个洞（marker 的意义正是把覆盖限制在第一拍）。
            self._align_persona_pack(config)
            return config
        raw = self._read_json(path)
        try:
            config = AssistantsConfig.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(f"assistants.json 校验失败: {exc}", detail=str(path)) from exc

        if self._builtin is None:
            # 没有数据源：不做内置搭子的清理 / 迁移 / 播种，原样返回（见构造里的说明）。
            return config

        stale = {item.id for item in config.assistants if item.builtin} & set(
            self._builtin.REMOVED_BUILTIN_IDS
        )
        if stale:
            config.assistants = [
                item for item in config.assistants if item.id not in stale
            ]
            if config.default_assistant in stale:
                config.default_assistant = self._builtin.DEFAULT_ASSISTANT_ID
            self._write_json(path, config.model_dump(mode="json"))
            logger.info("已移除过期的内置助手: %s", ", ".join(sorted(stale)))

        # 出厂改名的迁移（见 presets.RENAMED_BUILTINS）：老用户配置里存的还是旧名，
        # 而这是一次**产品改名** —— 只把"仍是出厂值"的名字 / 简介 / SOUL 换成新值，
        # 用户改过的一律不动。迁移完要落盘，否则下次启动又白算一遍。
        renamed = self._migrate_renamed_builtins(config)
        if renamed:
            self._write_json(path, config.model_dump(mode="json"))
            logger.info("已迁移出厂改名的内置搭子: %s", ", ".join(sorted(renamed)))

        # 内置搭子温度出厂值调整：同一条"只动仍是出厂值的"规矩，
        # 用户自己调过温度的机器不受影响。
        if self._migrate_builtin_temperatures(config):
            self._write_json(path, config.model_dump(mode="json"))

        # 出厂 id 迁移（见 presets.RENAMED_BUILTIN_IDS）。
        # ⚠️ 顺序：必须在**改名迁移之后** —— 上面那张表是按**旧 id** 查名字/人设的，
        # 顺序反了就永远匹配不上（id 已经换了，表里查不到）。
        if self._migrate_builtin_ids(config):
            self._write_json(path, config.model_dump(mode="json"))
            logger.info("已迁移内置搭子的 id: %s", path)

        # 默认搭子的出厂值迁移（见 ``presets.DEFAULT_ASSISTANT_ID``）。
        # ⚠️ 顺序：必须排在 **id 迁移之后** —— ``default_assistant`` 有可能刚被
        # id 迁移改过，反过来会让"默认值还是旧的"这个判断落空。
        # 也要排在 ``_seed_builtin_souls`` 之前：新补种的那个搭子得一起拿到初始 SOUL。
        if self._migrate_default_assistant(config):
            self._write_json(path, config.model_dump(mode="json"))
            logger.info("已迁移出厂默认搭子为: %s", config.default_assistant)

        # 内置搭子的初始 SOUL：**只在文件不存在时写**，绝不覆盖用户已编辑的。
        # 这条不放在"首次播种"分支里 —— 老用户升级后同样要拿到这份初始 SOUL，
        # 否则他们的内置搭子 SOUL.md 一直是空的。
        self._seed_builtin_souls(config)

        # 《搭子人格包》**一次性**对齐（先于回写）：把 SOUL/IDENTITY/RULES 矫成
        # 人格包原文并写 marker；此后这三个文件解锁（只有 RULES 由下面的回写继续管）。
        # 排在播种之后没有强约束，但"先补缺、再对齐"读起来顺序更自然。
        self._align_persona_pack(config)

        # 四位内置搭子的"写死"（见 ``assistants/locked_builtins``）。
        # ⚠️ 必须排在 ``_seed_builtin_souls`` **之后**：先补"文件不存在"的，
        # 再对这四个 id 做强制回写 —— 顺序反了的话，回写过的文件又会走进
        # "已存在就不写"的分支，白白多跑一轮。
        if self._enforce_locked_builtins(config):
            self._write_json(path, config.model_dump(mode="json"))
            logger.info("已把内置搭子的写死字段校正回出厂值")

        # 自建搭子的「全员进化」初始规则：**补缺口用的那一遍**。
        # 新建搭子时已经写过了，这里管的是"这个功能上线之前就存在的老搭子"——
        # 它们不会自己长出这段规则，而少了它就永远不会主动问用户要不要建进化任务。
        # ⚠️ 它改的是**人格文件**，不动 assistants.json，所以不需要 _write_json
        if self._patch_evolution_rules(config):
            logger.info("已给自建搭子补上「全员进化」初始规则")
        return config

    def _patch_evolution_rules(self, config: AssistantsConfig) -> bool:
        """给**已经存在**的自建搭子补一段「全员进化」初始规则（幂等）。

        ## 为什么必须有这一遍

        新建搭子时（界面建 / AI 建）已经会写这段规则了，但**之前建的搭子不会自己长出来**。
        少了这段，那个搭子永远不会主动问用户"要不要建每周进化任务" ——
        而界面上完全看不出缺了什么（规则文件本来就是用户可编辑的）。

        ## 三条纪律

        1. **只碰自建 / AI 建的**：判定用 ``self._builtin.is_locked()`` 取反 ——
           四个内置搭子走**预置任务**那条路，它们的 RULES.md 还会被启动回写覆盖，
           写了也是白写（而且会让"出厂原文"这件事变得不可信）。
        2. **只补不覆盖**：RULES.md 里已经有这一节就一个字都不动
           （``self._builtin.with_evolution_rule`` 自己判重）。
        3. **不用标记文件**：判据就是"文件里有没有那一节"，天然幂等 ——
           用户手动删掉这节 = 明确不要，系统不该偷偷补回来（与"用户改过算数"同一口径）。

        返回"有没有改动"（调用方据此决定要不要重写 assistants.json ——
        其实这些改动都在人格文件里，返回值只是为了让日志能说清"这一轮到底做没做事"）。
        """
        changed = False
        for item in config.assistants:
            if self._builtin.is_locked(item.id):
                continue
            name = (item.nickname or item.name).strip() or item.name
            try:
                current = self._builtin.read_file(self._paths, item.id, self._builtin.RULES_FILE)
                merged = self._builtin.with_evolution_rule(current, name)
                if merged == current:
                    continue
                self._builtin.write_file(self._paths, item.id, self._builtin.RULES_FILE, merged)
            except (OSError, ValueError) as exc:
                # 单个搭子写不进去不该拦住启动：它是"锦上添花"的一步
                logger.warning("给搭子 %s 补初始规则失败：%s", item.id, exc)
                continue
            changed = True
        return changed

    def _migrate_default_assistant(self, config: AssistantsConfig) -> bool:
        """把默认搭子交给「搭子总管」，并把总管补种给老配置。

        ## 为什么需要它

        的决策：打开客户端应先落到「搭子总管」。但
        ``default_assistant`` 是**持久化**的，光改代码里的常量对老机器没有任何影响
        （与 ``self._builtin.RENAMED_BUILTIN_IDS`` 是同一类问题），所以必须有这条一次性迁移。

        ## 两条规则，各自防一个坑

        1. **默认位只在"还是旧的出厂值"时才动**：用户自己挑过默认搭子就是他的
           选择，绝不动（与 ``self._builtin.RENAMED_BUILTINS`` 同一条规矩：只覆盖"还是出厂值"
           的那部分）。

        2. **总管不在清单里时，顺手补种**。这既是"默认位不能指向一个不存在的
           id"的技术需要，也是用户这轮的本意（"新增这个搭子"）—— 只靠默认位迁移
           的话，老配置里那个搭子根本不存在。``_load_assistants`` 那句"后续启动
           只读不补"在这里**有意让路**，理由与 ``self._builtin.REMOVED_BUILTIN_IDS`` 那次清理
           相同：这是**产品决策**，不是用户操作。

           ⚠️ 补种**故意与规则 1 绑在一起**，不许放宽成"只要不在清单里就补"：
           那会变成"删掉的总管下次启动又回来"，与"用户删内置搭子是明确意图"直接
           冲突。绑在一起之后：用户从没调过默认位 → 他只是没被问到，补给他；
           用户调过默认位 → 说明他对清单有主见，一切照他的来（想要总管可以从
           设置里点「恢复默认搭子」）。

        返回是否改动过（调用方据此决定要不要落盘）。
        """
        if config.default_assistant not in self._builtin.LEGACY_DEFAULT_ASSISTANT_IDS:
            return False
        target = next(
            (profile for profile in self._builtin.BUILTIN_ASSISTANTS if profile.id == self._builtin.DEFAULT_ASSISTANT_ID),
            None,
        )
        if target is None:
            # 预设表里都没有（有人改了常量却没加预设）→ 什么都不做，别把默认值改坏
            logger.warning("默认搭子 %s 不在预设表里，跳过迁移", self._builtin.DEFAULT_ASSISTANT_ID)
            return False
        if config.get(target.id) is None:
            config.upsert(target.model_copy(deep=True))
            logger.info("已补种新的默认搭子: %s", target.id)
        config.default_assistant = target.id
        return True

    def _migrate_renamed_builtins(self, config: AssistantsConfig) -> set[str]:
        """把出厂改过名的内置搭子迁到新值（见 ``presets.RENAMED_BUILTINS``）。

        为什么需要它：搭子配置是**持久化**的，老用户的 ``assistants.json`` 里存的
        是旧名，光改代码里的预设对他们没有任何影响 —— 而这是一次产品改名，
        升级用户看到旧名会以为是另一个东西。

        覆盖范围刻意收得很窄（与 ``_seed_builtin_souls`` 同一条规矩：绝不覆盖
        用户编辑过的内容）：

        - ``name`` / ``description`` **逐字等于**出厂旧值才替换；
        - ``SOUL.md`` 只在**逐字节等于**旧出厂文本时才整份换新；
        - 只处理 ``builtin=True`` 的条目 —— 用户拿同名 id 自建的搭子不受影响。

        返回被改过的搭子 id，供调用方决定要不要落盘。
        """
        current_by_id = {profile.id: profile for profile in self._builtin.BUILTIN_ASSISTANTS}
        migrated: set[str] = set()

        for item in config.assistants:
            if not item.builtin:
                continue
            old = self._builtin.RENAMED_BUILTINS.get(item.id)
            if not old:
                continue
            # ⚠️ 当前预设表的 key 是**新 id**（内置搭子改过 id，见 self._builtin.RENAMED_BUILTIN_IDS），
            # 而这张改名表的 key 是**旧 id** —— 所以必须先把 id 翻成新的再查当前值。
            # 少了这一步，整段改名迁移会**静默失效**（current 永远查不到，名字停在旧值），
            # 而它不会报任何错：用户只会觉得"升级之后名字怎么没变"。
            current = current_by_id.get(self._builtin.RENAMED_BUILTIN_IDS.get(item.id, item.id))
            if current is None:
                continue

            changed = False
            if item.name.strip() == old["name"]:
                item.name = current.name
                changed = True
            if item.description.strip() == old["description"]:
                item.description = current.description
                changed = True

            target = self._builtin.assistant_dir(self._paths, item.id) / self._builtin.SOUL_FILE
            try:
                on_disk = target.read_text(encoding="utf-8")
            except FileNotFoundError:
                # 没有文件（用户删过，或被补种前的老机器）→ 交给 _seed_builtin_souls
                on_disk = ""
            except OSError as exc:
                logger.warning("读取内置搭子 SOUL 失败 %s: %s", item.id, exc)
                on_disk = ""
            if on_disk == old["soul"]:
                # 同样要按**新 id** 查当前出厂人设（self._builtin.BUILTIN_SOULS 的 key 已经是新 id 了）
                fresh = self._builtin.BUILTIN_SOULS.get(self._builtin.RENAMED_BUILTIN_IDS.get(item.id, item.id))
                if fresh:
                    try:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(fresh, encoding="utf-8")
                        changed = True
                        logger.info("已更新内置搭子 SOUL 里的自称: %s", item.id)
                    except OSError as exc:
                        logger.warning("迁移内置搭子 SOUL 失败 %s: %s", item.id, exc)

            if changed:
                migrated.add(item.id)

        return migrated

    # 内置搭子温度出厂值调整（LoveBuddy 0.5 / RelationBuddy 0.4 /
    # soulmate 0.7）。温度是**用户可调**字段（不在硬锁范围内），所以这里沿用
    # ``self._builtin.RENAMED_BUILTINS`` 那条规矩：只迁移"仍是旧出厂值"的 —— 用户自己调过的不动。
    # 结构：{搭子 id: (旧出厂值, 新出厂值)}。只在这里追加，别改历史条目。
    _TEMPERATURE_MIGRATIONS: dict[str, tuple[float, float]] = {
        "LoveBuddy": (0.85, 0.5),
        "RelationBuddy": (0.7, 0.4),
        "soulmate": (0.8, 0.7),
    }

    def _migrate_builtin_temperatures(self, config: AssistantsConfig) -> bool:
        """把仍为旧出厂值的内置搭子温度迁到新值。返回是否改动过（供落盘判断）。"""
        changed = False
        for item in config.assistants:
            migration = self._TEMPERATURE_MIGRATIONS.get(item.id)
            if not migration:
                continue
            old_value, new_value = migration
            if item.temperature is not None and abs(item.temperature - old_value) < 1e-9:
                item.temperature = new_value
                changed = True
                logger.info("已把内置搭子 %s 的温度从 %s 迁到 %s", item.id, old_value, new_value)
        return changed

    def _seed_builtin_souls(self, config: AssistantsConfig) -> None:
        """给内置搭子补上初始人格文件（文件不存在才写）。

        原先只播 SOUL.md。给了搭子总管的成品 IDENTITY / RULES 文案，
        要求"替换到默认（首启）配置当中"，于是这里把三张表一起播（见 ``presets`` 的
        ``self._builtin.BUILTIN_SOULS`` / ``self._builtin.BUILTIN_IDENTITIES`` / ``self._builtin.BUILTIN_RULES``）；
        soulmate 的 ``USER.md`` 模板同批纳入（同样是"缺失才写"）。

        ⚠️ 规矩没变：**只在文件不存在时写**，绝不覆盖用户已经编辑过的内容。
        RULES.md 的"写死回写"与 SOUL/IDENTITY 的一次性对齐是另外两条路（见下面
        ``_align_persona_pack`` 与 ``_enforce_locked_builtins``）。
        """
        tables: list[tuple[str, dict[str, str]]] = [
            (self._builtin.SOUL_FILE, self._builtin.BUILTIN_SOULS),
            (self._builtin.IDENTITY_FILE, self._builtin.BUILTIN_IDENTITIES),
            (self._builtin.RULES_FILE, self._builtin.BUILTIN_RULES),
            (self._builtin.USER_FILE, self._builtin.BUILTIN_USERS),
        ]
        for item in config.assistants:
            if not item.builtin:
                continue
            for file_name, table in tables:
                default = table.get(item.id)
                if not default:
                    continue
                target = self._builtin.assistant_dir(self._paths, item.id) / file_name
                if target.is_file():
                    continue
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(default, encoding="utf-8")
                    logger.info("已写入内置搭子初始 %s: %s", file_name, item.id)
                except OSError as exc:
                    logger.warning("写入内置搭子 %s 失败 %s: %s", file_name, item.id, exc)

    # ------------------------------------------------------------------ #
    # 人格包一次性对齐
    # ------------------------------------------------------------------ #
    # ⚠️ marker 是**版本化**的（文件内容 = _PERSONA_PACK_VERSION）：
    # 人格包模板每次变更（如 43 批加"性别"行）都要把版本号 +1 —— 不然用户机器上
    # 0.1.50 已经写过的 marker 会让新模板永远不生效。重对齐会把 SOUL / IDENTITY /
    # RULES 覆盖成新原文，用户在那期间的手改会被覆盖 —— 这是"模板变更"的既定代价，
    # 文档里如实说明；此后文件依旧解锁，用户可继续改。
    # 版本 3（，46 批）：Soulmate 的出厂 RULES 新增「三、自动化任务（必须）」
    # 整节（并给「二、陪伴的规则」补上"仅限对话陪聊当中"的限定）。
    # ⚠️ 这一次的代价要说清楚：重对齐会把 SOUL / IDENTITY 一起覆盖回出厂原文，
    # 也就是**用户在 0.1.53 及更早版本里对这两份文件的手改会被清掉一次** ——
    # 包括 46 批"快捷设置"写进 IDENTITY.md 的昵称。只发生一次（marker 随即变成 3），
    # 之后用户再改就算数。选 bump 而不是"只换 RULES 不升版本"（RULES 本来就每次启动
    # 回写，不升也能生效），是为了守住"模板变更必升版本"这条规矩，别让它有例外。
    _PERSONA_PACK_MARKER = ".persona-pack-aligned"
    _PERSONA_PACK_VERSION = "3"

    def _align_persona_pack(self, config: AssistantsConfig) -> bool:
        """把三个内置搭子的人格文件**一次性**对齐到《搭子人格包》原文。

        ## 为什么是"一次性"而不是每次启动都回写

        的两句话合起来是这个设计：
        ① "soul.md 和 IDENTITY.md 也被固定了，这是不对的" —— 对齐之后它们必须
        **解锁**，用户改了要算数；
        ② "我需要删后，md 的内容都和搭子人格包里面的相同" —— 但**当前**机器上的
        SOUL/IDENTITY/RULES 是四十一批锁定期间被写坏/被 AI 写乱的，必须先矫成正文。

        一次性迁移同时满足两句：跑一遍把 SOUL/IDENTITY/RULES 覆盖成人格包原文
        （用户点名要删的那几句只在机器上的旧文件里，人格包版本没有，覆盖即消失），
        然后写 marker，**之后**这三个文件谁也不许再动 —— 用户的手改从此生效。
        只有 RULES 例外：它继续锁定，由 ``_enforce_locked_builtins`` 每次启动矫正。

        ## USER.md 只补缺

        它是报告维护的活文档（AI 拉报告后更新动态部分）：只在**缺失**时播种模板，
        已有的一律不碰 —— 覆盖等于抹掉已积累的报告数据。
        """
        marker = self._paths.data_dir / self._PERSONA_PACK_MARKER
        if marker.is_file():
            try:
                if marker.read_text(encoding="utf-8").strip() == self._PERSONA_PACK_VERSION:
                    return False
            except OSError as exc:
                # 读不出来就当没对齐过，重跑一遍 —— 覆盖的是出厂正文方向，安全侧
                logger.warning("读取人格包对齐标记失败（按未对齐处理）：%s", exc)

        changed = False
        for item in config.assistants:
            if not self._builtin.is_locked(item.id):
                continue
            directory = self._builtin.assistant_dir(self._paths, item.id)
            for file_name, table in self._builtin.FACTORY_TEXTS.items():
                factory = table.get(item.id)
                if not factory:
                    continue
                target = directory / file_name
                if file_name == self._builtin.USER_FILE:
                    # USER 是活文档，覆盖等于抹掉用户已积累的档案 —— 只做两件事：
                    # ① 缺失才补整份模板；② 已有但没跟上新模板行（"用户性别："）的，
                    #    在"用户称呼"行后**插一行**，其余内容一个字不动。
                    if self._seed_or_patch_user_file(target, factory):
                        changed = True
                    continue
                try:
                    if target.is_file() and target.read_text(encoding="utf-8") == factory:
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(factory, encoding="utf-8")
                    changed = True
                    logger.info("已把内置搭子 %s 的 %s 对齐到人格包原文", item.id, file_name)
                except OSError as exc:
                    logger.warning("对齐内置搭子 %s 的 %s 失败: %s", item.id, file_name, exc)

        try:
            marker.write_text(f"{self._PERSONA_PACK_VERSION}\n", encoding="utf-8")
        except OSError as exc:
            # marker 写不出来时**必须**让人知道：否则下次启动还会整份覆盖一遍，
            # 用户在两次启动之间改过的 SOUL 就会被吃掉
            logger.error("写入人格包对齐标记失败（下次启动会重新对齐一遍）：%s", exc)
        return changed

    @staticmethod
    def _seed_or_patch_user_file(target: Any, factory: str) -> bool:
        """USER.md 的两种补法：缺失补整份模板；已有则只插缺失的模板行。

        为什么单独一个函数：USER 与 SOUL/IDENTITY/RULES 的规矩**相反** ——
        后者是"以出厂为准"，前者是"以用户为准"。混在一个分支里写，迟早有人
        把"整份覆盖"顺手加到 USER 上，抹掉用户已积累的档案。
        """
        try:
            if not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(factory, encoding="utf-8")
                logger.info("已播种 USER 模板：%s", target.parent.name)
                return True

            current = target.read_text(encoding="utf-8")
            if "用户性别" in current:
                return False  # 模板行已经有了（哪怕用户改过措辞），一个字不动

            # 在"用户称呼"那行后面插一行"用户性别："；找不到锚点（AI 自己写的
            # 格式千奇百怪）就**追加在末尾** —— 追加不挤占原文任何一行，最安全。
            lines = current.replace("\r\n", "\n").split("\n")
            anchor = next(
                (index for index, line in enumerate(lines) if line.strip().startswith("用户称呼")),
                None,
            )
            insert_at = anchor + 1 if anchor is not None else len(lines)
            lines.insert(insert_at, "用户性别：")
            target.write_text("\n".join(lines), encoding="utf-8")
            logger.info("已在 USER 模板补入\"用户性别\"行：%s", target.parent.name)
            return True
        except OSError as exc:
            logger.warning("USER 模板补种/插行失败 %s: %s", target, exc)
            return False

    def _enforce_locked_builtins(self, config: AssistantsConfig) -> bool:
        """把四位内置搭子的"写死字段"强行掰回出厂值。返回是否改动过。

        ## 为什么必须每次启动都回写

        产品约定是"任何途径都不可改"。裁决层
        （``assistants/locked_builtins``）挡住了接口与技能，但**挡不住直接改文件**：
        ``assistants.json`` 就是普通文本。而"首次播种"救不回来 ——
        它的规矩恰恰是"文件已存在就不写"。

        所以这里对**这四个 id**换一条规矩：不一致就覆盖。

        ## 二次修正：人格文件只回写 RULES.md

        用户更正了口径："可是现在 soul.md 和 IDENTITY.md 也被固定了，这是不对的"。
        所以 SOUL/IDENTITY 的矫正收进了 ``_align_persona_pack``（**一次性**，
        对齐完就解锁）；这里持续回写的只剩 ``LOCKED_PERSONA_FILES``（= RULES.md）
        与三个配置字段。

        ## 与 ``_migrate_renamed_builtins`` 的差别（别把两者看成一回事）

        那边是"只在**还是旧出厂值**时才改"，怕吃掉用户的个性化；这边正相反 ——
        **必须**把个性化抹掉。两条规矩都对，只是服务的对象不同：普通内置搭子
        属于用户，这四个是产品的一部分。
        """
        changed = False
        for index, item in enumerate(config.assistants):
            if not self._builtin.is_locked(item.id):
                continue

            restored = self._builtin.restore_factory_fields(item)
            if restored != item:
                config.assistants[index] = restored
                changed = True
                logger.info("已把内置搭子 %s 的名称/简介/能力改回出厂值", item.id)

            for file_name in sorted(self._builtin.LOCKED_PERSONA_FILES):
                factory = self._builtin.factory_text(item.id, file_name)
                target = self._builtin.assistant_dir(self._paths, item.id) / file_name

                if not factory:
                    # 出厂态 = 没有这份文件。存在就删（见上面的说明）
                    if not target.is_file():
                        continue
                    try:
                        target.unlink()
                    except OSError as exc:
                        logger.warning("删除内置搭子 %s 失败 %s: %s", file_name, item.id, exc)
                        continue
                    changed = True
                    logger.warning("已删除内置搭子 %s 出厂态不存在的 %s", item.id, file_name)
                    continue

                try:
                    on_disk = target.read_text(encoding="utf-8")
                except FileNotFoundError:
                    on_disk = None
                except OSError as exc:
                    logger.warning("读取内置搭子 %s 失败 %s: %s", file_name, item.id, exc)
                    continue
                if on_disk == factory:
                    continue
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(factory, encoding="utf-8")
                except OSError as exc:
                    logger.warning("回写内置搭子 %s 失败 %s: %s", file_name, item.id, exc)
                    continue
                changed = True
                logger.info("已把内置搭子 %s 的 %s 改回出厂正文", item.id, file_name)

        return changed

    # ------------------------------------------------------------------ #
    # 出厂 id 迁移
    # ------------------------------------------------------------------ #
    def _migrate_builtin_ids(self, config: AssistantsConfig) -> bool:
        """把内置搭子的 id 从旧值迁到新值（见 ``presets.RENAMED_BUILTIN_IDS``）。

        为什么要迁移而不是"改了预设就行"：id 是**主键** —— 会话归属、群成员、
        人格文件目录（``data/assistants/<id>/``）、定时任务、长期记忆库名都挂在它上面。
        只改代码里的字面量而不搬数据，升级用户会看到：历史会话找不到搭子、群成员
        指向一个不存在的 id、人格文件全空（用户会以为"我的搭子被清空了"）。

        范围与幂等：
        - 只动 ``builtin=True`` 且命中迁移表的条目（用户自建的搭子碰都不碰）；
        - ``default_assistant`` 跟着改 —— 不然默认搭子会指向一个不存在的 id；
        - 幂等：跑第二次时旧 id 已经不存在，方法返回 False、什么都不写；
        - 人格目录顺带改名，失败只记 warning（见 `_rename_persona_dir`）。
        """
        migrated: list[str] = []
        for profile in config.assistants:
            new_id = self._builtin.RENAMED_BUILTIN_IDS.get(profile.id)
            if not new_id or not profile.builtin:
                continue
            if any(item.id == new_id for item in config.assistants):
                # 新 id 已经被占用（例如用户自己建过一个叫同名的）：**不动它**。
                # 宁可留下旧 id 的条目让用户自己收拾，也不能静默吞掉谁。
                logger.warning(
                    "内置搭子 %s 要改名为 %s，但新 id 已被占用，已跳过", profile.id, new_id
                )
                continue
            old_id = profile.id
            profile.id = new_id
            migrated.append(f"{old_id}→{new_id}")
            self._rename_persona_dir(old_id, new_id)

        if not migrated:
            return False
        if config.default_assistant in self._builtin.RENAMED_BUILTIN_IDS:
            config.default_assistant = self._builtin.RENAMED_BUILTIN_IDS[config.default_assistant]
        logger.info("内置搭子 id 已迁移: %s", ", ".join(migrated))
        return True

    def _rename_persona_dir(self, old_id: str, new_id: str) -> None:
        """把人格文件目录 ``data/assistants/<旧 id>`` 改名为新 id。

        ⚠️ **大小写变化要走两步改名**：``lovebuddy → LoveBuddy`` 在 Windows / macOS
        这类大小写不敏感的文件系统上，直接 rename 常被判成"源与目标是同一个路径"
        而失败。先搬到临时名、再搬回目标名，两边文件系统都稳。

        目标已存在时**不覆盖**（宁可留着旧目录让人自己看，也不静默丢掉人格文件）；
        任何 OSError 都只记 warning —— 配置迁移不该因为一个目录搬不动就整体失败。
        """
        root = self._paths.data_dir / "assistants"
        source = root / old_id
        target = root / new_id
        if not source.exists() or target.exists():
            return
        temp = root / f"__migrating_{old_id}"
        try:
            if old_id.lower() == new_id.lower():
                source.rename(temp)
                temp.rename(target)
            else:
                source.rename(target)
            logger.info("人格文件目录已迁移: %s → %s", old_id, new_id)
        except OSError as exc:
            logger.warning("人格文件目录改名失败（%s → %s）：%s；旧目录保留", old_id, new_id, exc)
            # 中途失败的收敛：临时目录还在就搬回原名，别留下一个谁也认不出的目录
            if temp.exists() and not source.exists():
                try:
                    temp.rename(source)
                except OSError:
                    pass

    # ------------------------------------------------------------------ #
    # AI 群（groups.json）
    # ------------------------------------------------------------------ #
    def load_groups(self) -> GroupsConfig:
        """载入 AI 群定义；首次启动写一个空文件。

        加载失败返回空配置而不是抛异常：与 custom_skills 同理，这个文件是
        用户（或未来的群管理界面）改的，写坏不该让应用起不来。
        """
        path = self._paths.groups_file
        if not path.exists():
            config = GroupsConfig(groups=[])
            self._write_json(path, config.model_dump(mode="json"))
            return config
        raw = self._read_json(path)
        try:
            config = GroupsConfig.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            logger.error("groups.json 校验失败，已忽略该文件: %s", exc)
            return GroupsConfig(groups=[])

        # 内置搭子改过 id（见 presets.RENAMED_BUILTIN_IDS）：群成员与发言顺序里存的
        # 还是旧 id。**这是最容易漏的一处** —— 不迁的话，升级用户的群会指向一个不
        # 存在的搭子：讨论起不来、成员名显示成 id。迁移是幂等的（旧 id 迁完就没了）。
        changed = False
        for group in config.groups:
            members = [self._builtin.RENAMED_BUILTIN_IDS.get(item, item) for item in group.member_assistant_ids]
            order = [self._builtin.RENAMED_BUILTIN_IDS.get(item, item) for item in group.speaking_order]
            if members != group.member_assistant_ids or order != group.speaking_order:
                group.member_assistant_ids = members
                group.speaking_order = order
                changed = True
        if changed:
            self.save_groups(config)
            logger.info("已把群成员里的搭子 id 迁到新值: %s", path)
        return config

    def save_groups(self, config: GroupsConfig) -> GroupsConfig:
        validated = GroupsConfig.model_validate(config.model_dump(mode="json"))
        self._write_json(self._paths.groups_file, validated.model_dump(mode="json"))
        return validated

    # ------------------------------------------------------------------ #
    # 保存
    # ------------------------------------------------------------------ #
    def save_assistants(self, config: AssistantsConfig) -> AssistantsConfig:
        validated = AssistantsConfig.model_validate(config.model_dump(mode="json"))
        self._write_json(self._paths.assistants_file, validated.model_dump(mode="json"))
        if self._config is not None:
            self._config = self._config.model_copy(update={"assistants": validated})
        return validated

    def save_mcp(self, config: McpConfig) -> McpConfig:
        """写回 MCP 配置。落盘时会剥离密钥类环境变量（见 ``config/secrets.py``）。"""
        validated = McpConfig.model_validate(config.model_dump(mode="json"))
        payload = validated.model_dump(mode="json")
        if self._strip_secrets_on_save:
            from .secrets import is_secret_key

            for server in payload.get("servers", []):
                env = server.get("env") or {}
                server["env"] = {k: v for k, v in env.items() if not is_secret_key(k)}
        self._write_json(self._paths.mcp_file, payload)
        if self._config is not None:
            self._config = self._config.model_copy(update={"mcp": validated})
        return validated

    def load_custom_skills(self) -> CustomSkillsConfig:
        """载入用户自定义技能；首次启动写一个空文件。

        **加载失败返回空配置而不是抛异常**：这个文件是用户手工编辑的
        （也可能由助手通过工具写入），写坏一个逗号不该让整个应用起不来 ——
        那样用户连进设置页改回的机会都没有。
        """
        path = self._paths.custom_skills_file
        if not path.exists():
            config = CustomSkillsConfig(skills=[])
            self._write_json(path, config.model_dump(mode="json"))
            return config
        raw = self._read_json(path)
        try:
            return CustomSkillsConfig.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            logger.error("custom_skills.json 校验失败，已忽略该文件: %s", exc)
            return CustomSkillsConfig(skills=[])

    def save_custom_skills(self, config: CustomSkillsConfig) -> CustomSkillsConfig:
        validated = CustomSkillsConfig.model_validate(config.model_dump(mode="json"))
        self._write_json(self._paths.custom_skills_file, validated.model_dump(mode="json"))
        return validated

    def save_models(self, models: ModelsConfig) -> ModelsConfig:
        """校验并写回模型配置，同时刷新缓存。

        **API Key 不落盘**：密钥由 Electron 主进程用 safeStorage（Windows DPAPI）
        加密保管，这里写出去的是空字符串。内存中的配置仍然保留真实 Key，
        否则保存完这个动作本身就会让对话立刻用不了。
        """
        validated = ModelsConfig.model_validate(models.model_dump(mode="json"))
        payload = validated.model_dump(mode="json")
        if self._strip_secrets_on_save:
            for spec in payload.get("models", []):
                spec["api_key"] = ""
        else:
            # 独立模式（没有 safeStorage 托管）：Key 单独加密存放，
            # models.json 里只留空字符串。加密不可用时退回明文 + 告警。
            self._save_keys_encrypted_or_warn(validated, payload)
        self._write_json(self._paths.models_file, payload)
        if self._config is not None:
            self._config = self._config.model_copy(update={"models": validated})
        return validated

    def save_settings(self, settings: AppSettings) -> AppSettings:
        validated = AppSettings.model_validate(settings.model_dump(mode="json"))
        payload = validated.model_dump(mode="json")
        if self._strip_secrets_on_save:
            # 日历密码与模型 Key 同规则：**内存里有、磁盘上没有**。
            # 只在"外部托管"时剥离 —— 独立运行（没有 safeStorage）时硬剥会让
            # 用户填过的密码在下次保存时静默消失，而他会以为是密码填错了。
            payload.setdefault("calendar", {})["caldav_password"] = ""
        self._write_json(self._paths.settings_file, payload)
        if self._config is not None:
            self._config = self._config.model_copy(update={"settings": validated})
        return validated

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def _read_json(path) -> dict[str, Any]:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"配置文件不是合法 JSON: {exc}", detail=str(path)) from exc
        except OSError as exc:
            raise ConfigError(f"无法读取配置文件: {exc}", detail=str(path)) from exc
        if not isinstance(data, dict):
            raise ConfigError("配置文件顶层必须是对象", detail=str(path))
        return data

    # 配置文件里可能含明文 API Key（独立运行模式，见 save_models）。临时文件
    # 在替换前同样带着它，所以两者都用"仅所有者可读写"创建。
    _FILE_MODE = 0o600

    @classmethod
    def _write_json(cls, path, payload: dict[str, Any]) -> None:
        """原子写入：先写临时文件再替换，避免半截文件导致启动失败。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            # 用 os.open 而不是 open()：只有前者能在**创建时**就带上权限位。
            # open() 先按默认 umask 建文件、再 chmod 的话，中间有一个窗口期
            # 该文件是 644 —— 而它内容里可能正躺着一个 API Key。
            # （Windows 上权限位基本被忽略，但这里不影响语义：用户目录本身就已隔离。）
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, cls._FILE_MODE)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError as exc:
            raise ConfigError(f"无法写入配置文件: {exc}", detail=str(path)) from exc

    @property
    def paths(self) -> AppPaths:
        return self._paths

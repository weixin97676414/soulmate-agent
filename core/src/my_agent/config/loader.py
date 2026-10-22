








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

if TYPE_CHECKING:  
    
    
    from ..assistants.bootstrap import BuiltinAssistants

logger = logging.getLogger(__name__)


def _default_models() -> ModelsConfig:







    return ModelsConfig(default_model="", models=[])


class ConfigStore:


    def __init__(
        self,
        paths: AppPaths,
        *,
        manage_secrets: bool = False,
        builtin: BuiltinAssistants | None = None,
    ) -> None:
        self._paths = paths
        self._config: AppConfig | None = None
        
        
        self._strip_secrets_on_save = manage_secrets
        
        
        
        
        
        
        
        
        
        
        self._builtin = builtin

    
    
    
    def load(self, *, reload: bool = False) -> AppConfig:
        if self._config is not None and not reload:
            return self._config

        self._paths.ensure()
        settings = self._load_settings()
        models = self._load_models()
        mcp = self._load_mcp()
        assistants = self._load_assistants()

        
        
        
        
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
        except Exception as exc:  
            raise ConfigError(f"settings.json 校验失败: {exc}", detail=str(path)) from exc

        
        
        
        
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
        except Exception as exc:  
            raise ConfigError(f"models.json 校验失败: {exc}", detail=str(path)) from exc

        if not self._strip_secrets_on_save:
            
            
            
            self._apply_encrypted_keys(models)
        return models

    
    
    
    def _secrets_path(self):

        return self._paths.models_file.parent / "secrets.enc"

    def _remove_secrets_file(self) -> None:
        path = self._secrets_path()
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            
            
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






        keys = {spec.id: spec.api_key for spec in validated.models if spec.api_key}
        if not keys:
            
            
            
            
            
            
            self._remove_secrets_file()
            return

        blob = keystore.dump_keys(keys) if keystore.is_available() else None
        if blob is None:
            
            
            logger.warning(
                "当前以独立模式运行，且本机无法使用系统加密（DPAPI 仅 Windows 可用），"
                "API Key 将以**明文**写入 %s。若需要加密保护，请通过桌面客户端运行。",
                self._paths.models_file,
            )
            return

        path = self._secrets_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            
            
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
            
            
            
            
            
            
            
            
            
            
            from ..mcp.presets import build_sqlite_server

            config = McpConfig(servers=[build_sqlite_server(self._paths)])
            self._write_json(path, config.model_dump(mode="json"))
            logger.info("已生成默认 MCP 配置（含自带的 SQLite 只读查询）: %s", path)
            return config
        raw = self._read_json(path)
        try:
            return McpConfig.model_validate(raw)
        except Exception as exc:  
            raise ConfigError(f"mcp.json 校验失败: {exc}", detail=str(path)) from exc

    def _load_assistants(self) -> AssistantsConfig:










        path = self._paths.assistants_file
        if not path.exists():
            if self._builtin is None:
                
                config = AssistantsConfig()
                self._write_json(path, config.model_dump(mode="json"))
                logger.info("已生成空的助手配置（未注入内置搭子数据源）: %s", path)
                return config
            config = self._builtin.build_default_config()
            self._write_json(path, config.model_dump(mode="json"))
            logger.info("已生成内置助手预设: %s", path)
            
            
            
            
            
            self._seed_builtin_souls(config)
            
            
            
            self._align_persona_pack(config)
            return config
        raw = self._read_json(path)
        try:
            config = AssistantsConfig.model_validate(raw)
        except Exception as exc:  
            raise ConfigError(f"assistants.json 校验失败: {exc}", detail=str(path)) from exc

        if self._builtin is None:
            
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

        
        
        
        renamed = self._migrate_renamed_builtins(config)
        if renamed:
            self._write_json(path, config.model_dump(mode="json"))
            logger.info("已迁移出厂改名的内置搭子: %s", ", ".join(sorted(renamed)))

        
        
        
        if self._migrate_builtin_persona_texts(config):
            logger.info("已把内置搭子的出厂正文换成新说法")

        
        
        if self._migrate_builtin_temperatures(config):
            self._write_json(path, config.model_dump(mode="json"))

        
        
        
        if self._migrate_builtin_ids(config):
            self._write_json(path, config.model_dump(mode="json"))
            logger.info("已迁移内置搭子的 id: %s", path)

        
        
        
        
        if self._migrate_default_assistant(config):
            self._write_json(path, config.model_dump(mode="json"))
            logger.info("已迁移出厂默认搭子为: %s", config.default_assistant)

        
        
        
        
        if self._seed_added_builtins(config):
            self._write_json(path, config.model_dump(mode="json"))

        
        
        
        self._seed_builtin_souls(config)

        
        
        
        self._align_persona_pack(config)

        
        
        
        
        if self._enforce_locked_builtins(config):
            self._write_json(path, config.model_dump(mode="json"))
            logger.info("已把内置搭子的写死字段校正回出厂值")

        
        
        
        
        if self._patch_evolution_rules(config):
            logger.info("已给自建搭子补上「全员进化」初始规则")
        return config

    def _patch_evolution_rules(self, config: AssistantsConfig) -> bool:





















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
                
                logger.warning("给搭子 %s 补初始规则失败：%s", item.id, exc)
                continue
            changed = True
        return changed

    def _migrate_default_assistant(self, config: AssistantsConfig) -> bool:




























        if config.default_assistant not in self._builtin.LEGACY_DEFAULT_ASSISTANT_IDS:
            return False
        target = next(
            (profile for profile in self._builtin.BUILTIN_ASSISTANTS if profile.id == self._builtin.DEFAULT_ASSISTANT_ID),
            None,
        )
        if target is None:
            
            logger.warning("默认搭子 %s 不在预设表里，跳过迁移", self._builtin.DEFAULT_ASSISTANT_ID)
            return False
        if config.get(target.id) is None:
            config.upsert(target.model_copy(deep=True))
            logger.info("已补种新的默认搭子: %s", target.id)
        config.default_assistant = target.id
        return True

    def _migrate_renamed_builtins(self, config: AssistantsConfig) -> set[str]:















        current_by_id = {profile.id: profile for profile in self._builtin.BUILTIN_ASSISTANTS}
        migrated: set[str] = set()

        for item in config.assistants:
            if not item.builtin:
                continue
            old = self._builtin.RENAMED_BUILTINS.get(item.id)
            if not old:
                continue
            
            
            
            
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
                
                on_disk = ""
            except OSError as exc:
                logger.warning("读取内置搭子 SOUL 失败 %s: %s", item.id, exc)
                on_disk = ""
            if on_disk == old["soul"]:
                
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

    def _migrate_builtin_persona_texts(self, config: AssistantsConfig) -> set[str]:















        table = self._builtin.PERSONA_TEXT_MIGRATIONS
        if not table:
            return set()
        changed: set[str] = set()
        for item in config.assistants:
            if not item.builtin:
                continue
            old_texts = table.get(item.id)
            if not old_texts:
                continue
            directory = self._builtin.assistant_dir(self._paths, item.id)
            for file_name in (self._builtin.SOUL_FILE, self._builtin.IDENTITY_FILE):
                old_text = old_texts.get(file_name)
                if not old_text:
                    continue
                target = directory / file_name
                try:
                    on_disk = target.read_text(encoding="utf-8")
                except FileNotFoundError:
                    
                    continue
                except OSError as exc:
                    logger.warning("读取内置搭子 %s 的 %s 失败: %s", item.id, file_name, exc)
                    continue
                if on_disk != old_text:
                    
                    continue
                fresh = self._builtin.FACTORY_TEXTS.get(file_name, {}).get(item.id)
                if not fresh:
                    continue
                try:
                    target.write_text(fresh, encoding="utf-8")
                    changed.add(item.id)
                    logger.info("已更新内置搭子 %s 的出厂正文: %s", item.id, file_name)
                except OSError as exc:
                    logger.warning("更新内置搭子 %s 的 %s 失败: %s", item.id, file_name, exc)
        return changed

    
    
    
    
    _TEMPERATURE_MIGRATIONS: dict[str, tuple[float, float]] = {
        "LoveBuddy": (0.85, 0.5),
        "RelationBuddy": (0.7, 0.4),
        "soulmate": (0.8, 0.7),
    }

    def _migrate_builtin_temperatures(self, config: AssistantsConfig) -> bool:

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

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    _PERSONA_PACK_MARKER = ".persona-pack-aligned"
    _PERSONA_PACK_VERSION = "4"

    
    
    
    _ADDED_BUILTINS_MARKER = ".added-builtins"

    def _seed_added_builtins(self, config: AssistantsConfig) -> bool:















        ids = tuple(self._builtin.ADDED_BUILTIN_IDS)
        if not ids:
            return False
        version = ",".join(ids)
        marker = self._paths.data_dir / self._ADDED_BUILTINS_MARKER
        if marker.is_file():
            try:
                if marker.read_text(encoding="utf-8").strip() == version:
                    return False
            except OSError as exc:
                
                logger.warning("读取内置搭子补种标记失败（按未补过处理）：%s", exc)

        changed = False
        for profile in self._builtin.BUILTIN_ASSISTANTS:
            if profile.id not in ids:
                continue
            if config.get(profile.id) is not None:
                continue
            config.upsert(profile.model_copy(deep=True))
            changed = True
            logger.info("已补种新增的内置搭子: %s", profile.id)

        try:
            marker.write_text(f"{version}\n", encoding="utf-8")
        except OSError as exc:
            
            logger.error("写入内置搭子补种标记失败（下次启动会重新补种）：%s", exc)
        return changed

    def _align_persona_pack(self, config: AssistantsConfig) -> bool:




















        marker = self._paths.data_dir / self._PERSONA_PACK_MARKER
        if marker.is_file():
            try:
                if marker.read_text(encoding="utf-8").strip() == self._PERSONA_PACK_VERSION:
                    return False
            except OSError as exc:
                
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
            
            
            logger.error("写入人格包对齐标记失败（下次启动会重新对齐一遍）：%s", exc)
        return changed

    @staticmethod
    def _seed_or_patch_user_file(target: Any, factory: str) -> bool:






        try:
            if not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(factory, encoding="utf-8")
                logger.info("已播种 USER 模板：%s", target.parent.name)
                return True

            current = target.read_text(encoding="utf-8")
            if "用户性别" in current:
                return False  

            
            
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

    
    
    
    def _migrate_builtin_ids(self, config: AssistantsConfig) -> bool:













        migrated: list[str] = []
        for profile in config.assistants:
            new_id = self._builtin.RENAMED_BUILTIN_IDS.get(profile.id)
            if not new_id or not profile.builtin:
                continue
            if any(item.id == new_id for item in config.assistants):
                
                
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
            
            if temp.exists() and not source.exists():
                try:
                    temp.rename(source)
                except OSError:
                    pass

    
    
    
    def load_groups(self) -> GroupsConfig:





        path = self._paths.groups_file
        if not path.exists():
            config = GroupsConfig(groups=[])
            self._write_json(path, config.model_dump(mode="json"))
            return config
        raw = self._read_json(path)
        try:
            config = GroupsConfig.model_validate(raw)
        except Exception as exc:  
            logger.error("groups.json 校验失败，已忽略该文件: %s", exc)
            return GroupsConfig(groups=[])

        
        
        
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

    
    
    
    def save_assistants(self, config: AssistantsConfig) -> AssistantsConfig:
        validated = AssistantsConfig.model_validate(config.model_dump(mode="json"))
        self._write_json(self._paths.assistants_file, validated.model_dump(mode="json"))
        if self._config is not None:
            self._config = self._config.model_copy(update={"assistants": validated})
        return validated

    def save_mcp(self, config: McpConfig) -> McpConfig:

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






        path = self._paths.custom_skills_file
        if not path.exists():
            config = CustomSkillsConfig(skills=[])
            self._write_json(path, config.model_dump(mode="json"))
            return config
        raw = self._read_json(path)
        try:
            return CustomSkillsConfig.model_validate(raw)
        except Exception as exc:  
            logger.error("custom_skills.json 校验失败，已忽略该文件: %s", exc)
            return CustomSkillsConfig(skills=[])

    def save_custom_skills(self, config: CustomSkillsConfig) -> CustomSkillsConfig:
        validated = CustomSkillsConfig.model_validate(config.model_dump(mode="json"))
        self._write_json(self._paths.custom_skills_file, validated.model_dump(mode="json"))
        return validated

    def save_models(self, models: ModelsConfig) -> ModelsConfig:






        validated = ModelsConfig.model_validate(models.model_dump(mode="json"))
        payload = validated.model_dump(mode="json")
        if self._strip_secrets_on_save:
            for spec in payload.get("models", []):
                spec["api_key"] = ""
        else:
            
            
            self._save_keys_encrypted_or_warn(validated, payload)
        self._write_json(self._paths.models_file, payload)
        if self._config is not None:
            self._config = self._config.model_copy(update={"models": validated})
        return validated

    def save_settings(self, settings: AppSettings) -> AppSettings:
        validated = AppSettings.model_validate(settings.model_dump(mode="json"))
        payload = validated.model_dump(mode="json")
        if self._strip_secrets_on_save:
            
            
            
            payload.setdefault("calendar", {})["caldav_password"] = ""
        self._write_json(self._paths.settings_file, payload)
        if self._config is not None:
            self._config = self._config.model_copy(update={"settings": validated})
        return validated

    
    
    
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

    
    
    _FILE_MODE = 0o600

    @classmethod
    def _write_json(cls, path, payload: dict[str, Any]) -> None:

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            
            
            
            
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, cls._FILE_MODE)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError as exc:
            raise ConfigError(f"无法写入配置文件: {exc}", detail=str(path)) from exc

    @property
    def paths(self) -> AppPaths:
        return self._paths

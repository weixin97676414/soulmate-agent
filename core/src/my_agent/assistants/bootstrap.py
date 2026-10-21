






























from __future__ import annotations

from typing import Any

from . import evolution, locked_builtins, persona
from .presets import (
    ADDED_BUILTIN_IDS,
    BUILTIN_ASSISTANTS,
    BUILTIN_IDENTITIES,
    BUILTIN_RULES,
    BUILTIN_SOULS,
    BUILTIN_USERS,
    DEFAULT_ASSISTANT_ID,
    LEGACY_DEFAULT_ASSISTANT_IDS,
    PERSONA_TEXT_MIGRATIONS,
    REMOVED_BUILTIN_IDS,
    RENAMED_BUILTIN_IDS,
    RENAMED_BUILTINS,
    builtin_config,
)


class BuiltinAssistants:






    
    ADDED_BUILTIN_IDS = ADDED_BUILTIN_IDS
    DEFAULT_ASSISTANT_ID = DEFAULT_ASSISTANT_ID
    REMOVED_BUILTIN_IDS = REMOVED_BUILTIN_IDS
    RENAMED_BUILTIN_IDS = RENAMED_BUILTIN_IDS
    RENAMED_BUILTINS = RENAMED_BUILTINS
    
    PERSONA_TEXT_MIGRATIONS = PERSONA_TEXT_MIGRATIONS
    LEGACY_DEFAULT_ASSISTANT_IDS = LEGACY_DEFAULT_ASSISTANT_IDS
    BUILTIN_ASSISTANTS = BUILTIN_ASSISTANTS
    BUILTIN_SOULS = BUILTIN_SOULS
    BUILTIN_IDENTITIES = BUILTIN_IDENTITIES
    BUILTIN_RULES = BUILTIN_RULES
    BUILTIN_USERS = BUILTIN_USERS

    
    SOUL_FILE = persona.SOUL_FILE
    IDENTITY_FILE = persona.IDENTITY_FILE
    RULES_FILE = persona.RULES_FILE
    USER_FILE = persona.USER_FILE

    
    def build_default_config(self) -> Any:

        return builtin_config()

    
    def read_file(self, *args: Any, **kwargs: Any) -> Any:
        return persona.read_file(*args, **kwargs)

    def write_file(self, *args: Any, **kwargs: Any) -> Any:
        return persona.write_file(*args, **kwargs)

    def assistant_dir(self, *args: Any, **kwargs: Any) -> Any:
        return persona.assistant_dir(*args, **kwargs)

    
    def is_locked(self, *args: Any, **kwargs: Any) -> Any:
        return locked_builtins.is_locked(*args, **kwargs)

    def factory_text(self, *args: Any, **kwargs: Any) -> Any:
        return locked_builtins.factory_text(*args, **kwargs)

    def restore_factory_fields(self, *args: Any, **kwargs: Any) -> Any:
        return locked_builtins.restore_factory_fields(*args, **kwargs)

    @property
    def FACTORY_TEXTS(self) -> Any:  
        return locked_builtins.FACTORY_TEXTS

    @property
    def LOCKED_PERSONA_FILES(self) -> Any:  
        return locked_builtins.LOCKED_PERSONA_FILES

    
    def with_evolution_rule(self, *args: Any, **kwargs: Any) -> Any:
        return evolution.with_evolution_rule(*args, **kwargs)

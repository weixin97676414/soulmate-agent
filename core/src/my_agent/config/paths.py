























from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

APP_DIR_NAME = "Soulmate Agent"



LEGACY_APP_DIR_NAMES = ("Soulmate", "AgentDesktop")

LEGACY_APP_DIR_NAME = LEGACY_APP_DIR_NAMES[0]
ENV_DATA_DIR = "AGENT_DATA_DIR"


def default_data_dir() -> Path:

    override = os.environ.get(ENV_DATA_DIR)
    if override:
        return Path(override).expanduser().resolve()

    appdata = os.environ.get("APPDATA")
    if appdata:
        root = Path(appdata) / APP_DIR_NAME
        _migrate_legacy_dir(root)
        return root
    
    return Path.home() / f".{APP_DIR_NAME.lower()}"


def _migrate_legacy_dir(target: Path) -> None:






    appdata = target.parent
    for legacy_name in LEGACY_APP_DIR_NAMES:
        legacy = appdata / legacy_name
        if legacy == target or target.exists() or not legacy.exists():
            continue
        try:
            legacy.rename(target)
        except OSError as exc:
            logger.warning("旧数据目录 %s 迁移失败，继续使用新目录：%s", legacy, exc)
            return
        logger.info("已把旧数据目录 %s 迁移到 %s", legacy, target)
        return


@dataclass(frozen=True)
class AppPaths:


    root: Path

    @classmethod
    def resolve(cls, root: str | os.PathLike[str] | None = None) -> AppPaths:
        return cls(Path(root).expanduser().resolve() if root else default_data_dir())

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def workspace_dir(self) -> Path:
        return self.root / "workspace"

    @property
    def artifacts_dir(self) -> Path:
        return self.root / "artifacts"

    @property
    def skills_dir(self) -> Path:





        return self.root / "skills"

    @property
    def skills_inbox_dir(self) -> Path:






        return self.skills_dir / "inbox"

    @property
    def models_dir(self) -> Path:













        return self.root / "models"

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.json"

    @property
    def models_file(self) -> Path:
        return self.config_dir / "models.json"

    @property
    def mcp_file(self) -> Path:
        return self.config_dir / "mcp.json"

    @property
    def assistants_file(self) -> Path:
        return self.config_dir / "assistants.json"

    @property
    def custom_skills_file(self) -> Path:
        return self.config_dir / "custom_skills.json"

    @property
    def groups_file(self) -> Path:
        return self.config_dir / "groups.json"

    @property
    def db_file(self) -> Path:
        return self.data_dir / "agent.db"

    def ensure(self) -> AppPaths:

        for path in (
            self.root,
            self.config_dir,
            self.data_dir,
            self.logs_dir,
            self.workspace_dir,
            self.artifacts_dir,
            self.skills_dir,
            self.skills_inbox_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return self

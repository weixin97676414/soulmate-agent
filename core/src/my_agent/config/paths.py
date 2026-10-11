"""应用路径解析。

客户端场景下所有用户数据统一落在 ``%APPDATA%/Soulmate Agent/``：

    Soulmate Agent/
    ├── config/           settings.json / models.json / mcp.json（可由图形界面读写）
    ├── data/             agent.db（SQLite）、会话与审计
    ├── logs/             结构化日志（按天切分）
    ├── workspace/        用户上传的附件与 Agent 操作的文件（白名单目录）
    └── artifacts/        Skill 产出的图表 / 文档 / 表格

开发模式下可通过环境变量 ``AGENT_DATA_DIR`` 覆盖，测试时用临时目录。

## 改名与迁移

应用 0.1.18 从 ``Soulmate`` 改名为 ``Soulmate Agent``，数据目录跟着变。
**客户端（Electron）那边负责把旧目录搬过来**（见
``desktop/electron/main.ts`` 的 migrateLegacyUserData）—— 不搬的话用户原来的
配置、密钥与会话会看起来"凭空消失"。

下面这份 ``LEGACY_APP_DIR_NAMES`` 是给**独立运行**（CLI、开发调试）准备的：
那条路径没有 Electron，没人替它搬。两边共用同一份"旧名字清单"。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

APP_DIR_NAME = "Soulmate Agent"
# 改名前的目录名，**最近的排在最前**：
# - Soulmate：0.1.17 及更早用的名字；
# - AgentDesktop：那之前用的名字。
LEGACY_APP_DIR_NAMES = ("Soulmate", "AgentDesktop")
#: 兼容旧引用（历史上只有这一个名字）
LEGACY_APP_DIR_NAME = LEGACY_APP_DIR_NAMES[0]
ENV_DATA_DIR = "AGENT_DATA_DIR"


def default_data_dir() -> Path:
    """返回平台默认的用户数据根目录（必要时先把旧目录搬过来）。"""
    override = os.environ.get(ENV_DATA_DIR)
    if override:
        return Path(override).expanduser().resolve()

    appdata = os.environ.get("APPDATA")
    if appdata:
        root = Path(appdata) / APP_DIR_NAME
        _migrate_legacy_dir(root)
        return root
    # 非 Windows 或环境异常时的兜底
    return Path.home() / f".{APP_DIR_NAME.lower()}"


def _migrate_legacy_dir(target: Path) -> None:
    """独立运行时把旧名字的数据目录搬过来（失败只记日志，绝不阻断启动）。

    三条与 Electron 侧一致的语义：新目录已存在则**不动**（避免两次启动把两份
    目录搅在一起）、旧目录不存在就跳过、**搬不动就继续用新目录**（一个移动失败
    不该让应用起不来 —— 那种情况下"空着启动"比"启动失败"好得多）。
    """
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
    """集中管理各子目录，避免路径字符串在代码里散落。"""

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
        """技能包落盘目录（``skills/<技能 id>/``）。

        与 ``workspace``（用户文件）分开：技能包是**应用自己装的东西**，
        放进工作区会让"清空工作区"顺手把已安装技能的辅助文件删掉。
        """
        return self.root / "skills"

    @property
    def skills_inbox_dir(self) -> Path:
        """技能**投放区**：用户把技能文件夹/文件丢进来，应用扫描接入。

        与解包出来的技能目录并列，但**不能被当成技能** —— 否则扫描会把应用
        自己解出来的包再导一遍，每次启动多一条（保留名见 ``skill/install.py``）。
        界面上「打开技能文件夹」打开的也是它。
        """
        return self.skills_dir / "inbox"

    @property
    def models_dir(self) -> Path:
        """本地模型落盘目录（``models/<模型名>/``）。

        ⚠️ 2026-10-08 新增：语音与嵌入模型**改为用户按需下载**（不再随安装包分发），
        下到这里。放在**用户数据目录**而不是程序目录，有三个理由：
        - 安装目录在 Windows 上默认不可写（Program Files / 受控目录），写进去会失败；
        - 升级/重装客户端不该把用户已经下好的 800MB 模型再抹一遍；
        - "清空用户数据"与"删模型"应该是**两件可分开的事**（见下面 ``models/`` 不进 skills）。

        子目录名与随包时代的 ``core/models/<模型名>`` **保持一致**，
        这样两个时代的路径常量（``VOICE_SUBDIR`` / ``MODEL_DIRNAME``）一个都不用改。
        读取顺序见 ``voice/models.py::candidate_roots`` 与
        ``memory/local_embedding.py::candidate_dirs`` —— 都是"用户目录优先、随包兜底"。
        """
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
        """创建全部目录（幂等）。"""
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

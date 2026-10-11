"""**用户给技能的密钥**的读取与校验。

## ⚠️ 它与 `config/secrets.py` 是两条**互不相干**的链路

| | `config/secrets.py` | 本模块 |
|---|---|---|
| 存什么 | 模型 API Key / MCP 环境变量 / 集成凭据（日历密码） | 用户经 `request_secret` 交给技能的东西（私钥、API Secret…） |
| 谁会用 | LLM 注册表、MCP 管理器、日历 | **只有** `http_request` / `http_fetch` 在发请求前 |
| 存在哪 | Electron 的 `secrets.bin`（三段式结构） | Electron 的 `skill-secrets.bin`（扁平 `名字 -> 值`） |
| 注入变量 | `AGENT_SECRETS_FILE` | `AGENT_SKILL_SECRETS_FILE` |

**刻意不复用、不合并、不互相 import**（产品要求：
"不要动我们现有的秘钥存储逻辑"）。理由不止是"少改动"——`secrets.bin` 的结构是
固定的三段式，它的 `normalize()` **只保留 `models` / `mcp` / `integrations`
三个顶层键，其余键会被静默丢弃**（见 `desktop/electron/secrets.ts`）。
往里塞第四种东西的后果是"存进去就没了、而且不报错"，是最难查的那类问题。

## 读取方式与 `secrets.py` 一致（这套是踩出来的）

Electron 把解密后的内容写进一个**临时文件**，把路径经环境变量传进来；本进程
**读完立即删除**该文件。不用环境变量直接传值，是因为环境变量会被子进程继承 ——
而本进程会 spawn MCP Server（`env={**os.environ, ...}`），密钥会直接漏给第三方进程。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: 传给 Python 的环境变量名。⚠️ 与 `secrets.py` 的 `ENV_SECRETS_FILE` **不同**——
#: 两条链路各有各的临时文件（见模块顶部对照表）。
ENV_SKILL_SECRETS_FILE = "AGENT_SKILL_SECRETS_FILE"

#: 名字的合法字符集。**唯一真相来源**是 `security/secret_ref.py::SECRET_NAME_PATTERN`
#: （占位符匹配用的就是它）。这里做的是"读进来时再过滤一遍"：
#: 文件由另一个进程写，不能假设它一定干净 —— 一个带 `}` 的名字会让占位符语法错乱。
_MAX_NAME_LEN = 64
_ALLOWED_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)


def is_valid_name(name: str) -> bool:
    """名字能不能拿来当引用名（与 ``secret_ref.SECRET_NAME_PATTERN`` 同一套规则）。"""
    if not name or len(name) > _MAX_NAME_LEN:
        return False
    return all(ch in _ALLOWED_CHARS for ch in name)


@dataclass
class SkillSecrets:
    """用户给技能的那批密钥（名字 -> 明文）。"""

    keys: dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.keys

    def get(self, name: str) -> str | None:
        return self.keys.get(name)

    def names(self) -> list[str]:
        """已保存的名字（**不含值**）—— 这是可以安全记日志的那种信息。"""
        return sorted(self.keys)

    def to_dict(self) -> dict[str, Any]:
        return {"keys": dict(self.keys)}


def parse_skill_secrets(raw: Any) -> SkillSecrets:
    """把外部传入的 JSON 收敛成 ``SkillSecrets``，脏数据一律忽略。

    输入来自另一个进程，不能假设它合法：宁可少注入几个名字，也不能因为格式问题
    让整个应用起不来（与 ``secrets.parse_secrets`` 同一个取舍）。**非法名字直接丢**
    —— 留着它只会在占位符替换时静默对不上。
    """
    if not isinstance(raw, dict):
        return SkillSecrets()

    # 兼容两种形态：`{"keys": {...}}`（当前）与裸的 `{name: value}`（早期格式）。
    # 兼容不是为了省事 —— 旧版 Electron 写出来的临时文件如果被新核心读到，
    # 用户会看到"我之前给的密钥怎么没了"，而且没有任何提示。
    source = raw.get("keys")
    if not isinstance(source, dict):
        source = raw

    keys: dict[str, str] = {}
    dropped: list[str] = []
    for name, value in source.items():
        if not isinstance(name, str) or not isinstance(value, str) or not value:
            continue
        if not is_valid_name(name):
            dropped.append(name[:32])
            continue
        keys[name] = value
    if dropped:
        # ⚠️ 只报**名字**，绝不报值（连截断的值都不报）
        logger.warning("忽略了 %s 个名字不合法的技能密钥：%s", len(dropped), dropped)
    return SkillSecrets(keys=keys)


def read_skill_secrets_file(path: str | Path | None) -> SkillSecrets | None:
    """读取用户密钥文件，**读取后立即删除**。

    **返回 ``None`` 表示「不由外部托管」**（没传路径）—— 与
    ``secrets.read_secrets_file`` 同一个约定：独立运行后端（开发调试、CLI）时
    没有 Electron 写这个文件，这时"没有密钥"和"密钥被托管但为空"是两件事。

    ⚠️ 日志里**只报名字个数**，绝不报内容。
    """
    if not path:
        return None

    file_path = Path(path)
    raw: Any = {}
    try:
        if file_path.is_file():
            raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # ValueError 必须显式列进来：非法 UTF-8 抛的是 UnicodeDecodeError，
        # 它是 ValueError 的子类、**不是** OSError。漏掉它会让进程直接起不来
        # （见 `secrets.read_secrets_file` 里同一段注释）。
        logger.warning("技能密钥文件读取失败，将按未提供处理: %s", exc)
    finally:
        try:
            file_path.unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover - 极端情况
            logger.warning("技能密钥文件删除失败: %s", exc)

    secrets = parse_skill_secrets(raw)
    logger.info("已注入 %s 个用户给技能的密钥（只记个数，不记内容）", len(secrets.keys))
    return secrets


__all__ = [
    "ENV_SKILL_SECRETS_FILE",
    "SkillSecrets",
    "is_valid_name",
    "parse_skill_secrets",
    "read_skill_secrets_file",
]

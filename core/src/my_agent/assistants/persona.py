"""助手的人格（SOUL）与记忆（MEMORY）文件。

## 为什么是文件，而不是再加几个数据库字段

用户要在助手的配置里**看到并编辑**它的人格与记忆。数据库里存的那份
（``AssistantProfile.system_prompt``）在界面上是一段文字，而向量库里那批记忆
**根本不可读**（是一堆数字）。

所以这两个东西做成**人能直接打开看、直接改的文件**，放在每个助手自己的目录下：

    <data>/assistants/<助手 id>/
    ├── SOUL.md     人格、价值观、说话方式
    └── MEMORY.md   这个助手记得的事

## 与既有两套记忆的关系（不要混淆）

- **短期记忆**（``memory/short_term.py``）：这次对话说了什么 + 摘要压缩。自动的。
- **长期记忆 / 知识库**（chromadb 向量库）：你喂进去的**大批资料**，按语义检索。
  机器存、机器查。
- **本模块的 MEMORY.md**：助手**主动记下来的、值得长期记住的少量事实**（偏好、
  习惯、约定）。人可读、可改。

三者互不替代：向量库适合"从一万段里找相关"，MEMORY.md 适合"就这么几条，每次都该知道"。

## 白名单是硬要求

文件名**只认白名单里的两个**。这里要是允许任意文件名，就等于把"往数据目录里
写任意文件"这个能力交出去（路径穿越 ``../`` 会写到别处）。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _atomic_write_text(target: Path, content: str) -> None:
    """原子写文本：先写同目录的临时文件，再 ``os.replace`` 换上去。

    ⚠️ 为什么必须原子（第 87 批，M-15）：这些文件（尤其 ``SOUL.md`` / ``IDENTITY.md``）
    会被拼进**每一轮**的 system 提示词（见 ``agents/persona.py::build_persona_section``），
    写一半崩溃会留下**截断的人格** —— 而下次启动会照常读它，
    用户只会觉得"搭子突然变了个样"，且没有任何报错。

    项目其它写盘点都是这么做的（``config/loader.py``、``memory/spill.py``、
    ``agent/scheduler.py``），这里以前是唯一一个裸 ``write_text``。
    同目录 + ``os.replace``：同一分区上它是原子操作（跨分区才会退化成复制）。
    """
    tmp = target.with_name(f".{target.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)

# 只认这四个名字。加新文件时必须显式加到这里 —— 顺带也决定了界面上显示哪几项。
SOUL_FILE = "SOUL.md"
IDENTITY_FILE = "IDENTITY.md"
RULES_FILE = "RULES.md"
MEMORY_FILE = "MEMORY.md"
USER_FILE = "USER.md"
ALLOWED_FILES: tuple[str, ...] = (SOUL_FILE, IDENTITY_FILE, RULES_FILE, MEMORY_FILE, USER_FILE)

# 单个文件的大小上限。它们是**每次对话都可能注入提示词**的内容，
# 不设上限等于让人（或模型）用一个巨大文件把上下文撑爆。
MAX_FILE_BYTES = 32_000

DEFAULT_SOUL_HINT = (
    "# SOUL\n\n"
    "这里写这个助手的人格：它怎么看自己、怎么说话、在意什么。\n"
)

# 助手身份（用户要求单独成文）：名字、角色定位、自我介绍 —— 它"是谁"。
# 与 SOUL 的分工：SOUL 是"性格"，IDENTITY 是"身份卡片"。
DEFAULT_IDENTITY_HINT = (
    "# IDENTITY · 助手身份\n\n"
    "这里写这个助手的身份：名字、定位、自我介绍。\n"
)

# 「系统提示词」的文件化（用户要求）：过去它挤在表单里，内容多了显示不下，
# 而且助手自己改不了。现在与人格/记忆同形式 —— 文件、可查看、AI 可改。
DEFAULT_RULES_HINT = (
    "# RULES · 工作逻辑与规则\n\n"
    "这里写这个助手的工作方式与规矩：先做什么后做什么、什么必须确认、\n"
    "回答要什么风格。助手也可以按你的要求修改（每次修改都会先让你确认）。\n"
)

DEFAULT_MEMORY_HINT = (
    "# MEMORY\n\n"
    "这里写这个助手记得的事：你的偏好、习惯、约定。\n"
    "助手也可以自己往这里补充（每次补充都会先让你确认）。\n"
)

# 对齐 openclaw 的 user.md：关于「用户是谁」的档案。
# 与 MEMORY 的分工 —— MEMORY 记的是"事"，USER.md 记的是"人"：
# 昵称、职业、长期偏好这类一以贯之的事实，助手每次都该知道。
DEFAULT_USER_HINT = (
    "# USER · 关于用户\n\n"
    "这里写关于用户本人的档案：怎么称呼、职业、长期偏好。\n"
    "助手也可以按你的要求往里补充（每次补充都会先让你确认）。\n"
)


def assistant_dir(paths: Any, assistant_id: str) -> Path:
    """该助手的目录。id 已经过字符集校验（只允许字母数字 _-），不含路径分隔符。"""
    return Path(paths.data_dir) / "assistants" / assistant_id


def _resolve(paths: Any, assistant_id: str, name: str) -> Path:
    if name not in ALLOWED_FILES:
        raise ValueError(f"不支持的文件名：{name}")
    return assistant_dir(paths, assistant_id) / name


def read_file(paths: Any, assistant_id: str, name: str) -> str:
    """读一个文件；不存在返回空串（首次使用是常态，不该报错）。"""
    target = _resolve(paths, assistant_id, name)
    try:
        return target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        logger.warning("读取助手文件失败 %s/%s：%s", assistant_id, name, exc)
        return ""


def write_file(paths: Any, assistant_id: str, name: str, content: str) -> None:
    """写一个文件。超长直接拒绝 —— 它会被塞进提示词，太大等于让上下文爆掉。

    ## 这里也拦一道"内置搭子写死"（兜底，不是主防线）

    四位内置搭子的人格文件里**只有 RULES.md** 是写死的（修正：
    SOUL / IDENTITY 对齐一次后解锁，见 ``assistants/locked_builtins.py``）。
    主防线在各自的入口（HTTP 路由、搭子总管技能），但人格文件的写入口**不止一个**：
    设置页、``self_persona_update``、``team_update_assistant``、
    ``team_ensure_required_skills``…… 漏掉任何一个，模型就还有一条路能改掉
    "它不该改的那个人"。

    所以在这里再卡一次 —— 这是**唯一**的写盘函数，卡住它就卡住了所有路径。
    ⚠️ ``SOUL.md`` / ``IDENTITY.md`` / ``MEMORY.md`` / ``USER.md`` 都不在锁内：
    性格、身份、记忆与"关于用户的认识"必须继续能写，否则搭子就是一块不会成长的
    石头（用户明确要求）。

    循环导入说明：``locked_builtins`` 反向依赖本模块，所以这里**函数内**再导入。
    """
    from . import locked_builtins

    locked_builtins.ensure_persona_writable(assistant_id, name)

    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError(
            f"{name} 最多 {MAX_FILE_BYTES // 1000} KB，当前内容超出。"
            "它会被放进每次对话的提示词里，写太长会挤掉真正的对话。"
        )
    target = _resolve(paths, assistant_id, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(target, content)


def list_files(paths: Any, assistant_id: str) -> list[dict[str, Any]]:
    """列出该助手的文件（含内容，供界面直接展示与编辑）。"""
    items: list[dict[str, Any]] = []
    hints = {
        SOUL_FILE: DEFAULT_SOUL_HINT,
        IDENTITY_FILE: DEFAULT_IDENTITY_HINT,
        RULES_FILE: DEFAULT_RULES_HINT,
        MEMORY_FILE: DEFAULT_MEMORY_HINT,
        USER_FILE: DEFAULT_USER_HINT,
    }
    for name in ALLOWED_FILES:
        target = _resolve(paths, assistant_id, name)
        exists = target.is_file()
        items.append(
            {
                "name": name,
                "exists": exists,
                "size": target.stat().st_size if exists else 0,
                "content": read_file(paths, assistant_id, name),
                "hint": hints[name],
            }
        )
    return items


def build_persona_section(
    paths: Any, assistant_id: str, *, nickname: str = ""
) -> str:
    """把五个文件拼成一段可注入的文本；全部为空（且没有昵称）就返回空串。

    这一段由 ``engine.AgentConfig.persona`` 承接，最终并进**第一条** system
    （见 ``agent/engine.py`` 的 ``_system_prompt``）。

    ⚠️ 不要改成"另起一条 system 消息"：``ensure_system`` 每轮都会把第 0 位消息
    替换成 ``_system_prompt()`` 的结果，另起的那条会被静默抹掉。
    （摘要正是因此必须单独插入 —— 但人格不该走那条路。）

    ## 顺序（用户明确指定，勿再改）
    IDENTITY → SOUL → USER → MEMORY → RULES。
    身份与人格在最前、用户档案居中、记忆靠后、工作规则殿后。

    ## 昵称
    ``nickname`` 是助手在界面里的名字（``AssistantProfile.nickname``）。
    它**不落任何文件**、直接注入在最前 —— 否则用户改了昵称却要再去改
    IDENTITY.md 才能让 AI 知道"我叫什么"，问"你是谁"时会答成默认的 buddy 名。
    """
    if not assistant_id:
        return ""

    parts: list[str] = []
    soul = read_file(paths, assistant_id, SOUL_FILE).strip()
    identity = read_file(paths, assistant_id, IDENTITY_FILE).strip()
    rules = read_file(paths, assistant_id, RULES_FILE).strip()
    memory = read_file(paths, assistant_id, MEMORY_FILE).strip()
    user = read_file(paths, assistant_id, USER_FILE).strip()

    if nickname.strip():
        parts.append("## 你的名字\n" f"你叫「{nickname.strip()}」，用户会这样称呼你。")
    if identity:
        parts.append("## 你的身份（IDENTITY）\n" + identity)
    if soul:
        parts.append("## 你的人格（SOUL）\n" + soul)
    if user:
        parts.append("## 关于用户（USER）\n" + user)
    if memory:
        parts.append("## 你记得的事（MEMORY）\n" + memory)
    if rules:
        parts.append("## 你的工作逻辑与规则（RULES）\n" + rules)

    if not parts:
        return ""
    return "\n\n".join(parts)


__all__ = [
    "ALLOWED_FILES",
    "DEFAULT_IDENTITY_HINT",
    "DEFAULT_RULES_HINT",
    "DEFAULT_USER_HINT",
    "IDENTITY_FILE",
    "MAX_FILE_BYTES",
    "MEMORY_FILE",
    "RULES_FILE",
    "SOUL_FILE",
    "USER_FILE",
    "assistant_dir",
    "build_persona_section",
    "list_files",
    "read_file",
    "write_file",
]

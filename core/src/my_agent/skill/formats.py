"""技能包**格式识别层**：把"一坨文件"翻译成"这是什么格式的技能"。

## 为什么要单独一层

技能包来源五花八门，但"认格式"这件事和"落盘 / 下载 / 记账"是三件不相干的事。
混在一起写，格式规则就没法用单元测试单独钉住 —— 每种格式都要先造一个真实
文件系统、走一遍网络与落盘才能验，测试写不动，规则就会慢慢漂。

所以：**本模块只有纯函数与纯数据，不做任何 IO、不碰 Path、不发网络请求。**
输入是"包内相对路径 → 字节"的字典，输出是一组 :class:`SkillRoot`。

## 支持哪些格式（按识别优先级）

1. ``skill.json`` —— 声明式可执行技能（http / command），与老实现一致，优先级最高；
2. ``SKILL.md`` —— Claude/Anthropic Agent Skills：**每个含 SKILL.md 的目录各是一个技能**
   （老实现只取第一个，一个包里有多个技能时其余全丢），YAML frontmatter 的
   ``name`` / ``description`` / ``allowed-tools`` 会被抽出来；
3. 规则文件 —— ``AGENTS.md`` / ``CLAUDE.md`` / ``.cursorrules`` / ``*.mdc`` /
   ``.clinerules/`` 下的 md 与 txt（Cursor / Cline 生态）；
4. MCP 配置 —— 内容里含 ``mcpServers`` 的 ``.json`` / ``.yaml`` / ``.yml``；
5. 可执行脚本 —— ``.py/.sh/.js/.mjs/.cjs/.ps1/.bat/.cmd`` 各成一条命令技能；
6. 通用提示词 —— **仅当上面一条都没命中时**，散落的 ``.md`` / ``.txt`` 才当技能导入。

第 6 条的那个"仅当"很关键：否则一个 Claude Skill 包里的 ``references/*.md``
会被拆成一堆噪音技能，用户看到的技能列表瞬间失控。

## 一个包可以出多个技能 —— 但落盘不能重复

每条 :class:`SkillRoot` 都记着自己"在包里的哪棵子树"（``root``）或"只要哪几个文件"
（``only_files``）。落盘时按这个范围写，多技能包才不会把整包重落 N 遍、
也不会让两个技能互相覆盖对方的文件。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

# ``(包内相对路径, 内容)``。路径一律 ``/`` 分隔、已剥掉公共根目录。
Member = tuple[str, bytes]

# 字段长度上限与 ``schemas.CustomSkillDef`` 保持一致（name 48 / description 600）。
# 超了要**如实记进 note**，不能静默截断（这个项目最不能接受静默降级）。
MAX_NAME_CHARS = 48
MAX_DESCRIPTION_CHARS = 600

SKILL_FILE = "SKILL.md"
SKILL_JSON = "skill.json"

# 明确命名的规则文件：文件名（小写）→ 来源格式标识
RULE_FILE_FORMATS: dict[str, str] = {
    "agents.md": "agents-md",
    "claude.md": "agents-md",
    "claude.local.md": "agents-md",
    ".cursorrules": "cursorrules",
    "cursorrules": "cursorrules",
}

# 可执行脚本后缀 → 解释器标识（界面上显示"需要什么才能跑"）
SCRIPT_SUFFIXES: dict[str, str] = {
    ".py": "python",
    ".sh": "bash",
    ".js": "node",
    ".mjs": "node",
    ".cjs": "node",
    ".ps1": "powershell",
    ".bat": "cmd",
    ".cmd": "cmd",
}

# 通用提示词文档：**只在包里没有任何正规技能包结构时**才当技能导入，
# 否则一个 Claude Skill 里 references/*.md 会被拆成一堆噪音技能。
#
# ⚠️ 刻意**不收 .txt**：几乎任何一个压缩包里都有 readme.txt / license.txt，
# 把它们当技能导入，用户会看到一堆莫名其妙的技能卡 —— 而"传错包"时报一句
# "包里没有找到技能"比生成一个垃圾技能更容易看懂。
PLAIN_DOC_SUFFIXES = {".md"}

MCP_KEY = "mcpServers"
MCP_KEYS = ("mcpServers", "mcp_servers")

# 导入结果里的人话标签。前端按 source_format 显示徽标，这里只给消息用。
FORMAT_LABELS: dict[str, str] = {
    "claude-skill": "Claude 技能",
    "skill-json": "声明式技能",
    "cursor-mdc": "Cursor 规则",
    "cursorrules": "Cursor 规则",
    "clinerules": "Cline 规则",
    "agents-md": "项目规则",
    "plain-md": "提示词文档",
    "mcp-json": "MCP 配置",
    "script": "脚本",
    "folder": "本机文件夹",
    "manual": "手动创建",
}


def format_label(source_format: str) -> str:
    """来源格式的人话名（认不出来就原样返回，方便排查）。"""
    return FORMAT_LABELS.get(source_format, source_format or "未知来源")


@dataclass(frozen=True)
class SkillRoot:
    """从技能包里认出来的**一个技能根**。

    ``root`` 与 ``only_files`` 二选一表达"这个技能在包里占哪些文件"：
    - ``only_files`` 非空 → 落盘时只落这几个文件（规则文件、脚本）；
    - 否则 → 落 ``root`` 这棵子树（``""`` 表示包根）。
    """

    root: str
    kind: str  # instruction | command | mcp | json
    name: str
    description: str
    source_format: str
    instructions: str = ""
    allowed_tools: tuple[str, ...] = ()
    scripts: tuple[str, ...] = ()
    mcp_servers: tuple[dict[str, Any], ...] = ()
    only_files: tuple[str, ...] = ()
    note: str = ""
    #: **给用户看的名字**（正文一级标题，如「行程规划设计（精确到小时）」）。
    #:
    #: ⚠️ 与 ``name`` 是**两件事**，绝对不能合并：
    #: ``name`` 来自 frontmatter、经 ``package._root_id`` 的 ``slugify`` 派生出**技能 id**
    #: （也就是落盘目录名 ``skills/<id>/`` 与搭子档案里 ``enabled_skills`` 的值）。
    #: 把中文标题写回 ``name``，id 就会从 ``travel-itinerary-planning`` 变成一长串中文 slug ——
    #: 已落盘的目录对不上、用户勾过的技能集体失效。所以中文名只能放这里。
    #:
    #: 只收**含汉字**的标题（见 :func:`display_title`）：英文标题当显示名并不比
    #: frontmatter 的 name 更有用，那就保持原名，别拿标题去覆盖。
    #: 放在最后是因为 dataclass 的字段顺序约束（有默认值的不能排在没有默认值的前面）。
    title: str = ""


# --------------------------------------------------------------------------- #
# frontmatter（受限 YAML 子集）
# --------------------------------------------------------------------------- #
_FRONTMATTER_RE = re.compile(r"\A\ufeff?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_HEADING_RE = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def _scalar(raw: str) -> Any:
    """把一个 YAML 标量转成 Python 值（去引号、拆内联列表、识别布尔）。"""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_scalar(item) for item in inner.split(",") if item.strip()]
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    return value


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """拆出 frontmatter 与正文；没有 frontmatter 时返回 ``({}, 原文)``。

    ⚠️ **只支持受限 YAML 子集**：``key: value``、``key: [a, b]``、缩进 ``- item`` 列表。

    核心包里**没有 PyYAML**（见 ``core/pyproject.toml``，那是刻意的体积决定），
    而 frontmatter 是外部输入 —— 为三个键引一个 YAML 依赖不划算，手写一个
    只认这三种形状的解析器反而更可控：认不出来的行**跳过**，绝不猜。

    正文里保留 frontmatter 之外的**全部**内容（含空行），不做任何截断。
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    data: dict[str, Any] = {}
    current: str | None = None
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current:
            existing = data.get(current)
            if not isinstance(existing, list):
                existing = [] if existing in ("", None) else [existing]
                data[current] = existing
            existing.append(_scalar(stripped[2:]))
            continue
        if ":" not in stripped:
            continue  # 嵌套映射（metadata 之类）我们不需要，直接跳过
        key, _, raw = stripped.partition(":")
        current = key.strip().lower()
        data[current] = _scalar(raw)
    return data, text[match.end() :]


def first_heading(text: str) -> str:
    match = _HEADING_RE.search(text)
    return match.group(1).strip() if match else ""


def _has_han(text: str) -> bool:
    """含不含汉字。判断"这个标题能不能当中文显示名"就靠它。"""
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def display_title(text: str) -> str:
    """从正文里取**给用户看的名字**，取不到返回空串（由调用方回退到原名）。

    只认含汉字的（并截到 :data:`MAX_NAME_CHARS`）：这批第三方技能包的 frontmatter
    ``name`` 是英文 slug、正文标题才是中文（``# 行程规划设计（精确到小时）``）——
    这才是用户想在界面上看到的东西。反过来，一个包里标题本来就是英文时，
    拿它当显示名并不比原名更清楚，那就别覆盖。

    ⚠️ 与 :func:`_clean_name` 的分工：那个决定 **id**（不能动），这个只决定**显示**。
    """
    heading = first_heading(text)
    if not heading or not _has_han(heading):
        return ""
    return heading[:MAX_NAME_CHARS]


def summarize(text: str, limit: int = 200) -> str:
    """从正文抠一句简介 —— 给 ``description`` 兜底。

    这不是"截断内容"：``description`` 是给模型判断"这个技能什么时候适用"的一句话，
    空了整条技能会被 ``_validate_custom`` 拒收（指导型要求简介非空）。
    正文本身仍然**完整**注入，一个字不少。
    """
    for line in text.splitlines():
        cleaned = line.strip().lstrip("#").strip()
        if not cleaned:
            continue
        if cleaned.startswith((">", "|", "```")):
            continue
        return cleaned[:limit]
    return ""


# --------------------------------------------------------------------------- #
# 路径小工具（纯字符串运算，不碰文件系统）
# --------------------------------------------------------------------------- #
def _parent(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _suffix(path: str) -> str:
    base = _basename(path).lower()
    return f".{base.rsplit('.', 1)[-1]}" if "." in base[1:] else ""


def _inside_any(path: str, dirs: list[str]) -> bool:
    """``path`` 是否落在某个技能根之下（``""`` 表示包根，落谁都在它之下）。"""
    for root in dirs:
        if root == "":
            return True
        if path == root or path.startswith(root + "/"):
            return True
    return False


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8-sig", errors="replace")


def _string_list(value: Any) -> list[str]:
    """把 frontmatter 里可能写成各种形状的值统一成字符串列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


def _clean_name(value: Any, fallback: str) -> tuple[str, str]:
    text = str(value).strip() if value is not None else ""
    if not text:
        return fallback[:MAX_NAME_CHARS], ""
    if len(text) > MAX_NAME_CHARS:
        return text[:MAX_NAME_CHARS], f"名称过长已截到 {MAX_NAME_CHARS} 字"
    return text, ""


def _clean_description(value: Any) -> tuple[str, str]:
    text = str(value).strip() if value is not None else ""
    if len(text) > MAX_DESCRIPTION_CHARS:
        return text[:MAX_DESCRIPTION_CHARS], f"简介过长已截到 {MAX_DESCRIPTION_CHARS} 字"
    return text, ""


def _sorted_paths(files: dict[str, bytes], *, basename: str | None = None, suffix: str | None = None) -> list[str]:
    names = sorted(files)
    if basename is not None:
        names = [item for item in names if _basename(item).lower() == basename.lower()]
    if suffix is not None:
        names = [item for item in names if _suffix(item) == suffix]
    return names


def _scripts_under(files: dict[str, bytes], root: str) -> list[str]:
    """某个技能根子树内的可执行脚本（用于在该技能的说明里点出"脚本在哪"）。"""
    result = []
    for path in sorted(files):
        if _suffix(path) not in SCRIPT_SUFFIXES:
            continue
        parent = _parent(path)
        if root:
            if parent != root and not parent.startswith(f"{root}/"):
                continue
        result.append(path)
    return result


# --------------------------------------------------------------------------- #
# MCP 配置（json / yaml 的受限解析）
# --------------------------------------------------------------------------- #
def _yaml_scalar(raw: str) -> Any:
    value = raw.strip()
    if value in ("", "~", "null"):
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [_yaml_scalar(item) for item in inner.split(",")] if inner else []
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    return value


def _yaml_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append((len(raw) - len(raw.lstrip(" ")), stripped))
    return lines


def _yaml_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    """解析一处同缩进的块（映射或列表）。解析不动就返回 ``None`` 让上层放弃。"""
    if index >= len(lines):
        return None, index
    if lines[index][1].startswith("- "):
        items: list[Any] = []
        while index < len(lines) and lines[index][0] == indent and lines[index][1].startswith("- "):
            raw = lines[index][1][2:].strip()
            head, sep, rest = raw.partition(":")
            is_inline_map = bool(sep) and " " not in head and "/" not in head and head != ""
            if is_inline_map:
                item: dict[str, Any] = {head.strip(): _yaml_scalar(rest)}
                index += 1
                while index < len(lines) and lines[index][0] > indent:
                    key, sub_sep, sub_rest = lines[index][1].partition(":")
                    if not sub_sep:
                        break
                    item[key.strip()] = _yaml_scalar(sub_rest)
                    index += 1
                items.append(item)
            else:
                items.append(_yaml_scalar(raw))
                index += 1
        return items, index
    mapping: dict[str, Any] = {}
    while index < len(lines) and lines[index][0] == indent:
        key, sep, rest = lines[index][1].partition(":")
        if not sep:
            return None, index
        key = key.strip()
        rest = rest.strip()
        index += 1
        if rest:
            mapping[key] = _yaml_scalar(rest)
        elif index < len(lines) and lines[index][0] > indent:
            child, index = _yaml_block(lines, index, lines[index][0])
            if child is None:
                return None, index
            mapping[key] = child
        else:
            mapping[key] = None
    return mapping, index


def parse_minimal_yaml(text: str) -> Any:
    """极简 YAML：只支持映射 / 列表 / 标量，够读 MCP 配置。

    刻意不引 PyYAML。**解析不动就返回 ``None``**（含锚点、多文档、标签等高级语法）——
    宁可识别不出来，也不要造出一份结构错误的配置去连一堆不存在的服务。
    """
    lines = _yaml_lines(text)
    if not lines:
        return None
    value, index = _yaml_block(lines, 0, lines[0][0])
    if index != len(lines):
        return None
    return value


def extract_mcp_servers(text: str) -> list[dict[str, Any]]:
    """从 json / yaml 文本里抠出 ``mcpServers`` 结构（原始 server 字典列表）。

    **只认结构、不做校验与归一化**：真正的 transport 归一化与字段校验走 MCP 已有的
    导入实现（``mcp/manager.py`` 与 ``routes/mcp.py``）。这里再抄一遍必然与它漂移，
    而"粘贴能导入、包里导入报一堆字段错"是最难查的一类问题。
    """
    data: Any = None
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return []
    else:
        data = parse_minimal_yaml(text)
    if not isinstance(data, dict):
        return []
    raw = next((data[key] for key in MCP_KEYS if isinstance(data.get(key), dict)), None)
    if not isinstance(raw, dict):
        return []
    servers: list[dict[str, Any]] = []
    for name, item in raw.items():
        if isinstance(item, dict):
            servers.append({"name": str(name), **item})
        else:
            servers.append({"name": str(name)})
    return servers


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #
def identify_roots(files: dict[str, bytes], *, package_name: str) -> list[SkillRoot]:
    """从"包内路径 → 字节"里认出一组 :class:`SkillRoot`。

    识别顺序见模块开头；返回的顺序稳定（便于测试与会话内展示）。
    一条都没认出来时返回空列表，由调用方决定怎么报错（通常是"没有找到技能说明"）。
    """
    skill_dirs = [
        _parent(path) for path in files if _basename(path).lower() == SKILL_FILE.lower()
    ]
    roots: list[SkillRoot] = []

    # ① 声明式定义（可执行技能）。真正展开成 http/command 定义在 package.py 里 ——
    #    那一份解析逻辑必须与老实现共用，不能在这里重写。
    for path in _sorted_paths(files, basename=SKILL_JSON):
        roots.append(
            SkillRoot(
                root=_parent(path),
                kind="json",
                name=package_name,
                description="",
                source_format="skill-json",
            )
        )

    # ② Claude Agent Skills：每个含 SKILL.md 的目录各是一个技能
    for root in sorted(set(skill_dirs), key=lambda item: (item.count("/"), item)):
        path = f"{root}/SKILL.md" if root else "SKILL.md"
        body = _decode(files.get(path, b""))
        meta, content = split_frontmatter(body)
        notes: list[str] = []
        name, note = _clean_name(
            meta.get("name"), first_heading(content) or (_basename(root) or package_name)
        )
        # 显示名另算一份（见 `SkillRoot.title`）：**不参与 id 派生**，改它不会动 id
        title = display_title(content)
        if note:
            notes.append(note)
        description, note = _clean_description(meta.get("description"))
        if note:
            notes.append(note)
        if not description:
            description = summarize(content) or f"技能包 {name} 提供的操作指导"
        scripts = _scripts_under(files, root)
        roots.append(
            SkillRoot(
                root=root,
                kind="instruction",
                name=name,
                title=title,
                description=description,
                source_format="claude-skill",
                instructions=content.strip(),
                allowed_tools=tuple(
                    _string_list(meta.get("allowed-tools") or meta.get("allowed_tools"))
                ),
                scripts=tuple(scripts),
                note="；".join(item for item in notes if item),
            )
        )

    # ③ 规则文件（Cursor / Cline / 项目规则）
    for path in sorted(files):
        parent = _parent(path)
        if _inside_any(parent, skill_dirs):
            continue  # 技能根里的参考文档不是独立技能（否则 references/*.md 会炸出一堆卡）
        base = _basename(path).lower()
        if base in RULE_FILE_FORMATS:
            source = RULE_FILE_FORMATS[base]
        elif _suffix(path) == ".mdc":
            source = "cursor-mdc"
        elif "/.clinerules/" in f"/{path.lower()}" and _suffix(path) in (".md", ".txt"):
            source = "clinerules"
        else:
            continue
        content = _decode(files[path])
        meta, body = split_frontmatter(content)
        fallback = _basename(path).rsplit(".", 1)[0] or package_name
        name, note = _clean_name(meta.get("name"), first_heading(body) or fallback)
        description, description_note = _clean_description(meta.get("description"))
        if not description:
            description = summarize(body) or f"规则文件：{_basename(path)}"
        roots.append(
            SkillRoot(
                root=parent,
                kind="instruction",
                name=name,
                title=display_title(body),
                description=description,
                source_format=source,
                instructions=body.strip(),
                only_files=(path,),
                note="；".join(item for item in (note, description_note) if item),
            )
        )

    # ④ MCP 配置（内容里真的含 mcpServers 才算，光叫 mcp.json 不算）
    for path in sorted(files):
        if _suffix(path) not in (".json", ".yaml", ".yml"):
            continue
        if _basename(path).lower() == SKILL_JSON:
            continue
        servers = extract_mcp_servers(_decode(files[path]))
        if not servers:
            continue
        roots.append(
            SkillRoot(
                root=_parent(path),
                kind="mcp",
                name=_basename(path).rsplit(".", 1)[0] or package_name,
                description=f"来自 {package_name} 的 MCP 服务配置（{len(servers)} 个服务）",
                source_format="mcp-json",
                mcp_servers=tuple(servers),
                only_files=(path,),
            )
        )

    # ⑤ 可执行脚本：各成一条命令技能（产品要求"包内脚本作为可调用能力接进技能"，
    #    需用户确认才执行 —— 权限在路由层统一置 confirm）
    #
    # ⚠️ ：**技能根里的脚本不再单独成技能**（与 ③ 规则文件同款排除）。
    # 一个 Claude Skill 目录里的 `scripts/x.py` 是**这个技能的支撑文件** ——
    # ② 已经把它收进 `skill.scripts`（模型照样知道有它、正文也按它写的步骤调），
    # 再单独开一张技能卡只会让噪音爆炸：实测导入一个素材库时技能卡从 **259 张**
    # 涨到 **643 张**，多出来的 384 张全是名为 `gen_hint_words` 这类的孤立脚本 ——
    # 用户既不知道它属于哪个技能，也没有正文告诉模型该怎么用。
    # **纯脚本包**（整个包里没有 SKILL.md 的）不受影响，仍每个脚本一张卡。
    for path in sorted(files):
        interpreter = SCRIPT_SUFFIXES.get(_suffix(path))
        if not interpreter:
            continue
        if _inside_any(_parent(path), skill_dirs):
            continue
        stem = _basename(path).rsplit(".", 1)[0] or package_name
        roots.append(
            SkillRoot(
                root=_parent(path),
                kind="command",
                name=stem,
                description=f"{package_name} 包内脚本（{interpreter}）：{path}",
                source_format="script",
                scripts=(path,),
                only_files=(path,),
            )
        )

    # ⑥ 通用提示词文档：**只在上面一条都没命中时**才认，否则会制造噪音技能
    if not roots:
        for path in sorted(files):
            if _suffix(path) not in PLAIN_DOC_SUFFIXES:
                continue
            content = _decode(files[path])
            meta, body = split_frontmatter(content)
            fallback = _basename(path).rsplit(".", 1)[0] or package_name
            name, note = _clean_name(meta.get("name"), first_heading(body) or fallback)
            description, description_note = _clean_description(meta.get("description"))
            if not description:
                description = summarize(body) or f"{package_name} 提供的操作指导"
            roots.append(
                SkillRoot(
                    root=_parent(path),
                    kind="instruction",
                    name=name,
                    title=display_title(body),
                    description=description,
                    source_format="plain-md",
                    instructions=body.strip(),
                    only_files=(path,),
                    note="；".join(item for item in (note, description_note) if item),
                )
            )

    return _dedupe_names(roots)


def _dedupe_names(roots: list[SkillRoot]) -> list[SkillRoot]:
    """重名技能补上父目录名区分（``rules`` → ``a/rules``）。

    不区分的话，界面会出现两张同名卡、导入结果里两行一样的名字，
    而其中只有一张能删 —— 这种"看起来一样、行为不一样"的坑最难解释。
    """
    seen: dict[str, int] = {}
    result: list[SkillRoot] = []
    for item in roots:
        key = item.name
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 1:
            result.append(item)
            continue
        parent = item.root.rsplit("/", 1)[-1] if item.root else ""
        label = f"{parent}/{item.name}" if parent else f"{item.name} {seen[key]}"
        result.append(
            SkillRoot(
                root=item.root,
                kind=item.kind,
                name=label[:MAX_NAME_CHARS],
                # ⚠️ `title` 必须跟着带过来。这里是在**重建**一个 SkillRoot，漏掉哪个字段
                # 那个字段就静默丢了 —— 表现是"重名的那几个技能显示名退回英文 slug"，
                # 而同样的两个包换个名字不重名时又正常，极难复现。
                title=item.title,
                description=item.description,
                source_format=item.source_format,
                instructions=item.instructions,
                allowed_tools=item.allowed_tools,
                scripts=item.scripts,
                mcp_servers=item.mcp_servers,
                only_files=item.only_files,
                note=item.note,
            )
        )
    return result


__all__ = [
    "FORMAT_LABELS",
    "MAX_DESCRIPTION_CHARS",
    "MAX_NAME_CHARS",
    "MCP_KEYS",
    "Member",
    "RULE_FILE_FORMATS",
    "SCRIPT_SUFFIXES",
    "SKILL_FILE",
    "SKILL_JSON",
    "SkillRoot",
    "display_title",
    "extract_mcp_servers",
    "first_heading",
    "format_label",
    "identify_roots",
    "parse_minimal_yaml",
    "split_frontmatter",
    "summarize",
]

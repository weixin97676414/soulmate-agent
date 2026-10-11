"""技能包解析：把"包字节"变成一组 :class:`CustomSkillDef`。

## 三条路共用这一份解析（以前各写一份，迟早漂移）

- HTTP 路由（上传 / 从 URL 下载 / 从本机文件夹导入）；
- 内置技能 ``skill_package_install``（让模型按用户给的链接自己下载安装）；
- 启动时的技能文件夹扫描。

所以这里只做"解析"这一件事：取成员（``archive.py``）→ 认格式（``formats.py``）→
转成定义。落盘由 ``folder.py`` 负责，路由负责记账。

## 一个包可以出多个技能

``formats.identify_roots`` 已经按格式把包切成若干个技能根，这里逐个转成定义，
每条定义带上 ``package_root``（它在包里的子树）或 ``scripts``（只要那几个文件），
落盘时按这个范围写 —— 老实现"每条定义都把整包重落一遍"的缺陷就此消除。

## 命令型技能的命令模板**落盘后**才能确定

脚本技能要跑的是"落盘后的绝对路径"，而解析阶段还不知道最终目录（id 要去重）。
所以解析时把 ``command_template`` 留空，由 ``bind_script_commands`` 在落盘之后回填。
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config.schemas import CustomSkillDef
from .archive import MAX_PACKAGE_BYTES, PackageMembers, iter_members, members_from_directory
from .formats import SCRIPT_SUFFIXES, SkillRoot, identify_roots

logger = logging.getLogger(__name__)

__all__ = [
    "MAX_PACKAGE_BYTES",
    "ParsedPackage",
    "bind_script_commands",
    "parse_directory",
    "parse_members",
    "parse_package",
    "parse_payload",
    "resolve_command",
    "slugify",
]

# 脚本 → 解释器命令。``{path}`` 会被替换成落盘后的绝对路径。
#
# ⚠️ Windows 上的 python 有很多种装法（python / python3 / py 启动器），
# 所以这里先探测本机到底有哪个，一个都探测不到就**如实标注"暂不可用"**
# 而不是装上一个注定跑不起来的技能（静默降级是这个项目最不能接受的失败方式）。
INTERPRETER_COMMANDS: dict[str, list[str]] = {
    "python": ["python", "python3", "py"],
    "bash": ["bash", "sh"],
    "node": ["node"],
    "powershell": ["powershell", "pwsh"],
    "cmd": [],
}

SCRIPT_TEMPLATES: dict[str, str] = {
    "python": '"{exe}" "{path}"',
    "bash": '"{exe}" "{path}"',
    "node": '"{exe}" "{path}"',
    "powershell": '"{exe}" -NoProfile -File "{path}"',
    "cmd": 'cmd /c "{path}"',
}


def slugify(text: str, *, fallback: str = "skill") -> str:
    """中文也保留（``str.isalnum()`` 对汉字为真），只把空白与符号换成 ``-``。

    ``fallback``：**整串都被过滤光时**（比如名字是纯符号）拿什么当结果。

    ⚠️ 这个参数是末批（H-06）加的：``server/routes/groups.py`` 里原先有一份
    **逐字相同**的实现，只差兜底值（`"group"` vs 这里的 `"skill"`）。
    收敛成"一份实现 + 一个参数"，就不存在"改了一边忘了另一边"。
    """
    cleaned = "".join(ch if ch.isalnum() or ch in "_-" else "-" for ch in text.lower())
    return cleaned.strip("-") or fallback


def _root_id(root: SkillRoot) -> str:
    """技能 id：优先用**已去重过的显示名**（中文也合法），截到 64 字（字段上限）。"""
    return slugify(root.name)[:64] or "skill"


@dataclass
class ParsedPackage:
    """一次解析的完整结果。"""

    defs: list[CustomSkillDef] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    members: PackageMembers = field(default_factory=PackageMembers)
    roots: list[SkillRoot] = field(default_factory=list)
    # 没有参与识别、但会原样落盘的文件（界面上要如实说"这些也保留了"）
    unrecognized: list[str] = field(default_factory=list)

    @property
    def mcp_roots(self) -> list[SkillRoot]:
        return [item for item in self.roots if item.kind == "mcp"]


def _parse_skill_json(
    raw: bytes, results: list[dict[str, Any]], *, package_root: str
) -> list[CustomSkillDef]:
    """解析 ``skill.json``：支持单个定义或 ``{"skills": [...]}`` 批量。"""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        results.append({"name": "skill.json", "ok": False, "message": f"不是合法的 JSON：{exc}"})
        return []
    items = data.get("skills") if isinstance(data, dict) else data
    if not isinstance(items, list):
        items = [data]
    defs: list[CustomSkillDef] = []
    for index, item in enumerate(items):
        label = f"skill.json#{index + 1}" if len(items) > 1 else "skill.json"
        try:
            defn = CustomSkillDef.model_validate(item)
        except Exception as exc:  # noqa: BLE001
            results.append({"name": label, "ok": False, "message": f"字段校验失败：{exc}"})
            continue
        update: dict[str, Any] = {"package_root": package_root}
        if not defn.source_format:
            update["source_format"] = "skill-json"
        defs.append(defn.model_copy(update=update))
    return defs


def _covered(roots: list[SkillRoot], members: PackageMembers) -> set[str]:
    """哪些成员被某个技能根"认领"了（用于算出"没参与识别但已保留"的文件）。"""
    covered: set[str] = set()
    names = [name for name, _ in members.members]
    for root in roots:
        if root.only_files:
            covered.update(root.only_files)
            continue
        if root.kind == "json":
            path = f"{root.root}/skill.json" if root.root else "skill.json"
            covered.add(path)
            continue
        for name in names:
            if not root.root:
                covered.add(name)
            elif name == root.root or name.startswith(f"{root.root}/"):
                covered.add(name)
    return covered


def parse_payload(
    payload: bytes, package_name: str, *, filename: str = ""
) -> ParsedPackage:
    """解析一"包"字节（zip / tar.gz / 单文件自动识别）。

    包本身不可用（超大 / 没有可识别的技能）时抛 ``ValueError``，
    由调用方决定怎么呈现（路由转 4xx，技能转人话）。
    """
    packed = iter_members(payload, filename or f"{package_name}.zip")
    return parse_members(packed, package_name)


def parse_directory(root: Path, package_name: str = "") -> ParsedPackage:
    """解析本机文件夹（「导入文件夹」那条路）。"""
    packed = members_from_directory(root)
    return parse_members(packed, package_name or root.name)


def parse_members(packed: PackageMembers, package_name: str) -> ParsedPackage:
    """成员 → 技能定义。识别规则全在 ``formats.identify_roots``。"""
    files = packed.as_files()
    roots = identify_roots(files, package_name=package_name)
    if not roots:
        # 把包里的文件名列出来：用户传错包（比如传了安装包）时，
        # 一句"没找到技能"他无从判断，看到文件名就能立刻明白传错了什么。
        names = [name for name, _ in packed.members]
        shown = "、".join(names[:8]) or "（空包）"
        more = f" 等共 {len(names)} 个文件" if len(names) > 8 else ""
        raise ValueError(
            "这个包里没有找到任何技能：既没有 SKILL.md / skill.json，"
            "也没有规则文件（AGENTS.md、.cursorrules、*.mdc、.clinerules）、"
            f"Markdown 说明或可执行脚本。包内文件：{shown}{more}"
        )

    results: list[dict[str, Any]] = []
    defs: list[CustomSkillDef] = []
    for root in roots:
        if root.kind == "json":
            path = f"{root.root}/skill.json" if root.root else "skill.json"
            defs.extend(_parse_skill_json(files.get(path, b""), results, package_root=root.root))
            continue
        if root.kind == "mcp" or root.kind not in ("instruction", "command"):
            continue  # MCP 由调用方单独接入（见 ParsedPackage.mcp_roots）
        update: dict[str, Any] = {
            # ⚠️ `id` 由 `root.name` 派生（frontmatter 的英文 name → slug），**一行都不能动**：
            # 它是落盘目录 `skills/<id>/` 与搭子档案 `enabled_skills` 的值，改了就等于
            # 换了一个技能，已装目录与用户勾选会集体对不上。
            "id": _root_id(root),
            # 而**显示名**优先用正文一级标题（中文），见 `SkillRoot.title`。
            # 这两件事必须分开：`slugify` 是保留汉字的，把中文写回 `name` 会真的把 id 换掉。
            "name": root.title or root.name,
            "description": root.description,
            "kind": root.kind,
            "source_format": root.source_format,
            "package_root": root.root,
            "allowed_tools": list(root.allowed_tools),
            "scripts": list(root.scripts),
            "pack_files": list(root.only_files),
            "note": root.note,
        }
        if root.kind == "instruction":
            update["instructions"] = root.instructions
        else:
            # 命令模板要等落盘拿到最终绝对路径才能写（见模块开头）
            update["command_template"] = ""
            update["permission_level"] = "confirm"
        defs.append(CustomSkillDef(**update))

    covered = _covered(roots, packed)
    unrecognized = [name for name, _ in packed.members if name not in covered]

    return ParsedPackage(
        defs=defs, results=results, members=packed, roots=roots, unrecognized=unrecognized
    )


def parse_package(payload: bytes, package_name: str, *, filename: str = "") -> ParsedPackage:
    """``parse_payload`` 的别名（老调用点用的名字，保留以免两处漂移）。"""
    return parse_payload(payload, package_name, filename=filename)


def _probe(interpreter: str) -> str | None:
    """探测本机有没有这个解释器；没有返回 ``None``。"""
    for candidate in INTERPRETER_COMMANDS.get(interpreter, []):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def resolve_command(script_path: Path, interpreter: str) -> tuple[str, str]:
    """给出"跑这个脚本"的命令模板与提示。

    返回 ``(命令模板, 提示)``：探测不到解释器时命令为空、提示写明原因 ——
    技能**照样装、照样显示**，只是标注"现在跑不了"。
    """
    template = SCRIPT_TEMPLATES.get(interpreter, "")
    if not template:
        return f'"{script_path}"', ""
    if interpreter == "cmd":
        return template.format(path=script_path), ""
    executable = _probe(interpreter)
    if not executable:
        return (
            "",
            f"未找到 {interpreter} 解释器，这个脚本现在跑不了；"
            f"装好 {interpreter} 后重新扫描技能文件夹即可。",
        )
    return template.format(exe=executable, path=script_path), ""


def bind_script_commands(defn: CustomSkillDef, dest_dir: Path) -> CustomSkillDef:
    """落盘之后回填命令型技能的命令模板（脚本的绝对路径此时才确定）。

    解释器缺失时把原因合并进 ``note``（**不静默**），``command_template`` 留空 —— 
    执行时 ``_run_command`` 会给出"这个技能没有配置要执行的命令"，界面上还有 note 解释原因。
    """
    if defn.kind != "command" or not defn.scripts:
        return defn
    relative = defn.scripts[0]
    script_path = dest_dir / Path(relative).name
    interpreter = SCRIPT_SUFFIXES.get(Path(relative).suffix.lower(), "")
    command, note = resolve_command(script_path, interpreter)
    notes = [item for item in (defn.note, note) if item]
    return defn.model_copy(
        update={
            "command_template": command,
            "note": "；".join(notes),
            "permission_level": "confirm",
        }
    )

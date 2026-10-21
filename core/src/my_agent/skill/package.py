






















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








    cleaned = "".join(ch if ch.isalnum() or ch in "_-" else "-" for ch in text.lower())
    return cleaned.strip("-") or fallback


def _root_id(root: SkillRoot) -> str:

    return slugify(root.name)[:64] or "skill"


@dataclass
class ParsedPackage:


    defs: list[CustomSkillDef] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    members: PackageMembers = field(default_factory=PackageMembers)
    roots: list[SkillRoot] = field(default_factory=list)
    
    unrecognized: list[str] = field(default_factory=list)

    @property
    def mcp_roots(self) -> list[SkillRoot]:
        return [item for item in self.roots if item.kind == "mcp"]


def _parse_skill_json(
    raw: bytes, results: list[dict[str, Any]], *, package_root: str
) -> list[CustomSkillDef]:

    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:  
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
        except Exception as exc:  
            results.append({"name": label, "ok": False, "message": f"字段校验失败：{exc}"})
            continue
        update: dict[str, Any] = {"package_root": package_root}
        if not defn.source_format:
            update["source_format"] = "skill-json"
        defs.append(defn.model_copy(update=update))
    return defs


def _covered(roots: list[SkillRoot], members: PackageMembers) -> set[str]:

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





    packed = iter_members(payload, filename or f"{package_name}.zip")
    return parse_members(packed, package_name)


def parse_directory(root: Path, package_name: str = "") -> ParsedPackage:

    packed = members_from_directory(root)
    return parse_members(packed, package_name or root.name)


def parse_members(packed: PackageMembers, package_name: str) -> ParsedPackage:

    files = packed.as_files()
    roots = identify_roots(files, package_name=package_name)
    if not roots:
        
        
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
            continue  
        update: dict[str, Any] = {
            
            
            
            "id": _root_id(root),
            
            
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
            
            update["command_template"] = ""
            update["permission_level"] = "confirm"
        defs.append(CustomSkillDef(**update))

    covered = _covered(roots, packed)
    unrecognized = [name for name, _ in packed.members if name not in covered]

    return ParsedPackage(
        defs=defs, results=results, members=packed, roots=roots, unrecognized=unrecognized
    )


def parse_package(payload: bytes, package_name: str, *, filename: str = "") -> ParsedPackage:

    return parse_payload(payload, package_name, filename=filename)


def _probe(interpreter: str) -> str | None:

    for candidate in INTERPRETER_COMMANDS.get(interpreter, []):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def resolve_command(script_path: Path, interpreter: str) -> tuple[str, str]:





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

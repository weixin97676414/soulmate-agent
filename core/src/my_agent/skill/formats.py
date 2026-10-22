
































from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


Member = tuple[str, bytes]



MAX_NAME_CHARS = 48
MAX_DESCRIPTION_CHARS = 600

SKILL_FILE = "SKILL.md"
SKILL_JSON = "skill.json"


RULE_FILE_FORMATS: dict[str, str] = {
    "agents.md": "agents-md",
    "claude.md": "agents-md",
    "claude.local.md": "agents-md",
    ".cursorrules": "cursorrules",
    "cursorrules": "cursorrules",
}


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







PLAIN_DOC_SUFFIXES = {".md"}

MCP_KEY = "mcpServers"
MCP_KEYS = ("mcpServers", "mcp_servers")


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

    return FORMAT_LABELS.get(source_format, source_format or "未知来源")


@dataclass(frozen=True)
class SkillRoot:







    root: str
    kind: str  
    name: str
    description: str
    source_format: str
    instructions: str = ""
    allowed_tools: tuple[str, ...] = ()
    scripts: tuple[str, ...] = ()
    mcp_servers: tuple[dict[str, Any], ...] = ()
    only_files: tuple[str, ...] = ()
    note: str = ""
    
    
    
    
    
    
    
    
    
    
    
    title: str = ""





_FRONTMATTER_RE = re.compile(r"\A\ufeff?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_HEADING_RE = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def _scalar(raw: str) -> Any:

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
            continue  
        key, _, raw = stripped.partition(":")
        current = key.strip().lower()
        data[current] = _scalar(raw)
    return data, text[match.end() :]


def first_heading(text: str) -> str:
    match = _HEADING_RE.search(text)
    return match.group(1).strip() if match else ""


def _has_han(text: str) -> bool:

    return any("\u4e00" <= char <= "\u9fff" for char in text)


def display_title(text: str) -> str:









    heading = first_heading(text)
    if not heading or not _has_han(heading):
        return ""
    return heading[:MAX_NAME_CHARS]


def summarize(text: str, limit: int = 200) -> str:






    for line in text.splitlines():
        cleaned = line.strip().lstrip("#").strip()
        if not cleaned:
            continue
        if cleaned.startswith((">", "|", "```")):
            continue
        return cleaned[:limit]
    return ""





def _parent(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _suffix(path: str) -> str:
    base = _basename(path).lower()
    return f".{base.rsplit('.', 1)[-1]}" if "." in base[1:] else ""


def _inside_any(path: str, dirs: list[str]) -> bool:

    for root in dirs:
        if root == "":
            return True
        if path == root or path.startswith(root + "/"):
            return True
    return False


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8-sig", errors="replace")


def _string_list(value: Any) -> list[str]:

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





    lines = _yaml_lines(text)
    if not lines:
        return None
    value, index = _yaml_block(lines, 0, lines[0][0])
    if index != len(lines):
        return None
    return value


def extract_mcp_servers(text: str) -> list[dict[str, Any]]:






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





def identify_roots(files: dict[str, bytes], *, package_name: str) -> list[SkillRoot]:





    skill_dirs = [
        _parent(path) for path in files if _basename(path).lower() == SKILL_FILE.lower()
    ]
    roots: list[SkillRoot] = []

    
    
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

    
    for root in sorted(set(skill_dirs), key=lambda item: (item.count("/"), item)):
        path = f"{root}/SKILL.md" if root else "SKILL.md"
        body = _decode(files.get(path, b""))
        meta, content = split_frontmatter(body)
        notes: list[str] = []
        name, note = _clean_name(
            meta.get("name"), first_heading(content) or (_basename(root) or package_name)
        )
        
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

    
    for path in sorted(files):
        parent = _parent(path)
        if _inside_any(parent, skill_dirs):
            continue  
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

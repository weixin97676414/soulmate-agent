


















from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from ..config.schemas import CustomSkillDef
from ..errors import SkillExecutionError
from ..utils.http import async_client
from .base import BaseSkill, SkillContext, SkillMeta
from .decorator import skill

logger = logging.getLogger(__name__)










_BLOCKED_HOSTS = frozenset(
    {
        "169.254.169.254",
        "169.254.170.2",
        "100.100.100.200",
        "metadata.google.internal",
        "metadata",
        "metadata.goog",
    }
)


def _check_http_target(url: str) -> None:






    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").strip().lower()
    if host in _BLOCKED_HOSTS:
        raise SkillExecutionError(
            f"不允许把技能地址指向云元数据服务（{host}）。请填写真实的服务地址。"
        )


async def _run_http(defn: CustomSkillDef, values: dict[str, Any]) -> str:
    url = defn.render(values, defn.url).strip()
    if not url:
        raise SkillExecutionError("这个技能没有配置请求地址。")
    _check_http_target(url)

    headers = {key: defn.render(values, value) for key, value in defn.headers.items()}
    body = defn.render(values, defn.body_template) if defn.body_template else None

    try:
        async with async_client(timeout=defn.timeout, follow_redirects=False) as client:
            response = await client.request(
                defn.method, url, headers=headers, content=body if body else None
            )
    except httpx.TimeoutException as exc:
        raise SkillExecutionError(f"请求超时（>{defn.timeout}s）。") from exc
    except httpx.HTTPError as exc:
        raise SkillExecutionError(f"请求失败：{exc}") from exc

    text = response.text
    if response.status_code >= 400:
        
        from ..security.redact import redact

        raise SkillExecutionError(
            f"请求返回 HTTP {response.status_code}：{redact(text[:300])}"
        )
    return text or "(空响应)"


def _argv_for(defn: CustomSkillDef, values: dict[str, Any]) -> list[str]:







    return [item for item in defn.render_argv(values, defn.command_template) if item.strip()]


async def _run_command(defn: CustomSkillDef, values: dict[str, Any]) -> str:
    
    
    
    
    
    
    
    
    
    argv = _argv_for(defn, values)
    if not argv:
        raise SkillExecutionError("这个技能没有配置要执行的命令。")

    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        
        
        
        
        
        raise SkillExecutionError(
            f"命令启动失败：{exc}。"
            "（提示：命令不再经过系统 shell —— 模板的第一个词必须是**可执行程序**"
            "（如 python / node / 某个 .exe 的名字或完整路径），"
            "不要用 echo、dir 这类系统内置命令，也不要写 | 、> 、&& 这类 shell 语法。）"
        ) from exc

    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=defn.timeout)
    except TimeoutError as exc:
        process.kill()
        raise SkillExecutionError(f"命令执行超时（>{defn.timeout}s），已终止。") from exc

    output = stdout.decode("utf-8", errors="replace") if stdout else ""
    if process.returncode != 0:
        
        
        raise SkillExecutionError(
            f"命令退出码 {process.returncode}：{output or '(无输出)'}"
        )
    return output or "(命令执行完成，无输出)"


def build_custom_skill_class(defn: CustomSkillDef) -> type[BaseSkill]:


    class _CustomSkill(BaseSkill):
        async def run(self, ctx: Any, **params: Any) -> str:  
            if defn.kind == "http":
                return await _run_http(defn, params)
            return await _run_command(defn, params)

    _CustomSkill.meta = SkillMeta(
        name=defn.id,
        display_name=defn.name,
        description=defn.description or defn.name,
        parameters=defn.to_tool_schema(),
        category="custom",
        
        domain=defn.domain,
        permission_level=defn.permission_level,
        timeout=defn.timeout,
        enabled=defn.enabled,
        source="custom",
        
        
        
        
        command_preview=(
            (lambda values: " ".join(_argv_for(defn, values)))
            if defn.kind == "command"
            else None
        ),
    )
    _CustomSkill.__name__ = f"CustomSkill_{defn.id}"
    return _CustomSkill


def runtime_skills_dir(store: Any, skill_id: str) -> Path | None:

    root = getattr(store, "skills_root", None)
    if not root:
        return None
    return Path(root) / skill_id


class CustomSkillStore:










    def __init__(
        self,
        loader: Any,
        saver: Any,
        reloader: Any,
        skills_root: Any = None,
        skills: Any = None,
    ) -> None:
        self._load = loader
        self._save = saver
        self._reload = reloader
        self.skills_root = skills_root
        self.skills = skills

    def load(self) -> Any:
        return self._load()

    def save(self, config: Any) -> Any:
        saved = self._save(config)
        self._reload(saved)
        return saved

    @property
    def paths(self) -> Any:

        from types import SimpleNamespace

        root = Path(self.skills_root) if self.skills_root else None
        return SimpleNamespace(skills_dir=root)


class InstallParam(BaseModel):
    name: str = Field(..., description="参数名，只能字母数字下划线")
    description: str = Field("", description="这个参数是什么（给模型看）")
    required: bool = True


class CustomSkillInstallParams(BaseModel):
    name: str = Field(..., min_length=1, description="技能显示名")
    description: str = Field(..., min_length=1, description="什么时候该用它（会原样给模型）")
    kind: str = Field("http", description="http 或 command")
    url: str = Field("", description="HTTP 技能的请求地址，可含 {参数名}")
    method: str = Field("GET", description="GET/POST/PUT/DELETE")
    command_template: str = Field("", description="命令技能的要执行命令")
    params: list[InstallParam] = Field(default_factory=list)


@skill(
    name="custom_skill_install",
    display_name="安装自定义技能",
    description=(
        "帮用户安装一个新的自定义技能（之后用户在「技能」页能看到、能改、能删）。"
        "当用户说「帮我做一个能查XX的技能」时使用。"
        "**传入与已有技能相同的名字会覆盖更新它** —— 用户说「优化一下你装的"
        "那个查快递技能」时，先读出旧定义再按新内容重新安装即可。"
        "安装/更新都需要用户确认。"
    ),
    params_model=CustomSkillInstallParams,
    category="persona",
    permission_level="confirm",
    tags=["技能", "安装"],
)
class CustomSkillInstallSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = CustomSkillInstallParams(**params)
        try:
            store = ctx.service("custom_skill_store")
        except SkillExecutionError as exc:
            raise SkillExecutionError("技能存取服务不可用，无法安装。") from exc

        if args.kind not in ("http", "command"):
            raise SkillExecutionError("kind 只能是 http 或 command。")
        if args.kind == "http" and not args.url.strip():
            raise SkillExecutionError("HTTP 技能必须提供 url。")
        if args.kind == "command" and not args.command_template.strip():
            raise SkillExecutionError("命令技能必须提供 command_template。")

        from ..config.schemas import CustomSkillDef, CustomSkillParam

        
        
        
        
        sanitized = (
            "".join(
                ch if ch.isalnum() or ch in "_-" else "-" for ch in args.name.strip().lower()
            ).strip("-")
            or "custom-skill"
        )
        defn = CustomSkillDef(
            id=sanitized,
            name=args.name.strip(),
            description=args.description.strip(),
            params=[
                CustomSkillParam(name=p.name, description=p.description, required=p.required)
                for p in args.params
            ],
            kind=args.kind,  
            url=args.url.strip(),
            method=args.method.upper() if args.method.upper() in ("GET", "POST", "PUT", "DELETE") else "GET",  
            command_template=args.command_template,
            permission_level="confirm",
        )

        config = store.load()
        if config.get(defn.id) is not None:
            defn = defn.model_copy(update={"id": f"{defn.id}-{len(config.skills) + 1}"})
            config.upsert(defn)
        else:
            config.upsert(defn)
        store.save(config)

        return {
            "ok": True,
            "id": defn.id,
            "message": (
                f"已安装技能「{defn.name}」（id: {defn.id}）。"
                "立即生效，用户可在「技能」页查看或修改。"
            ),
        }


class SkillPackageInstallParams(BaseModel):
    url: str = Field(
        ..., min_length=1, description="技能包（zip）的下载地址，通常以 .zip 结尾"
    )


@skill(
    name="skill_package_install",
    display_name="从链接安装技能包",
    description=(
        "从用户给的**下载链接**安装一个技能包（zip，内含 skill.json 或 SKILL.md）。"
        "当用户说「下载并加载这个 skill」「装一下这个链接里的技能」并给出一个链接时使用。"
        "安装后技能立即生效，用户可在「技能」页查看。需要用户确认。"
    ),
    params_model=SkillPackageInstallParams,
    category="persona",
    permission_level="confirm",
    tags=["技能", "安装"],
)
class SkillPackageInstallSkill(BaseSkill):






    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = SkillPackageInstallParams(**params)
        try:
            store = ctx.service("custom_skill_store")
        except SkillExecutionError as exc:
            raise SkillExecutionError("技能存取服务不可用，无法安装。") from exc

        import asyncio

        import httpx

        from ..security.urls import validate_endpoint
        from .archive import MAX_PACKAGE_BYTES
        from .install import SkillRejected, unpack_for, validate_defn
        from .package import bind_script_commands, parse_package

        url = args.url.strip()
        
        validate_endpoint(url, field="技能包地址")

        try:
            async with async_client(timeout=httpx.Timeout(20.0, connect=8.0)) as client:
                response = await asyncio.wait_for(
                    client.get(url, follow_redirects=True), timeout=20.0
                )
                response.raise_for_status()
                data = response.content
        except Exception as exc:  
            raise SkillExecutionError(f"下载技能包失败：{exc}") from exc

        if len(data) > MAX_PACKAGE_BYTES:
            raise SkillExecutionError(
                f"技能包超过 {MAX_PACKAGE_BYTES // 1024 // 1024}MB，已拒绝下载。"
            )

        filename = url.rsplit("/", 1)[-1].rsplit("?", 1)[0] or "skill.zip"
        package_name = filename.rsplit(".", 1)[0] or "skill"
        try:
            parsed = parse_package(data, package_name, filename=filename)
        except ValueError as exc:
            raise SkillExecutionError(str(exc)) from exc

        config = store.load()
        installed: list[str] = []
        unpacked: list[str] = []
        rejected: list[str] = []
        for defn in parsed.defs:
            item = defn.model_copy(update={"id": defn.id.strip() or "skill"})
            try:
                validate_defn(store, item)
            except SkillRejected as exc:
                rejected.append(f"{item.name or item.id}（{exc.message}）")
                continue
            if config.get(item.id) is not None:
                item = item.model_copy(update={"id": f"{item.id}-{len(config.skills) + 1}"})
            dest = runtime_skills_dir(store, item.id)
            if dest is not None:
                
                
                summary = unpack_for(
                    store, item, parsed.members.members, parsed.members.container
                )
                if summary.get("count"):
                    unpacked.append(f"{item.id}（{summary['count']} 个文件）")
                item = bind_script_commands(item, dest)
            config.upsert(item)
            installed.append(item.name or item.id)
        store.save(config)

        extra = f"技能包已解开：{'、'.join(unpacked)}。" if unpacked else ""
        skipped = f"以下条目未安装：{'；'.join(rejected)}。" if rejected else ""
        
        
        mcp_note = (
            f"包内有 {len(parsed.mcp_roots)} 份 MCP 服务配置，未自动接入 —— "
            "请在「MCP 服务」页粘贴导入。"
            if parsed.mcp_roots
            else ""
        )
        return {
            "ok": True,
            "installed": installed,
            "message": (
                f"已从链接安装 {len(installed)} 个技能：{'、'.join(installed)}。"
                f"{extra}{skipped}{mcp_note}"
                "立即生效，用户可在「技能」页查看。"
            ),
        }


def sync_custom_skills(manager: Any, config: Any) -> int:









    manager.clear(source="custom")
    for defn in config.skills:
        if defn.kind == "instruction":
            continue
        try:
            manager.register(build_custom_skill_class(defn))
        except Exception:  
            logger.exception("自定义技能注册失败：%s", defn.id)
    return len(config.skills)


def backfill_display_names(config: Any, skills_dir: Any) -> bool:





















    if not skills_dir:
        return False
    from . import formats

    root = Path(str(skills_dir))
    changed = False
    for defn in getattr(config, "skills", []) or []:
        if not defn.id:
            continue
        path = root / defn.id / formats.SKILL_FILE
        try:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:  
            logger.warning("回填显示名时读不到 %s：%s", path, exc)
            continue
        _, body = formats.split_frontmatter(text)
        title = formats.display_title(body)
        if not title or title == defn.name:
            continue
        logger.info("技能「%s」的显示名回填为「%s」（原先叫「%s」）", defn.id, title, defn.name)
        defn.name = title
        changed = True
    return changed


def known_skill_names(runtime: Any) -> set[str]:

















    names = set(runtime.skills.all_names())
    config = getattr(runtime, "custom_skills", None)
    for defn in getattr(config, "skills", []) or []:
        if defn.id:
            names.add(defn.id)
        if defn.name:
            names.add(defn.name)
    return names




















INLINE_TEXT_LIMIT = 400







ON_DEMAND_LISTING = 6


def _can_read_files(enabled_skills: list[str] | None) -> bool:








    if not enabled_skills:
        return True
    return any("file" in item.lower() or "read" in item.lower() for item in enabled_skills)


def collect_instructions(
    config: Any,
    enabled_skills: list[str] | None,
    *,
    package_dirs: dict[str, str] | None = None,
) -> list[tuple[str, str]]:























    sections: list[tuple[str, str]] = []
    for defn in config.skills:
        if defn.kind != "instruction" or not defn.enabled:
            continue
        if not defn.instructions.strip():
            continue
        
        if defn.id not in (enabled_skills or ()):
            continue
        content = defn.instructions.strip()
        folder = (package_dirs or {}).get(defn.id)
        if folder:
            from .folder import INDEX_FILE, MAX_LISTING, listing_hint

            
            
            on_demand = _can_read_files(enabled_skills) and len(content) > INLINE_TEXT_LIMIT
            
            
            
            hint = listing_hint(
                Path(folder), limit=ON_DEMAND_LISTING if on_demand else MAX_LISTING
            )
            if on_demand:
                content = _on_demand_content(defn, folder, hint, len(content))
            elif hint:
                content = (
                    f"{content}\n\n"
                    f"这个技能包的文件都在本机目录：{folder}\n"
                    f"需要模板、示例或脚本时直接读该目录下的文件（用 file_read 之类的能力），"
                    f"不要凭印象编造它们的内容。"
                    f"（完整清单见 {Path(folder) / INDEX_FILE}）包内文件：\n{hint}"
                )
        sections.append((defn.name, content))
    return sections


def _on_demand_content(defn: Any, folder: str, hint: str, total: int) -> str:













    lines = [
        f"⚠️ 这份技能的详细说明（共 {total} 字）没有放进你的提示词，为的是不占上下文。",
        "**动手前必须先读下面这个文件** —— 它是这个技能唯一的权威说明，",
        "不要凭印象或经验去猜它的步骤、格式和参数。",
        "",
        f"完整说明（先读它）：{Path(folder) / 'SKILL.md'}",
        "",
        f"简介（用它判断什么时候该上这个技能）：{defn.description.strip() or defn.name}",
    ]
    if hint:
        
        
        lines += ["", "同目录下的包内文件（模板 / 示例 / 脚本）：", hint]
    return "\n".join(lines)


def collect_xjx_instructions(runtime: Any, assistant_id: str) -> list[tuple[str, str]]:








    from .builtin import xjx

    skills = xjx.skills_for_assistant(assistant_id, getattr(runtime, "line", ""))
    sections: list[tuple[str, str]] = []
    for item in skills:
        try:
            content = xjx.instructions(item.name).strip()
        except (KeyError, OSError) as exc:  
            logger.error("心鉴学技能正文读取失败：%s（%s）", item.name, exc)
            continue
        if content:
            sections.append((item.display_name, content))
    return sections


def package_dir_for(runtime: Any, skill_id: str) -> str:






    paths = getattr(runtime, "paths", None)
    root = getattr(paths, "skills_dir", None)
    if root is None:
        return ""
    return str(Path(root) / skill_id)


def _package_dirs(runtime: Any) -> dict[str, str]:

    mapping: dict[str, str] = {}
    config = getattr(runtime, "custom_skills", None)
    for defn in getattr(config, "skills", []) or []:
        if defn.kind != "instruction":
            continue
        folder = package_dir_for(runtime, defn.id)
        if folder and Path(folder).is_dir():
            mapping[defn.id] = folder
    return mapping


def allowed_skill_names(
    runtime: Any, assistant_id: str, enabled_skills: Any
) -> set[str]:







    skills = getattr(runtime, "skills", None)
    if skills is None:
        
        
        return set(enabled_skills or ())
    return skills.allowed_names(
        assistant_id=assistant_id or None, enabled_skills=enabled_skills
    )


def persona_with_instructions(
    runtime: Any, assistant_id: str, enabled_skills: list[str] | None
) -> str:






    from ..assistants.persona import build_persona_section

    
    
    assistant = runtime.assistants.get(assistant_id)
    nickname = assistant.nickname if assistant else ""
    base = build_persona_section(runtime.paths, assistant_id, nickname=nickname)
    
    sections = collect_instructions(
        runtime.custom_skills,
        allowed_skill_names(runtime, assistant_id, enabled_skills),
        package_dirs=_package_dirs(runtime),
    )
    sections += collect_xjx_instructions(runtime, assistant_id)
    if not sections:
        return base
    extra = "\n\n".join(f"### 指导：{name}\n\n{content}" for name, content in sections)
    return f"{base}\n\n{extra}" if base else extra


__all__ = [
    "CustomSkillInstallSkill",
    "CustomSkillStore",
    "SkillPackageInstallSkill",
    "backfill_display_names",
    "build_custom_skill_class",
    "collect_instructions",
    "collect_xjx_instructions",
    "known_skill_names",
    "package_dir_for",
    "persona_with_instructions",
    "sync_custom_skills",
]

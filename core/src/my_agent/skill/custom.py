"""把用户写的声明式技能定义，变成真正能被模型调用的技能。

## 为什么每个定义要"造一个类"

``SkillManager.register`` 要求 ``meta`` 挂在**类**上（``type(instance).meta``），
它会把类上的元数据深拷贝到实例上 —— 这是刻意的：启用状态与权限是实例级的
可变状态，直接共用类属性会让"禁用一个技能"污染所有实例。

所以这里用 ``type()`` 动态造子类、把 meta 设为类属性。造实例的写法不行。

## 两种动作

- ``http``：发一个 HTTP 请求（对接外部服务最常见的方式）
- ``command``：跑一条本机命令

**模板替换用朴素字符串替换，不用 ``str.format``**：``format`` 会把 ``{}``
当表达式解析，模板里只要有 JSON 就会炸 —— 而请求体恰恰几乎都是 JSON。
"""

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

# ⚠️ **这里不再有"命令/响应输出上限"。**
#
# 曾经是 20000 字符，理由是"模型上下文按 token 计费，一条命令返回 10MB 日志会把
# 这一轮撑爆"。这条理由只对了一半：确实会撑，但**该由物理容量去管，而不是我们
# 提前砍掉** —— 用户写的自定义技能是他自己配的东西，返回什么就该原样看到什么。
#
# 用户的原话："不要做任何截断/省略，将所有内容完整给到 ai。"
# 真装不下时由 memory/spill.py 无损外置并给出续读指引。

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
    """挡掉云元数据服务。

    与 ``security/urls.py`` 同一个理由：这些地址"被访问到就等于失陷"，
    而 HTTP 技能的地址来自用户输入，同样构成 SSRF 形态。
    本机地址**允许**（本地模型/本地服务是一等功能）。
    """
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
        # 响应体是不可信文本，可能回显 Authorization 之类的头
        from ..security.redact import redact

        raise SkillExecutionError(
            f"请求返回 HTTP {response.status_code}：{redact(text[:300])}"
        )
    return text or "(空响应)"


def _argv_for(defn: CustomSkillDef, values: dict[str, Any]) -> list[str]:
    """这次要执行的 argv —— **唯一一份**实现（第 93 批修）。

    ⚠️ 为什么必须共享：确认卡上那句"将执行的命令"与这里**必须逐字一致**，
    而两边各写一次的话，像"某些 token 渲染成空白就被丢掉"这种小差异会让它们分叉 ——
    "看到什么"和"跑什么"对不上，正是确认卡最不能出的问题
    （原先预览用未过滤的 `render_argv`，比执行侧多一个空参数）。
    """
    return [item for item in defn.render_argv(values, defn.command_template) if item.strip()]


async def _run_command(defn: CustomSkillDef, values: dict[str, Any]) -> str:
    # ⚠️ **argv 数组**（`render_argv`），不是一条拼出来的命令串。
    #
    # 这里以前是 `defn.render(values, defn.command_template)` + `create_subprocess_shell`：
    # 占位符的值来自**模型**，拼进 shell 命令后，值里的 `&` / `|` / `>` 就是 shell 语法
    # （`{host}` 被填成 `x & del /f /q ...` 就会真的执行）。
    # 现在两条一起改：① 模板先切成 argv、再逐个 token 替换占位符（值不改变参数结构）；
    # ② 走 `create_subprocess_exec`，整条命令不再经过任何 shell。
    # ⇒ 模板里写管道 / 重定向 / `&&` 的技能**不再有 shell 含义**，那些字符会作为普通
    #    参数原样传下去（这是不再经过 shell 的必然代价，已在文档里告知用户）。
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
        # ⚠️ 不再经过 shell 之后，"程序找不到"还多出两类**以前能跑、现在跑不了**的写法，
        # 它们的症状都是 WinError 2，光看错误码用户根本不知道自己哪里写错了：
        #   ① 用了 cmd 的内置命令（echo / dir / type / exit / copy…）—— 它们不是可执行文件；
        #   ② 模板里写了 shell 语法（管道 `|` / 重定向 `>` / `&&` / `%VAR%`）。
        # 所以这里必须把原因讲明白（项目口径：不静默、如实说明）。
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
        # 失败时把**完整**输出交出去。这里以前只留 500 字符，而"命令为什么失败"
        # 的答案经常就在被丢掉的那一段里（前 500 字符往往只是启动日志）。
        raise SkillExecutionError(
            f"命令退出码 {process.returncode}：{output or '(无输出)'}"
        )
    return output or "(命令执行完成，无输出)"


def build_custom_skill_class(defn: CustomSkillDef) -> type[BaseSkill]:
    """把一个定义变成可注册的技能类（meta 必须在类上，见模块开头）。"""

    class _CustomSkill(BaseSkill):
        async def run(self, ctx: Any, **params: Any) -> str:  # noqa: ANN001, ARG002
            if defn.kind == "http":
                return await _run_http(defn, params)
            return await _run_command(defn, params)

    _CustomSkill.meta = SkillMeta(
        name=defn.id,
        display_name=defn.name,
        description=defn.description or defn.name,
        parameters=defn.to_tool_schema(),
        category="custom",
        # 小分类随定义带过来（导入时从源目录的分类文件夹名写入；老定义的默认值是空）
        domain=defn.domain,
        permission_level=defn.permission_level,
        timeout=defn.timeout,
        enabled=defn.enabled,
        source="custom",
        # 命令型技能：让确认卡能显示"实际会执行的那条命令"（消费方见
        # `security/permission.py::_with_command_preview`）。
        # ⚠️ 这里调的是**执行侧同一个** `_argv_for` —— 不是"逻辑等价的一份"。
        # 各写一次的话，"看到什么"与"跑什么"迟早会对不上（第 93 批就修过一处）。
        command_preview=(
            (lambda values: " ".join(_argv_for(defn, values)))
            if defn.kind == "command"
            else None
        ),
    )
    _CustomSkill.__name__ = f"CustomSkill_{defn.id}"
    return _CustomSkill


def runtime_skills_dir(store: Any, skill_id: str) -> Path | None:
    """技能包该落在哪（``skills/<技能 id>``）；store 没有落盘根时返回 ``None``。"""
    root = getattr(store, "skills_root", None)
    if not root:
        return None
    return Path(root) / skill_id


class CustomSkillStore:
    """技能视角的自定义技能存取口（由 runtime 注入）。

    刻意只暴露很少的能力，而不是把整个 runtime 交给技能 ——
    技能拿到的能力越小，越不容易被诱导做越权的事。

    ``skills``（技能管理器，可选）只用于"这个 id 是不是内置技能"的重名判定；
    ``skills_root`` 是技能包落盘根目录，给了它模型自己从链接装的包才会被
    **整包解开**（见 ``skill/folder.py`` 的说明）。
    """

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
        """让 ``skill/install.py`` 那套（只读 ``paths.skills_dir``）能直接吃这个对象。"""
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

        # id 从显示名生成，**先算好再构造**。以前是拿 id="" 占位构造再
        # model_copy 替换 —— 而 id 有"至少 1 个字符"的校验，占位值自己就过不了，
        # 模型每装一个技能都撞 ValidationError（用户实测撞过）。
        # 这里**不能让模型自己起 id**：它可能撞上内置技能名，注册时会把内置技能覆盖掉。
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
            kind=args.kind,  # type: ignore[arg-type]
            url=args.url.strip(),
            method=args.method.upper() if args.method.upper() in ("GET", "POST", "PUT", "DELETE") else "GET",  # type: ignore[arg-type]
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
    """让模型能按用户给的链接**自己下载并安装**技能包（产品要求）。

    与 HTTP 路由的 import-url 走同一套 ``skill/package.py`` 解析逻辑，
    只是安装动作通过 ``CustomSkillStore`` 完成（技能拿不到 runtime）。
    """

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
        # 与集市、自定义 HTTP 技能同一套 SSRF 校验：拒绝内网/云元数据地址
        validate_endpoint(url, field="技能包地址")

        try:
            async with async_client(timeout=httpx.Timeout(20.0, connect=8.0)) as client:
                response = await asyncio.wait_for(
                    client.get(url, follow_redirects=True), timeout=20.0
                )
                response.raise_for_status()
                data = response.content
        except Exception as exc:  # noqa: BLE001
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
                # 按这条定义的范围落盘：SKILL.md 里可能写着"按 templates/x.md 来"，
                # 只装定义等于把模板扔了（见 skill/folder.py 顶部说明）
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
        # 包里带的 MCP 配置在这里**不自动接入**：技能拿不到 MCP 管理器，
        # 而且"模型下载一个包就顺手改掉用户的 MCP 服务"风险太大。如实告诉用户去哪装。
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
    """把自定义技能同步进管理器；返回当前数量。

    **先清掉旧的再注册新的**：用户改了定义（或删掉一个）后，
    旧实例还挂在管理器里的话，模型会继续看到已经不存在的工具。

    ``instruction`` 类型**不注册成工具**：它不执行任何动作，注册了只会
    让模型看到一个"调了也没意义"的工具。它的内容走 ``collect_instructions``
    进 system（见 scheduler / chat 路由的 persona 组装处）。
    """
    manager.clear(source="custom")
    for defn in config.skills:
        if defn.kind == "instruction":
            continue
        try:
            manager.register(build_custom_skill_class(defn))
        except Exception:  # noqa: BLE001 - 一个定义写坏不该拖垮其它技能
            logger.exception("自定义技能注册失败：%s", defn.id)
    return len(config.skills)


def backfill_display_names(config: Any, skills_dir: Any) -> bool:
    """把已装技能的**显示名**回填成中文（读包目录 ``SKILL.md`` 的正文一级标题）。

    返回"这次有没有真的改过" —— 没改就别写盘（理由见最后一段）。

    **为什么需要它**：这批第三方技能包的 frontmatter ``name`` 是英文 slug
    （``travel-itinerary-planning``），**中文名在正文标题里**
    （``# 行程规划设计（精确到小时）``）。新导入的已经会取标题
    （见 ``formats.display_title`` 与 ``package.parse_members``），但**先装好的那批**
    定义里存的还是英文 —— 界面上就成了"英文名 + 灰字英文名"两行一样的东西，
    用户根本看不出这是个中文产品（2026-10-07 报的）。

    ⚠️ **只改显示名（``defn.name``），绝不动 ``defn.id``**：id 既是落盘目录
    ``skills/<id>/`` 的名字，也是搭子档案 ``enabled_skills`` 里存的值 ——
    改了它，用户勾过的技能会**集体失效**。这与 ``parse_members`` 里那份分工是同一条约束。

    ⚠️ 只处理磁盘上**真有 ``SKILL.md``** 的：AI 创建 / 手动建的技能本来没有说明文件，
    也就没有标题可读，一律维持原名。

    ⚠️ 只在值**真的变了**时返回 True：配置每次启动都会读，少了这个判断就会
    "每次开机重写一遍用户配置、并广播一次 skills_changed"，白忙而且难查。
    """
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
        except OSError as exc:  # 读不到就跳过：回填是锦上添花，不该拖垮启动
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
    """当前技能库里"存在的东西"的全集：**工具技能 + 指导型技能**。

    为什么必须走这一个函数，而不是各自去查 ``skills.all_names()``：

    指导型技能（``kind='instruction'``）按设计**不会注册成工具**（见
    ``sync_custom_skills``：它没有动作，注册了只会让模型看到一个调了也没意义的工具）。
    于是 ``SkillManager.all_names()`` 里永远没有它 —— 可它明明装好了、界面上也有。
    拿这个"工具表"去回答"这个技能存在吗"，就会把已经装好的指导型技能判成**不存在**，
    一处根因、三种症状：

    1. 保存搭子时 422「技能不存在」（白名单校验用了工具表）；
    2. 已经勾上它的搭子被标成「有 N 个工具当前不可用」（派生字段用了工具表）；
    3. 新建/复制搭子时算默认勾选，那些技能一个都算不进来。

    所以：**凡是判断"技能存不存在"，都查这里**。名字与 id 都收进来 ——
    白名单里既可能出现工具名（``excel_read``），也可能出现自定义技能的 id。
    """
    names = set(runtime.skills.all_names())
    config = getattr(runtime, "custom_skills", None)
    for defn in getattr(config, "skills", []) or []:
        if defn.id:
            names.add(defn.id)
        if defn.name:
            names.add(defn.name)
    return names


# **指导型技能的正文默认不塞进 system**：只给"简介 + 完整说明的路径"，模型真要用
# 的时候自己去读那个文件。这条线是那条默认规则的**例外** —— 正文短到"还不如直接给"
# 时才整份注入。
#
# ⚠️ 口径变过两轮，当前以第二轮为准（定）：
#
# 1. 起初是"超过 :data:`FULL_TEXT_LIMIT`（8000 字）才降级"；
# 2. 后来试过"跨技能合计超过某个总量（5 万）才降级"，**否决了** —— 它要用户记一个
#    数字，而且"谁被降级"取决于技能在配置里的先后，同一个搭子换个勾选顺序待遇就变；
# 3. **现在是"默认按需"**：规则只有一条，不随总量变化，用户不用记任何数字。
#
# 400 这个数的由来**不是"省 token"**，而是"摘要比正文还长"：按需版要写
# 技能简介 + 完整说明路径 + 包目录 + 包内文件清单，这一套本身就要两三百字。正文比它
# 还短时，按需反而更占地方、还白白多一次读取。
#
# ⚠️ 按需**不是省事**：它把"读说明"变成模型的一个动作。所以降级文案写得比较硬
# （见 :func:`_on_demand_content`），并且它依赖模型**真能读到**那个文件 ——
# 技能包目录因此必须永远可读，见 ``server/runtime.py::_build_path_policy``。
INLINE_TEXT_LIMIT = 400

#: 按需读取时**最多列几个包内文件**（正文整份注入时仍用 ``folder.MAX_LISTING``，40 个）。
#:
#: ⚠️ 收窄它的理由是实测出来的：按需版每个技能约 730 字，其中文件清单占了大头 ——
#: 勾 254 个技能时清单一项就撑起 18 万字里的三分之一。而这条路径下模型本来就要先读
#: ``SKILL.md``，说明里会点名它要用哪几个文件，列四十条纯属白占提示词。
#: 少列的部分**不丢**：完整清单始终在包目录的 ``_pack_index.md``（见 `folder.write_index`）。
ON_DEMAND_LISTING = 6


def _can_read_files(enabled_skills: list[str] | None) -> bool:
    """这个搭子有没有可能去读文件。

    ⚠️ 入参现在的口径是"该搭子**实际可用**的技能集合"（由 `SkillManager.allowed_names`
    展开，见 `skill/groups.py`）—— 它显式且永不为空（至少含内置技能里的 `file_read`），
    所以下面那个空值分支实际上已经走不到了。留着它只有一个作用：
    万一哪个调用点还没更新，**偏保守地认为能读** ——
    多一次读取的成本，远小于"给了路径却读不到"导致的静默丢信息。
    """
    if not enabled_skills:
        return True
    return any("file" in item.lower() or "read" in item.lower() for item in enabled_skills)


def collect_instructions(
    config: Any,
    enabled_skills: list[str] | None,
    *,
    package_dirs: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    """收集要注入 system 的指导型技能，返回 ``[(名称, 内容), ...]``。

    ⚠️ ``enabled_skills`` 现在的口径是**该搭子实际可用的技能集合**
    （由 `SkillManager.allowed_names` 展开，见 `skill/groups.py`），
    **不是**用户勾选的原始记录 —— 它显式、且永不为空。
    **没有"空 = 全注入"这回事了**（产品约定："没有默认加载全部技能的搭子了"）：
    指导型技能一律属于「我的技能」，没被勾中就不该出现在 system 里 ——
    否则会出现"工具没暴露、提示词里却写着它"这种自相矛盾的状态。
    ``enabled`` 关掉的（全局禁用）不注入。

    ``package_dirs``：技能 id → **该技能包落盘的绝对目录**。传了就在正文后面
    附上"文件在这、都有哪些"，模型才能真的去读 SKILL.md 里提到的那些辅助文件
    （模板、示例、脚本）。没传或那个目录不存在时什么都不附 —— 不写一句
    "（无附件）"之类的废话占 system。

    **正文默认不注入**：只要满足 ① 该技能确实落了盘、② 这个搭子读得到文件
    这两个条件，就只给"简介 + 目录 + 文件清单"，完整说明留给模型按需读
    ``<目录>/SKILL.md``。唯一的例外是正文短到 :data:`INLINE_TEXT_LIMIT` 以下 ——
    那时按需版本身反而更长，直接给全文更省。

    读不了文件的搭子（可用集合里没有文件类技能）仍走全量注入 —— 否则等于
    告诉他"去看那个文件"，而他根本没有读文件的能力。
    """
    sections: list[tuple[str, str]] = []
    for defn in config.skills:
        if defn.kind != "instruction" or not defn.enabled:
            continue
        if not defn.instructions.strip():
            continue
        # ⚠️ 不再有"空 = 全注入"：没被勾中就不注入（见上面的说明）
        if defn.id not in (enabled_skills or ()):
            continue
        content = defn.instructions.strip()
        folder = (package_dirs or {}).get(defn.id)
        if folder:
            from .folder import INDEX_FILE, MAX_LISTING, listing_hint

            # ⚠️ 顺序是"能读 **且** 够长"：两个条件都满足才降级。少了 `can_read`
            # 会变成"告诉一个瞎子去看那份文件"（模型没有读文件的能力，正文就真丢了）。
            on_demand = _can_read_files(enabled_skills) and len(content) > INLINE_TEXT_LIMIT
            # 清单上限**按走向**给：整份注入时多列几行；按需读取时少列（理由见常量说明）。
            # 这里必须与上面的判断用同一个 `on_demand` —— 算出两个不同的走向，就会出现
            # "说自己读不了文件、却又只给了十几行清单"这种自相矛盾的注入。
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
    """技能的"按需读取"版正文：**去哪读** + 一句为什么，不省略任何内容。

    完整说明原封不动留在包目录里，只是不再整份占 system。

    ⚠️ 措辞是**故意写这么硬**的。这条路径把"读说明"变成了模型的一个动作，而模型有个
    很常见的失败模式：凭技能名的印象直接开干、不去读。所以"动手前必须先读"要单独成句
    放在最前面，夹在一段说明里就容易被忽略。同理，末尾那句"不要凭印象编造"必须留着 ——
    它防的是"摘要够用"的错觉（摘要只够判断该不该用，不够照着做）。

    ⚠️ 摘要只给 ``description``，这**不是**随手挑的字段：技能包的 description 里本来就
    写着"触发 / 触发词 / 适用场景"（导入时就要求了），那正是模型判断"现在该不该用这个
    技能"的依据。判断依据不能省 —— 省掉就成了"技能在，但模型不知道什么时候该用"。
    """
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
        # ⚠️ 不再单列一行"技能包目录"：它就是上面那个 SKILL.md 的父目录，白占一行。
        # 但要说明清单的基准目录 —— 清单里是相对路径，不说基准，模型对不上号。
        lines += ["", "同目录下的包内文件（模板 / 示例 / 脚本）：", hint]
    return "\n".join(lines)


def collect_xjx_instructions(runtime: Any, assistant_id: str) -> list[tuple[str, str]]:
    """收集该搭子在本线路上应拿到的**内置专属技能**正文（心鉴学那套）。

    为什么不并进 ``collect_instructions``：那一个的入参是"用户勾选过的技能
    ``enabled_skills``"，而内置专属技能**根本不在用户的技能库里** —— 它们不落盘、
    不进自定义技能表，是"线路 + 搭子归属"的纯函数（见 ``builtin/xjx.py``）。
    硬塞进那条白名单链路，就等于给它们加了一个"能不能被过滤掉"的口子，
    而这正是用户明确要求不存在的东西。所以这里**不经过任何白名单**。
    """
    from .builtin import xjx

    skills = xjx.skills_for_assistant(assistant_id, getattr(runtime, "line", ""))
    sections: list[tuple[str, str]] = []
    for item in skills:
        try:
            content = xjx.instructions(item.name).strip()
        except (KeyError, OSError) as exc:  # 资源缺失属于安装损坏，不该炸掉整轮对话
            logger.error("心鉴学技能正文读取失败：%s（%s）", item.name, exc)
            continue
        if content:
            sections.append((item.display_name, content))
    return sections


def package_dir_for(runtime: Any, skill_id: str) -> str:
    """某个技能包应该落在哪（``skills/<技能 id>``），返回绝对路径字符串。

    路径**由技能 id 推导**而不是存进配置：id 是白名单里引用的键、也不允许被改名，
    推导出来的位置天然跟着走；存成字段反而多出一份可能对不上的副本
    （用户搬了数据目录、或者手工挪过文件夹）。
    """
    paths = getattr(runtime, "paths", None)
    root = getattr(paths, "skills_dir", None)
    if root is None:
        return ""
    return str(Path(root) / skill_id)


def _package_dirs(runtime: Any) -> dict[str, str]:
    """指导型技能 id → 它的包目录（只在目录真的存在时才给，避免注入死路径）。"""
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
    """该搭子**实际可用**的技能名集合（工具装配与提示词注入共用同一口径）。

    ⚠️ 抽成一个函数而不是在 `persona_with_instructions` 里现写：它必须与
    `AgentConfig.enabled_skills` 那边**完全同一套判定**（见 `skill/groups.py`），
    两条链一旦不一致，就会出现"工具清单里没有它、提示词里却写着它" ——
    模型会照着提示词去调，然后拿到一句"不在当前会话启用的技能范围内"。
    """
    skills = getattr(runtime, "skills", None)
    if skills is None:
        # 运行时还没装载技能管理器（部分单测直接构造 runtime）→ 退化成"照原样传"，
        # 至少不会因为拿不到它而把整轮对话炸掉。
        return set(enabled_skills or ())
    return skills.allowed_names(
        assistant_id=assistant_id or None, enabled_skills=enabled_skills
    )


def persona_with_instructions(
    runtime: Any, assistant_id: str, enabled_skills: list[str] | None
) -> str:
    """助手人格文件 + 已启用指导型技能 + 内置专属技能，合成一段注入 system 的文本。

    chat 路由、群聊与定时任务调度**都要走这里**，不能一处拼一处不拼 ——
    否则同一个助手"我直接问"和"定时任务跑出来"行为不一致，
    那是最难排查的一类 bug。
    """
    from ..assistants.persona import build_persona_section

    # 昵称来自助手配置（不是人格文件）：改了昵称，AI 下次就知道自己叫什么。
    # 拿不到（助手已删等）就传空串，build_persona_section 会跳过名字段。
    assistant = runtime.assistants.get(assistant_id)
    nickname = assistant.nickname if assistant else ""
    base = build_persona_section(runtime.paths, assistant_id, nickname=nickname)
    # 与工具装配同一口径：入参是"用户勾了哪几个"的原始记录，先展开成实际可用集合
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

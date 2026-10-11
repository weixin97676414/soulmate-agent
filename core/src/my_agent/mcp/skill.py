"""把 MCP 工具包装成 Skill。

这是「MCP 能力统一进 Skill 系统」的适配层（开发文档 6.4 节）。
包装之后，Agent 循环对「内置技能」与「MCP 工具」完全一视同仁——
工具卡片、权限确认、审计日志、执行链路这些横切能力全都自动生效，
不需要为 MCP 单独写一套。
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from typing import TYPE_CHECKING, Any

from ..skill.base import BaseSkill, SkillContext, SkillMeta
from .types import McpToolInfo

if TYPE_CHECKING:
    from .client import McpClient

# 工具名允许的字符集。OpenAI 的函数名规范就是 `^[a-zA-Z0-9_-]{1,64}$`，
# 超出范围的名称会被网关直接拒绝，必须在包装时收敛。
_NAME_SAFE = re.compile(r"[^A-Za-z0-9_-]")
_NAME_MAX = 64

# 只读动词：命中则认为不产生副作用
READ_TOKENS = frozenset(
    {
        "read", "list", "get", "query", "search", "find", "stat", "describe",
        "head", "info", "show", "view", "fetch", "lookup", "count", "exists",
        "check", "peek", "inspect", "export", "download", "resolve", "match",
        "grep", "scan", "diff", "compare", "history", "status", "preview",
    }
)

# 写动词：命中则视为有副作用，需要人工确认
#
# 这张表漏词不会报错，只会让一个**有副作用**的工具被静默放行 ——
# 所以宁可多收。之前缺的那批正是最容易漏的：``search_and_replace`` 命中只读动词
# ``search`` 被判成 safe，``list_and_purge`` 命中 ``list`` 也被判成 safe，
# 而这两个实际上一个在改写内容、一个在删除数据。
WRITE_TOKENS = frozenset(
    {
        "write", "create", "add", "insert", "update", "edit", "modify", "set",
        "delete", "remove", "drop", "clear", "reset", "truncate", "unlink",
        "move", "rename", "copy", "mkdir", "touch", "chmod", "chown",
        "execute", "run", "exec", "spawn", "kill", "install", "uninstall",
        "start", "stop", "restart", "send", "post", "put", "patch", "upload",
        "push", "publish", "submit", "apply", "commit", "merge", "format",
        # 补全：这些同样是"改变状态"，只是名字里没有经典的写动词
        "replace", "transform", "convert", "save", "store", "append",
        "purge", "wipe", "sync", "revoke", "grant", "assign", "rotate",
        "register", "deregister", "enable", "disable", "lock", "unlock",
        "increment", "decrement", "import", "restore", "revert", "rollback",
        "schedule", "cancel", "retry", "invoke", "trigger", "notify",
        "rename_move", "link", "symlink", "extract", "deploy", "release",
    }
)

# 单复数/时态归一化时只用去掉尾部 s，避免引入词干化依赖
_WORD_SPLIT = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z0-9]+")


def _tokens(name: str) -> set[str]:
    """把工具名切成小写词元集合。

    必须按词元而不是子串匹配：``"prune"`` 里含有 ``"run"``，
    用子串判断会把一个只读的清理工具误判成写操作，反之亦然。
    """
    tokens: set[str] = set()
    for chunk in re.split(r"[^A-Za-z0-9]+", name or ""):
        if not chunk:
            continue
        tokens.add(chunk.lower())
        for word in _WORD_SPLIT.findall(chunk):
            tokens.add(word.lower())
    return tokens


def _hit(tokens: set[str], vocabulary: frozenset[str]) -> bool:
    for token in tokens:
        if token in vocabulary:
            return True
        # 兼容 reads / deleted / files 这类变形
        if token.endswith("s") and token[:-1] in vocabulary:
            return True
    return False


def infer_permission_level(tool: McpToolInfo) -> str:
    """推断工具所需的权限级别。

    判定优先级（从最可靠到最不可靠）：

    1. MCP 的 ``destructiveHint`` / ``readOnlyHint`` 注解 —— Server 自己声明的事实；
    2. 工具名中的**写动词** —— 宁可多问一次，不可误改；
    3. 工具名中的只读动词；
    4. 都判断不出来时归为 ``confirm``。

    第 4 条是刻意的**保守默认**：第三方 Server 的工具我们一无所知，
    默默放行才是真正危险的选择。用户可以在「技能」页签里逐个改成 safe。
    """
    if tool.destructive is True:
        return "confirm"
    if tool.read_only is True:
        return "safe"

    tokens = _tokens(tool.name)
    if _hit(tokens, WRITE_TOKENS):
        return "confirm"
    if _hit(tokens, READ_TOKENS):
        return "safe"
    return "confirm"


def namespaced_name(server: str, tool: str) -> str:
    """生成带命名空间的工具名，避免多个 Server 的同名工具互相覆盖。

    用**双下划线**分隔而不是单个：单下划线无法区分
    「Server `a_b` 的工具 `c`」与「Server `a` 的工具 `b_c`」，
    两者都会拼成 ``a_b_c``。开发文档里写的是单下划线，这里做了一点偏离，
    为的是让工具名在界面上能一眼看出归属。

    超长时截断并追加哈希，保证仍是合法且唯一的函数名。
    """
    raw = f"{server}__{tool}"
    cleaned = _NAME_SAFE.sub("_", raw)

    # 分量里出现分隔符本身就意味着歧义：
    #   ("a__b", "c") 与 ("a", "b__c")  →  都拼成 a__b__c
    # 后者会把前者**静默覆盖**（只少注册一个工具，没有任何报错，界面上看不出来）。
    # 注意哈希的输入不能是 raw —— 两条链路的 raw 完全相同，算出来也一样。
    if "__" in server or "__" in tool:
        digest = hashlib.sha1(f"{server}\x00{tool}".encode()).hexdigest()[:6]
        cleaned = f"{cleaned[: _NAME_MAX - 7]}_{digest}"

    if len(cleaned) <= _NAME_MAX:
        return cleaned
    digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:8]
    return f"{cleaned[: _NAME_MAX - 9]}_{digest}"


def build_mcp_skill(
    client: McpClient,
    tool: McpToolInfo,
    *,
    permission_level: str,
) -> BaseSkill:
    """为单个 MCP 工具构造一个 Skill 实例。

    ``meta`` 挂成类属性是必须的：``SkillManager.register`` 会读取
    ``type(instance).meta`` 并深拷贝到实例上——这正是我们想要的行为
    （每个工具一份独立的启用状态与权限级别）。
    """
    server = client.server_name
    tool_name = namespaced_name(server, tool.name)
    description = tool.description.strip() or f"{server} 提供的工具 {tool.name}"

    meta = SkillMeta(
        name=tool_name,
        display_name=f"{tool.title or tool.name}",
        # 前缀标明来源，模型在多工具场景下更容易选对
        description=f"[{server}] {description}",
        parameters=tool.input_schema or {"type": "object", "properties": {}},
        category="mcp",
        permission_level=permission_level,
        timeout=client.config.timeout,
        source="mcp",
        tags=[server, tool.name],
    )

    class _McpToolSkill(BaseSkill):
        """MCP 工具在 Skill 系统里的代理。

        不做参数校验：MCP Server 会用自己声明的 inputSchema 校验，
        我们提前拦一遍只会把 Server 的错误信息变得更难懂。

        **错误翻译**：MCP 域的错误（工具失败、服务不可用）在这里统一转成
        ``SkillExecutionError``。原因有两点：跨越 Skill 边界的异常类型应当
        属于 Skill 域；否则 ``SkillManager`` 会把 ``McpToolCallError`` 再包
        一层 ``SkillExecutionError``，错误文本出现 "工具 x 执行出错：MCP 工具
        x 执行失败：…" 这样的重复前缀，反而稀释了真正有用的信息。
        """

        async def run(self, ctx: SkillContext, **params: Any) -> Any:
            from ..errors import McpServerError, SkillExecutionError

            if not client.is_ready:
                raise SkillExecutionError(
                    f"MCP Server「{server}」当前不可用，工具 {tool.name} 无法执行。"
                    f"请在「设置 → MCP 服务」中检查连接状态。"
                )
            try:
                return await client.call_tool(tool.name, params)
            except McpServerError as exc:
                raise SkillExecutionError(exc.message) from exc
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                # SDK 自己抛的 ``McpError`` 之类不在我们的异常体系里。不翻译的话
                # 它会穿透到 SkillManager 的兜底分支，被包成
                # "工具 x 执行出错：McpError: ..." —— 前缀重复，而且看不出
                # 这是 MCP 那边的问题还是本地代码的问题。
                raise SkillExecutionError(
                    f"MCP Server「{server}」的工具 {tool.name} 执行失败：{exc}"
                ) from exc

    _McpToolSkill.meta = meta
    _McpToolSkill.__name__ = f"McpToolSkill_{tool_name}"
    _McpToolSkill.__qualname__ = _McpToolSkill.__name__
    instance = _McpToolSkill()
    # 保存原始工具名，便于界面显示与排查
    instance.mcp_server = server  # type: ignore[attr-defined]
    instance.mcp_tool = tool.name  # type: ignore[attr-defined]
    instance.mcp_client = client  # type: ignore[attr-defined]
    return instance


__all__ = [
    "READ_TOKENS",
    "WRITE_TOKENS",
    "build_mcp_skill",
    "infer_permission_level",
    "namespaced_name",
]

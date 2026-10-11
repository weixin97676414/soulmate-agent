"""MCP 传输方式：stdio 与远程（SSE / Streamable HTTP）。

对应《智能体框架开发文档》6.1 节列的三种传输。原先只实现 stdio，
所以只能连"本机起子进程"的 Server，连不上任何托管服务。

## 为什么单独抽一层

三种传输在**建连方式**上完全不同，但在**连接之后**完全一样：都是拿到一对
``(read, write)`` 流，交给 ``ClientSession``，然后走同一套探活 / 重连 / 停止逻辑。

把它抽出来的价值在于：``McpClient`` 里的 actor 模型、崩溃重启、命令队列、
优雅关停这些**难写且已经写好**的部分一行都不用动 —— 只有建连那一处换了实现。
如果直接在 ``_run`` 里写 if/else，那份复杂度会渗进生命周期代码里。

## 远程传输的失败语义

stdio 的"连不上"通常是命令写错（立刻失败、重试没意义）；远程的"连不上"更常见的是
网络抖动或服务端重启（重试有意义）。两者最终都归到 ``McpManager`` 的重连计数上，
由它决定"连续失败几次算不可用"——这里不做区分，避免判断逻辑散落两处。
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from ..config.schemas import McpServerConfig
from ..errors import McpSdkMissingError, PathNotAllowedError
from ..security.paths import PathPolicy

logger = logging.getLogger(__name__)


def validate_cwd(config: McpServerConfig, policy: PathPolicy | None = None) -> str | None:
    """校验 ``cwd`` 并返回规范化后的路径。

    ``cwd`` 决定第三方 Server 在哪个目录里读写文件。配错了不会报错，只会让它
    **在别的地方动文件** —— 这类问题通常要等到用户发现"我的文件被动过"才暴露。

    分两道校验：

    1. **形状**：绝对路径、存在、确实是目录。挡住的是"写错了路径"。
    2. **范围**：落在用户配置的目录白名单内（有白名单时才生效）。挡住的是
       "路径没错，但不该让它在那儿干活"。

    ## 为什么范围校验不是默认全开的

    只在**用户确实配置了** ``allowed_dirs``（``policy.is_restricted``）时才启用。
    没配置白名单的用户本来就没表达过"只许在这些目录"，凭空给他加限制会让
    原本能跑的 MCP 服务突然起不来 —— 而那是一次静默的行为变更，用户只会觉得
    "升级之后 MCP 坏了"。

    一旦启用，报错信息必须**告诉用户怎么改**（去设置里加哪个目录），
    否则就只是换了个地方卡住他。
    """
    raw = (config.cwd or "").strip()
    if not raw:
        return None

    path = Path(raw).expanduser()
    if not path.is_absolute():
        # 相对路径的基准是"客户端进程的当前目录"，而它在开发模式与安装后
        # 完全不同 —— 同一个配置在两台机器上会指向不同地方
        raise ValueError(f"MCP 服务「{config.name}」的 cwd 必须是绝对路径：{raw}")
    if not path.exists():
        raise ValueError(f"MCP 服务「{config.name}」的 cwd 不存在：{path}")
    if not path.is_dir():
        raise ValueError(f"MCP 服务「{config.name}」的 cwd 不是目录：{path}")

    if policy is not None and policy.is_restricted:
        try:
            policy.check(str(path), mode="read")
        except PathNotAllowedError as exc:
            raise ValueError(
                f"MCP 服务「{config.name}」的 cwd（{path}）不在允许的目录白名单内。"
                f"当前白名单：{policy.describe()}。"
                "如果这个服务确实需要在该目录运行，请先把它加进"
                "「设置 → 工作区 → 允许目录」。"
            ) from exc

    return str(path)


def _remote_headers(config: McpServerConfig) -> dict[str, str] | None:
    return dict(config.headers) or None


async def open_transport(
    config: McpServerConfig, stack: AsyncExitStack, policy: PathPolicy | None = None
) -> tuple[Any, Any]:
    """按配置建立连接，返回 ``(read, write)`` 流。

    调用方把 ``AsyncExitStack`` 传进来，是为了让**建连与断开发生在同一个任务内** ——
    MCP SDK 底层用 anyio 的 cancel scope，跨任务退出会抛
    ``Attempted to exit cancel scope in a different task``，而报错完全看不出根因。
    这也是 ``McpClient`` 采用 actor 模型的原因。

    ``policy`` 只有 stdio 传输用得上（远程传输没有"在哪个目录跑"这回事）。
    """
    if config.transport == "stdio":
        return await _open_stdio(config, stack, policy)
    if config.transport == "sse":
        return await _open_sse(config, stack)
    if config.transport == "streamable_http":
        return await _open_streamable_http(config, stack)
    raise ValueError(f"不支持的 MCP 传输方式：{config.transport}")


async def _open_stdio(
    config: McpServerConfig, stack: AsyncExitStack, policy: PathPolicy | None = None
) -> tuple[Any, Any]:
    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client

    from .client import build_subprocess_env

    cwd = validate_cwd(config, policy)
    params = StdioServerParameters(
        command=config.command,
        args=list(config.args),
        # 只放行白名单 + 用户显式配置的 env，见 build_subprocess_env 的说明
        env=build_subprocess_env(config.env),
        cwd=cwd,
    )
    return await stack.enter_async_context(stdio_client(params))


async def _open_sse(config: McpServerConfig, stack: AsyncExitStack) -> tuple[Any, Any]:
    try:
        from mcp.client.sse import sse_client
    except ImportError as exc:  # pragma: no cover - 依赖缺失时的兜底
        raise McpSdkMissingError(
            "当前安装的 mcp 版本不支持 SSE 传输，请升级：pip install -U \"my-agent-core[mcp]\""
        ) from exc

    logger.info("MCP 服务 %s 使用 SSE 传输连接 %s", config.name, config.url)
    streams = await stack.enter_async_context(
        sse_client(config.url, headers=_remote_headers(config))
    )
    # sse_client 产出 (read, write)
    read, write = streams[0], streams[1]
    return read, write


async def _open_streamable_http(
    config: McpServerConfig, stack: AsyncExitStack
) -> tuple[Any, Any]:
    try:
        # ⚠️ 函数名是 ``streamable_http_client``（带下划线），不是
        # ``streamablehttp_client`` —— 后者在 mcp 2.2.0 里不存在，会触发
        # ImportError 并走下面的"不支持"兜底，而这正是实测反馈 bug。
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as exc:  # pragma: no cover
        raise McpSdkMissingError(
            "当前安装的 mcp 版本不支持 Streamable HTTP 传输，"
            "请升级：pip install -U \"my-agent-core[mcp]\""
        ) from exc

    # ⚠️ streamable_http_client **不接受 `headers` 关键字**（只有 sse_client 接受）——
    # 直接传会报 ``unexpected keyword argument 'headers'``（用户实测 #11）。
    # 认证头必须通过自定义 ``http_client`` 传入。用官方工厂构造，避免自己拼
    # httpx 客户端时与 mcp 内部的版本/配置校验不一致（那会报一个很难懂的错）。
    http_client = None
    headers = _remote_headers(config)
    if headers:
        try:
            from mcp.shared._httpx_utils import create_mcp_http_client

            http_client = create_mcp_http_client(headers=headers)
        except ImportError:  # pragma: no cover - 极端版本差异下的兜底
            logger.warning(
                "MCP 服务 %s 需要自定义请求头，但当前 mcp 版本没有可用的 http 客户端工厂；"
                "本次连接将不带这些头。",
                config.name,
            )

    logger.info("MCP 服务 %s 使用 Streamable HTTP 连接 %s", config.name, config.url)
    # 先登记 http_client 的关闭，再进入会话：退出时 LIFO，先关会话再关 client，
    # 顺序反了会在已关闭的连接上发请求。
    if http_client is not None:
        stack.push_async_callback(http_client.aclose)
    streams = await stack.enter_async_context(
        streamable_http_client(config.url, http_client=http_client)
    )
    # streamable_http_client 产出 (read, write, get_session_id)，
    # 第三个是用于重连时复用会话的取值函数，我们走完整重连，不需要它
    return streams[0], streams[1]


def transport_summary(config: McpServerConfig) -> str:
    """给状态卡片用的一句话描述。"""
    if config.transport == "stdio":
        return f"{config.command} {' '.join(config.args)}".strip()
    return config.url

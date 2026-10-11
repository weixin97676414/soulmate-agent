"""命令行接口。

对应《智能体框架开发文档》13.2 节。桌面客户端之外的第二种使用方式，
主要给三类场景用：

1. **排查问题**：不想开界面，直接问一句看它怎么反应；
2. **接入脚本**：把一次任务跑完拿结果，`--trace-file` 留下完整执行记录；
3. **复现问题**：拿到一份 trace JSONL 后离线回放，不用重跑模型。

## 为什么不需要服务器

``run`` 直接在**本进程**里构建 runtime 并跑 Agent，不经过 HTTP。
这样才有实用价值 —— 要是必须先启一个服务再连它，命令行就失去了
"快速试一下"的意义。代价是没有确认通道（confirm 级技能一律拒绝），
这在无人的命令行里正是期望行为。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="my-agent",
        description="智能体核心的命令行入口（不启动 HTTP 服务）。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- skills ---- #
    skills = sub.add_parser("skills", help="查看已注册的技能")
    skills.add_argument("action", nargs="?", default="list", choices=["list"])
    skills.add_argument("--all", action="store_true", help="包含已禁用的技能")
    skills.add_argument("--json", action="store_true", help="输出 JSON")

    # ---- run ---- #
    run = sub.add_parser("run", help="跑一次任务并把回答打到标准输出")
    run.add_argument("prompt", help="要交给智能体的问题或指令")
    run.add_argument("--session", help="沿用已有会话 id（默认新建）")
    run.add_argument("--model", help="指定模型 id（默认用配置里的默认模型）")
    run.add_argument("--assistant", help="使用某个助手预设")
    run.add_argument("--trace-file", help="把完整执行记录写成 JSONL（每行一个 span）")
    run.add_argument("--quiet", action="store_true", help="只输出最终回答，不显示工具调用")

    # ---- replay ---- #
    replay = sub.add_parser("replay", help="回放一份 trace JSONL")
    replay.add_argument("trace_file")
    replay.add_argument("--json", action="store_true")

    return parser


# --------------------------------------------------------------------------- #
# skills
# --------------------------------------------------------------------------- #
async def _cmd_skills(args: argparse.Namespace) -> int:
    from ..config.paths import AppPaths
    from ..server.runtime import create_runtime

    runtime = create_runtime(AppPaths.resolve().ensure())
    try:
        metas = runtime.skills.list_metas(enabled_only=not args.all)
        if args.json:
            print(json.dumps([m.to_dict() for m in metas], ensure_ascii=False, indent=2))
            return 0

        if not metas:
            print(f"没有{'可用的' if not args.all else ''}技能。")
            return 0

        # 按分类分组打印：技能多了以后平铺一列根本找不到东西
        groups: dict[str, list[Any]] = {}
        for meta in metas:
            groups.setdefault(meta.category, []).append(meta)

        for category in sorted(groups):
            print(f"\n[{category}]")
            for meta in groups[category]:
                mark = {"safe": " ", "confirm": "!", "admin": "!"}.get(
                    meta.permission_level, "?"
                )
                name = meta.display_name or meta.name
                print(f"  {mark} {meta.name:<28} {name}")
        print(f"\n共 {len(metas)} 个技能（行首空=免确认，!=需要人工确认）")
        return 0
    finally:
        # 只查技能也初始化了 runtime（会建数据库连接），不收拾干净会留下锁文件
        await runtime.shutdown()


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
async def _cmd_run(args: argparse.Namespace) -> int:
    from ..agent.context import ContextPolicy
    from ..agent.engine import Agent, AgentConfig
    from ..config.paths import AppPaths
    from ..observability.tracer import Tracer
    from ..server.runtime import create_runtime
    from ..skill.base import SkillContext
    from ..skill.custom import persona_with_instructions

    runtime = create_runtime(AppPaths.resolve().ensure())
    await runtime.initialize()

    tracer = Tracer(enabled=bool(args.trace_file))
    try:
        session = await runtime.get_session(args.session, model_id=args.model)

        if args.assistant:
            profile = runtime.resolve_assistant(args.assistant)
            if profile is None:
                print(f"助手「{args.assistant}」不存在。", file=sys.stderr)
                return 2
            session.apply_assistant(profile)

        model_id = args.model or session.model_id or runtime.config.models.default_model
        llm = runtime.registry.get(model_id)

        settings = runtime.config.settings
        agent_cfg = settings.agent
        ctx = SkillContext(
            settings=settings,
            tracer=tracer,
            paths=runtime.paths,
            # 命令行里没有人能点"允许"，所以**不注入确认回调** ——
            # SkillContext 在无通道时默认拒绝，正是这里想要的行为
            audit=runtime.audit.record,
            session_id=session.id,
            workspace=runtime.workspace,
            path_policy=runtime.path_policy,
            extra=runtime.skill_services_for(session.assistant_id),
        )
        agent = Agent(
            llm=llm,
            utility_llm=runtime.utility_llm(llm),
            skill_manager=runtime.skills,
            memory=session.memory,
            config=AgentConfig(
                max_iterations=agent_cfg.max_iterations,
                temperature=agent_cfg.temperature,
                top_p=agent_cfg.top_p,
                frequency_penalty=agent_cfg.frequency_penalty,
                presence_penalty=agent_cfg.presence_penalty,
                # 提示词只由搭子的人格文档（+ 已启用的指导型技能）提供 ——
                # 这里曾有 ``system_prompt=session.system_prompt or
                # agent_cfg.system_prompt``（自定义 + 内置兜底那条链），已按用户
                # 要求整体退役。命令行与桌面端走同一份提示词，免得同一个人格在
                # 两种入口表现不同。
                persona=lambda: persona_with_instructions(  # type: ignore[arg-type,return-value]
                    runtime, session.assistant_id, session.enabled_skills
                ),
                # 与桌面端同一口径：展开成"内置 ∪ 自己的专属 ∪ 勾选的通用/我的"
                # （见 skill/groups.py）
                enabled_skills=runtime.skills.allowed_names(
                    assistant_id=session.assistant_id,
                    enabled_skills=session.enabled_skills,
                ),
                # 命令行和桌面端同一口径：专属技能按会话所属搭子过滤
                target_assistant=session.assistant_id or "",
                token_limit=runtime.effective_context_tokens(model_id),
                context_policy=ContextPolicy(
                    keep_recent=agent_cfg.keep_recent_messages,
                    compress_threshold=agent_cfg.compress_threshold,
                ),
                enable_planner=agent_cfg.enable_planner,
                enable_reflection=agent_cfg.enable_reflection,
                reflection_rounds=agent_cfg.reflection_rounds,
            ),
            ctx=ctx,
            tracer=tracer,
        )

        # 多轮任务里每轮都会产出文本，但**最终回答**是最后一轮的那段。
        # 用 message_end 记录它，而不是把所有轮次的文本拼起来 ——
        # 否则脚本里拿到的是"分析…、再查一下…、结论是 X"这种中间话。
        final_answer = ""
        async for event in agent.run_stream(args.prompt):
            if event.type == "delta":
                if not args.quiet:
                    # 增量直接写、不换行，观感接近真流式
                    sys.stdout.write(event.data.get("text", ""))
                    sys.stdout.flush()
            elif event.type == "message_end":
                final_answer = event.data.get("content") or ""
            elif event.type == "tool_call" and not args.quiet:
                name = event.data.get("display_name") or event.data.get("name")
                print(f"\n  ⚙ {name} …", file=sys.stderr)
            elif event.type == "tool_result" and not args.quiet:
                status = event.data.get("status")
                if status != "ok":
                    print(f"  ↳ {status}: {str(event.data.get('result'))[:160]}", file=sys.stderr)
            elif event.type == "error":
                print(f"\n[错误] {event.data.get('message')}", file=sys.stderr)

        # quiet 模式不逐段输出，最后一次性给最终回答 —— 这样它可以直接
        # 被 `$(...)` 或管道接走，不会混进工具调用的提示文字
        if args.quiet:
            print(final_answer)
        else:
            print()

        await runtime.persist_session(session)
        if args.trace_file:
            _write_trace(args.trace_file, tracer)
            if not args.quiet:
                print(f"\n执行记录已写入 {args.trace_file}", file=sys.stderr)
        return 0
    finally:
        await runtime.shutdown()


def _write_trace(target: str, tracer: Any) -> None:
    """把 Trace 写成 JSONL。

    **一行一个 span**，而不是一个整包 JSON：这种格式可以边写边读、
    可以 ``grep``、也可以用 ``jq`` 单查某一步。整包 JSON 在 trace 很长时
    必须全部读进内存才能看，而排查问题恰恰是"我只看那一个失败的 span"。
    """
    payload = tracer.export()
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        # 第一行是元信息，之后每行一个 span
        handle.write(
            json.dumps(
                {
                    "kind": "trace",
                    "trace_id": payload.get("trace_id"),
                    "started_at": payload.get("started_at"),
                    # ⚠️ 键名与 `Tracer.export()` 保持一致（`total_duration_ms`）。
                    # 以前这里写的是 `duration_ms`，而 `export()` 从没有那个键 ——
                    # 于是写出来的 trace 头耗时**恒为 null**，`replay` 打印
                    # 「耗时 Nonems」（下面读的就是这个键，两处必须同名）。
                    "total_duration_ms": payload.get("total_duration_ms"),
                    "usage": payload.get("usage"),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        for span in payload.get("spans") or []:
            handle.write(
                json.dumps({"kind": "span", **span}, ensure_ascii=False, default=str) + "\n"
            )


# --------------------------------------------------------------------------- #
# replay
# --------------------------------------------------------------------------- #
def _cmd_replay(args: argparse.Namespace) -> int:
    """回放 trace JSONL。

    回放**不重跑模型** —— 它只把记录重新呈现出来。想复现一次失败，
    需要的往往是看到"当时传了什么、拿到什么"，而不是再花一次钱重新生成
    （重新生成的结果也不会一模一样）。
    """
    path = Path(args.trace_file)
    if not path.is_file():
        print(f"文件不存在：{path}", file=sys.stderr)
        return 2

    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            # 只警告不中断：trace 文件可能被人工编辑过，
            # 因为一行坏格式就整份读不了，对排查反而是阻碍
            print(f"[警告] 第 {line_no} 行不是合法 JSON，已跳过", file=sys.stderr)

    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
        return 0

    header = next((r for r in records if r.get("kind") == "trace"), None)
    spans = [r for r in records if r.get("kind") == "span"]

    if header:
        print(f"trace {header.get('trace_id')}  耗时 {header.get('total_duration_ms')}ms")
        usage = header.get("usage") or {}
        if usage:
            print(
                f"  输入 {usage.get('prompt_tokens', 0)} / 输出 "
                f"{usage.get('completion_tokens', 0)} / 缓存命中 "
                f"{usage.get('cached_tokens', 0)}"
            )
    print(f"  共 {len(spans)} 个 span")
    if not spans:
        return 0

    # 用缩进体现父子层级，而不是只按时间平铺 —— 层级才是"哪一步最慢"的答案
    depth_of: dict[str, int] = {}
    for span in spans:
        parent = span.get("parent_id")
        depth_of[span.get("span_id") or ""] = depth_of.get(parent or "", -1) + 1

    for span in spans:
        indent = "  " * depth_of.get(span.get("span_id") or "", 0)
        status = span.get("status") or "-"
        mark = {"ok": "✓", "error": "✗", "cancelled": "⊘"}.get(status, "·")
        duration = span.get("duration_ms")
        took = f"{duration:.0f}ms" if isinstance(duration, (int, float)) else "-"
        print(f"{indent}{mark} {span.get('name'):<28} {took:>9}  {status}")
        if span.get("error"):
            print(f"{indent}    ! {span['error']}")
    return 0


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "skills":
        return asyncio.run(_cmd_skills(args))
    if args.command == "run":
        return asyncio.run(_cmd_run(args))
    if args.command == "replay":
        return _cmd_replay(args)

    build_parser().print_help()  # pragma: no cover - argparse 已保证不会到这
    return 1

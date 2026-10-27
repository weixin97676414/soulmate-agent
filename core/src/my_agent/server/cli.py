
















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

    
    skills = sub.add_parser("skills", help="查看已注册的技能")
    skills.add_argument("action", nargs="?", default="list", choices=["list"])
    skills.add_argument("--all", action="store_true", help="包含已禁用的技能")
    skills.add_argument("--json", action="store_true", help="输出 JSON")

    
    run = sub.add_parser("run", help="跑一次任务并把回答打到标准输出")
    run.add_argument("prompt", help="要交给智能体的问题或指令")
    run.add_argument("--session", help="沿用已有会话 id（默认新建）")
    run.add_argument("--model", help="指定模型 id（默认用配置里的默认模型）")
    run.add_argument("--assistant", help="使用某个助手预设")
    run.add_argument("--trace-file", help="把完整执行记录写成 JSONL（每行一个 span）")
    run.add_argument("--quiet", action="store_true", help="只输出最终回答，不显示工具调用")

    
    replay = sub.add_parser("replay", help="回放一份 trace JSONL")
    replay.add_argument("trace_file")
    replay.add_argument("--json", action="store_true")

    return parser





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
        
        await runtime.shutdown()





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
                
                
                
                
                
                persona=lambda: persona_with_instructions(  
                    runtime, session.assistant_id, session.enabled_skills
                ),
                
                
                enabled_skills=runtime.skills.allowed_names(
                    assistant_id=session.assistant_id,
                    enabled_skills=session.enabled_skills,
                ),
                
                target_assistant=session.assistant_id or "",
                token_limit=runtime.effective_context_tokens(model_id),
                supports_vision=getattr(llm, "supports_vision", False),
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

        
        
        
        final_answer = ""
        async for event in agent.run_stream(args.prompt):
            if event.type == "delta":
                if not args.quiet:
                    
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






    payload = tracer.export()
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        
        handle.write(
            json.dumps(
                {
                    "kind": "trace",
                    "trace_id": payload.get("trace_id"),
                    "started_at": payload.get("started_at"),
                    
                    
                    
                    
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





def _cmd_replay(args: argparse.Namespace) -> int:






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





def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "skills":
        return asyncio.run(_cmd_skills(args))
    if args.command == "run":
        return asyncio.run(_cmd_run(args))
    if args.command == "replay":
        return _cmd_replay(args)

    build_parser().print_help()  
    return 1

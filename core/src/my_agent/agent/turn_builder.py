























from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..skill.custom import persona_with_instructions
from .context import ContextPolicy
from .engine import AgentConfig

if TYPE_CHECKING:  
    from ..config.schemas import AssistantProfile
    from ..server.runtime import AppRuntime
    from .session import Session


def build_agent_config(
    *,
    runtime: AppRuntime,
    session: Session,
    profile: AssistantProfile | None,
    model_id: str,
    llm: Any,
    plan_decider: Any = None,
) -> AgentConfig:





    agent_cfg = runtime.config.settings.agent
    return AgentConfig(
        
        
        max_iterations=(
            profile.max_iterations
            if profile and profile.max_iterations
            else agent_cfg.max_iterations
        ),
        max_tool_calls_per_turn=(
            profile.max_tool_calls_per_turn
            if profile and profile.max_tool_calls_per_turn
            else agent_cfg.max_tool_calls_per_turn
        ),
        temperature=(
            profile.temperature
            if profile and profile.temperature is not None
            else agent_cfg.temperature
        ),
        
        
        top_p=agent_cfg.top_p,
        frequency_penalty=agent_cfg.frequency_penalty,
        presence_penalty=agent_cfg.presence_penalty,
        
        reasoning_effort=session.reasoning_effort,
        
        
        
        persona=lambda: persona_with_instructions(  
            runtime, session.assistant_id, session.enabled_skills
        ),
        same_tool_failure_tolerance=agent_cfg.same_tool_failure_tolerance,
        
        
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
        
        
        
        enable_planner=plan_decider is not None,
        plan_decider=plan_decider,
        enable_reflection=agent_cfg.enable_reflection,
        reflection_rounds=agent_cfg.reflection_rounds,
    )

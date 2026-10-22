











from __future__ import annotations

from my_agent.assistants import evolution


def test_task_name_uses_the_users_format() -> None:

    assert evolution.task_name("Soulmate") == "全员进化中 Soulmate"
    assert evolution.task_name("Love Buddy") == "全员进化中 Love Buddy"
    
    assert evolution.task_name("  小明  ") == "全员进化中 小明"
    
    assert evolution.task_name("") == "全员进化中"


def test_rule_never_touches_existing_text_and_is_idempotent() -> None:

    original = "# RULES\n\n我自己的规则：先看再改。\n"
    once = evolution.with_evolution_rule(original, "小明")

    assert "我自己的规则：先看再改。" in once
    assert evolution.SECTION_TITLE in once
    assert evolution.task_name("小明") in once

    
    assert evolution.with_evolution_rule(once, "小明") == once
    assert once.count(evolution.SECTION_TITLE) == 1


def test_rule_forbids_nagging_and_protects_itself() -> None:

    text = evolution.evolution_rule("小明")

    
    assert "30 天后再问一次" in text
    assert "别反复问" in text
    
    assert "同意就不再追问" not in text
    
    assert "不要删改它" in text
    
    assert "scheduled_task_create" in text
    assert "10080" in text
    assert "start_at" in text


def test_rule_gives_decidable_timings() -> None:





    text = evolution.evolution_rule("小明")

    assert "你记不记得我以前说过" in text
    assert "你又忘了" in text
    assert "记住" in text and "某件事" in text
    
    assert "在合适的时机" not in text


def test_rule_requires_the_log_and_checklist_in_the_task_prompt() -> None:

    text = evolution.evolution_rule("小明")

    assert "进化日志.md" in text
    assert "待验证清单" in text
    assert "32 KB" in text


def test_builtin_prompt_is_iterative_not_just_cleanup() -> None:

    text = evolution.builtin_prompt("Soulmate", "soulmate")

    assert "进化日志" in text
    assert "待验证" in text
    assert "证据" in text
    assert "指标：新增 N · 合并 N · 冲突消解 N · 待验证完成率 N/M" in text
    assert "32 KB" in text
    assert "最近 6 轮" in text
    assert "scheduled_task_update" in text
    
    assert len(set(evolution.EVOLUTION_FOCUS.values())) == len(evolution.EVOLUTION_FOCUS)
    for assistant_id, focus in evolution.EVOLUTION_FOCUS.items():
        here = evolution.builtin_prompt(assistant_id, assistant_id)
        assert focus in here
        
        assert sum(1 for other in evolution.EVOLUTION_FOCUS.values() if other in here) == 1


def test_unknown_buddy_falls_back_to_the_generic_focus() -> None:

    text = evolution.builtin_prompt("小明", "my-own")

    assert evolution.EVOLUTION_FOCUS_DEFAULT in text
    assert evolution.EVOLUTION_FOCUS["soulmate"] not in text


def test_legacy_prompt_is_frozen_for_the_upgrade_channel() -> None:





    legacy = evolution._legacy_builtin_prompt("小明")
    new = evolution.builtin_prompt("小明", "soulmate")

    assert legacy != new
    assert "最后用三段话收尾" in legacy
    assert "进化日志" not in legacy
    
    assert evolution._prompt_body(legacy) == legacy.split("\n", 1)[1]
    assert "小明" not in evolution._prompt_body(legacy)


def test_manager_review_uses_the_team_reading_channel() -> None:

    text = evolution.manager_review_prompt()

    assert "team_read_assistant_file" in text
    assert "memory_append" in text
    assert "进化日志" in text
    assert "下月重点" in text or "下个月的重点" in text

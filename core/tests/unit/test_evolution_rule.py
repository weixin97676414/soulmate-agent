"""「全员进化」共用约定的单元测试（任务名格式 + 初始规则正文）。

这三条各守护一件"错了也不会报错"的事：

- **任务名格式**：逐字给了格式（``全员进化中 `` + 搭子名，中间一个空格）。
  写成 ``全员进化中·Soulmate`` 之类照样能建任务、照样能跑，只是用户一眼就看出不是他要的。
- **幂等**：这段规则会在两条创建路径上被写进 RULES.md，重复追加会让文件越滚越长。
- **"不同意就不再追问"**：这句少了，搭子会每次聊天都问一遍，用户只觉得被骚扰。
"""

from __future__ import annotations

from my_agent.assistants import evolution


def test_task_name_uses_the_users_format() -> None:
    """``全员进化中 `` + 搭子名（中间**一个空格**，是用户原文里的）。"""
    assert evolution.task_name("Soulmate") == "全员进化中 Soulmate"
    assert evolution.task_name("Love Buddy") == "全员进化中 Love Buddy"
    # 前后空白要清掉：任务名以空格结尾，在列表里看着像坏的
    assert evolution.task_name("  小明  ") == "全员进化中 小明"
    # 名字为空也不该拼出"以空格结尾"的名字
    assert evolution.task_name("") == "全员进化中"


def test_rule_never_touches_existing_text_and_is_idempotent() -> None:
    """已有内容一个字不动；重复调用不重复追加。"""
    original = "# RULES\n\n我自己的规则：先看再改。\n"
    once = evolution.with_evolution_rule(original, "小明")

    assert "我自己的规则：先看再改。" in once
    assert evolution.SECTION_TITLE in once
    assert evolution.task_name("小明") in once

    # 第二次（例如 AI 又调了一次建搭子 / 补丁又跑了一遍）不该变成两份
    assert evolution.with_evolution_rule(once, "小明") == once
    assert once.count(evolution.SECTION_TITLE) == 1


def test_rule_forbids_nagging_and_protects_itself() -> None:
    """正文里那两句"防骚扰"与"防删改"的约束必须在。"""
    text = evolution.evolution_rule("小明")

    # 不写这句，模型很可能每次对话都问一遍
    assert "不同意就不再追问" in text
    # 说明这段是系统写的、别人不许删改（搭子自己读 RULES 时也会看到）
    assert "不要删改它" in text
    # 建任务的四件事要说全：名字 / 指令 / 间隔一周 / 起始时间
    assert "scheduled_task_create" in text
    assert "10080" in text
    assert "start_at" in text

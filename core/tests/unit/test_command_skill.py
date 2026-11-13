







from __future__ import annotations

import sys

import pytest

from my_agent.errors import SkillExecutionError
from my_agent.security.permission import risk_of
from my_agent.skill.base import SkillContext, SkillMeta
from my_agent.skill.builtin.command import BuddyRunCommandSkill
from my_agent.skill.groups import is_exclusive, owners_of


def _meta() -> SkillMeta:
    return SkillMeta(
        name="buddy_run_command",
        description="执行命令行",
        permission_level="confirm",
        source="builtin",
    )


def test_skill_is_exclusive_to_buddy_manager() -> None:

    assert is_exclusive("buddy_run_command")
    assert owners_of("buddy_run_command") == ("BuddyManager",)


def test_risk_is_high_so_it_can_never_be_remembered() -> None:

    assert risk_of(_meta()) == "high"


@pytest.mark.asyncio
async def test_runs_a_command_and_reports_exit_code() -> None:
    ctx = SkillContext()
    result = await BuddyRunCommandSkill().run(ctx, command="echo hello")

    assert result["exit_code"] == 0
    assert "hello" in result["stdout"]
    assert result["timed_out"] is False
    assert result["cwd"]


@pytest.mark.asyncio
async def test_nonzero_exit_is_reported_not_raised() -> None:

    ctx = SkillContext()
    cmd = "exit 3" if sys.platform.startswith("win") else "exit 3"
    result = await BuddyRunCommandSkill().run(ctx, command=cmd)

    assert result["exit_code"] != 0
    assert "退出码" in result["message"]


@pytest.mark.asyncio
async def test_timeout_kills_and_reports() -> None:

    ctx = SkillContext()
    slow = "ping -n 6 127.0.0.1 > nul" if sys.platform.startswith("win") else "sleep 6"
    result = await BuddyRunCommandSkill().run(ctx, command=slow, timeout=1)

    assert result["timed_out"] is True
    assert "强制终止" in result["message"]


@pytest.mark.asyncio
async def test_blank_command_is_rejected() -> None:





    ctx = SkillContext()
    with pytest.raises(SkillExecutionError) as exc:
        await BuddyRunCommandSkill().run(ctx, command="   ")
    assert "不能为空" in str(exc.value)


@pytest.mark.asyncio
async def test_bad_cwd_is_rejected() -> None:

    ctx = SkillContext()
    with pytest.raises(SkillExecutionError):
        await BuddyRunCommandSkill().run(
            ctx, command="echo hi", cwd="/这个目录不存在/绝不/可能/存在"
        )

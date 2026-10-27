







from __future__ import annotations

import pytest

from my_agent.errors import SkillPermissionError
from my_agent.security.permission import PermissionGuard, risk_of
from my_agent.skill.base import SkillContext, SkillMeta


def _meta(name: str, level: str = "confirm") -> SkillMeta:
    return SkillMeta(name=name, description="测试用", permission_level=level)  


def test_read_only_skills_are_low_risk() -> None:

    assert risk_of(_meta("read_file")) == "low"
    assert risk_of(_meta("list_dir")) == "low"
    assert risk_of(_meta("get_persona_files")) == "low"
    assert risk_of(_meta("kb_search")) == "low"
    
    assert risk_of(_meta("system_screenshot")) == "low"
    assert risk_of(_meta("computer_read_screen")) == "low"


def test_write_skills_are_medium() -> None:
    assert risk_of(_meta("write_file")) == "medium"
    assert risk_of(_meta("http_request")) == "medium"
    assert risk_of(_meta("update_model")) == "medium"


def test_destructive_skills_are_high() -> None:

    assert risk_of(_meta("delete_file")) == "high"
    assert risk_of(_meta("remove_dir")) == "high"
    assert risk_of(_meta("system_lock")) == "high"
    assert risk_of(_meta("system_shutdown")) == "high"
    assert risk_of(_meta("computer_mouse_click")) == "high"
    assert risk_of(_meta("computer_type_text")) == "high"
    assert risk_of(_meta("request_secret")) == "high"


def test_safe_and_admin_map_to_low_and_high() -> None:
    assert risk_of(_meta("anything", "safe")) == "low"
    assert risk_of(_meta("anything", "admin")) == "high"


@pytest.mark.asyncio
async def test_low_risk_confirm_does_not_ask_but_writes_audit() -> None:

    entries: list = []

    async def audit(entry) -> None:
        entries.append(entry)

    ctx = SkillContext(audit=audit)
    guard = PermissionGuard()

    await guard.check(_meta("read_file"), {}, ctx)

    assert len(entries) == 1
    assert entries[0].action == "auto_approved"
    assert entries[0].status == "auto_approved"
    assert entries[0].target == "read_file"


@pytest.mark.asyncio
async def test_medium_risk_still_asks_and_can_be_rejected() -> None:

    asked: list[str] = []

    async def confirm(request) -> bool:
        asked.append(request.skill_name)
        return False

    ctx = SkillContext(confirm=confirm)
    guard = PermissionGuard()

    with pytest.raises(SkillPermissionError):
        await guard.check(_meta("write_file"), {}, ctx)

    assert asked == ["write_file"]


@pytest.mark.asyncio
async def test_high_risk_is_never_auto_approved() -> None:

    ctx = SkillContext()
    guard = PermissionGuard()

    with pytest.raises(SkillPermissionError):
        await guard.check(_meta("delete_file", "admin"), {}, ctx)

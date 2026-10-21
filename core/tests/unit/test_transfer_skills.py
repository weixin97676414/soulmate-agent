






















from __future__ import annotations

import io
import json
import zipfile

import pytest

from my_agent.assistants.transfer import apply_buddy, parse_buddy_package
from my_agent.config.paths import AppPaths
from my_agent.config.schemas import CustomSkillDef
from my_agent.server.runtime import AppRuntime
from my_agent.skill.install import install_defs



GUIDE_ID = "xinjianxue-skill-self_qa-global"


def zip_bytes(files: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data if isinstance(data, bytes) else data.encode("utf-8"))
    return buffer.getvalue()


def guide_def(*, skill_id: str = GUIDE_ID, enabled: bool = True) -> CustomSkillDef:

    return CustomSkillDef(
        id=skill_id,
        name=skill_id,
        description="随包带的指导型技能",
        kind="instruction",
        instructions="照这段说明做事。",
        enabled=enabled,
    )


def buddy_zip(skills: list[str], *, extra: dict[str, str | bytes] | None = None) -> bytes:

    files: dict[str, str | bytes] = {
        "buddy.json": json.dumps(
            {
                "名称": "岸",
                "昵称": "岸",
                "说明": "从包里导入的搭子。",
                "soul.md": "# SOUL\n先行一步。",
                "技能名": skills,
            },
            ensure_ascii=False,
        )
    }
    files.update(extra or {})
    return zip_bytes(files)


def guide_pack_zip(skill_id: str = GUIDE_ID) -> bytes:

    return zip_bytes(
        {"skill.json": json.dumps({**guide_def(skill_id=skill_id).model_dump(), "enabled": True})}
    )


@pytest.fixture
async def runtime(tmp_path):
    rt = AppRuntime(AppPaths(tmp_path / "data").ensure())
    await rt.initialize()
    try:
        yield rt
    finally:
        await rt.shutdown()


def install(runtime: AppRuntime, defs: list[CustomSkillDef]) -> None:

    install_defs(runtime, defs, [])





async def test_guide_skill_is_not_reported_missing(runtime):

    install(runtime, [guide_def()])
    
    
    assert GUIDE_ID not in runtime.skills.all_names()

    outcome = await apply_buddy(
        runtime, parse_buddy_package(buddy_zip([GUIDE_ID]), "buddy-an-global.zip")
    )

    assert outcome["skills_missing"] == []
    assert GUIDE_ID in outcome["skills"]
    
    profile = runtime.assistants.get(outcome["assistant"]["id"])
    assert GUIDE_ID in profile.enabled_skills


async def test_guide_skill_name_is_not_reported_twice(runtime):






    install(runtime, [guide_def()])

    payload = buddy_zip([GUIDE_ID], extra={"skills/x.zip": guide_pack_zip()})
    outcome = await apply_buddy(runtime, parse_buddy_package(payload, "p.zip"))

    mentioned = [
        item for item in outcome["results"] if GUIDE_ID in json.dumps(item, ensure_ascii=False)
    ]
    assert mentioned, "至少要有一条关于这个技能的回报"
    assert outcome["skills_missing"] == []
    
    assert all(item.get("ok") for item in mentioned), mentioned


async def test_missing_skill_still_reported(runtime):

    outcome = await apply_buddy(
        runtime, parse_buddy_package(buddy_zip(["no-such-skill"]), "p.zip")
    )
    assert outcome["skills_missing"] == ["no-such-skill"]


async def test_skill_name_with_trailing_space_still_matches(runtime):

    install(runtime, [guide_def()])

    outcome = await apply_buddy(
        runtime, parse_buddy_package(buddy_zip([f"{GUIDE_ID} "]), "p.zip")
    )

    assert outcome["skills_missing"] == []
    assert GUIDE_ID in outcome["skills"]





async def test_pack_guide_skill_is_installed_and_configured(runtime):

    payload = buddy_zip([GUIDE_ID], extra={"skills/x.zip": guide_pack_zip()})
    outcome = await apply_buddy(runtime, parse_buddy_package(payload, "p.zip"))

    assert outcome["skills_missing"] == []
    assert GUIDE_ID in outcome["skills"]
    assert GUIDE_ID in runtime.assistants.get(outcome["assistant"]["id"]).enabled_skills


async def test_disabled_skill_used_by_pack_is_opened(runtime):






    install(runtime, [guide_def(enabled=False)])
    assert runtime.custom_skills.get(GUIDE_ID).enabled is False

    outcome = await apply_buddy(runtime, parse_buddy_package(buddy_zip([GUIDE_ID]), "p.zip"))

    assert runtime.custom_skills.get(GUIDE_ID).enabled is True
    assert any(
        "自动打开" in (item.get("message") or "") for item in outcome["results"]
    ), "打开了就要说，不能悄悄改配置"


async def test_only_used_skills_are_opened(runtime):

    other = "some-other-skill"
    install(runtime, [guide_def(enabled=False), guide_def(skill_id=other, enabled=False)])

    await apply_buddy(runtime, parse_buddy_package(buddy_zip([GUIDE_ID]), "p.zip"))

    assert runtime.custom_skills.get(GUIDE_ID).enabled is True
    assert runtime.custom_skills.get(other).enabled is False, "无关技能不该被动到"



from __future__ import annotations

from pathlib import Path

import pytest

from my_agent.errors import SkillExecutionError
from my_agent.skill.builtin.svg_tools import SvgCreateSkill, normalize_svg
from my_agent.storage.preview import build_preview


_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="60" viewBox="0 0 120 60">'
    '<rect width="120" height="60" fill="url(#g)"/></svg>'
)


async def test_creates_artifact_in_workspace(skill_env):

    result = await SvgCreateSkill().run(skill_env.ctx, filename="封面.svg", svg=_SVG, title="封面设计")

    written = skill_env.paths.artifacts_dir / "封面.svg"
    assert written.is_file()
    assert written.read_text(encoding="utf-8") == _SVG
    
    ids = {item.id for item in await skill_env.workspace.list_files(kind="artifact")}
    assert written.name in ids
    assert result["filename"] == "封面.svg"
    assert result["artifact"]["original_name"] == "封面.svg"


async def test_preview_builds_svg_payload(skill_env):





    result = await SvgCreateSkill().run(skill_env.ctx, filename="封面.svg", svg=_SVG)

    payload = build_preview(
        Path(result["file"]),
        original_name=result["filename"],
        mime=None,
        download_url="/v1/files/x?kind=artifact",
    )
    assert payload["kind"] == "svg"
    assert "<svg" in payload["content"]


async def test_strips_code_fence(skill_env):

    result = await SvgCreateSkill().run(
        skill_env.ctx, filename="a.svg", svg=f"```svg\n{_SVG}\n```"
    )
    assert (skill_env.paths.artifacts_dir / result["filename"]).read_text(encoding="utf-8") == _SVG


async def test_appends_svg_suffix(skill_env):
    result = await SvgCreateSkill().run(skill_env.ctx, filename="封面", svg=_SVG)
    assert result["filename"] == "封面.svg"


async def test_rejects_non_svg_text(skill_env):
    with pytest.raises(SkillExecutionError) as exc:
        await SvgCreateSkill().run(skill_env.ctx, filename="a.svg", svg="这是我想画的东西")
    assert "svg" in str(exc.value).lower()


async def test_rejects_script(skill_env):

    with pytest.raises(SkillExecutionError) as exc:
        await SvgCreateSkill().run(
            skill_env.ctx, filename="a.svg", svg=f"{_SVG[:-6]}<script>alert(1)</script></svg>"
        )
    assert "script" in str(exc.value)


async def test_rejects_unsafe_filename(skill_env):





    with pytest.raises(SkillExecutionError) as exc:
        await SvgCreateSkill().run(skill_env.ctx, filename="bad?.svg", svg=_SVG)
    assert "文件名" in str(exc.value)


async def test_drops_directory_from_filename(skill_env):

    result = await SvgCreateSkill().run(skill_env.ctx, filename=r"C:\Windows\封面.svg", svg=_SVG)
    assert result["filename"] == "封面.svg"
    assert (skill_env.paths.artifacts_dir / "封面.svg").is_file()


async def test_rejects_empty(skill_env):
    with pytest.raises(SkillExecutionError):
        await SvgCreateSkill().run(skill_env.ctx, filename="a.svg", svg="   ")


def test_normalize_keeps_plain_svg_untouched():
    assert normalize_svg(f"  {_SVG}  ") == _SVG

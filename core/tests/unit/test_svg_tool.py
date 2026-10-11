"""自由 SVG 技能：能落盘、能被登记（= 前端预览拿得到），非法输入要明确报错。"""

from __future__ import annotations

from pathlib import Path

import pytest

from my_agent.errors import SkillExecutionError
from my_agent.skill.builtin.svg_tools import SvgCreateSkill, normalize_svg
from my_agent.storage.preview import build_preview

# 不需要 pytest.mark.asyncio：pyproject 里 asyncio_mode = "auto"
_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="60" viewBox="0 0 120 60">'
    '<rect width="120" height="60" fill="url(#g)"/></svg>'
)


async def test_creates_artifact_in_workspace(skill_env):
    """正常路径：写进产物目录 + 登记成功（登记不上就等于前端看不见）。"""
    result = await SvgCreateSkill().run(skill_env.ctx, filename="封面.svg", svg=_SVG, title="封面设计")

    written = skill_env.paths.artifacts_dir / "封面.svg"
    assert written.is_file()
    assert written.read_text(encoding="utf-8") == _SVG
    # 产物列表里要能查到它 —— 这一条才是"预览能不能出图"的前提
    ids = {item.id for item in await skill_env.workspace.list_files(kind="artifact")}
    assert written.name in ids
    assert result["filename"] == "封面.svg"
    assert result["artifact"]["original_name"] == "封面.svg"


async def test_preview_builds_svg_payload(skill_env):
    """用户的验收口径是"**能成功预览**"，所以这里直接过一遍预览构建。

    只验"文件存在"是不够的：预览接口有自己的后缀分派（`preview.py`），
    哪天它不认这类文件了，产物照样在磁盘上，用户却是一片空白。
    """
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
    """模型常把内容包在 ```svg 里一起交上来，剥不干净就是一张破图。"""
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
    """预览走 `<img>` 不会执行脚本；但文件会被另存到用户目录，之后可能被浏览器打开。"""
    with pytest.raises(SkillExecutionError) as exc:
        await SvgCreateSkill().run(
            skill_env.ctx, filename="a.svg", svg=f"{_SVG[:-6]}<script>alert(1)</script></svg>"
        )
    assert "script" in str(exc.value)


async def test_rejects_unsafe_filename(skill_env):
    """文件名不合格要**明确报错**：登记失败只会记 warning，产物会静默消失在列表里。

    注意这里用 `bad?.svg` 而不是 `../x.svg`：目录部分会被 `Path(...).name` 丢掉
    （与 `artifact_output` 的取舍一致），所以要测的是"去掉目录之后仍然不合格"的名字。
    """
    with pytest.raises(SkillExecutionError) as exc:
        await SvgCreateSkill().run(skill_env.ctx, filename="bad?.svg", svg=_SVG)
    assert "文件名" in str(exc.value)


async def test_drops_directory_from_filename(skill_env):
    """模型给出路径时只取文件名，绝不按它写盘（防越界）。"""
    result = await SvgCreateSkill().run(skill_env.ctx, filename=r"C:\Windows\封面.svg", svg=_SVG)
    assert result["filename"] == "封面.svg"
    assert (skill_env.paths.artifacts_dir / "封面.svg").is_file()


async def test_rejects_empty(skill_env):
    with pytest.raises(SkillExecutionError):
        await SvgCreateSkill().run(skill_env.ctx, filename="a.svg", svg="   ")


def test_normalize_keeps_plain_svg_untouched():
    assert normalize_svg(f"  {_SVG}  ") == _SVG

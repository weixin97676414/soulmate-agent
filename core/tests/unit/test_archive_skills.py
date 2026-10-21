










from __future__ import annotations

import tarfile
import zipfile

import pytest

from my_agent.errors import SkillExecutionError
from my_agent.skill.builtin.archive import ArchiveListSkill, ArchiveReadSkill


def _snapshot(root) -> set[str]:

    return {str(path.relative_to(root)) for path in root.rglob("*")}


def _make_zip(tmp_path, name: str = "资料.zip"):

    target = tmp_path / name
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("说明.txt", "这是一份说明。\n第二行。\n")
        archive.writestr("sub/数据.md", "# 数据\n\n内容在这里。\n")
        archive.writestr("logo.bin", b"\x00\x01\x02binary")
    return target


@pytest.mark.asyncio
async def test_list_and_read_zip(skill_env, tmp_path):
    archive = _make_zip(tmp_path)

    listing = await ArchiveListSkill().run(skill_env.ctx, file_path=str(archive))

    assert listing["format"] == "zip"
    assert listing["file_count"] == 3
    names = {item["name"] for item in listing["entries"]}
    assert {"说明.txt", "sub/数据.md", "logo.bin"} <= names

    read = await ArchiveReadSkill().run(
        skill_env.ctx, file_path=str(archive), member="sub/数据.md"
    )
    assert "内容在这里" in read["content"]
    assert read["size"] > 0


@pytest.mark.asyncio
async def test_reading_never_writes_to_disk(skill_env, tmp_path):





    archive = _make_zip(tmp_path)
    before = _snapshot(tmp_path)

    await ArchiveListSkill().run(skill_env.ctx, file_path=str(archive))
    await ArchiveReadSkill().run(skill_env.ctx, file_path=str(archive), member="说明.txt")

    assert _snapshot(tmp_path) == before, "读取压缩包不该在磁盘上多出任何东西"


@pytest.mark.asyncio
async def test_binary_member_is_reported_not_garbled(skill_env, tmp_path):
    archive = _make_zip(tmp_path)

    result = await ArchiveReadSkill().run(
        skill_env.ctx, file_path=str(archive), member="logo.bin"
    )

    assert result["binary"] is True
    assert result["size"] > 0
    assert "二进制" in result["message"]
    assert "content" not in result, "二进制文件不该把乱码当成内容返回"


@pytest.mark.asyncio
async def test_missing_member_points_at_archive_list(skill_env, tmp_path):
    archive = _make_zip(tmp_path)

    with pytest.raises(SkillExecutionError) as exc:
        await ArchiveReadSkill().run(
            skill_env.ctx, file_path=str(archive), member="没有这个.txt"
        )

    assert "archive_list" in str(exc.value), "报错要告诉模型去哪儿拿准确的文件名"


@pytest.mark.asyncio
async def test_unsupported_format_says_why(skill_env, tmp_path):
    target = tmp_path / "压缩包.7z"
    target.write_bytes(b"7z\xbc\xaf\x27\x1c not really")

    with pytest.raises(SkillExecutionError) as exc:
        await ArchiveListSkill().run(skill_env.ctx, file_path=str(target))

    message = str(exc.value)
    assert "7z" in message
    assert "标准库" in message or "解压工具" in message, "要说清为什么不支持、以及怎么办"


@pytest.mark.asyncio
async def test_tar_gz_is_supported(skill_env, tmp_path):
    payload = tmp_path / "笔记.txt"
    payload.write_text("tar 里的内容\n", encoding="utf-8")
    target = tmp_path / "备份.tar.gz"
    with tarfile.open(target, "w:gz") as archive:
        archive.add(payload, arcname="笔记.txt")

    listing = await ArchiveListSkill().run(skill_env.ctx, file_path=str(target))
    assert listing["format"] == "tar"
    assert any(item["name"] == "笔记.txt" for item in listing["entries"])

    read = await ArchiveReadSkill().run(
        skill_env.ctx, file_path=str(target), member="笔记.txt"
    )
    assert "tar 里的内容" in read["content"]


@pytest.mark.asyncio
async def test_long_member_is_truncated_with_a_note(skill_env, tmp_path):
    target = tmp_path / "长文.zip"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("长文.txt", "很长的内容。" * 200)

    result = await ArchiveReadSkill().run(
        skill_env.ctx, file_path=str(target), member="长文.txt", max_chars=100
    )

    assert result["truncated"] is True
    assert len(result["content"]) == 100
    assert "max_chars" in result["note"], "截断要说明怎么继续读"

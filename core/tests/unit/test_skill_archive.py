







from __future__ import annotations

import io
import tarfile
import zipfile

import pytest

from my_agent.skill import archive


def make_zip(items: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as handle:
        for name, content in items.items():
            handle.writestr(name, content)
    return buffer.getvalue()


def make_targz(items: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as handle:
        for name, content in items.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            handle.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def names(packed: archive.PackageMembers) -> list[str]:
    return [name for name, _ in packed.members]





def test_zip_strips_a_single_top_level_directory():
    packed = archive.iter_members(
        make_zip({"my-skill/SKILL.md": "x", "my-skill/assets/a.txt": "y"}), "p.zip"
    )
    assert sorted(names(packed)) == ["SKILL.md", "assets/a.txt"]
    assert packed.root == "my-skill"
    assert packed.container == "zip"


def test_zip_keeps_a_flat_layout_untouched():

    packed = archive.iter_members(make_zip({"a.md": "x", "b.md": "y"}), "p.zip")
    assert sorted(names(packed)) == ["a.md", "b.md"]
    assert packed.root == ""


def test_zip_keeps_multiple_skill_folders_separate():

    packed = archive.iter_members(make_zip({"a/SKILL.md": "x", "b/SKILL.md": "y"}), "p.zip")
    assert sorted(names(packed)) == ["a/SKILL.md", "b/SKILL.md"]


def test_zip_blocks_path_traversal_and_reports_it():
    packed = archive.iter_members(
        make_zip({"SKILL.md": "x", "../../escaped.txt": "bad"}), "p.zip"
    )
    assert names(packed) == ["SKILL.md"]
    assert "../../escaped.txt" in packed.skipped


def test_zip_blocks_absolute_and_drive_paths():
    packed = archive.iter_members(
        make_zip({"/abs.txt": "a", "C:evil.txt": "b", "ok.txt": "c"}), "p.zip"
    )
    assert names(packed) == ["ok.txt"]
    assert len(packed.skipped) == 2





def test_targz_is_supported():
    packed = archive.iter_members(make_targz({"my/SKILL.md": "x"}), "p.tar.gz")
    assert names(packed) == ["SKILL.md"]
    assert packed.container == "tar"


def test_targz_skips_symlink_members():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as handle:
        data = b"hello"
        info = tarfile.TarInfo("real.txt")
        info.size = len(data)
        handle.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo("link.txt")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        handle.addfile(link)
    packed = archive.iter_members(buffer.getvalue(), "p.tar.gz")
    assert names(packed) == ["real.txt"]
    assert "link.txt" in packed.skipped


def test_single_file_becomes_one_member():
    packed = archive.iter_members("# 规矩\n".encode(), "SKILL.md")
    assert names(packed) == ["SKILL.md"]
    assert packed.container == "file"


def test_zip_is_detected_by_content_not_extension():

    packed = archive.iter_members(make_zip({"SKILL.md": "x"}), "mystery")
    assert names(packed) == ["SKILL.md"]
    assert packed.container == "zip"


def test_a_renamed_non_zip_is_treated_as_a_single_file():
    packed = archive.iter_members(b"just some words", "notes.txt")
    assert names(packed) == ["notes.txt"]





def test_oversized_package_is_rejected(monkeypatch):
    monkeypatch.setattr(archive, "MAX_PACKAGE_BYTES", 10)
    with pytest.raises(ValueError) as exc:
        archive.iter_members(b"x" * 100, "p.zip")
    assert "超过" in str(exc.value)


def test_too_many_members_is_rejected(monkeypatch):
    monkeypatch.setattr(archive, "MAX_MEMBERS", 2)
    with pytest.raises(ValueError) as exc:
        archive.iter_members(make_zip({"a.md": "1", "b.md": "2", "c.md": "3"}), "p.zip")
    assert "太多" in str(exc.value)


def test_unpacked_size_limit_is_enforced(monkeypatch):

    monkeypatch.setattr(archive, "MAX_UNPACKED_BYTES", 4)
    with pytest.raises(ValueError) as exc:
        archive.iter_members(make_zip({"a.md": "1234567890"}), "p.zip")
    assert "过大" in str(exc.value)


def test_bad_zip_reports_readable_error():
    with pytest.raises(ValueError) as exc:
        archive.iter_members(b"PK\x03\x04broken", "p.zip")
    assert "zip" in str(exc.value)





def test_directory_members_keep_nested_paths(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "SKILL.md").write_text("x", encoding="utf-8")
    (tmp_path / "sub" / "a.txt").write_text("y", encoding="utf-8")
    packed = archive.members_from_directory(tmp_path)
    assert sorted(names(packed)) == ["SKILL.md", "sub/a.txt"]
    assert packed.container == "folder"
    
    assert packed.root == ""


def test_directory_skips_engineering_noise(tmp_path):
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "index.js").write_text("x", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x", encoding="utf-8")
    (tmp_path / "SKILL.md").write_text("x", encoding="utf-8")
    packed = archive.members_from_directory(tmp_path)
    assert names(packed) == ["SKILL.md"]


def test_directory_rejects_empty_folder(tmp_path):
    with pytest.raises(ValueError) as exc:
        archive.members_from_directory(tmp_path)
    assert "没有任何文件" in str(exc.value)


def test_directory_missing_folder_is_friendly(tmp_path):
    with pytest.raises(ValueError) as exc:
        archive.members_from_directory(tmp_path / "nope")
    assert "不存在" in str(exc.value)


def test_zip_bomb_guard_rests_on_a_real_cpython_behavior():
















    import io
    import struct
    import zipfile
    import zlib

    real_size = 2 * 1024 * 1024
    declared = 1024

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("bomb.txt", b"\0" * real_size)
    raw = bytearray(buffer.getvalue())

    
    
    prefix_crc = zlib.crc32(b"\0" * declared)
    marker = b"PK\x01\x02"
    index = raw.find(marker)
    patched = False
    while index >= 0:
        name_len = struct.unpack_from("<H", raw, index + 28)[0]
        if bytes(raw[index + 46 : index + 46 + name_len]) == b"bomb.txt":
            struct.pack_into("<I", raw, index + 16, prefix_crc)
            struct.pack_into("<I", raw, index + 24, declared)
            local = struct.unpack_from("<I", raw, index + 42)[0]
            struct.pack_into("<I", raw, local + 14, prefix_crc)
            struct.pack_into("<I", raw, local + 22, declared)
            patched = True
            break
        index = raw.find(marker, index + 4)
    assert patched, "没改到中央目录，这条用例本身失效了（zip 结构变了？）"

    archive_file = zipfile.ZipFile(io.BytesIO(bytes(raw)))
    assert archive_file.getinfo("bomb.txt").file_size == declared
    assert len(archive_file.read("bomb.txt")) == declared, (
        "CPython 不再按声明的 file_size 截断了 —— archive.py 的 zip bomb 防护需要重做"
    )

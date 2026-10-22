












from __future__ import annotations

import httpx
import pytest

from my_agent.errors import PathNotAllowedError, SkillExecutionError
from my_agent.skill.builtin import file_tools, output_read
from my_agent.skill.builtin.file_tools import (
    FileReadParams,
    FileReadSkill,
    FileWriteParams,
    FileWriteSkill,
)
from my_agent.skill.builtin.http_tools import (
    HttpFetchSkill,
    HttpRequestParams,
    HttpRequestSkill,
    _send,
)
from my_agent.skill.builtin.output_read import ReadToolOutputParams, ReadToolOutputSkill


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)





def test_read_only_tools_are_safe_and_mutating_tools_need_confirm() -> None:
    assert HttpFetchSkill.meta.permission_level == "safe"
    assert FileReadSkill.meta.permission_level == "safe"
    assert ReadToolOutputSkill.meta.permission_level == "safe"
    
    
    
    assert HttpRequestSkill.meta.permission_level == "safe"
    assert FileWriteSkill.meta.permission_level == "confirm"





@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  
        "http://[fd00:ec2::254]/latest/meta-data/",  
        "http://[::ffff:169.254.169.254]/",  
        "file:///C:/Windows/win.ini",  
        "ftp://example.com/x",
    ],
)
async def test_metadata_and_bad_schemes_are_rejected(url: str) -> None:

    with pytest.raises(SkillExecutionError):
        await _send(method="GET", url=url, headers={}, body=None, timeout=5.0)


def test_localhost_is_deliberately_allowed() -> None:










    from my_agent.security.urls import validate_endpoint

    validate_endpoint("http://127.0.0.1:8000/x", field="t")
    validate_endpoint("http://192.168.1.1/x", field="t")





@pytest.mark.asyncio
async def test_large_response_is_returned_whole() -> None:






    big = b"z" * (2 * 1024 * 1024)  

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big)

    result = await _send(
        method="GET",
        url="https://example.com/big",
        headers={},
        body=None,
        timeout=5.0,
        transport=_transport(handler),
    )

    assert result["bytes"] == len(big)
    assert len(result["body"]) == len(big)
    
    assert "truncated" not in result


@pytest.mark.asyncio
async def test_normal_response_is_returned_whole() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content='{"hello": "世界"}'.encode(),
        )

    result = await _send(
        method="GET",
        url="https://example.com/api",
        headers={},
        body=None,
        timeout=5.0,
        transport=_transport(handler),
    )

    assert result["ok"] is True
    assert result["status_code"] == 200
    assert "世界" in result["body"]


@pytest.mark.asyncio
async def test_redirect_target_is_validated_too() -> None:






    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://169.254.169.254/"})

    with pytest.raises(SkillExecutionError):
        await _send(
            method="GET",
            url="https://example.com/redirect",
            headers={},
            body=None,
            timeout=5.0,
            transport=_transport(handler),
        )


@pytest.mark.asyncio
async def test_bad_method_is_rejected() -> None:
    skill = HttpRequestSkill()
    with pytest.raises(SkillExecutionError, match="不支持的方法"):
        await skill.run(
            None, **HttpRequestParams(method="TELEPORT", url="https://example.com").model_dump()
        )





@pytest.mark.asyncio
async def test_file_write_then_read_roundtrip(skill_env) -> None:
    target = skill_env.root / "notes" / "hello.txt"

    write = await FileWriteSkill().run(
        skill_env.ctx,
        **FileWriteParams(path=str(target), content="第一行\n第二行").model_dump(),
    )
    assert write["chars_written"] == 7
    
    
    assert target.read_bytes() == "第一行\n第二行".encode()

    read = await FileReadSkill().run(
        skill_env.ctx, **FileReadParams(path=str(target)).model_dump()
    )
    assert read["kind"] == "file"
    assert read["content"] == "第一行\n第二行"


@pytest.mark.asyncio
async def test_file_read_returns_whole_content(skill_env) -> None:

    target = skill_env.root / "big.txt"
    payload = "a" * 300_000  
    target.write_text(payload, encoding="utf-8")

    result = await FileReadSkill().run(
        skill_env.ctx, **FileReadParams(path=str(target)).model_dump()
    )

    assert result["content"] == payload
    assert "truncated" not in result
    assert "max_chars" not in result


@pytest.mark.asyncio
async def test_huge_file_hands_off_to_range_reader_instead_of_cutting(skill_env, monkeypatch) -> None:








    monkeypatch.setattr(file_tools, "WHOLE_READ_LIMIT_BYTES", 10)
    target = skill_env.root / "huge.log"
    target.write_text("x" * 1000, encoding="utf-8")

    result = await FileReadSkill().run(
        skill_env.ctx, **FileReadParams(path=str(target)).model_dump()
    )

    assert result["too_large_to_read_at_once"] is True
    
    
    assert "read_tool_output" in result["hint"]
    assert "next_offset" in result["hint"]
    
    assert "content" not in result


@pytest.mark.asyncio
async def test_file_append_keeps_existing_content(skill_env) -> None:
    target = skill_env.root / "append.txt"
    target.write_text("原有内容", encoding="utf-8")

    await FileWriteSkill().run(
        skill_env.ctx,
        **FileWriteParams(path=str(target), content="+新增", mode="append").model_dump(),
    )

    assert target.read_text(encoding="utf-8") == "原有内容+新增"


@pytest.mark.asyncio
async def test_file_list_directory(skill_env) -> None:
    folder = skill_env.root / "folder"
    (folder / "sub").mkdir(parents=True)
    (folder / "a.txt").write_text("x", encoding="utf-8")

    result = await FileReadSkill().run(
        skill_env.ctx, **FileReadParams(path=str(folder)).model_dump()
    )

    assert result["kind"] == "directory"
    names = [item["name"] for item in result["entries"]]
    
    assert names == ["sub", "a.txt"]
    assert "truncated" not in result


@pytest.mark.asyncio
async def test_file_list_directory_has_no_count_cap(skill_env) -> None:


    folder = skill_env.root / "many"
    folder.mkdir()
    for index in range(600):
        (folder / f"f{index:03d}.txt").write_text("", encoding="utf-8")

    result = await FileReadSkill().run(
        skill_env.ctx, **FileReadParams(path=str(folder)).model_dump()
    )

    assert result["count"] == 600


@pytest.mark.asyncio
async def test_path_outside_whitelist_is_rejected(skill_env) -> None:

    with pytest.raises(PathNotAllowedError):
        await FileReadSkill().run(
            skill_env.ctx, **FileReadParams(path="C:/Windows/System32/drivers/etc/hosts").model_dump()
        )


@pytest.mark.asyncio
async def test_gbk_file_is_decoded(skill_env) -> None:

    target = skill_env.root / "gbk.txt"
    target.write_bytes("中文内容".encode("gb18030"))

    result = await FileReadSkill().run(
        skill_env.ctx, **FileReadParams(path=str(target)).model_dump()
    )

    assert result["content"] == "中文内容"
    assert result["encoding"] in ("gb18030", "utf-8")


@pytest.mark.asyncio
async def test_write_rejects_unknown_mode(skill_env) -> None:
    with pytest.raises(SkillExecutionError, match="overwrite 或 append"):
        await FileWriteSkill().run(
            skill_env.ctx,
            **FileWriteParams(
                path=str(skill_env.root / "x.txt"), content="x", mode="truncate_all"
            ).model_dump(),
        )





@pytest.mark.asyncio
async def test_range_read_covers_whole_file_in_segments(skill_env) -> None:





    payload = "".join(f"第{i}行 内容\n" for i in range(2000))
    target = skill_env.root / "long.txt"
    
    
    with target.open("w", encoding="utf-8", newline="") as handle:
        handle.write(payload)

    skill = ReadToolOutputSkill()
    collected: list[str] = []
    offset = 0
    for _ in range(100):  
        result = await skill.run(
            skill_env.ctx,
            **ReadToolOutputParams(path=str(target), offset=offset, limit=1000).model_dump(),
        )
        collected.append(result["content"])
        if result["eof"]:
            break
        assert result["next_offset"] > offset, "next_offset 必须前进，否则模型会原地打转"
        offset = result["next_offset"]
    else:  
        raise AssertionError("分段读取没能读完文件")

    assert "".join(collected) == payload


@pytest.mark.asyncio
async def test_range_read_single_call_when_it_fits(skill_env) -> None:
    target = skill_env.root / "small.txt"
    target.write_text("短内容", encoding="utf-8")

    result = await ReadToolOutputSkill().run(
        skill_env.ctx, **ReadToolOutputParams(path=str(target)).model_dump()
    )

    assert result["content"] == "短内容"
    assert result["eof"] is True


@pytest.mark.asyncio
async def test_range_read_rejects_directory(skill_env) -> None:
    folder = skill_env.root / "d"
    folder.mkdir()

    with pytest.raises(SkillExecutionError, match="是目录"):
        await ReadToolOutputSkill().run(
            skill_env.ctx, **ReadToolOutputParams(path=str(folder)).model_dump()
        )


def test_range_read_window_bound_is_declared_in_schema() -> None:









    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ReadToolOutputParams(path="x.txt", limit=output_read.MAX_WINDOW_CHARS + 1)

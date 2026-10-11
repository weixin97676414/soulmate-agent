"""新增能力「HTTP 请求」「本地文件读写」「分段读取」的回归测试。

重点不是"正常路径能不能用"，而是两类边界：

1. **安全**：内网/云元数据地址必须被拒（SSRF）、文件路径必须过白名单；
2. **不丢内容**（本轮的硬要求）：响应体与文件内容**完整返回**，
   任何"装不下"都必须以"可续读"的方式表达，**不允许截断或省略**。

权限级别也在这里钉住：只读走 safe（不打扰用户），会改东西的走 confirm ——
**例外**是 `http_request`：点名要求它免批准且永久开启
（见 `my_agent/skill/locked.py` 与 `http_tools.py` 的模块说明）。
"""

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


# --------------------------------------------------------------------------- #
# 权限级别：读写必须分开
# --------------------------------------------------------------------------- #
def test_read_only_tools_are_safe_and_mutating_tools_need_confirm() -> None:
    assert HttpFetchSkill.meta.permission_level == "safe"
    assert FileReadSkill.meta.permission_level == "safe"
    assert ReadToolOutputSkill.meta.permission_level == "safe"
    # http_request 是**用户点名的例外**：它照样可能改对方的真实数据，但产品要求
    # AI 直接用、不弹确认（"很多能力要靠它拿数据"）。写文件的 FileWriteSkill
    # 仍然保持 confirm —— 免批准的口径只覆盖用户列出的那九个技能。
    assert HttpRequestSkill.meta.permission_level == "safe"
    assert FileWriteSkill.meta.permission_level == "confirm"


# --------------------------------------------------------------------------- #
# SSRF
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # 云元数据服务
        "http://[fd00:ec2::254]/latest/meta-data/",  # 它的 IPv6 地址
        "http://[::ffff:169.254.169.254]/",  # IPv4 映射形式的伪装
        "file:///C:/Windows/win.ini",  # 非 http 协议
        "ftp://example.com/x",
    ],
)
async def test_metadata_and_bad_schemes_are_rejected(url: str) -> None:
    """云元数据地址与非 http(s) 协议一律拒绝，且**在发请求之前**就拒绝。"""
    with pytest.raises(SkillExecutionError):
        await _send(method="GET", url=url, headers={}, body=None, timeout=5.0)


def test_localhost_is_deliberately_allowed() -> None:
    """回环与内网地址是**刻意放行**的，这里把它钉成明确的行为而不是遗漏。

    理由：这是个本地桌面应用，用户完全可能让搭子去访问"我自己跑的那个服务"
    （``http://127.0.0.1:8000``）或内网的 NAS、局域网接口。一律拦掉会把
    正常用法也一起禁掉，而这一层真正要防的是**云元数据端点**——那才是
    "被诱导去读机器凭证"的经典目标，它已经被挡住了。

    这条断言的意义：如果哪天有人把 localhost 也加到拦截名单里，
    这个测试会失败，从而被迫**显式地**做这个决定，而不是顺手改掉。
    """
    from my_agent.security.urls import validate_endpoint

    validate_endpoint("http://127.0.0.1:8000/x", field="t")
    validate_endpoint("http://192.168.1.1/x", field="t")


# --------------------------------------------------------------------------- #
# 响应体：**完整返回，不截断**
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_large_response_is_returned_whole() -> None:
    """大响应必须**完整**返回。

    曾经这里有一个 512KB 的上限：超了就 break 并把 truncated=True 交出去。
    用户明确要求取消它 —— "很多用户的外部服务是花钱买的，我们没有资格给别人
    截掉或者省略"，我们没有依据替用户判断"512KB 之后的内容不重要"。
    """
    big = b"z" * (2 * 1024 * 1024)  # 2MB，是旧上限的 4 倍

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
    # 旧的 truncated 字段不该再出现：它本身就是"我们砍了内容"的自白
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
    """**重定向之后的地址也要过校验**。

    只验初始地址的话，一个公开可访问的地址就能把我们跳到内网去 ——
    这正是 SSRF 最常见的绕过方式。
    """

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


# --------------------------------------------------------------------------- #
# 文件读写
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_file_write_then_read_roundtrip(skill_env) -> None:
    target = skill_env.root / "notes" / "hello.txt"

    write = await FileWriteSkill().run(
        skill_env.ctx,
        **FileWriteParams(path=str(target), content="第一行\n第二行").model_dump(),
    )
    assert write["chars_written"] == 7
    # 换行必须是**原样**写入：Windows 上文本模式会把 \n 翻成 \r\n，
    # 对 shell 脚本、配置文件这类东西是实打实的破坏。
    assert target.read_bytes() == "第一行\n第二行".encode()

    read = await FileReadSkill().run(
        skill_env.ctx, **FileReadParams(path=str(target)).model_dump()
    )
    assert read["kind"] == "file"
    assert read["content"] == "第一行\n第二行"


@pytest.mark.asyncio
async def test_file_read_returns_whole_content(skill_env) -> None:
    """读文件**不做字符数上限**（曾经有 200000 字符的截断）。"""
    target = skill_env.root / "big.txt"
    payload = "a" * 300_000  # 超过旧上限 200000
    target.write_text(payload, encoding="utf-8")

    result = await FileReadSkill().run(
        skill_env.ctx, **FileReadParams(path=str(target)).model_dump()
    )

    assert result["content"] == payload
    assert "truncated" not in result
    assert "max_chars" not in result


@pytest.mark.asyncio
async def test_huge_file_hands_off_to_range_reader_instead_of_cutting(skill_env, monkeypatch) -> None:
    """超过内存护栏的文件：**不读、也不切**，而是转交分段读取。

    这是本轮最需要守住的一条边界。"转交"与"截断"的区别在于：
    - 截断：内容丢了，模型拿不回来；
    - 转交：内容一条不少，模型按区间分几次读完。

    用 monkeypatch 把护栏压到 10 字节，避免为了测试造一个 32MB 的文件。
    """
    monkeypatch.setattr(file_tools, "WHOLE_READ_LIMIT_BYTES", 10)
    target = skill_env.root / "huge.log"
    target.write_text("x" * 1000, encoding="utf-8")

    result = await FileReadSkill().run(
        skill_env.ctx, **FileReadParams(path=str(target)).model_dump()
    )

    assert result["too_large_to_read_at_once"] is True
    # 必须**明确告诉模型怎么办**，且给的是可照抄的调用示例 ——
    # 否则"太大了"这三个字在模型眼里就是"这次拿不到"
    assert "read_tool_output" in result["hint"]
    assert "next_offset" in result["hint"]
    # 不能出现"被砍掉的内容"
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
    # 目录排在文件前面（便于一眼看清结构）
    assert names == ["sub", "a.txt"]
    assert "truncated" not in result


@pytest.mark.asyncio
async def test_file_list_directory_has_no_count_cap(skill_env) -> None:
    """列目录不做数量上限：用户问的是"这里有哪些文件"，
    给他前 500 个等于让他以为这就是全部（而且不会察觉少了什么）。"""
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
    """白名单之外的路径必须被拒 —— 这是这一层唯一的防线。"""
    with pytest.raises(PathNotAllowedError):
        await FileReadSkill().run(
            skill_env.ctx, **FileReadParams(path="C:/Windows/System32/drivers/etc/hosts").model_dump()
        )


@pytest.mark.asyncio
async def test_gbk_file_is_decoded(skill_env) -> None:
    """GBK 文本文件要能读出来（国内用户的老 txt/csv 很常见）。"""
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


# --------------------------------------------------------------------------- #
# 分段读取：它是"无损外置"的另一半
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_range_read_covers_whole_file_in_segments(skill_env) -> None:
    """分段读到底必须拿到**与原文完全一致**的内容。

    这是"内容可以不在上下文里，但绝不可以不可达"这条原则的验证点：
    把多次分段的结果拼起来，必须一字不差。
    """
    payload = "".join(f"第{i}行 内容\n" for i in range(2000))
    target = skill_env.root / "long.txt"
    # newline="" 才是"把这段字符原样写进去"：文本模式会把 \n 翻成 \r\n，
    # 那样比对的就是另一份内容了（这条测试要验证"逐字符一致"）
    with target.open("w", encoding="utf-8", newline="") as handle:
        handle.write(payload)

    skill = ReadToolOutputSkill()
    collected: list[str] = []
    offset = 0
    for _ in range(100):  # 上限只是防止测试自身死循环
        result = await skill.run(
            skill_env.ctx,
            **ReadToolOutputParams(path=str(target), offset=offset, limit=1000).model_dump(),
        )
        collected.append(result["content"])
        if result["eof"]:
            break
        assert result["next_offset"] > offset, "next_offset 必须前进，否则模型会原地打转"
        offset = result["next_offset"]
    else:  # pragma: no cover - 循环没读完说明实现有问题
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
    """单次窗口的上界必须**写在 schema 里**，而不是靠运行期偷偷截断。

    为什么强调这一点：schema 上的界会被框架转成一条"参数不合法，请修正后重试"
    的工具错误交给模型（见 ``skill/manager.py`` 的 ``SkillValidationError`` 分支），
    模型看得懂、能自己改；而"运行期偷偷按上限切"就是又一次无声的内容丢失。

    还要注意这里拒绝的是"这一次读多少"，不是"能读到多少内容" ——
    内容一直在文件里，模型改小 limit 分几次读就能全部拿到。
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ReadToolOutputParams(path="x.txt", limit=output_read.MAX_WINDOW_CHARS + 1)

"""对话里的本机图片：核心侧代理读图（``/v1/media/local-image``）。

渲染层加载不了本机路径（``D:\\tmp\\x.png`` 不是合法 URL，``file://`` 在开发态与生产 CSP 下
都拿不到），所以由核心读文件回字节。这一组守的是**这个接口不能被当成"任意读盘"用**：
只认图片扩展名、拒绝网络路径、白名单照旧生效；而失败时必须给得出**人话**
（前端把那句话直接显示给用户 —— 破图是最不可接受的失败方式，用户明确说过这点）。
"""

from __future__ import annotations

import pytest

from my_agent.security.paths import PathPolicy

# 接口只看扩展名与大小、不解码图片内容（这层不该引入图像库），所以用假字节就够。
IMAGE_BYTES = b"\x89PNG\r\n\x1a\n" + b"not-a-real-png-but-the-route-does-not-decode"


def _make_image(directory, name: str = "chart.png") -> str:
    target = directory / name
    target.write_bytes(IMAGE_BYTES)
    return str(target)


async def _get(client, path: str):
    return await client.get("/v1/media/local-image", params={"path": path})


@pytest.mark.asyncio
async def test_serves_a_local_image(client, tmp_path):
    target = _make_image(tmp_path)
    response = await _get(client, target)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/png")
    assert response.content == IMAGE_BYTES


@pytest.mark.asyncio
async def test_missing_file_reports_a_readable_reason(client, tmp_path):
    """文件不存在要给得出原因（前端原样显示），不能只回一个 404。"""
    missing = str(tmp_path / "nope.png")
    response = await _get(client, missing)
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "不存在" in detail and "nope.png" in detail


@pytest.mark.asyncio
async def test_non_image_extension_is_refused(client, tmp_path):
    """只认图片扩展名 —— 否则它就是一个能读任意文件的接口。"""
    secret = tmp_path / "secret.txt"
    secret.write_text("机密", encoding="utf-8")
    response = await _get(client, str(secret))
    assert response.status_code == 415
    assert "格式" in response.json()["detail"]


@pytest.mark.asyncio
async def test_network_path_is_refused(client):
    """UNC 路径必须拒：Windows 会向那台机器发起 SMB 认证，可能泄露本机凭据。"""
    response = await _get(client, r"\\evil-server\share\a.png")
    assert response.status_code == 403
    assert "网络路径" in response.json()["detail"]


@pytest.mark.asyncio
async def test_relative_path_is_refused(client, tmp_path):
    """相对路径指向哪里完全取决于进程的工作目录 —— 不如直接说清楚要绝对路径。"""
    response = await _get(client, "chart.png")
    assert response.status_code == 400
    assert "绝对路径" in response.json()["detail"]


@pytest.mark.asyncio
async def test_directory_is_refused(client, tmp_path):
    folder = tmp_path / "images.png"  # 用图片扩展名命名，确保拦它的是"是目录"而不是格式
    folder.mkdir()
    response = await _get(client, str(folder))
    assert response.status_code == 400
    assert "文件夹" in response.json()["detail"]


@pytest.mark.asyncio
async def test_oversized_image_is_refused(client, tmp_path, monkeypatch):
    """上限是"别把几十 MB 读进内存"，所以按**声明大小**先拒，而不是读完再说。"""
    from my_agent.server.routes import media

    monkeypatch.setattr(media, "MAX_LOCAL_IMAGE_BYTES", 8)
    target = _make_image(tmp_path)
    response = await _get(client, target)
    assert response.status_code == 413
    assert "过大" in response.json()["detail"]


@pytest.mark.asyncio
async def test_data_stream_syntax_is_refused(client, tmp_path):
    """NTFS 数据流写法（``a.png:ads``）读的不是那个文件本身，语法校验要先拦住它。"""
    target = _make_image(tmp_path)
    response = await _get(client, f"{target}:hidden")
    assert response.status_code == 403
    assert "数据流" in response.json()["detail"]


@pytest.mark.asyncio
async def test_whitelist_still_applies(client, runtime, tmp_path):
    """用户配了「文件访问白名单」时，这里也要守 —— 与技能读文件同一套规则。"""
    allowed = tmp_path / "允许目录"
    allowed.mkdir()
    outside = tmp_path / "别处"
    outside.mkdir()
    target = _make_image(outside)
    runtime.path_policy = PathPolicy([str(allowed)])

    response = await _get(client, target)
    assert response.status_code == 403
    assert "白名单之外" in response.json()["detail"]

    inside = _make_image(allowed)
    ok = await _get(client, inside)
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_percent_encoded_path_is_retried(client, tmp_path):
    """模型把带空格的路径按 URL 规矩写成 ``my%20dir/a.png`` —— 字面查找必然 404，
    所以查不到且含 ``%`` 时按解码后的路径再试一次（以文件是否真存在为准）。"""
    folder = tmp_path / "my dir"
    folder.mkdir()
    target = _make_image(folder, "chart.png")
    encoded = target.replace("my dir", "my%20dir")
    assert encoded != target

    response = await _get(client, encoded)
    assert response.status_code == 200, response.text
    assert response.content == IMAGE_BYTES

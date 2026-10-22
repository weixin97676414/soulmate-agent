







from __future__ import annotations

import pytest

from my_agent.security.paths import PathPolicy


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

    missing = str(tmp_path / "nope.png")
    response = await _get(client, missing)
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "不存在" in detail and "nope.png" in detail


@pytest.mark.asyncio
async def test_non_image_extension_is_refused(client, tmp_path):

    secret = tmp_path / "secret.txt"
    secret.write_text("机密", encoding="utf-8")
    response = await _get(client, str(secret))
    assert response.status_code == 415
    assert "格式" in response.json()["detail"]


@pytest.mark.asyncio
async def test_network_path_is_refused(client):

    response = await _get(client, r"\\evil-server\share\a.png")
    assert response.status_code == 403
    assert "网络路径" in response.json()["detail"]


@pytest.mark.asyncio
async def test_relative_path_is_refused(client, tmp_path):

    response = await _get(client, "chart.png")
    assert response.status_code == 400
    assert "绝对路径" in response.json()["detail"]


@pytest.mark.asyncio
async def test_directory_is_refused(client, tmp_path):
    folder = tmp_path / "images.png"  
    folder.mkdir()
    response = await _get(client, str(folder))
    assert response.status_code == 400
    assert "文件夹" in response.json()["detail"]


@pytest.mark.asyncio
async def test_oversized_image_is_refused(client, tmp_path, monkeypatch):

    from my_agent.server.routes import media

    monkeypatch.setattr(media, "MAX_LOCAL_IMAGE_BYTES", 8)
    target = _make_image(tmp_path)
    response = await _get(client, target)
    assert response.status_code == 413
    assert "过大" in response.json()["detail"]


@pytest.mark.asyncio
async def test_data_stream_syntax_is_refused(client, tmp_path):

    target = _make_image(tmp_path)
    response = await _get(client, f"{target}:hidden")
    assert response.status_code == 403
    assert "数据流" in response.json()["detail"]


@pytest.mark.asyncio
async def test_whitelist_still_applies(client, runtime, tmp_path):

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


    folder = tmp_path / "my dir"
    folder.mkdir()
    target = _make_image(folder, "chart.png")
    encoded = target.replace("my dir", "my%20dir")
    assert encoded != target

    response = await _get(client, encoded)
    assert response.status_code == 200, response.text
    assert response.content == IMAGE_BYTES

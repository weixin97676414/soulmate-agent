"""搭子 / 搭子群导入接口的端到端：上传 → 落盘 → 再导一次仍然幂等。

单元测试已经覆盖了"解析与落盘"，这里验的是**接口这一层**：路由能收 zip、
路径不会与 ``/{assistant_id}`` 打架、失败时给出的是 4xx + 人话而不是 500。
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from my_agent.config.paths import AppPaths
from my_agent.server.runtime import AppRuntime

from .conftest import make_client, serve_runtime

_BUDDY = {
    "名称": "端到端搭子",
    "昵称": "小端",
    "说明": "接口测试用的搭子。",
    "soul.md": "# SOUL\n端到端语气。",
    "rules.md": "# RULES\n端到端规则。",
    "技能名": [],
}

_SKILL = {
    "id": "e2e-skill",
    "name": "端到端技能",
    "description": "演示技能",
    "kind": "instruction",
    "instructions": "照做。",
}


def zip_bytes(files: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data if isinstance(data, bytes) else data.encode("utf-8"))
    return buffer.getvalue()


@pytest.fixture
async def live(tmp_path):
    runtime = AppRuntime(AppPaths(tmp_path / "data").ensure())
    await runtime.initialize()
    try:
        async with serve_runtime(runtime) as url:
            async with make_client(url) as client:
                yield runtime, client
    finally:
        await runtime.shutdown()


async def test_import_buddy_then_again(live):
    runtime, client = live
    payload = zip_bytes(
        {
            "buddy.json": json.dumps(_BUDDY, ensure_ascii=False),
            "skills/e2e-skill.zip": zip_bytes({"skill.json": json.dumps(_SKILL, ensure_ascii=False)}),
        }
    )

    first = await client.post(
        "/v1/assistants/import",
        files={"package": ("端到端搭子.zip", payload, "application/zip")},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["action"] == "create"
    assistant_id = body["assistant"]["id"]
    assert runtime.assistants.get(assistant_id) is not None

    # 技能既装上了、也配给了这个搭子
    profile = runtime.assistants.get(assistant_id)
    assert profile is not None and "e2e-skill" in profile.enabled_skills

    # 再导一次：不重复建、不重复装
    second = await client.post(
        "/v1/assistants/import",
        files={"package": ("端到端搭子.zip", payload, "application/zip")},
    )
    assert second.status_code == 200, second.text
    assert second.json()["action"] == "update"
    assert [item.name for item in runtime.assistants.sorted()].count("端到端搭子") == 1
    assert [item.id for item in runtime.custom_skills.skills] == ["e2e-skill"]


async def test_import_group(live):
    runtime, client = live
    payload = zip_bytes(
        {
            "group.json": json.dumps({"name": "端到端小队"}, ensure_ascii=False),
            "buddies/甲/buddy.json": json.dumps({**_BUDDY, "名称": "甲"}, ensure_ascii=False),
            "buddies/乙/buddy.json": json.dumps({**_BUDDY, "名称": "乙"}, ensure_ascii=False),
        }
    )
    response = await client.post(
        "/v1/assistants/import-group",
        files={"package": ("端到端小队.zip", payload, "application/zip")},
    )
    assert response.status_code == 200, response.text
    group = runtime.groups.get(response.json()["group"]["id"])
    assert group is not None and group.name == "端到端小队"
    assert len(group.member_assistant_ids) == 2


async def test_bad_package_returns_400_with_reason(live):
    """坏包要 400 + 人话，不能是 500 —— 前端把 detail 原样展示给用户。"""
    _, client = live
    response = await client.post(
        "/v1/assistants/import",
        files={"package": ("乱写.zip", zip_bytes({"readme.txt": "不是搭子包"}), "application/zip")},
    )
    assert response.status_code == 400
    assert "搭子" in response.json()["detail"]


async def test_import_routes_do_not_shadow_assistant_id(live):
    """字面量路由排在 `/{assistant_id}` 之前，别被路径参数吃掉。"""
    runtime, client = live
    response = await client.get("/v1/assistants")
    assert response.status_code == 200
    assert response.json()["assistants"], "至少要有内置搭子"









from __future__ import annotations

import io
import json
import zipfile

import pytest

from my_agent.skill.custom import collect_instructions, persona_with_instructions

from .conftest import make_client


@pytest.fixture
async def http(base_url):
    async with make_client(base_url) as client:
        yield client


def make_zip(files: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def skill_json(**overrides) -> str:
    payload = {
        "id": "weather-proxy",
        "name": "天气代理",
        "description": "查询指定城市的天气",
        "kind": "http",
        "url": "https://example.com/weather?city={city}",
        "params": [{"name": "city", "description": "城市名", "required": True}],
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


async def upload(http, data: bytes, filename: str = "pack.zip"):
    return await http.post(
        "/v1/skills/custom/import",
        files={"package": (filename, data, "application/zip")},
    )





async def test_import_actionable_skill(runtime, http):
    resp = await upload(http, make_zip({"skill.json": skill_json()}))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["results"][0]["ok"] is True
    assert body["results"][0]["kind"] == "http"

    listing = (await http.get("/v1/skills/custom")).json()
    assert any(item["id"] == "weather-proxy" for item in listing["skills"])


async def test_import_skill_md_only_becomes_instruction(runtime, http):

    resp = await upload(
        http, make_zip({"SKILL.md": "# 规矩\n\n永远先问清楚城市再查天气。"})
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["results"][0]["kind"] == "instruction"

    listing = (await http.get("/v1/skills/custom")).json()
    defn = next(item for item in listing["skills"] if item["kind"] == "instruction")
    assert "先问清楚城市" in defn["instructions"]


async def test_import_both_files_installs_both(runtime, http):

    resp = await upload(
        http,
        make_zip({"skill.json": skill_json(), "SKILL.md": "天气数据可能有延迟，要说明。"}),
    )
    assert resp.status_code == 200, resp.text
    kinds = sorted(item["kind"] for item in resp.json()["results"])
    assert kinds == ["http", "instruction"]


async def test_import_bad_json_reports_but_does_not_block(runtime, http):

    resp = await upload(
        http,
        make_zip({"skill.json": "{ not json", "SKILL.md": "兜底指导仍然有效。"}),
    )
    body = resp.json()
    assert body["results"][0]["ok"] is False
    assert body["results"][-1]["ok"] is True  


async def test_import_rejects_non_zip(http):
    resp = await upload(http, b"this is not a zip")
    assert resp.status_code == 400


async def test_import_rejects_package_without_any_skill(http):








    resp = await upload(http, make_zip({"readme.txt": b"nothing here"}))
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "没有找到任何技能" in detail
    
    
    assert "readme.txt" in detail


async def test_import_plain_markdown_becomes_instruction(http):

    resp = await upload(http, make_zip({"guide.md": "# 写作规矩\n\n先列提纲再写。"}))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["results"][0]["ok"] is True
    assert body["results"][0]["kind"] == "instruction"
    assert body["results"][0]["source_format"] == "plain-md"





async def test_instruction_reaches_system_prompt(runtime, http):





    resp = await upload(http, make_zip({"SKILL.md": "回复必须以「收到」开头。"}))
    skill_id = resp.json()["installed"][0]["id"]

    
    
    text = persona_with_instructions(runtime, "office", [skill_id])
    assert "回复必须以「收到」开头" in text


async def test_instruction_respects_global_disable(runtime, http):
    resp = await upload(http, make_zip({"SKILL.md": "被禁用后不该出现。"}))
    skill_id = resp.json()["installed"][0]["id"]
    config = runtime.custom_skills.model_copy(deep=True)
    config.skills[0].enabled = False
    runtime.reload_custom_skills(config)

    
    assert collect_instructions(runtime.custom_skills, {skill_id}) == []
    
    
    
    assert "被禁用后不该出现" not in persona_with_instructions(runtime, "office", [skill_id])





_LONG_BODY = "第一步：先查城市。第二步：再查天气。" * 60  





_LONG_MD = f"---\nname: 长技能\ndescription: 触发：要查天气时用它。\n---\n\n{_LONG_BODY}\n"


async def test_长技能只给路径不给正文(runtime, http):









    resp = await upload(http, make_zip({"SKILL.md": _LONG_MD}))
    skill_id = resp.json()["installed"][0]["id"]
    folder = runtime.paths.skills_dir / skill_id

    sections = collect_instructions(
        runtime.custom_skills,
        
        
        
        
        {skill_id, "file_read", "calc"},
        package_dirs={skill_id: str(folder)},
    )
    assert len(sections) == 1
    text = sections[0][1]
    assert "第二步：再查天气" not in text, "正文不该整份进 system"
    assert str(folder / "SKILL.md") in text, "必须给出完整说明的路径"
    assert "必须先读" in text, "要用硬指令，不能写成「可以参考」"


async def test_短技能直接给全文(runtime, http):





    resp = await upload(http, make_zip({"SKILL.md": "回复必须以「收到」开头。"}))
    skill_id = resp.json()["installed"][0]["id"]
    folder = runtime.paths.skills_dir / skill_id

    text = collect_instructions(
        runtime.custom_skills,
        {skill_id, "file_read"},  
        package_dirs={skill_id: str(folder)},
    )[0][1]
    assert "回复必须以「收到」开头" in text
    assert "必须先读" not in text


async def test_读不了文件的搭子仍给全文(runtime, http):





    from my_agent.skill import custom

    resp = await upload(http, make_zip({"SKILL.md": _LONG_MD}))
    skill_id = resp.json()["installed"][0]["id"]
    folder = runtime.paths.skills_dir / skill_id

    
    
    assert custom._can_read_files([skill_id]) is False, f"前提不成立：{skill_id} 含 file/read"

    text = collect_instructions(
        runtime.custom_skills, {skill_id}, package_dirs={skill_id: str(folder)}
    )[0][1]
    assert "第二步：再查天气" in text, "读不了文件就必须给全文，不能让技能变成空壳"





async def test_sync_without_key_is_friendly(runtime, http):

    from my_agent.config.schemas import ModelSpec

    runtime.config.models.models.append(
        ModelSpec(id="no-key", base_url="https://api.example.com/v1", model_name="m")
    )
    resp = await http.post("/v1/models/sync", json={"model_id": "no-key"})
    assert resp.status_code == 400
    assert "API Key" in resp.json()["detail"]


async def test_sync_returns_live_models(runtime, http, monkeypatch):
    from my_agent.config.schemas import ModelSpec

    spec = ModelSpec(
        id="with-key",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model_name="m",
    )
    runtime.config.models.models.append(spec)

    async def fake_test_model(_spec):
        return {"ok": True, "models": ["m-new-1", "m-new-2"]}

    monkeypatch.setattr(runtime, "test_model", fake_test_model)
    resp = await http.post("/v1/models/sync", json={"model_id": "with-key"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["models"] == ["m-new-1", "m-new-2"]


async def test_sync_local_not_running_is_friendly(runtime, http):





    from my_agent.config.schemas import ModelSpec

    runtime.config.models.models.append(
        ModelSpec(
            id="local",
            base_url="http://127.0.0.1:49999/v1",
            model_name="m",
            api_key="",
        )
    )
    resp = await http.post("/v1/models/sync", json={"model_id": "local"})
    assert resp.status_code == 400
    assert "启动" in resp.json()["detail"]


async def test_sync_unknown_model_is_404(http):
    resp = await http.post("/v1/models/sync", json={"model_id": "nope"})
    assert resp.status_code == 404

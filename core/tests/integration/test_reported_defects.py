







from __future__ import annotations

import io
import zipfile

import pytest

from my_agent.skill.custom import collect_instructions

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


async def upload(http, data: bytes, filename: str = "pack.zip"):
    return await http.post(
        "/v1/skills/custom/import",
        files={"package": (filename, data, "application/zip")},
    )


def assistant_payload(**overrides):
    payload = {
        "id": "defect-probe",
        "name": "缺陷探针",
        "emoji": "🧪",
        "description": "回归用例用的搭子",
        "system_prompt": "你是测试助手",
        "model_id": "",
        "temperature": 0.5,
        "max_iterations": 3,
        "enabled_skills": [],
        "confirm_mode": None,
    }
    payload.update(overrides)
    return payload





async def test_instruction_only_skill_counts_as_existing(runtime, http):







    resp = await upload(http, make_zip({"guide/SKILL.md": "回复必须先说「收到」。"}), "guide.zip")
    assert resp.status_code == 200, resp.text
    skill_id = resp.json()["installed"][0]["id"]
    assert resp.json()["installed"][0]["kind"] == "instruction"

    
    created = await http.post("/v1/assistants", json=assistant_payload(enabled_skills=[skill_id]))
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["enabled_skills"] == [skill_id]
    assert body["unavailable_skills"] == []

    
    saved = await http.put(
        "/v1/assistants/defect-probe",
        json=assistant_payload(enabled_skills=[skill_id]),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["unavailable_skills"] == []





async def test_package_is_unpacked_whole_and_root_is_stripped(runtime, http):





    payload = make_zip(
        {
            "my-skill/SKILL.md": "照 templates/report.md 的格式输出。",
            "my-skill/templates/report.md": "# 模板\n",
            "my-skill/assets/logo.txt": "logo\n",
            "../../escaped.txt": "不该被写出来\n",
        }
    )
    resp = await upload(http, payload, "my-skill.zip")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    skill_id = body["installed"][0]["id"]
    assert body["unpacked"][skill_id] == 3  

    folder = runtime.paths.skills_dir / skill_id
    assert (folder / "SKILL.md").is_file()
    
    assert (folder / "templates" / "report.md").is_file()
    assert (folder / "assets" / "logo.txt").is_file()
    
    assert not (runtime.paths.skills_dir.parent / "escaped.txt").exists()
    assert not (folder.parent / "escaped.txt").exists()

    
    
    
    sections = collect_instructions(
        runtime.custom_skills, {skill_id}, package_dirs={skill_id: str(folder)}
    )
    assert len(sections) == 1
    text = sections[0][1]
    assert str(folder) in text
    assert "templates/report.md" in text


async def test_配了白名单也读得到技能包(runtime, http):












    from my_agent.security.paths import PathPolicy

    resp = await upload(http, make_zip({"SKILL.md": "# 规矩\n\n先列提纲。", "templates/a.md": "x"}))
    skill_id = resp.json()["installed"][0]["id"]
    packaged = runtime.paths.skills_dir / skill_id / "SKILL.md"
    assert packaged.is_file()

    
    unrelated = runtime.paths.root / "别处"
    unrelated.mkdir(exist_ok=True)
    runtime.config.settings.security.allowed_dirs = [str(unrelated)]
    policy = runtime._build_path_policy()  
    assert isinstance(policy, PathPolicy)

    
    assert policy.check(str(packaged), mode="read") == packaged.resolve()
    
    from my_agent.errors import PathNotAllowedError

    outside = runtime.paths.root / "用户文件.txt"
    with pytest.raises(PathNotAllowedError):
        policy.check(str(outside), mode="read")





async def test_workspace_stats_counts_what_is_on_disk(runtime, http):






    before = (await http.get("/v1/files/stats")).json()
    assert before["total"] == 0

    (runtime.paths.workspace_dir / "笔记.txt").write_text("x" * 10, encoding="utf-8")
    (runtime.paths.artifacts_dir / "报表.md").write_text("y" * 20, encoding="utf-8")
    
    (runtime.paths.workspace_dir / ".gitkeep").write_text("", encoding="utf-8")

    after = (await http.get("/v1/files/stats")).json()
    assert after["total"] == 2
    assert after["uploads"] == 1
    assert after["artifacts"] == 1
    assert after["total_bytes"] == 30





async def test_deleting_a_skill_removes_its_unpacked_folder(runtime, http):




    resp = await upload(http, make_zip({"SKILL.md": "指导正文。"}), "cleanup.zip")
    assert resp.status_code == 200, resp.text
    skill_id = resp.json()["installed"][0]["id"]
    folder = runtime.paths.skills_dir / skill_id
    assert folder.is_dir()

    removed = await http.delete(f"/v1/skills/custom/{skill_id}")
    assert removed.status_code == 200, removed.text
    assert not folder.exists()

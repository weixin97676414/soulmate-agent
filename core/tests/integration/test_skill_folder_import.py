









from __future__ import annotations

import io
import json
import zipfile

import pytest

from .conftest import make_client


@pytest.fixture
async def http(base_url):
    async with make_client(base_url) as client:
        yield client


def make_zip(files: dict[str, str | bytes]) -> bytes:
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





async def test_import_folder_installs_skill_and_keeps_nested_files(runtime, http):

    source = runtime.paths.root / "外部技能源"
    (source / "templates").mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: 报表助手\ndescription: 生成周报\n---\n\n照 templates/x.md 的格式来。\n",
        encoding="utf-8",
    )
    (source / "templates" / "x.md").write_text("# 模板\n", encoding="utf-8")

    resp = await http.post("/v1/skills/custom/import-path", json={"path": str(source)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    defn = body["installed"][0]
    assert defn["source_format"] == "claude-skill"
    assert defn["description"] == "生成周报"

    folder = runtime.paths.skills_dir / defn["id"]
    assert (folder / "SKILL.md").is_file()
    assert (folder / "templates" / "x.md").is_file()


async def test_import_folder_reports_missing_path(runtime, http):
    resp = await http.post(
        "/v1/skills/custom/import-path", json={"path": str(runtime.paths.root / "不存在")}
    )
    assert resp.status_code == 400
    assert "不存在" in resp.json()["detail"]





async def test_multi_skill_package_keeps_each_skill_files_separate(runtime, http):

    payload = make_zip(
        {
            "a/SKILL.md": "# 甲\n照自己的模板做。\n",
            "a/templates/only-a.md": "A\n",
            "b/SKILL.md": "# 乙\n照自己的模板做。\n",
            "b/templates/only-b.md": "B\n",
        }
    )
    resp = await upload(http, payload)
    assert resp.status_code == 200, resp.text
    installed = resp.json()["installed"]
    assert len(installed) == 2

    by_name = {item["name"]: item["id"] for item in installed}
    folder_a = runtime.paths.skills_dir / by_name["甲"]
    folder_b = runtime.paths.skills_dir / by_name["乙"]
    assert (folder_a / "SKILL.md").is_file()
    assert (folder_a / "templates" / "only-a.md").is_file()
    
    assert not (folder_a / "templates" / "only-b.md").exists()
    assert (folder_b / "templates" / "only-b.md").is_file()
    assert not (folder_b / "templates" / "only-a.md").exists()


async def test_skill_files_endpoint_lists_unpacked_files(runtime, http):
    resp = await upload(http, make_zip({"SKILL.md": "正文\n", "assets/logo.txt": "x\n"}))
    skill_id = resp.json()["installed"][0]["id"]
    body = (await http.get(f"/v1/skills/custom/{skill_id}/files")).json()
    paths = [item["path"] for item in body["files"]]
    assert "SKILL.md" in paths
    assert "assets/logo.txt" in paths
    
    assert not any(name.startswith("_") for name in paths)





async def test_script_in_a_package_becomes_a_confirm_level_command_skill(runtime, http):
    resp = await upload(http, make_zip({"scripts/hello.py": "print('hi')\n"}))
    assert resp.status_code == 200, resp.text
    defn = resp.json()["installed"][0]
    assert defn["kind"] == "command"
    assert defn["source_format"] == "script"
    
    assert defn["permission_level"] == "confirm"

    folder = runtime.paths.skills_dir / defn["id"]
    assert (folder / "hello.py").is_file()
    if defn["command_template"]:
        assert str(folder / "hello.py") in defn["command_template"]
    else:
        
        assert "解释器" in defn["note"]





async def test_scan_inbox_is_idempotent_and_picks_up_changes(runtime, http):
    inbox = runtime.paths.skills_inbox_dir
    entry = inbox / "我的技能"
    entry.mkdir(parents=True)
    (entry / "SKILL.md").write_text("# 我的技能\n\n第一版说明。\n", encoding="utf-8")

    first = (await http.post("/v1/skills/custom/scan", json={"only": ""})).json()
    assert first["counts"]["added"] == 1
    assert first["ok"] is True

    
    second = (await http.post("/v1/skills/custom/scan", json={"only": ""})).json()
    assert second["counts"]["added"] == 0
    assert second["counts"]["skipped"] == 1

    
    (entry / "SKILL.md").write_text("# 我的技能\n\n第二版说明。\n", encoding="utf-8")
    third = (await http.post("/v1/skills/custom/scan", json={"only": ""})).json()
    assert third["counts"]["updated"] == 1

    listing = (await http.get("/v1/skills/custom")).json()
    defn = next(item for item in listing["skills"] if item["id"] == "我的技能")
    assert "第二版说明" in defn["instructions"]
    assert "第一版说明" not in defn["instructions"]


async def test_scan_inbox_does_not_touch_other_skills(runtime, http):

    resp = await upload(http, make_zip({"SKILL.md": "上传来的技能\n"}))
    assert resp.status_code == 200
    before = len((await http.get("/v1/skills/custom")).json()["skills"])

    outcome = (await http.post("/v1/skills/custom/scan", json={"only": ""})).json()
    
    assert outcome["scanned"] == 0
    assert outcome["counts"]["added"] == 0
    after = len((await http.get("/v1/skills/custom")).json()["skills"])
    assert after == before


async def test_folder_endpoint_reports_the_inbox(runtime, http):
    body = (await http.get("/v1/skills/custom/folder")).json()
    assert body["inbox"].replace("\\", "/").endswith("skills/inbox")
    assert body["exists"] is True


async def test_inbox_mcp_config_is_picked_up_by_the_startup_path(runtime):






    entry = runtime.paths.skills_inbox_dir / "带 MCP 的技能"
    entry.mkdir(parents=True)
    (entry / "SKILL.md").write_text("# 带 MCP 的技能\n", encoding="utf-8")
    (entry / "mcp.json").write_text(
        json.dumps(
            {"mcpServers": {"投放区测试服务": {"command": "definitely-not-a-real-command"}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    outcome = runtime.scan_skill_inbox()
    assert outcome["scanned"] == 1
    
    
    assert outcome["mcp_roots"], "投放区里的 MCP 配置没有被发现"

    
    
    await runtime._connect_inbox_mcp(outcome["mcp_roots"])





async def test_inbox_is_a_reserved_skill_name(runtime, http):

    resp = await http.post(
        "/v1/skills/custom",
        json={
            "skill": {
                "id": "inbox",
                "name": "inbox",
                "description": "占名测试",
                "kind": "instruction",
                "instructions": "正文",
            }
        },
    )
    assert resp.status_code == 409
    assert "保留" in resp.json()["detail"]





async def test_claude_skill_with_frontmatter_keeps_body_and_drops_frontmatter(runtime, http):
    resp = await upload(
        http,
        make_zip(
            {
                "SKILL.md": (
                    "---\n"
                    "name: 周报助手\n"
                    "description: 生成结构化周报\n"
                    "allowed-tools: [file_read]\n"
                    "---\n"
                    "\n"
                    "# 周报助手\n"
                    "\n"
                    "先问清楚范围。\n"
                )
            }
        ),
    )
    defn = resp.json()["installed"][0]
    assert defn["name"] == "周报助手"
    assert defn["allowed_tools"] == ["file_read"]
    assert "先问清楚范围" in defn["instructions"]
    
    assert "---" not in defn["instructions"]


async def test_package_without_any_skill_lists_its_files(runtime, http):
    resp = await upload(http, make_zip({"readme.txt": "nothing", "data.bin": "\x00\x01"}))
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "没有找到任何技能" in detail
    assert "readme.txt" in detail

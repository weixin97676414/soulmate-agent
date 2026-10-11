"""技能文件夹与全格式技能包导入的集成测试。

覆盖本次新增的两条导入路（本机文件夹、投放区扫描），以及两件老实现会做错的事：

1. **一个包含多个技能时，每条技能只落自己那一份文件** —— 老实现是"每条定义都把
   整包重落一遍"，三个技能就会有三份完整副本、路径全对不上；
2. **脚本技能的命令模板要指向落盘后的绝对路径** —— 解析时还不知道最终目录，
   必须落盘后回填，否则命令跑的是别的地方。
"""

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


# --------------------------------------------------------------------------- #
# 导入本机文件夹
# --------------------------------------------------------------------------- #
async def test_import_folder_installs_skill_and_keeps_nested_files(runtime, http):
    """多层目录原样导入：不压缩、不丢子目录。"""
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


# --------------------------------------------------------------------------- #
# 多技能包：落盘按技能根隔离
# --------------------------------------------------------------------------- #
async def test_multi_skill_package_keeps_each_skill_files_separate(runtime, http):
    """一个包含两个技能：各技能目录里**只有自己那份**文件。"""
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
    # 关键：甲拿不到乙的文件（老实现会把整包重落一份，两个目录内容一样）
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
    # 我们自己的清单文件不出现在"包内文件"里
    assert not any(name.startswith("_") for name in paths)


# --------------------------------------------------------------------------- #
# 脚本技能
# --------------------------------------------------------------------------- #
async def test_script_in_a_package_becomes_a_confirm_level_command_skill(runtime, http):
    resp = await upload(http, make_zip({"scripts/hello.py": "print('hi')\n"}))
    assert resp.status_code == 200, resp.text
    defn = resp.json()["installed"][0]
    assert defn["kind"] == "command"
    assert defn["source_format"] == "script"
    # 脚本是可执行能力，绝不能默认免确认
    assert defn["permission_level"] == "confirm"

    folder = runtime.paths.skills_dir / defn["id"]
    assert (folder / "hello.py").is_file()
    if defn["command_template"]:
        assert str(folder / "hello.py") in defn["command_template"]
    else:
        # 探测不到解释器时命令为空，但必须**说明原因**（不静默）
        assert "解释器" in defn["note"]


# --------------------------------------------------------------------------- #
# 技能投放区（inbox）
# --------------------------------------------------------------------------- #
async def test_scan_inbox_is_idempotent_and_picks_up_changes(runtime, http):
    inbox = runtime.paths.skills_inbox_dir
    entry = inbox / "我的技能"
    entry.mkdir(parents=True)
    (entry / "SKILL.md").write_text("# 我的技能\n\n第一版说明。\n", encoding="utf-8")

    first = (await http.post("/v1/skills/custom/scan", json={"only": ""})).json()
    assert first["counts"]["added"] == 1
    assert first["ok"] is True

    # 内容没变 → 不动（否则每次启动都重写一遍配置）
    second = (await http.post("/v1/skills/custom/scan", json={"only": ""})).json()
    assert second["counts"]["added"] == 0
    assert second["counts"]["skipped"] == 1

    # 改了文件 → 更新（投放区是"源"）
    (entry / "SKILL.md").write_text("# 我的技能\n\n第二版说明。\n", encoding="utf-8")
    third = (await http.post("/v1/skills/custom/scan", json={"only": ""})).json()
    assert third["counts"]["updated"] == 1

    listing = (await http.get("/v1/skills/custom")).json()
    defn = next(item for item in listing["skills"] if item["id"] == "我的技能")
    assert "第二版说明" in defn["instructions"]
    assert "第一版说明" not in defn["instructions"]


async def test_scan_inbox_does_not_touch_other_skills(runtime, http):
    """投放区扫描只碰 inbox —— 应用自己解包出来的技能目录不能被再导一遍。"""
    resp = await upload(http, make_zip({"SKILL.md": "上传来的技能\n"}))
    assert resp.status_code == 200
    before = len((await http.get("/v1/skills/custom")).json()["skills"])

    outcome = (await http.post("/v1/skills/custom/scan", json={"only": ""})).json()
    # 投放区是空的（刚上传的那个技能落在 skills/<id>/，不在 inbox 里）
    assert outcome["scanned"] == 0
    assert outcome["counts"]["added"] == 0
    after = len((await http.get("/v1/skills/custom")).json()["skills"])
    assert after == before


async def test_folder_endpoint_reports_the_inbox(runtime, http):
    body = (await http.get("/v1/skills/custom/folder")).json()
    assert body["inbox"].replace("\\", "/").endswith("skills/inbox")
    assert body["exists"] is True


async def test_inbox_mcp_config_is_picked_up_by_the_startup_path(runtime):
    """投放区里技能包带的 MCP 配置：启动扫描能发现它，后台那条路会去接。

    ⚠️ 这条链路必须有测试钉着：界面上那个「重新扫描」按钮已于 2026-10-06 移除
    （技能页只留一个「添加技能」入口），启动后的后台任务是投放区 MCP 配置
    **唯一**还能被接上的途径（见 ``Runtime._connect_inbox_mcp``）。
    """
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
    # 扫描本身**不接** MCP（启动路径是同步的，拉起子进程会拖住客户端），
    # 但必须把配置原样带出来给后台任务
    assert outcome["mcp_roots"], "投放区里的 MCP 配置没有被发现"

    # 后台那条路：命令是假的、必然接不上，但**绝不能抛** ——
    # 抛出会把启动流程带崩，而用户只是往文件夹里丢了个坏配置
    await runtime._connect_inbox_mcp(outcome["mcp_roots"])


# --------------------------------------------------------------------------- #
# 保留名
# --------------------------------------------------------------------------- #
async def test_inbox_is_a_reserved_skill_name(runtime, http):
    """允许一个技能叫 inbox，就等于让它把用户投放区整个覆盖掉。"""
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


# --------------------------------------------------------------------------- #
# 其它格式
# --------------------------------------------------------------------------- #
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
    # frontmatter 不该混进正文（否则会被原样塞进 system 提示词）
    assert "---" not in defn["instructions"]


async def test_package_without_any_skill_lists_its_files(runtime, http):
    resp = await upload(http, make_zip({"readme.txt": "nothing", "data.bin": "\x00\x01"}))
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "没有找到任何技能" in detail
    assert "readme.txt" in detail

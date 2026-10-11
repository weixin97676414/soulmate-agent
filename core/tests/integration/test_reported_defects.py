"""用户反馈缺陷的回归用例（2026-10-03 那批）。

**每一条都钉住一个具体症状**，注释里写清"它挡的是什么"。本次里有三条来自同一个
根因（指导型技能不注册成工具 → 被"存不存在"的判断判成不存在），所以它们看起来
像三个毛病：保存报 422、界面提示"不可用"、新建搭子的默认勾选算不进来。
把它们一起钉住，是因为将来只要有人把任一处改回 ``all_names()``，就会有其中一条红。
"""

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


# --------------------------------------------------------------------------- #
# ① 指导型技能必须算"存在"（三处症状同一个根因）
# --------------------------------------------------------------------------- #
async def test_instruction_only_skill_counts_as_existing(runtime, http):
    """只有 SKILL.md 的技能装好后：配给搭子不该 422，也不该被标成"不可用"。

    症状（用户原话的大意）：装了个指导型技能，勾给搭子时保存报"技能不存在"；
    勉强存上的那些，界面上一直挂着"有 1 个工具当前不可用"。
    根因：这两处都拿 ``SkillManager.all_names()``（只有能执行动作的工具）当
    "技能库全集"，而指导型技能按设计不会注册成工具。
    """
    resp = await upload(http, make_zip({"guide/SKILL.md": "回复必须先说「收到」。"}), "guide.zip")
    assert resp.status_code == 200, resp.text
    skill_id = resp.json()["installed"][0]["id"]
    assert resp.json()["installed"][0]["kind"] == "instruction"

    # 新建时把它写进白名单 —— 修复前这一条是 422
    created = await http.post("/v1/assistants", json=assistant_payload(enabled_skills=[skill_id]))
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["enabled_skills"] == [skill_id]
    assert body["unavailable_skills"] == []

    # 再保存一次（界面上"点开又保存"就是这个动作）——修复前同样是 422
    saved = await http.put(
        "/v1/assistants/defect-probe",
        json=assistant_payload(enabled_skills=[skill_id]),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["unavailable_skills"] == []


# --------------------------------------------------------------------------- #
# ② 技能包要**整包落盘**（而不是只把 SKILL.md 读进内存）
# --------------------------------------------------------------------------- #
async def test_package_is_unpacked_whole_and_root_is_stripped(runtime, http):
    """整包解开、剥掉公共根目录、挡住路径穿越。

    症状：技能说明里写着"按 templates/xxx 的格式来"，但那几个文件根本没落盘，
    模型只能凭空编 —— 表现成"这个技能怎么不按说明来"。
    """
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
    assert body["unpacked"][skill_id] == 3  # 三条正常文件；带 ../ 的那条被挡下

    folder = runtime.paths.skills_dir / skill_id
    assert (folder / "SKILL.md").is_file()
    # 剥掉了公共根目录 my-skill/：模板就在包根下
    assert (folder / "templates" / "report.md").is_file()
    assert (folder / "assets" / "logo.txt").is_file()
    # 路径穿越被挡住：skills 目录的上一级不该出现那个文件
    assert not (runtime.paths.skills_dir.parent / "escaped.txt").exists()
    assert not (folder.parent / "escaped.txt").exists()

    # 注入 system 的正文里要带上**真实目录**与文件清单，模型才知道去哪读
    # ⚠️ 第二个参数 起是"该搭子**实际可用**的技能集合"（显式、无"空 = 全注入"）：
    # 指导型技能属「我的技能」，没被勾中就不注入。所以这里显式给上它。
    sections = collect_instructions(
        runtime.custom_skills, {skill_id}, package_dirs={skill_id: str(folder)}
    )
    assert len(sections) == 1
    text = sections[0][1]
    assert str(folder) in text
    assert "templates/report.md" in text


async def test_配了白名单也读得到技能包(runtime, http):
    """⚠️ 2026-10-07 补的洞：配过「文件访问白名单」的用户，模型**必须**仍能读到技能包。

    背景：指导型技能的正文默认不注入 system（见 `skill/custom.py`），模型要用的时候
    得自己去读 ``<技能包目录>/SKILL.md``。而技能包落在**用户数据目录**下，用户的文件
    白名单里通常没有它 —— 于是模型读不到，表现成"技能装了、技能页也有、搭子就是按不
    出来"，报错还写着"不在白名单内"，用户根本想不到要去把自己的应用数据目录加进去。

    技能包是**应用自己落盘**的（`config/paths.py` 里就把它与 workspace 分开，理由是
    "清空工作区不该删掉已装技能的辅助文件"），本就不该按"用户的文件"来管 ——
    所以它进了 `always_allowed`。这条走**生产路径** `_build_path_policy` 验，而不是
    在用例里自己拼一份白名单（那验不到真正的构造代码）。
    """
    from my_agent.security.paths import PathPolicy

    resp = await upload(http, make_zip({"SKILL.md": "# 规矩\n\n先列提纲。", "templates/a.md": "x"}))
    skill_id = resp.json()["installed"][0]["id"]
    packaged = runtime.paths.skills_dir / skill_id / "SKILL.md"
    assert packaged.is_file()

    # 把白名单收紧到一个与技能包**无关**的目录，再按生产路径重建策略
    unrelated = runtime.paths.root / "别处"
    unrelated.mkdir(exist_ok=True)
    runtime.config.settings.security.allowed_dirs = [str(unrelated)]
    policy = runtime._build_path_policy()  # noqa: SLF001
    assert isinstance(policy, PathPolicy)

    # 技能包里的文件必须放行
    assert policy.check(str(packaged), mode="read") == packaged.resolve()
    # 而普通用户路径仍应被拦 —— 顺带证明上面的放行是"专门给技能包开的"，不是白名单整个失效
    from my_agent.errors import PathNotAllowedError

    outside = runtime.paths.root / "用户文件.txt"
    with pytest.raises(PathNotAllowedError):
        policy.check(str(outside), mode="read")


# --------------------------------------------------------------------------- #
# ③ 工作区统计要**以磁盘为准**
# --------------------------------------------------------------------------- #
async def test_workspace_stats_counts_what_is_on_disk(runtime, http):
    """直接在目录里放文件，统计就要跟着变（记录表此时根本没有这些行）。

    症状：界面上"共 N 个文件 / 占用 X MB"和资源管理器里看到的不一样。
    根因：数字来自数据库记录（或带 limit 的列表），而用户是能绕过应用直接
    在目录里增删文件的。
    """
    before = (await http.get("/v1/files/stats")).json()
    assert before["total"] == 0

    (runtime.paths.workspace_dir / "笔记.txt").write_text("x" * 10, encoding="utf-8")
    (runtime.paths.artifacts_dir / "报表.md").write_text("y" * 20, encoding="utf-8")
    # 隐藏文件不算（.gitkeep 之类）
    (runtime.paths.workspace_dir / ".gitkeep").write_text("", encoding="utf-8")

    after = (await http.get("/v1/files/stats")).json()
    assert after["total"] == 2
    assert after["uploads"] == 1
    assert after["artifacts"] == 1
    assert after["total_bytes"] == 30


# --------------------------------------------------------------------------- #
# ④ 删技能要连落盘目录一起删
# --------------------------------------------------------------------------- #
async def test_deleting_a_skill_removes_its_unpacked_folder(runtime, http):
    """删掉技能后，``skills/<id>/`` 不该留着。

    留着的话，同名技能重新安装时会看到上一版的残留文件（覆盖只覆盖同名文件）。
    """
    resp = await upload(http, make_zip({"SKILL.md": "指导正文。"}), "cleanup.zip")
    assert resp.status_code == 200, resp.text
    skill_id = resp.json()["installed"][0]["id"]
    folder = runtime.paths.skills_dir / skill_id
    assert folder.is_dir()

    removed = await http.delete(f"/v1/skills/custom/{skill_id}")
    assert removed.status_code == 200, removed.text
    assert not folder.exists()

"""技能包上传（zip）与模型清单同步接口的集成测试。

覆盖三件事：
- zip 导入：skill.json 可执行 / SKILL.md 指导型 / 两者都有 / 坏包逐条报告
- 指导型技能真的被注入 system（走 persona_with_instructions 这条生产路径）
- ``POST /v1/models/sync``：免 Key 拒绝、同步成功、本机服务没启动的人话报错
"""

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


# --------------------------------------------------------------------------- #
# zip 导入
# --------------------------------------------------------------------------- #
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
    """只有 SKILL.md → 整包按指导型导入：不做动作，内容进 system。"""
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
    """skill.json 与 SKILL.md 都有：动作照装，指导单独成一条。"""
    resp = await upload(
        http,
        make_zip({"skill.json": skill_json(), "SKILL.md": "天气数据可能有延迟，要说明。"}),
    )
    assert resp.status_code == 200, resp.text
    kinds = sorted(item["kind"] for item in resp.json()["results"])
    assert kinds == ["http", "instruction"]


async def test_import_bad_json_reports_but_does_not_block(runtime, http):
    """坏定义逐条报告，不拖垮包里其它条目。"""
    resp = await upload(
        http,
        make_zip({"skill.json": "{ not json", "SKILL.md": "兜底指导仍然有效。"}),
    )
    body = resp.json()
    assert body["results"][0]["ok"] is False
    assert body["results"][-1]["ok"] is True  # SKILL.md 那条成功


async def test_import_rejects_non_zip(http):
    resp = await upload(http, b"this is not a zip")
    assert resp.status_code == 400


async def test_import_rejects_package_without_any_skill(http):
    """包里没有可识别的东西 → 明确 400，并把包内文件列出来。

    ⚠️ **口径变化（2026-10-06）**：以前包里只要有 ``.md`` **或** ``.txt``
    就会被当成"通用提示词技能"导入（当时是逐文件找 SKILL.md 的老实现，
    这条用例钉的是"两者都没有就拒绝"）。现在 ``.txt`` **不算**提示词文档 ——
    几乎任何压缩包里都有 readme.txt / license.txt，把它们当技能会制造一堆
    莫名其妙的技能卡；而"传错包"时报错比生成一个垃圾技能更容易看懂。
    """
    resp = await upload(http, make_zip({"readme.txt": b"nothing here"}))
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "没有找到任何技能" in detail
    # 报错要带上包内文件：用户传错包（比如传了安装包）时，
    # 看到文件名才能立刻明白自己传错了什么
    assert "readme.txt" in detail


async def test_import_plain_markdown_becomes_instruction(http):
    """包里只有一份 ``.md`` → 当成提示词技能导入（本次新支持的格式之一）。"""
    resp = await upload(http, make_zip({"guide.md": "# 写作规矩\n\n先列提纲再写。"}))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["results"][0]["ok"] is True
    assert body["results"][0]["kind"] == "instruction"
    assert body["results"][0]["source_format"] == "plain-md"


# --------------------------------------------------------------------------- #
# 指导型注入
# --------------------------------------------------------------------------- #
async def test_instruction_reaches_system_prompt(runtime, http):
    """走 persona_with_instructions 这条**生产路径**验证注入。

    只测 collect_instructions 会漏掉"runtime 属性不存在/取错"这一层
    —— 参数链路必须从入口走到底（与 reasoning_effort 那次的教训相同）。
    """
    resp = await upload(http, make_zip({"SKILL.md": "回复必须以「收到」开头。"}))
    skill_id = resp.json()["installed"][0]["id"]

    # ⚠️ 第三个参数 起是"该搭子**额外勾选**的技能"（指导型技能属「我的技能」，
    # 不勾就不注入）—— 传 None 的话它只剩内置技能，指导正文不会出现。
    text = persona_with_instructions(runtime, "office", [skill_id])
    assert "回复必须以「收到」开头" in text


async def test_instruction_respects_global_disable(runtime, http):
    resp = await upload(http, make_zip({"SKILL.md": "被禁用后不该出现。"}))
    skill_id = resp.json()["installed"][0]["id"]
    config = runtime.custom_skills.model_copy(deep=True)
    config.skills[0].enabled = False
    runtime.reload_custom_skills(config)

    # 勾了它、但它被全局禁用 → 仍然不注入（"被禁用"与"没勾"是两条不同的理由，都要拦）
    assert collect_instructions(runtime.custom_skills, {skill_id}) == []
    # ⚠️ 这里**不能**断言整个人格为空：人格里还包含出厂 SOUL.md（每个内置搭子都有）。
    # 这条用例要验的是"被禁用的指导没有进人格"，而原先那句 `== ""` 之所以成立，
    # 只是因为当时首启漏播了 SOUL（那个 bug 已修）。
    assert "被禁用后不该出现" not in persona_with_instructions(runtime, "office", [skill_id])


# --------------------------------------------------------------------------- #
# 按需读取（产品约定：**默认按需**，不再是"超过多少字才降级"）
# --------------------------------------------------------------------------- #
_LONG_BODY = "第一步：先查城市。第二步：再查天气。" * 60  # 远超 INLINE_TEXT_LIMIT

# ⚠️ 长技能要用**带 frontmatter** 的 SKILL.md。不带 frontmatter 时，导入会给它一个
# 从**正文里截**出来的 description（截前若干字）—— 于是按需版里那句"技能简介"
# 本身就会含正文片段，"正文没进 system"这个断言就验不出东西了（我第一版就这么写错的，
# 表现为断言失败但打印出来的 text 里真的有降级文案、看着像自相矛盾）。
_LONG_MD = f"---\nname: 长技能\ndescription: 触发：要查天气时用它。\n---\n\n{_LONG_BODY}\n"


async def test_长技能只给路径不给正文(runtime, http):
    """⚠️ 指导型技能的正文**默认不塞进 system**：只留简介 + 完整说明的路径。

    这条钉住三件事，缺一条这个机制就废：

    ① **正文不在** system 里 —— 一轮对话里挂几十个技能，全塞进去会挤掉对话本身；
    ② **路径必须在** —— 不在的话模型无从读起，技能等于没装；
    ③ **"必须先读"这句硬指令要在** —— 模型有个很常见的失败模式：凭技能名的印象直接
       开干、不去读。所以这句措辞不能软化成"可以参考"。
    """
    resp = await upload(http, make_zip({"SKILL.md": _LONG_MD}))
    skill_id = resp.json()["installed"][0]["id"]
    folder = runtime.paths.skills_dir / skill_id

    sections = collect_instructions(
        runtime.custom_skills,
        # ⚠️ 第二个参数要按**生产路径**给：那边传的是 `SkillManager.allowed_names(...)`，
        # 即"这个搭子实际可用的一整套技能"，它**恒含内置技能**（`file_read` 就在里面）。
        # 只传一个技能 id 的话，`_can_read_files` 会因为名字里没有 file/read 而判成
        # "读不了文件"，于是**不降级** —— 用例看着在测按需读取，其实什么都没测到。
        {skill_id, "file_read", "calc"},
        package_dirs={skill_id: str(folder)},
    )
    assert len(sections) == 1
    text = sections[0][1]
    assert "第二步：再查天气" not in text, "正文不该整份进 system"
    assert str(folder / "SKILL.md") in text, "必须给出完整说明的路径"
    assert "必须先读" in text, "要用硬指令，不能写成「可以参考」"


async def test_短技能直接给全文(runtime, http):
    """正文短到"不如直接给"时不做按需 —— 这是那条默认规则的**唯一例外**。

    理由不是"省 token"，恰恰相反：按需版本身要写简介 + 路径 + 目录 + 文件清单，
    两三百字打底。正文比它短时，按需反而更占地方、还白搭一次读取。
    """
    resp = await upload(http, make_zip({"SKILL.md": "回复必须以「收到」开头。"}))
    skill_id = resp.json()["installed"][0]["id"]
    folder = runtime.paths.skills_dir / skill_id

    text = collect_instructions(
        runtime.custom_skills,
        {skill_id, "file_read"},  # 同上看齐生产路径
        package_dirs={skill_id: str(folder)},
    )[0][1]
    assert "回复必须以「收到」开头" in text
    assert "必须先读" not in text


async def test_读不了文件的搭子仍给全文(runtime, http):
    """⚠️ 这条防的是"告诉一个瞎子去看那份文件"。

    按需读取的前提是模型**真能去读**。可用集合里没有文件类技能时，降级等于把正文
    丢了 —— 那种情况下宁可整份注入（多占点上下文，也不能让它无据可依）。
    """
    from my_agent.skill import custom

    resp = await upload(http, make_zip({"SKILL.md": _LONG_MD}))
    skill_id = resp.json()["installed"][0]["id"]
    folder = runtime.paths.skills_dir / skill_id

    # 前提：这个 id 里不含 file / read，否则 `_can_read_files` 会判成"能读"、
    # 这条用例就验不到东西了（而且会**静默**失效）。先断言前提成立。
    assert custom._can_read_files([skill_id]) is False, f"前提不成立：{skill_id} 含 file/read"

    text = collect_instructions(
        runtime.custom_skills, {skill_id}, package_dirs={skill_id: str(folder)}
    )[0][1]
    assert "第二步：再查天气" in text, "读不了文件就必须给全文，不能让技能变成空壳"


# --------------------------------------------------------------------------- #
# 模型清单同步
# --------------------------------------------------------------------------- #
async def test_sync_without_key_is_friendly(runtime, http):
    """云端厂商没 Key：给"去填 Key"的人话，而不是 401 原始报错。"""
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
    """本机服务没在跑：报"没启动"而不是底层连接错误。

    端口用 49999（保留段，几乎不会有服务在听）：**不能用 11434** ——
    这台机器上 Ollama 是真可能正在跑的，那样这条用例就会随机翻绿/翻红。
    """
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

"""技能包**格式识别**的单元测试（``skill/formats.py``）。

这一层是纯函数，所以每个格式规则都能直接钉住 —— 不用造文件系统、不用起服务。
本次支持的格式全在这里：Claude Agent Skills（含多技能与 frontmatter）、
Cursor/Cline/通用规则、MCP 配置、可执行脚本、通用 Markdown。

反过来说，**这里也是"什么不该被识别"的地方**：
一个 Claude Skill 包里的 ``references/*.md`` 不能变成一堆噪音技能，
几乎任何包里都有的 ``readme.txt`` 也不能。
"""

from __future__ import annotations

from my_agent.skill.formats import (
    MAX_DESCRIPTION_CHARS,
    extract_mcp_servers,
    identify_roots,
    parse_minimal_yaml,
    split_frontmatter,
)


def files(**items: str) -> dict[str, bytes]:
    return {name: value.encode("utf-8") for name, value in items.items()}


def kinds_of(roots) -> list[tuple[str, str]]:
    return [(item.source_format, item.name) for item in roots]


# --------------------------------------------------------------------------- #
# frontmatter
# --------------------------------------------------------------------------- #
def test_frontmatter_is_extracted_and_body_kept_whole():
    text = (
        "---\n"
        "name: 周报助手\n"
        "description: 生成结构化周报\n"
        "allowed-tools: [file_read, file_write]\n"
        "---\n"
        "\n"
        "# 周报助手\n"
        "\n"
        "正文第一行。\n"
    )
    meta, body = split_frontmatter(text)
    assert meta["name"] == "周报助手"
    assert meta["description"] == "生成结构化周报"
    assert meta["allowed-tools"] == ["file_read", "file_write"]
    # 正文原样保留（不截断、不剥空行）
    assert body == "\n# 周报助手\n\n正文第一行。\n"


def test_text_without_frontmatter_is_returned_unchanged():
    meta, body = split_frontmatter("# 标题\n\n正文\n")
    assert meta == {}
    assert body == "# 标题\n\n正文\n"


def test_frontmatter_list_can_use_dash_lines():
    meta, _ = split_frontmatter("---\nname: x\nallowed-tools:\n  - a\n  - b\n---\n正文\n")
    assert meta["allowed-tools"] == ["a", "b"]


# --------------------------------------------------------------------------- #
# Claude Agent Skills
# --------------------------------------------------------------------------- #
def test_skill_md_becomes_instruction_with_frontmatter_meta():
    roots = identify_roots(
        files(**{"SKILL.md": "---\nname: 报表助手\ndescription: 生成周报\n---\n\n# 报表助手\n\n照做。\n"}),
        package_name="pack",
    )
    assert len(roots) == 1
    root = roots[0]
    assert root.kind == "instruction"
    assert root.source_format == "claude-skill"
    assert root.name == "报表助手"
    assert root.description == "生成周报"
    assert "照做" in root.instructions
    # frontmatter 不该出现在正文里（否则会被原样塞进 system）
    assert "---" not in root.instructions


def test_one_package_with_multiple_skills_installs_them_all():
    """老实现只取第一个 SKILL.md，其余全丢 —— 这是本次修掉的缺陷。"""
    roots = identify_roots(
        files(**{"a/SKILL.md": "# 甲\n", "b/SKILL.md": "# 乙\n"}),
        package_name="pack",
    )
    assert {item.root for item in roots} == {"a", "b"}
    assert {item.name for item in roots} == {"甲", "乙"}


def test_name_falls_back_to_heading_then_folder():
    from_heading = identify_roots(files(**{"SKILL.md": "# 从标题取名\n"}), package_name="pack")
    assert from_heading[0].name == "从标题取名"
    from_dir = identify_roots(files(**{"my-skill/SKILL.md": "没有标题\n"}), package_name="pack")
    assert from_dir[0].name == "my-skill"


def test_long_description_is_trimmed_and_reported_not_silent():
    long = "描述" * (MAX_DESCRIPTION_CHARS)
    roots = identify_roots(
        files(**{"SKILL.md": f"---\ndescription: {long}\n---\n正文\n"}), package_name="pack"
    )
    assert len(roots[0].description) == MAX_DESCRIPTION_CHARS
    assert "截到" in roots[0].note  # 静默截断是不可接受的，必须有 note


def test_description_falls_back_to_body_summary():
    """简介空了整条技能会被拒收，所以必须兜底。"""
    roots = identify_roots(files(**{"SKILL.md": "先问清楚城市再查天气。\n"}), package_name="pack")
    assert roots[0].description == "先问清楚城市再查天气。"


def test_reference_docs_inside_a_skill_are_not_separate_skills():
    """一个 Claude Skill 里的 references/*.md 不能变成独立技能（否则噪音爆炸）。"""
    roots = identify_roots(
        files(**{"my/SKILL.md": "# 主技能\n", "my/references/notes.md": "参考资料\n"}),
        package_name="pack",
    )
    assert len(roots) == 1
    assert roots[0].source_format == "claude-skill"


# --------------------------------------------------------------------------- #
# Cursor / Cline / 通用规则
# --------------------------------------------------------------------------- #
def test_cursor_mdc_and_clinerules_and_agents_md_are_recognized():
    roots = identify_roots(
        files(
            **{
                ".cursor/rules/style.mdc": "---\ndescription: 代码风格\n---\n缩进两个空格。\n",
                ".clinerules/report.md": "报告要写结论先行。\n",
                "AGENTS.md": "这个仓库用 pnpm。\n",
                ".cursorrules": "不要改 lock 文件。\n",
            }
        ),
        package_name="pack",
    )
    found = {item.source_format for item in roots}
    assert found == {"cursor-mdc", "clinerules", "agents-md", "cursorrules"}
    mdc = next(item for item in roots if item.source_format == "cursor-mdc")
    assert mdc.description == "代码风格"
    assert mdc.only_files == (".cursor/rules/style.mdc",)


def test_duplicate_rule_names_are_disambiguated():
    """两张同名技能卡会有"看起来一样、只有一张能删"的坑，必须区分。"""
    roots = identify_roots(
        files(**{"a/rules.mdc": "甲\n", "b/rules.mdc": "乙\n"}), package_name="pack"
    )
    assert len({item.name for item in roots}) == 2


# --------------------------------------------------------------------------- #
# MCP 配置
# --------------------------------------------------------------------------- #
def test_mcp_json_is_recognized():
    payload = '{"mcpServers": {"fs": {"command": "npx", "args": ["-y", "x"]}}}'
    roots = identify_roots(files(**{"mcp.json": payload}), package_name="pack")
    assert len(roots) == 1
    assert roots[0].kind == "mcp"
    assert roots[0].mcp_servers[0]["name"] == "fs"
    assert roots[0].mcp_servers[0]["command"] == "npx"


def test_mcp_yaml_is_recognized():
    payload = "mcpServers:\n  fs:\n    command: npx\n    args: [\"-y\", \"x\"]\n"
    servers = extract_mcp_servers(payload)
    assert servers and servers[0]["name"] == "fs"
    assert servers[0]["args"] == ["-y", "x"]


def test_a_plain_json_without_mcp_key_is_not_an_mcp_config():
    """光叫 mcp.json 不算 —— 必须真的有 mcpServers 结构。"""
    roots = identify_roots(files(**{"mcp.json": '{"hello": "world"}'}), package_name="pack")
    assert roots == []


def test_minimal_yaml_returns_none_when_it_cannot_parse():
    """不支持的写法宁可返回 ``None``，也不要猜出一份结构错误的配置。

    猜错的后果是"连一堆不存在的服务"，用户根本无从排查。
    """
    assert parse_minimal_yaml("a: 1\n  b: 2\n") is None
    assert parse_minimal_yaml("") is None


# --------------------------------------------------------------------------- #
# 脚本 / 通用文档
# --------------------------------------------------------------------------- #
def test_scripts_become_command_roots():
    roots = identify_roots(
        files(**{"scripts/build.py": "print(1)\n", "run.sh": "echo hi\n"}),
        package_name="pack",
    )
    assert {item.source_format for item in roots} == {"script"}
    assert {item.kind for item in roots} == {"command"}
    assert {item.name for item in roots} == {"build", "run"}


def test_scripts_inside_a_skill_are_still_listed_on_the_skill():
    """SKILL.md 里提到的脚本要出现在该技能的 scripts 上（模型才知道有哪些脚本）。"""
    roots = identify_roots(
        files(**{"my/SKILL.md": "# 主技能\n", "my/scripts/x.py": "print(1)\n"}),
        package_name="pack",
    )
    skill = next(item for item in roots if item.source_format == "claude-skill")
    assert skill.scripts == ("my/scripts/x.py",)


def test_scripts_inside_a_skill_do_not_become_separate_skills():
    """⚠️ 技能根里的脚本**不再单独成一张命令卡**（2026-10-07 修）。

    实测教训：一个 236 个技能的素材库里几乎每个技能都带 `scripts/*.py`，
    不排除的话技能卡会从 **259 张炸到 643 张** —— 多出来的 384 张全是名为
    `gen_hint_words` 这类孤立脚本：用户不知道它属于哪个技能，也没有正文告诉模型
    该怎么用它（脚本必须配合 SKILL.md 的步骤才有意义）。

    与 ③ 规则文件分支同款口径（那边早就有"技能根里的参考文档不是独立技能"）。
    **纯脚本包不受影响**，仍每个脚本一张卡 —— 见上面那条用例。
    """
    roots = identify_roots(
        files(**{"my/SKILL.md": "# 主技能\n", "my/scripts/x.py": "print(1)\n"}),
        package_name="pack",
    )
    assert [item.source_format for item in roots] == ["claude-skill"]
    # 脚本本身没丢：它挂在该技能的 `scripts` 上（模型据此知道有哪些脚本可用）
    assert roots[0].scripts == ("my/scripts/x.py",)


def test_plain_markdown_only_when_nothing_else_matched():
    roots = identify_roots(files(**{"guide.md": "# 规矩\n"}), package_name="pack")
    assert kinds_of(roots) == [("plain-md", "规矩")]


def test_txt_files_are_not_treated_as_skills():
    """readme.txt / license.txt 几乎每个包里都有，不能变成技能卡。"""
    assert identify_roots(files(**{"readme.txt": "nothing"}), package_name="pack") == []


def test_claude_skill_wins_over_stray_markdown():
    roots = identify_roots(
        files(**{"my/SKILL.md": "# 主技能\n", "my/CHANGELOG.md": "# 更新记录\n"}),
        package_name="pack",
    )
    assert [item.source_format for item in roots] == ["claude-skill"]


def test_empty_input_yields_nothing():
    assert identify_roots({}, package_name="pack") == []

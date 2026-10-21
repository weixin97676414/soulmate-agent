










from __future__ import annotations

import io
import zipfile
from pathlib import Path

from my_agent.config.schemas import CustomSkillDef, CustomSkillsConfig
from my_agent.skill import formats
from my_agent.skill.custom import backfill_display_names
from my_agent.skill.package import parse_payload

_CN_SKILL = """---
name: travel-itinerary-planning
description: 行程规划设计：问清偏好、检索真实车次与门票。触发场景：行程安排、旅游规划。
---

# 行程规划设计（精确到小时）

## 适用场景

用户提到旅行意图即触发。
"""

_EN_SKILL = """---
name: plain-english
description: An English skill.
---

# Plain English Skill

Body.
"""


def make_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def defn(skill_id: str, name: str = "") -> CustomSkillDef:
    return CustomSkillDef(
        id=skill_id,
        name=name or skill_id,
        description="测试用",
        kind="instruction",
        instructions="正文",
    )





class TestDisplayTitle:
    def test_中文标题被取出来(self):
        assert (
            formats.display_title("# 行程规划设计（精确到小时）\n\n正文")
            == "行程规划设计（精确到小时）"
        )

    def test_英文标题不取(self):

        assert formats.display_title("# Plain English Skill\n\nBody.") == ""

    def test_没有标题时返回空(self):
        assert formats.display_title("只有正文，没有标题。") == ""

    def test_超长标题按上限截断(self):


        assert len(formats.display_title("# " + "中" * 80)) == formats.MAX_NAME_CHARS





class TestNameSplit:
    def test_id仍是英文slug而显示名是中文(self):

        parsed = parse_payload(make_zip({"SKILL.md": _CN_SKILL}), "pack")
        (item,) = parsed.defs
        assert item.id == "travel-itinerary-planning", "id 必须还是英文 slug（改了用户勾选全丢）"
        assert item.name == "行程规划设计（精确到小时）"

    def test_没有中文标题时显示名回退原名(self):
        parsed = parse_payload(make_zip({"SKILL.md": _EN_SKILL}), "pack")
        (item,) = parsed.defs
        assert item.id == "plain-english"
        assert item.name == "plain-english"

    def test_重名去重时中文显示名不丢(self):



        parsed = parse_payload(
            make_zip({"a/SKILL.md": _CN_SKILL, "b/SKILL.md": _CN_SKILL}), "pack"
        )
        assert [item.name for item in parsed.defs] == [
            "行程规划设计（精确到小时）",
            "行程规划设计（精确到小时）",
        ]
        
        assert len({item.id for item in parsed.defs}) == 2





class TestBackfill:
    @staticmethod
    def _plant(root: Path, skill_id: str, content: str) -> None:
        folder = root / skill_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_text(content, encoding="utf-8")

    def test_把英文名回填成中文标题(self, tmp_path):
        self._plant(tmp_path, "travel-itinerary-planning", _CN_SKILL)
        config = CustomSkillsConfig(skills=[defn("travel-itinerary-planning")])

        assert backfill_display_names(config, tmp_path) is True
        assert config.skills[0].name == "行程规划设计（精确到小时）"
        assert config.skills[0].id == "travel-itinerary-planning", "⚠️ id 不能跟着变"

    def test_幂等_值没变就不算改过(self, tmp_path):


        self._plant(tmp_path, "s1", _CN_SKILL)
        config = CustomSkillsConfig(skills=[defn("s1")])

        assert backfill_display_names(config, tmp_path) is True
        assert backfill_display_names(config, tmp_path) is False

    def test_没有中文标题时不动(self, tmp_path):
        self._plant(tmp_path, "s2", _EN_SKILL)
        config = CustomSkillsConfig(skills=[defn("s2")])

        assert backfill_display_names(config, tmp_path) is False
        assert config.skills[0].name == "s2"

    def test_没有落盘的技能不动(self, tmp_path):


        config = CustomSkillsConfig(skills=[defn("made-by-ai", "我自己起的名字")])

        assert backfill_display_names(config, tmp_path) is False
        assert config.skills[0].name == "我自己起的名字"

    def test_没有落盘根时直接返回False(self):
        config = CustomSkillsConfig(skills=[defn("s3")])
        assert backfill_display_names(config, None) is False

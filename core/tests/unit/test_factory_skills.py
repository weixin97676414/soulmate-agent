











from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from my_agent.config.schemas import CustomSkillDef, CustomSkillsConfig
from my_agent.skill import factory

_SKILL_MD = """---
name: {name}
description: 这是一个测试技能，用来验证播种。
---

# {title}

## 适用场景

只有测试才用。
"""


def write_skill(root: Path, domain: str, folder: str, name: str, title: str) -> None:
    target = root / domain / folder
    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(
        _SKILL_MD.format(name=name, title=title), encoding="utf-8"
    )


def write_index(root: Path, *, version: str = "1", excluded: list[str] | None = None) -> None:
    domains = sorted(item.name for item in root.iterdir() if item.is_dir())
    index = {
        "version": version,
        "excluded": excluded or [],
        "skills": [{"domain": name, "ids": []} for name in domains],
    }
    (root / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


class FakeRuntime:


    def __init__(self, base: Path) -> None:
        self.paths = SimpleNamespace(data_dir=base / "data", skills_dir=base / "skills")
        self.paths.data_dir.mkdir(parents=True, exist_ok=True)
        self.paths.skills_dir.mkdir(parents=True, exist_ok=True)
        self.custom_skills = CustomSkillsConfig()
        self.saved = 0

        def save(config: CustomSkillsConfig) -> CustomSkillsConfig:
            self.saved += 1
            return config

        self.config_store = SimpleNamespace(save_custom_skills=save)


@pytest.fixture
def resource(tmp_path, monkeypatch) -> Path:

    root = tmp_path / "factory_skills"
    root.mkdir()
    monkeypatch.setattr(factory, "resource_root", lambda: root)
    return root





class TestSchemaCompat:
    def test_老配置没有origin字段也能解析(self):


        defn = CustomSkillDef.model_validate(
            {"id": "legacy", "name": "老技能", "kind": "instruction", "instructions": "正文"}
        )
        assert defn.origin == "user"

    def test_不在field名里的键不会被当成必填(self):

        defn = CustomSkillDef.model_validate({"id": "a", "name": "b"})
        assert defn.domain == ""
        assert defn.origin == "user"





class TestIndex:
    def test_没有资源时安静返回None(self, tmp_path, monkeypatch):
        monkeypatch.setattr(factory, "resource_root", lambda: tmp_path / "不存在")
        assert factory.read_factory_index() is None

    def test_索引坏掉时返回None而不是抛异常(self, resource):
        (resource / "index.json").write_text("{ 这不是 json", encoding="utf-8")
        assert factory.read_factory_index() is None

    def test_索引结构不对时返回None(self, resource):
        (resource / "index.json").write_text('{"version": "1"}', encoding="utf-8")
        assert factory.read_factory_index() is None


class TestMarker:
    def test_没播过要播(self, tmp_path):
        assert factory.seeds_needed(tmp_path, "1") is True

    def test_同版本不再播(self, tmp_path):
        factory.write_marker(tmp_path, "1")
        assert factory.seeds_needed(tmp_path, "1") is False

    def test_版本变了要重播(self, tmp_path):
        factory.write_marker(tmp_path, "1")
        assert factory.seeds_needed(tmp_path, "2") is True

    def test_标记读不出来时按未播处理(self, tmp_path):

        (tmp_path / factory.MARKER_NAME).mkdir()
        assert factory.seeds_needed(tmp_path, "1") is True





class TestSeed:
    def test_播种后装进技能库且带factory标记(self, resource, tmp_path):
        write_skill(resource, "营销", "brand-strategy", "brand-strategy", "品牌策略与提案")
        write_index(resource)
        runtime = FakeRuntime(tmp_path)

        result = factory.seed_factory_skills(runtime)

        assert result["seed"] is True
        assert result["installed"] == 1
        (defn,) = runtime.custom_skills.skills
        assert defn.id == "brand-strategy"
        assert defn.name == "品牌策略与提案", "显示名取自正文标题"
        assert defn.origin == "factory"
        assert defn.domain == "营销"
        assert (runtime.paths.skills_dir / "brand-strategy" / "SKILL.md").is_file()

    def test_第二次启动不再播种(self, resource, tmp_path):
        write_skill(resource, "营销", "brand-strategy", "brand-strategy", "品牌策略与提案")
        write_index(resource)
        runtime = FakeRuntime(tmp_path)

        assert factory.seed_factory_skills(runtime)["seed"] is True
        again = factory.seed_factory_skills(runtime)
        assert again["seed"] is False
        assert again["reason"] == "已播过"

    def test_用户删掉的出厂技能不会复活(self, resource, tmp_path):


        write_skill(resource, "营销", "brand-strategy", "brand-strategy", "品牌策略与提案")
        write_index(resource)
        runtime = FakeRuntime(tmp_path)
        factory.seed_factory_skills(runtime)

        
        runtime.custom_skills.skills.clear()

        assert factory.seed_factory_skills(runtime)["seed"] is False
        assert runtime.custom_skills.skills == [], "删掉的不能自己回来"

    def test_已存在的同id技能是被更新而不是多出一张卡(self, resource, tmp_path):


        write_skill(resource, "营销", "brand-strategy", "brand-strategy", "品牌策略与提案")
        write_index(resource)
        runtime = FakeRuntime(tmp_path)
        
        runtime.custom_skills.skills.append(
            CustomSkillDef(id="brand-strategy", name="老品牌策略", description="旧的", 
                           kind="instruction", instructions="旧正文")
        )

        factory.seed_factory_skills(runtime)

        ids = [item.id for item in runtime.custom_skills.skills]
        assert ids == ["brand-strategy"], f"不能被改成 -2 后缀：{ids}"
        assert runtime.custom_skills.skills[0].name == "品牌策略与提案"

    def test_排除名单里的技能不装(self, resource, tmp_path):
        write_skill(resource, "医疗", "sample-medication", "sample-medication", "用药参考")
        write_skill(resource, "营销", "brand-strategy", "brand-strategy", "品牌策略与提案")
        write_index(resource, excluded=["sample-medication"])
        runtime = FakeRuntime(tmp_path)

        result = factory.seed_factory_skills(runtime)

        assert [item.id for item in runtime.custom_skills.skills] == ["brand-strategy"]
        assert result["installed"] == 1
        
        assert result["failed"] == 0

    def test_一条坏技能不拖垮整批(self, resource, tmp_path):

        write_skill(resource, "营销", "brand-strategy", "brand-strategy", "品牌策略与提案")
        
        write_index(resource)
        (resource / "不存在").mkdir()  
        index = json.loads((resource / "index.json").read_text(encoding="utf-8"))
        index["skills"].append({"domain": "不存在", "ids": []})
        (resource / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

        runtime = FakeRuntime(tmp_path)
        result = factory.seed_factory_skills(runtime)

        assert result["installed"] == 1
        assert result["failed"] == 1
        assert [item.id for item in runtime.custom_skills.skills] == ["brand-strategy"]

    def test_有失败时不写标记以便下次重试(self, resource, tmp_path):
        write_index(resource)
        (resource / "不存在").mkdir()
        index = json.loads((resource / "index.json").read_text(encoding="utf-8"))
        index["skills"].append({"domain": "不存在", "ids": []})
        (resource / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        runtime = FakeRuntime(tmp_path)

        factory.seed_factory_skills(runtime)

        assert factory.seeds_needed(runtime.paths.data_dir, "1") is True, "有失败就该下次再试"

    def test_不写任何搭子的可用能力(self, resource, tmp_path):


        write_skill(resource, "营销", "brand-strategy", "brand-strategy", "品牌策略与提案")
        write_index(resource)
        runtime = FakeRuntime(tmp_path)

        factory.seed_factory_skills(runtime)

        
        
        assert not hasattr(runtime, "assistants")

    def test_缺分类目录不算失败也不阻断写标记(self, resource, tmp_path):




        write_skill(resource, "营销", "brand-strategy", "brand-strategy", "品牌策略与提案")
        write_index(resource)
        index = json.loads((resource / "index.json").read_text(encoding="utf-8"))
        index["skills"].append({"domain": "磁盘上没有这个分类", "ids": []})
        (resource / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        runtime = FakeRuntime(tmp_path)

        result = factory.seed_factory_skills(runtime)

        assert result["missing"] == 1
        assert result["failed"] == 0
        assert result["installed"] == 1
        assert factory.seeds_needed(runtime.paths.data_dir, "1") is False, "缺目录不该让每次开机都重播"

    def test_出厂的每个技能都必须带分类(self, resource, tmp_path):





        write_skill(resource, "营销", "brand-strategy", "brand-strategy", "品牌策略与提案")
        write_skill(resource, "医疗", "sample-medication", "sample-medication", "用药参考")
        write_index(resource)
        runtime = FakeRuntime(tmp_path)

        factory.seed_factory_skills(runtime)

        for defn in runtime.custom_skills.skills:
            assert defn.origin == "factory"
            assert defn.domain, f"出厂技能 {defn.id} 没有分类，会掉进「我的技能」栏"

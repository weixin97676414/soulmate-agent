"""出厂技能（随客户端分发的那批）的播种逻辑。

这一组的重点不是"能不能装上"，而是三条**容易改坏、坏了又很难看出来**的边界：

1. **绝不产生 `-2` 后缀**：用户本机已经装着同 id 的技能，播种若走了
   `install_defs` 的 `unique_id`，技能页会当场翻倍。
2. **删掉的不复活**：技能定义存在用户配置里、用户能删；靠版本 marker 保证
   "播过就不再播"，否则用户删掉的出厂技能下次开机就自己回来了。
3. **老配置仍能解析**：新增的 `origin` 字段必须带默认值 ——
   `load_custom_skills` 解析失败会**返回空配置**，那等于用户几百个技能静默消失。
"""

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
    """只带播种真正用到的那几样东西，省掉起一整个 AppRuntime 的代价。"""

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
    """造一份小规模出厂资源，并把播种的"资源根"指过去。"""
    root = tmp_path / "factory_skills"
    root.mkdir()
    monkeypatch.setattr(factory, "resource_root", lambda: root)
    return root


# --------------------------------------------------------------------------- #
# 配置兼容性（本次最容易出人命的一条）
# --------------------------------------------------------------------------- #
class TestSchemaCompat:
    def test_老配置没有origin字段也能解析(self):
        """⚠️ 加字段忘了给默认值 = 老配置校验失败 = `load_custom_skills` 返回空配置
        = 用户那几百个技能静默全消失。这条断言就是那个唯一拦截点。"""
        defn = CustomSkillDef.model_validate(
            {"id": "legacy", "name": "老技能", "kind": "instruction", "instructions": "正文"}
        )
        assert defn.origin == "user"

    def test_不在field名里的键不会被当成必填(self):
        """老配置里连 `domain` 都可能没有（那是更晚加的）。"""
        defn = CustomSkillDef.model_validate({"id": "a", "name": "b"})
        assert defn.domain == ""
        assert defn.origin == "user"


# --------------------------------------------------------------------------- #
# 索引与 marker
# --------------------------------------------------------------------------- #
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
        """读不出来就重播一次：upsert 是幂等的，比"该播没播"安全。"""
        (tmp_path / factory.MARKER_NAME).mkdir()
        assert factory.seeds_needed(tmp_path, "1") is True


# --------------------------------------------------------------------------- #
# 播种行为
# --------------------------------------------------------------------------- #
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
        """⚠️ 这是"版本 marker"存在的全部理由。换成"每次启动补一遍"，
        用户删掉的出厂技能会在下次开机自己回来 —— 本项目在 MCP 播种那里踩过。"""
        write_skill(resource, "营销", "brand-strategy", "brand-strategy", "品牌策略与提案")
        write_index(resource)
        runtime = FakeRuntime(tmp_path)
        factory.seed_factory_skills(runtime)

        # 用户删掉它（技能页的删除入口做的就是这件事）
        runtime.custom_skills.skills.clear()

        assert factory.seed_factory_skills(runtime)["seed"] is False
        assert runtime.custom_skills.skills == [], "删掉的不能自己回来"

    def test_已存在的同id技能是被更新而不是多出一张卡(self, resource, tmp_path):
        """⚠️ 播种**不能**走 `install_defs` 的 `unique_id`：它会把已被占用的 id
        改成 `-2` 后缀，用户本机那 254 个会同 id 撞上，技能页直接翻倍。"""
        write_skill(resource, "营销", "brand-strategy", "brand-strategy", "品牌策略与提案")
        write_index(resource)
        runtime = FakeRuntime(tmp_path)
        # 模拟"用户机上已经装着同名 id 的老技能"
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
        # 排除是**用户明确不要**、不是出错，所以不该算进 failed
        assert result["failed"] == 0

    def test_一条坏技能不拖垮整批(self, resource, tmp_path):
        """一个分类目录坏了，其余分类照装 —— 否则一个坏技能会让首启失去全部出厂技能。"""
        write_skill(resource, "营销", "brand-strategy", "brand-strategy", "品牌策略与提案")
        # 造一个"解析不出来"的分类：里面有 SKILL.md 但目录名对不上资源里的记录
        write_index(resource)
        (resource / "不存在").mkdir()  # 索引里有、磁盘上没有
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
        """⚠️ 播种只管"装进技能库"。顺手勾给搭子会把首启提示词撑爆
        （实测勾 254 个时，光文件清单就占十八万字里的三分之一）。"""
        write_skill(resource, "营销", "brand-strategy", "brand-strategy", "品牌策略与提案")
        write_index(resource)
        runtime = FakeRuntime(tmp_path)

        factory.seed_factory_skills(runtime)

        # FakeRuntime 里没有 assistants，这条靠"播种只碰 custom_skills"来保证：
        # 一旦有人往上加"顺手勾给默认搭子"，这里会因为访问不存在的属性而炸。
        assert not hasattr(runtime, "assistants")

    def test_缺分类目录不算失败也不阻断写标记(self, resource, tmp_path):
        """⚠️ 独立核查发现的一条：资源里少了分类目录时**不能算 `failed`**。
        `failed` 会阻止写 marker，而 marker 不写就意味着**每次启动都重播一遍**那 254 个技能 ——
        十几秒的开机开销天天白付，而"资源缺目录"是打包/同步的配置问题，重试也不会自己好。
        """
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
        """⚠️ 「我的技能」栏的过滤、以及「完全免费」徽标，判据都是 **`domain` 有没有值**
        （见 `SkillSettings.tsx` 与 `groups.bucket_of`）——**不是** `origin`。
        所以一个不带 domain 的出厂技能会掉进「我的技能」栏、还会丢掉标签。
        出厂技能的 domain 来自"它所在的分类目录"，天然非空；这条断言把那个前提钉住。
        """
        write_skill(resource, "营销", "brand-strategy", "brand-strategy", "品牌策略与提案")
        write_skill(resource, "医疗", "sample-medication", "sample-medication", "用药参考")
        write_index(resource)
        runtime = FakeRuntime(tmp_path)

        factory.seed_factory_skills(runtime)

        for defn in runtime.custom_skills.skills:
            assert defn.origin == "factory"
            assert defn.domain, f"出厂技能 {defn.id} 没有分类，会掉进「我的技能」栏"

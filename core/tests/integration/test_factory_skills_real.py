"""对**真实**出厂技能资源树的校验（第 89 批，M-28）。

## 为什么需要这一组

`tests/unit/test_factory_skills.py` 那 17 条用例用的是**现造的假资源**
（`write_skill` / `write_index`），而 `tests/conftest.py` 里那个 session 级 autouse
fixture 又把 `factory.resource_root` 指到一个**不存在的目录** —— 于是全仓用例
都不碰真实的出厂技能：**播种算法被测过，真实产物从来没有被加载校验过**。

后果是"`index.json` 与磁盘漂移"这类问题一路静默：
`factory.seed_factory_skills` 遇到"分类目录不存在"只打一条 warning 就跳过
（这是**刻意**的，理由见那里的注释：算成失败会导致每次启动重播 254 个技能），
于是用户装到的技能比索引里写的少，而**测试全绿**。

这一组刻意**不 patch 资源根**，直接对真实资源树断言：索引可解析、域在
`DOMAIN_ORDER` 内、索引与磁盘逐条对得上、并且真的能被 `parse_directory`
解析出**同一批 id**（播种走的就是这条路径）。

⚠️ 开发态还没跑同步脚本时资源不存在，此时**跳过而不是失败** ——
这与生产口径一致（`read_factory_index` 对"没有这份资源"就是安静跳过）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from my_agent.skill.factory import RESOURCE_DIR, parse_directory
from my_agent.skill.groups import DOMAIN_ORDER
from my_agent.utils import resources


def _real_root() -> Path:
    """真实资源根。

    ⚠️ 不能调 `factory.resource_root()`：那个函数被 session 级 autouse fixture
    monkeypatch 成了"不存在的目录"（为了让别的用例不真装 254 个技能）。
    这里按同一套算法自己算一遍 —— 见 `factory.resource_root` 的实现。
    """
    return Path(resources.resources_dir()) / RESOURCE_DIR


@pytest.fixture(scope="module")
def index() -> dict:
    root = _real_root()
    index_file = root / "index.json"
    if not index_file.is_file():
        pytest.skip(f"本机没有出厂技能资源（{root}），跳过真实资源校验")
    return json.loads(index_file.read_text(encoding="utf-8"))


def test_index_is_well_formed(index):
    """索引本身要能读、有版本号、有技能条目。"""
    assert index.get("version"), "索引必须带版本号 —— 播种靠它判断'这个版本播过没有'"
    assert isinstance(index.get("skills"), list) and index["skills"], "索引里一条技能都没有"
    for entry in index["skills"]:
        assert isinstance(entry.get("ids"), list), f"条目缺 ids：{entry}"


def test_every_domain_is_known(index):
    """索引里的域必须在 `DOMAIN_ORDER` 内。

    ⚠️ 域不在清单里的后果不是报错，而是**那个分类下的技能在界面上找不到归属**：
    前端按 `DOMAIN_ORDER` 渲染分类，多出来的域没有位置可落
    （`skill/groups.py` 与 `SkillSettings.tsx` 两处清单要求逐字一致，打包闸也钉着）。
    """
    unknown = [entry["domain"] for entry in index["skills"] if entry["domain"] not in DOMAIN_ORDER]
    assert unknown == [], f"索引里有 DOMAIN_ORDER 之外的域：{unknown}"


def test_index_matches_disk(index):
    """索引与磁盘**逐条对得上**：分类目录存在，且不含已被排除的技能 id。

    这一条是整组的核心。`seed_factory_skills` 对"分类目录不存在"只告警跳过，
    所以"索引写了、磁盘没有"与"磁盘有、索引没写"两种漂移都不会有任何报错 ——
    用户看到的现象只是"说明里说有这个技能，但我这儿没有"。
    """
    root = _real_root()
    excluded = {str(item) for item in (index.get("excluded") or ())}

    missing_dirs = [entry["domain"] for entry in index["skills"] if not (root / entry["domain"]).is_dir()]
    assert missing_dirs == [], f"索引里这些分类在磁盘上不存在（会被静默跳过）：{missing_dirs}"

    # 被排除的 id 不该再出现在任何分类里，否则"排除"只是句空话
    all_ids = {skill_id for entry in index["skills"] for skill_id in entry["ids"]}
    leaked = sorted(all_ids & excluded)
    assert leaked == [], f"这些 id 声明为排除却仍在索引里：{leaked}"
    assert len(all_ids) == sum(len(entry["ids"]) for entry in index["skills"]), "同一 id 出现在多个分类"


def test_real_tree_parses_to_the_indexed_ids(index):
    """真解析一遍：每个分类解析出的 id 必须与索引里写的**完全一致**。

    播种用的就是 `parse_directory`（按分类整体解析），所以这条等价于
    "用户实际会装到的技能 == 索引承诺的技能"。id 算法漂移、某个 `skill.json`
    坏掉、重名技能没有被去重成 `<父目录>/<名字>`，都会在这里露出来。

    ⚠️ 逐分类解析而不是逐技能目录：两者算出的 id 在**重名**时不一样
    （见 `factory.seed_factory_skills` 里那段说明）。这里必须与播种同口径。
    """
    root = _real_root()
    # 与播种同口径：`excluded` 里的 id 在播种时被跳过，所以**索引里本来就不该有它们**
    excluded = {str(item) for item in (index.get("excluded") or ())}
    mismatched: list[str] = []
    total = 0
    for entry in index["skills"]:
        domain = entry["domain"]
        # ⚠️ `parse_directory` 返回的是 `ParsedPackage`（`.defs` 是技能定义列表），
        # 不是 id → 技能的字典 —— 播种循环里也是 `for defn in parsed.defs`。
        parsed = parse_directory(root / domain, domain)
        actual = sorted(defn.id for defn in parsed.defs if defn.id not in excluded)
        expected = sorted(str(item) for item in entry["ids"])
        total += len(actual)
        if actual != expected:
            only_index = sorted(set(expected) - set(actual))
            only_disk = sorted(set(actual) - set(expected))
            mismatched.append(f"{domain}: 索引多出{only_index} 磁盘多出{only_disk}")
    assert mismatched == [], "索引与真实资源解析结果不一致：\n" + "\n".join(mismatched)

    # 出厂技能整体数量级兜底：数量突然掉一大截说明同步脚本或资源被截断了
    assert total > 100, f"解析出的出厂技能只有 {total} 个，疑似资源不完整"

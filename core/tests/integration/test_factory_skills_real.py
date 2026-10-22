





















from __future__ import annotations

import json
from pathlib import Path

import pytest

from my_agent.skill.factory import RESOURCE_DIR, parse_directory
from my_agent.skill.groups import DOMAIN_ORDER
from my_agent.utils import resources


def _real_root() -> Path:






    return Path(resources.resources_dir()) / RESOURCE_DIR


@pytest.fixture(scope="module")
def index() -> dict:
    root = _real_root()
    index_file = root / "index.json"
    if not index_file.is_file():
        pytest.skip(f"本机没有出厂技能资源（{root}），跳过真实资源校验")
    return json.loads(index_file.read_text(encoding="utf-8"))


def test_index_is_well_formed(index):

    assert index.get("version"), "索引必须带版本号 —— 播种靠它判断'这个版本播过没有'"
    assert isinstance(index.get("skills"), list) and index["skills"], "索引里一条技能都没有"
    for entry in index["skills"]:
        assert isinstance(entry.get("ids"), list), f"条目缺 ids：{entry}"


def test_every_domain_is_known(index):






    unknown = [entry["domain"] for entry in index["skills"] if entry["domain"] not in DOMAIN_ORDER]
    assert unknown == [], f"索引里有 DOMAIN_ORDER 之外的域：{unknown}"


def test_index_matches_disk(index):






    root = _real_root()
    excluded = {str(item) for item in (index.get("excluded") or ())}

    missing_dirs = [entry["domain"] for entry in index["skills"] if not (root / entry["domain"]).is_dir()]
    assert missing_dirs == [], f"索引里这些分类在磁盘上不存在（会被静默跳过）：{missing_dirs}"

    
    all_ids = {skill_id for entry in index["skills"] for skill_id in entry["ids"]}
    leaked = sorted(all_ids & excluded)
    assert leaked == [], f"这些 id 声明为排除却仍在索引里：{leaked}"
    assert len(all_ids) == sum(len(entry["ids"]) for entry in index["skills"]), "同一 id 出现在多个分类"


def test_real_tree_parses_to_the_indexed_ids(index):









    root = _real_root()
    
    excluded = {str(item) for item in (index.get("excluded") or ())}
    mismatched: list[str] = []
    total = 0
    for entry in index["skills"]:
        domain = entry["domain"]
        
        
        parsed = parse_directory(root / domain, domain)
        actual = sorted(defn.id for defn in parsed.defs if defn.id not in excluded)
        expected = sorted(str(item) for item in entry["ids"])
        total += len(actual)
        if actual != expected:
            only_index = sorted(set(expected) - set(actual))
            only_disk = sorted(set(actual) - set(expected))
            mismatched.append(f"{domain}: 索引多出{only_index} 磁盘多出{only_disk}")
    assert mismatched == [], "索引与真实资源解析结果不一致：\n" + "\n".join(mismatched)

    
    assert total > 100, f"解析出的出厂技能只有 {total} 个，疑似资源不完整"

"""地点核对（``skill/builtin/geo_lookup.py``）。

## 为什么这些断言值得写死

心鉴学的报告接口要求地点写到**城市**一级，写错层级就是 ``400 地点无法识别``；
而"换一个分析对象"（switch_person）是**要扣 token** 的 ——
用户是拿钱在试错。所以这条链路上每一个"看起来差不多"的结果都要钉住：
少一层（只核到省）和错一层（核到隔壁州）在界面上都表现为"提交失败"，
但用户该做的下一步完全不同。
"""

from __future__ import annotations

import pytest

from my_agent.errors import SkillExecutionError
from my_agent.skill.base import SkillContext
from my_agent.skill.builtin import geo_lookup
from my_agent.skill.builtin.geo_lookup import check_place, lookup


# --------------------------------------------------------------------------- #
# 命中：回到规范写法
# --------------------------------------------------------------------------- #
def test_china_province_and_city() -> None:
    """最标准的一路：国家 + 省 + 市。"""
    result = lookup("中国", "浙江省", "杭州市")

    assert result.matched is True
    assert result.level == "city"
    assert result.canonical == "中国 浙江省 杭州市"


def test_suffix_is_optional() -> None:
    """用户不会写全称 —— 「浙江」「杭州」必须和「浙江省」「杭州市」等价。"""
    assert lookup("中国", "浙江", "杭州").canonical == "中国 浙江省 杭州市"
    assert lookup("中国", "浙江", "杭州").matched is True


def test_country_can_be_inferred_from_province() -> None:
    """只写了"浙江省 杭州市"也要能反推出国家 —— 用户经常省掉国家。"""
    result = check_place("浙江省 杭州市")

    assert result.matched is True
    assert result.country == "中国"
    assert result.canonical == "中国 浙江省 杭州市"


def test_city_alone_is_searched_across_the_country() -> None:
    """只给一个城市名：在全国范围里找，找到就补全省。"""
    result = check_place("杭州")

    assert result.matched is True
    assert result.province == "浙江省"
    assert result.canonical == "中国 浙江省 杭州市"


def test_municipality_does_not_repeat_the_city_name() -> None:
    """直辖市没有下级"市"：规范写法是「中国 北京市 海淀区」，不是「… 北京市 北京市」。"""
    result = lookup("中国", "北京", "北京", "海淀区")

    assert result.matched is True
    assert result.canonical == "中国 北京市"
    assert result.display() == "中国 北京市 海淀区"


def test_foreign_country_needs_the_region_name() -> None:
    """外国走到"州/省"一级 —— 这一层只有加进来过的国家才有。"""
    result = lookup("美国", "加利福尼亚州", "旧金山")

    assert result.matched is True
    assert result.canonical == "美国 加利福尼亚州 旧金山"


def test_city_written_in_the_province_slot_is_recovered() -> None:
    """「法国 巴黎」是极常见的写法：巴黎是城市，不是大区。

    这种输入**不该**甩一份大区清单让用户认 —— 他本来就不知道自己该写哪个大区。
    先按城市试一次，试中了就把规范写法告诉他。
    """
    result = lookup("法国", "巴黎")

    assert result.matched is True
    assert result.province == "法兰西岛大区"
    assert result.canonical == "法国 法兰西岛大区 巴黎"


def test_us_state_abbreviation() -> None:
    """``NY`` / ``CA`` 这类缩写要认 —— 用户原话里就是这么写的。"""
    assert lookup("美国", "CA", "旧金山").canonical == "美国 加利福尼亚州 旧金山"
    assert lookup("美国", "NY", "纽约").matched is True


# --------------------------------------------------------------------------- #
# 没命中：分层候选（这才是"逐级重试"的载体）
# --------------------------------------------------------------------------- #
def test_typo_returns_layered_candidates() -> None:
    """「杭洲」这种错字：给出同省 → 相邻省 → 全国主要城市三层候选。

    ``level`` 必须如实报成 ``province`` —— 省这一级是**核对过的**。
    报 ``none`` 会让模型重新问一遍省份，用户会觉得"这搭子怎么又问回来了"。
    """
    result = lookup("中国", "浙江", "杭洲")

    assert result.matched is False
    assert result.level == "province"
    assert result.province == "浙江省"

    scopes = {item["scope"] for item in result.candidates}
    assert scopes == {"same_region", "adjacent", "country_major"}

    # 同省候选里必须有真正的杭州 —— 逐级重试能命中的前提
    same_region = [item["value"] for item in result.candidates if item["scope"] == "same_region"]
    assert "中国 浙江省 杭州市" in same_region

    # 相邻省清单要一并给出来，模型才有"最近的那个"可挑
    assert result.adjacent, "省级邻接表没有生效"
    assert "江苏省" in result.adjacent


def test_candidates_are_deduplicated() -> None:
    """三层候选会重叠（省会同时属于"同省"和"该国主要城市"），不能出现重复项。"""
    result = lookup("中国", "浙江", "杭洲")
    values = [item["value"] for item in result.candidates]

    assert len(values) == len(set(values))


def test_unknown_province_falls_back_to_country_list() -> None:
    """省名核不上、又不是城市名 → 给出该国的一级行政区清单，并让用户确认。"""
    result = lookup("美国", "火星州", "随便市")

    assert result.matched is False
    assert "加利福尼亚州" in result.available


def test_unknown_country_says_so_instead_of_guessing() -> None:
    """库里没有的国家：明确说"核不上"，**绝不编一个相近的国家出来**。"""
    result = lookup("瓦坎达")

    assert result.matched is False
    assert result.country_known is False
    assert "国家" in result.note


def test_empty_input_asks_for_information() -> None:
    result = check_place("   ")

    assert result.matched is False
    assert "空" in result.note


# --------------------------------------------------------------------------- #
# 数据自检
# --------------------------------------------------------------------------- #
def test_adjacency_is_symmetric() -> None:
    """邻接关系必须对称：A 的邻居里有 B，B 的邻居里就得有 A。

    不对称的话，"相邻最近城市"这条降级链会在半个国家里凭空断掉，
    而且**不会报错** —— 只是候选少了一批，用户看到的是"找不到附近的地方"。
    """
    data = geo_lookup._adjacency()

    for key, section in (("provinces", "省"), ("countries", "国家")):
        table = data[key]
        for name, neighbours in table.items():
            for other in neighbours:
                assert other in table, f"{section}邻接表里有未知条目：{other}"
                assert name in table[other], f"{section}邻接不对称：{name} → {other} 没有回边"


def test_adjacency_covers_every_china_province() -> None:
    """34 个省级行政区一个都不能漏 —— 漏掉的那个省，"相邻城市"永远是空的。"""
    provinces = geo_lookup._adjacency()["provinces"]
    missing = [name for name in geo_lookup._regions() if name not in provinces]

    assert not missing, f"这些省级行政区没有邻接关系：{missing}"


# --------------------------------------------------------------------------- #
# 工具层
# --------------------------------------------------------------------------- #
def _ctx(assistant_id: str) -> SkillContext:
    return SkillContext(assistant_id=assistant_id)


@pytest.mark.asyncio
async def test_tool_rejects_non_owner_assistant() -> None:
    """专属技能的**配套工具**也必须是专属的：别的搭子连调都不该调得动。

    ⚠️ 这一层和"工具清单里看不见"是两回事，两道都要有：
    清单是给模型看的，而这条是给"模型硬要调"兜底的。
    """
    from my_agent.skill.builtin.geo_lookup import PlaceLookupSkill

    with pytest.raises(SkillExecutionError) as exc:
        await PlaceLookupSkill().run(_ctx("some-other-buddy"), city="杭州")

    assert "归属" in str(exc.value) or "Soulmate" in str(exc.value)


@pytest.mark.asyncio
async def test_tool_happy_path_returns_json() -> None:
    """正常路径返回 JSON 文本（工具返回值就是给模型读的，不是给界面渲染的）。"""
    import json

    from my_agent.skill.builtin.geo_lookup import PlaceLookupSkill

    payload = json.loads(await PlaceLookupSkill().run(_ctx("soulmate"), raw="浙江省 杭州市"))

    assert payload["matched"] is True
    assert payload["canonical"] == "中国 浙江省 杭州市"
    assert "current_place" in payload["next_step"]

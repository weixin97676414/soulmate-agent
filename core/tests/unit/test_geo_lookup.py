










from __future__ import annotations

import pytest

from my_agent.errors import SkillExecutionError
from my_agent.skill.base import SkillContext
from my_agent.skill.builtin import geo_lookup
from my_agent.skill.builtin.geo_lookup import check_place, lookup





def test_china_province_and_city() -> None:

    result = lookup("中国", "浙江省", "杭州市")

    assert result.matched is True
    assert result.level == "city"
    assert result.canonical == "中国 浙江省 杭州市"


def test_suffix_is_optional() -> None:

    assert lookup("中国", "浙江", "杭州").canonical == "中国 浙江省 杭州市"
    assert lookup("中国", "浙江", "杭州").matched is True


def test_country_can_be_inferred_from_province() -> None:

    result = check_place("浙江省 杭州市")

    assert result.matched is True
    assert result.country == "中国"
    assert result.canonical == "中国 浙江省 杭州市"


def test_city_alone_is_searched_across_the_country() -> None:

    result = check_place("杭州")

    assert result.matched is True
    assert result.province == "浙江省"
    assert result.canonical == "中国 浙江省 杭州市"


def test_municipality_does_not_repeat_the_city_name() -> None:

    result = lookup("中国", "北京", "北京", "海淀区")

    assert result.matched is True
    assert result.canonical == "中国 北京市"
    assert result.display() == "中国 北京市 海淀区"


def test_foreign_country_needs_the_region_name() -> None:

    result = lookup("美国", "加利福尼亚州", "旧金山")

    assert result.matched is True
    assert result.canonical == "美国 加利福尼亚州 旧金山"


def test_city_written_in_the_province_slot_is_recovered() -> None:





    result = lookup("法国", "巴黎")

    assert result.matched is True
    assert result.province == "法兰西岛大区"
    assert result.canonical == "法国 法兰西岛大区 巴黎"


def test_us_state_abbreviation() -> None:

    assert lookup("美国", "CA", "旧金山").canonical == "美国 加利福尼亚州 旧金山"
    assert lookup("美国", "NY", "纽约").matched is True





def test_typo_returns_layered_candidates() -> None:





    result = lookup("中国", "浙江", "杭洲")

    assert result.matched is False
    assert result.level == "province"
    assert result.province == "浙江省"

    scopes = {item["scope"] for item in result.candidates}
    assert scopes == {"same_region", "adjacent", "country_major"}

    
    same_region = [item["value"] for item in result.candidates if item["scope"] == "same_region"]
    assert "中国 浙江省 杭州市" in same_region

    
    assert result.adjacent, "省级邻接表没有生效"
    assert "江苏省" in result.adjacent


def test_candidates_are_deduplicated() -> None:

    result = lookup("中国", "浙江", "杭洲")
    values = [item["value"] for item in result.candidates]

    assert len(values) == len(set(values))


def test_unknown_province_falls_back_to_country_list() -> None:

    result = lookup("美国", "火星州", "随便市")

    assert result.matched is False
    assert "加利福尼亚州" in result.available


def test_unknown_country_says_so_instead_of_guessing() -> None:

    result = lookup("瓦坎达")

    assert result.matched is False
    assert result.country_known is False
    assert "国家" in result.note


def test_empty_input_asks_for_information() -> None:
    result = check_place("   ")

    assert result.matched is False
    assert "空" in result.note





def test_adjacency_is_symmetric() -> None:





    data = geo_lookup._adjacency()

    for key, section in (("provinces", "省"), ("countries", "国家")):
        table = data[key]
        for name, neighbours in table.items():
            for other in neighbours:
                assert other in table, f"{section}邻接表里有未知条目：{other}"
                assert name in table[other], f"{section}邻接不对称：{name} → {other} 没有回边"


def test_adjacency_covers_every_china_province() -> None:

    provinces = geo_lookup._adjacency()["provinces"]
    missing = [name for name in geo_lookup._regions() if name not in provinces]

    assert not missing, f"这些省级行政区没有邻接关系：{missing}"





def _ctx(assistant_id: str) -> SkillContext:
    return SkillContext(assistant_id=assistant_id)


@pytest.mark.asyncio
async def test_tool_rejects_non_owner_assistant() -> None:





    from my_agent.skill.builtin.geo_lookup import PlaceLookupSkill

    with pytest.raises(SkillExecutionError) as exc:
        await PlaceLookupSkill().run(_ctx("some-other-buddy"), city="杭州")

    assert "归属" in str(exc.value) or "Soulmate" in str(exc.value)


@pytest.mark.asyncio
async def test_tool_happy_path_returns_json() -> None:

    import json

    from my_agent.skill.builtin.geo_lookup import PlaceLookupSkill

    payload = json.loads(await PlaceLookupSkill().run(_ctx("soulmate"), raw="浙江省 杭州市"))

    assert payload["matched"] is True
    assert payload["canonical"] == "中国 浙江省 杭州市"
    assert "current_place" in payload["next_step"]


@pytest.mark.asyncio
async def test_unmatched_place_is_advice_not_a_gate() -> None:









    import json

    from my_agent.skill.builtin.geo_lookup import PlaceLookupSkill

    payload = json.loads(
        await PlaceLookupSkill().run(_ctx("soulmate"), raw="中国 新疆 北屯")
    )

    assert payload["matched"] is False
    step = payload["next_step"]
    assert "原样提交" in step
    assert "不是拦截" in step
    
    assert "挑地理上最近的一个" not in step

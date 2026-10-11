"""内置地点核对：把用户嘴里的地名，核成地点库里的规范写法。

## 为什么要有它

心鉴学的报告接口要求 ``current_place`` / ``birth_place`` 写到**城市**一级
（国家 + 省/州 + 城市）。写错一个层级就返回 ``400 地点无法识别``，而换一个分析
对象（``switch_person``）是**要扣 token** 的 —— "先核对、再提交"直接关系到用户花钱。

## 核对流程

逐级核对，**能匹配到多深就返回多深**；没命中时按"同省 → 相邻省/州 → 该国主要城市"
降级给候选（``candidates[].scope``），由模型结合用户原话挑最近的那个。
找不到就如实说"核不上"并要求向用户补全 —— **绝不编地名**。

为什么不直接算地理距离：库里没有经纬度。硬凑一份坐标表只会得到"看起来精确、
实际是编的"排序；分层候选 + 相邻省清单反而可靠。

## 数据

``my_agent/resources/geo/``（由 ``core/tools/build_geo_data.py`` 从《心鉴学-地点库》
转出，随核心打包）。缺文件**直接报错**，见 ``utils/resources.py`` 开头的说明。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ...utils.resources import load_json
from ..base import BaseSkill, SkillContext
from ..decorator import skill
from . import xjx

# --------------------------------------------------------------------------- #
# 归一化
# --------------------------------------------------------------------------- #
# 行政区划后缀：核对时"浙江"和"浙江省"是同一个地方，用户不会写全称。
_SUFFIXES = (
    "特别行政区", "自治区", "特别市", "地区", "新区",
    "省", "市", "区", "县", "州", "盟", "旗",
)

# 美国州名缩写（用户写 "CA" / "NY" 时不必让人去查全称）。
_US_STATE_ABBR: dict[str, str] = {
    "AL": "亚拉巴马州", "AK": "阿拉斯加州", "AZ": "亚利桑那州", "AR": "阿肯色州",
    "CA": "加利福尼亚州", "CO": "科罗拉多州", "CT": "康涅狄格州", "DE": "特拉华州",
    "FL": "佛罗里达州", "GA": "佐治亚州", "HI": "夏威夷州", "ID": "爱达荷州",
    "IL": "伊利诺伊州", "IN": "印第安纳州", "IA": "艾奥瓦州", "KS": "堪萨斯州",
    "KY": "肯塔基州", "LA": "路易斯安那州", "ME": "缅因州", "MD": "马里兰州",
    "MA": "马萨诸塞州", "MI": "密歇根州", "MN": "明尼苏达州", "MS": "密西西比州",
    "MO": "密苏里州", "MT": "蒙大拿州", "NE": "内布拉斯加州", "NV": "内华达州",
    "NH": "新罕布什尔州", "NJ": "新泽西州", "NM": "新墨西哥州", "NY": "纽约州",
    "NC": "北卡罗来纳州", "ND": "北达科他州", "OH": "俄亥俄州", "OK": "俄克拉何马州",
    "OR": "俄勒冈州", "PA": "宾夕法尼亚州", "RI": "罗得岛州", "SC": "南卡罗来纳州",
    "SD": "南达科他州", "TN": "田纳西州", "TX": "得克萨斯州", "UT": "犹他州",
    "VT": "佛蒙特州", "VA": "弗吉尼亚州", "WA": "华盛顿州", "WV": "西弗吉尼亚州",
    "WI": "威斯康星州", "WY": "怀俄明州", "DC": "华盛顿哥伦比亚特区",
}

# 口语里的州/省简称 → 库里的规范名。
#
# **只收最常用的那几个**：这种表越全越危险 —— 每一条都是一个人工判断，
# 猜错一个就会把用户引到一个相邻的州（而用户看不出来，因为结果看起来很正常）。
# 判断不了的就别放进来，让候选清单去兜底。
#
# 注意键要写**去后缀后的形式**：查表用的是 ``_loose``，而 ``_loose("加州")``
# 是 ``"加"``（"州"是后缀）。写成 "加州" 会永远查不中。
_REGION_ALIASES: dict[str, dict[str, str]] = {
    "美国": {
        "加": "加利福尼亚州",
        "德": "得克萨斯州",
        "佛": "佛罗里达州",
        "麻": "马萨诸塞州",
        "宾": "宾夕法尼亚州",
        "华": "华盛顿州",
    },
}

_PUNCT = re.compile(r"[\s\u3000·・,，、.。\-—_/\\()（）\[\]【】]+")

# 地点库里唯一有"完整省市两级"的国家。判定必须显式写成常量比较 ——
# ``country in _regions()`` 这种写法看着像在问"这个国家在不在中国省表里"，
# 实际是在问"这个国家名是不是某个省名"，永远是 False，而且不会报错。
CHINA = "中国"


def _norm(text: str) -> str:
    """全角转半角 + 去标点空白 + 拉丁小写。"""
    if not text:
        return ""
    out: list[str] = []
    for char in text:
        code = ord(char)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(char)
    return _PUNCT.sub("", "".join(out)).lower()


def _loose(text: str | None) -> str:
    """剥掉行政区划后缀的"松"键：``浙江省`` → ``浙江``。"""
    key = _norm(text or "")
    for _ in range(2):  # "广西壮族自治区" 要剥两层
        for suffix in _SUFFIXES:
            if key.endswith(suffix) and len(key) > len(suffix):
                key = key[: -len(suffix)]
                break
        else:
            break
    return key


def _alias_key(text: str | None) -> str:
    """缩写先查表（``NY`` → ``纽约州`` 的松键），再走松键。"""
    raw = (text or "").strip().upper()
    if raw in _US_STATE_ABBR:
        return _loose(_US_STATE_ABBR[raw])
    return _loose(text)


# --------------------------------------------------------------------------- #
# 数据集（惰性加载 + 缓存）
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _regions() -> dict[str, Any]:
    """中国 34 个省级行政区：``{省: {市: [区,…]}}``；直辖市是 ``{省: [区,…]}``。"""
    return load_json("geo", "regions.json")


@lru_cache(maxsize=1)
def _country_regions() -> dict[str, dict[str, list[str]]]:
    """中国之外精选国家：``{国家: {州/省: [城市,…]}}``。"""
    return load_json("geo", "countries_regions.json")


@lru_cache(maxsize=1)
def _adjacency() -> dict[str, dict[str, list[str]]]:
    return load_json("geo", "adjacency.json")


@lru_cache(maxsize=1)
def _country_keys() -> dict[str, str]:
    """国家名/英文名/ISO 码 → 中文规范名。"""
    index: dict[str, str] = {}
    for item in load_json("geo", "countries.json"):
        canonical = item.get("zh") or item.get("en") or ""
        if not canonical:
            continue
        raws = (item.get("zh", ""), item.get("en", ""), item.get("iso2", ""), item.get("iso3", ""))
        for raw in raws:
            for key in {_norm(raw), _loose(raw)}:
                if key:
                    index.setdefault(key, canonical)
    return index


@lru_cache(maxsize=1)
def _region_keys() -> dict[str, dict[str, str]]:
    """``{国家: {州/省松键: 规范名}}``。

    **中国被排除在外**：它有专门的 ``regions.json``，``countries_regions.json``
    里若也留了一份，两张表必然对不齐（一张到"市"、一张到"州"），
    到时候"查得到但查得浅了"这种半对的结果最难发现。
    """
    return {
        country: {_loose(name): name for name in regions} | _REGION_ALIASES.get(country, {})
        for country, regions in _country_regions().items()
        if country != CHINA
    }


@lru_cache(maxsize=1)
def _province_keys() -> dict[str, str]:
    return {_loose(name): name for name in _regions()}


def _cities_of(province: str) -> dict[str, list[str]]:
    value = _regions().get(province)
    if isinstance(value, dict):
        return value
    if isinstance(value, list):  # 直辖市：区列表当作它的一级列表
        return {"": list(value)}
    return {}


@lru_cache(maxsize=1)
def _city_index() -> dict[str, list[tuple[str, str]]]:
    """中国 ``市松键 → [(省, 市), …]``（同名市会落到多个省，如实都给）。"""
    index: dict[str, list[tuple[str, str]]] = {}
    for province, value in _regions().items():
        if isinstance(value, dict):
            for city in value:
                index.setdefault(_loose(city), []).append((province, city))
    return index


@lru_cache(maxsize=1)
def _district_index() -> dict[tuple[str, str], dict[str, str]]:
    index: dict[tuple[str, str], dict[str, str]] = {}
    for province, value in _regions().items():
        if isinstance(value, dict):
            for city, districts in value.items():
                index[(province, city)] = {_loose(d): d for d in districts}
    return index


@lru_cache(maxsize=1)
def _major_cities() -> dict[str, list[str]]:
    """主要城市：源数据按省会优先排列，取前 4 座；外国按州/省同样取前 4 座。"""
    major: dict[str, list[str]] = {}
    for province, value in _regions().items():
        cities = list(value) if isinstance(value, dict) else []
        major[province] = cities[:4] or [province]
    for country, regions in _country_regions().items():
        for region, cities in regions.items():
            major[f"{country}|{region}"] = cities[:4]
    return major


def _provinces_of(country: str) -> dict[str, str]:
    """该国一级行政区 ``{松键: 规范名}``。

    ``CHINA`` 必须先判：它是唯一有**完整省市库**（``regions.json``）的国家，
    而 ``countries_regions.json`` 里也可能有它的一份粗表 —— 先查后者会让
    "浙江省 → 杭州市"退化成"浙江省"或者干脆查不到，而用户完全无从察觉。
    """
    if country == CHINA:
        return _province_keys()
    if country in _region_keys():
        return _region_keys()[country]
    return {}


def _city_keys_of(country: str, region: str) -> dict[str, str]:
    if country == CHINA:
        return {_loose(c): c for c in _cities_of(region)}
    return {_loose(c): c for c in _country_regions().get(country, {}).get(region, [])}


def _is_municipality(country: str, region: str) -> bool:
    """直辖市（北京/上海/天津/重庆）：它没有下级"市"，区就是一级。"""
    return country == CHINA and isinstance(_regions().get(region), list)


# --------------------------------------------------------------------------- #
# 结果与候选
# --------------------------------------------------------------------------- #
_MAX_CANDIDATES = 60


@dataclass
class PlaceLookupResult:
    """一次核对的结果。``matched`` 为假时 ``candidates`` / ``available`` 才是重点。"""

    matched: bool
    level: str = "none"  # country / province / city / district / none
    country: str = ""
    province: str = ""
    city: str = ""
    district: str = ""
    country_known: bool = False
    note: str = ""
    candidates: list[dict[str, str]] = field(default_factory=list)
    available: list[str] = field(default_factory=list)
    adjacent: list[str] = field(default_factory=list)

    @property
    def canonical(self) -> str:
        """规范写法：``中国 浙江省 杭州市``（直辖市不重复市名）。"""
        parts: list[str] = []
        for item in (self.country, self.province, self.city):
            if item and item not in parts:
                parts.append(item)
        return " ".join(parts)

    def display(self) -> str:
        """给模型看的 ``.xxx`` 写法：``中国 浙江省 杭州市 西湖区``。"""
        parts = [self.canonical, self.district]
        return " ".join(p for p in parts if p)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "matched": self.matched,
            "level": self.level,
            "country_known": self.country_known,
            "canonical": self.canonical if self.matched else "",
            "parts": {
                "country": self.country,
                "province": self.province,
                "city": self.city,
                "district": self.district,
            },
        }
        if self.candidates:
            data["candidates"] = self.candidates[:_MAX_CANDIDATES]
        if self.available:
            data["available"] = self.available
        if self.adjacent:
            data["adjacent"] = self.adjacent
        if self.note:
            data["note"] = self.note
        return data


def _dedup(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for item in items:
        if item["value"] in seen:
            continue
        seen.add(item["value"])
        result.append(item)
        if len(result) >= _MAX_CANDIDATES:
            break
    return result


def _same_region(country: str, region: str) -> list[dict[str, str]]:
    """同省/同州的城市。直辖市没有下级"市"，就是它自己。"""
    if _is_municipality(country, region):
        return [{"scope": "same_region", "value": f"{country} {region}", "city": region}]
    if country == CHINA:
        cities = list(_cities_of(region))
    else:
        cities = list(_country_regions().get(country, {}).get(region, []))
    return [
        {"scope": "same_region", "value": f"{country} {region} {city}", "city": city}
        for city in cities
    ]


def _adjacent(country: str, region: str) -> tuple[list[dict[str, str]], list[str]]:
    """相邻省/州的主要城市。

    中国用省级邻接表；其它国家用国家级邻接表 —— 库里没有"外国省与省相邻"的
    数据，跨到邻国去找反而更可能是用户真实想说的那个地方（人在边境城市时
    写错国家并不罕见）。
    """
    if country == CHINA:
        neighbours = _adjacency()["provinces"].get(region, [])
        major = _major_cities()
        return (
            [
                {"scope": "adjacent", "value": f"{country} {item} {city}", "city": city}
                for item in neighbours
                for city in major.get(item, [])[:3]
            ],
            neighbours,
        )
    neighbours = _adjacency()["countries"].get(country, [])
    candidates: list[dict[str, str]] = []
    for other in neighbours:
        for other_region, cities in _country_regions().get(other, {}).items():
            candidates.extend(
                {"scope": "adjacent", "value": f"{other} {other_region} {city}", "city": city}
                for city in cities[:3]
            )
    return candidates, neighbours


def _country_major(country: str) -> list[dict[str, str]]:
    """该国主要城市：中国 = 各省省会，其它国家 = 各省/州的首府。"""
    if country == CHINA:
        major = _major_cities()
        return [
            {"scope": "country_major", "value": f"{country} {item} {major[item][0]}", "city": major[item][0]}
            for item in _regions()
            if major.get(item)
        ]
    return [
        {"scope": "country_major", "value": f"{country} {region} {city}", "city": city}
        for region, cities in _country_regions().get(country, {}).items()
        for city in cities[:2]
    ]


# --------------------------------------------------------------------------- #
# 核对
# --------------------------------------------------------------------------- #
def resolve_country(country: str | None, province: str | None, city: str | None) -> str | None:
    """定出国家规范名。用户没给国家时从省/市反推（``浙江``→中国，``纽约州``→美国）。"""
    if country:
        return _country_keys().get(_alias_key(country))
    if province:
        key = _alias_key(province)
        if key in _province_keys():
            return "中国"
        for known, regions in _region_keys().items():
            if key in regions:
                return known
    if city:
        key = _loose(city)
        if key in _city_index():
            return "中国"
        for known in _country_regions():
            for region in _country_regions()[known]:
                if key in _city_keys_of(known, region):
                    return known
    return None


def _find_city(country: str, city: str) -> list[tuple[str, str]]:
    """只给了城市时：在整个国家里找（返回 ``[(省/州, 城市), …]``）。"""
    key = _loose(city)
    if country == "中国":
        return _city_index().get(key, [])
    return [
        (region, cities[key])
        for region, cities in ((r, _city_keys_of(country, r)) for r in _country_regions().get(country, {}))
        if key in cities
    ]


def lookup(
    country: str | None = None,
    province: str | None = None,
    city: str | None = None,
    district: str | None = None,
) -> PlaceLookupResult:
    """逐级核对：命中回规范写法，没命中回分层候选。"""
    resolved = resolve_country(country, province, city)
    if not resolved:
        return PlaceLookupResult(
            matched=False,
            note=(
                "地点库里没有这个国家/地区。请让用户给出「国家 + 省/州 + 城市」，"
                "或先确认国家名的规范写法。"
            ),
        )

    result = PlaceLookupResult(matched=False, country=resolved, country_known=True)
    provinces = _provinces_of(resolved)
    if not provinces:
        # 国家认得，但没有省市数据：如实说"只能核到国家一级"，不拦着提交
        result.matched = not province and not city
        result.level = "country"
        result.note = (
            f"地点库里「{resolved}」只到国家一级，省/市无法核对。请与用户确认写法后提交；"
            "若服务端回 400 地点无法识别，再回来补全信息。"
        )
        return result

    if not province and not city:
        result.matched = True
        result.level = "country"
        return result

    if not province:
        hits = _find_city(resolved, city or "")
        if hits:
            result.province, result.city = hits[0]
            result.level = "city"
            result.matched = not district or _match_district(result, district or "", strict=True)
            if not result.matched:
                result.candidates = _dedup(
                    [
                        {"scope": "same_region", "value": item, "city": item.rsplit(" ", 1)[-1]}
                        for item in _district_values(result)
                    ]
                )
                result.note = f"「{result.canonical}」下没有「{district}」，candidates 是它的区/县。"
            return result
        result.available = sorted(provinces.values())
        result.note = (
            f"地点库里找不到城市「{city}」。available 是该国的一级行政区，"
            "请让用户从中确认，或补全省/州。"
        )
        return result

    province_name = provinces.get(_alias_key(province)) or provinces.get(_loose(province))
    if not province_name:
        # 把城市写在了省的位置 —— "美国 洛杉矶"、"法国 巴黎" 都是极常见的写法。
        # 先按城市试一次，比直接甩一份州清单有用得多（那份清单用户根本认不出哪个对）。
        hits = _find_city(resolved, province)
        if hits:
            result.province, result.city = hits[0]
            result.level = "city"
            result.matched = True
            result.note = (
                f"「{province}」在库里是「{result.province}」下的城市，"
                f"规范写法是「{result.canonical}」。"
            )
            return result
        result.level = "country"
        result.available = sorted(provinces.values())
        result.note = (
            f"地点库里没有「{resolved} {province}」这个省/州。available 是该国的一级行政区，"
            "请让用户从中确认。"
        )
        return result
    result.province = province_name

    if not city:
        result.matched = True
        result.level = "province"
        return result

    if _is_municipality(resolved, province_name):
        # 直辖市：用户把区写在了市的位置（或干脆只写"北京"）
        result.city = province_name
        result.level = "city"
        result.matched = True
        result.note = f"「{province_name}」是直辖市，规范写法不重复市名。"
        if district:
            _match_district(result, district)
        return result

    cities = _city_keys_of(resolved, province_name)
    city_name = cities.get(_loose(city))
    if not city_name:
        adjacent_candidates, neighbours = _adjacent(resolved, province_name)
        result.candidates = _dedup(
            _same_region(resolved, province_name)
            + adjacent_candidates
            + _country_major(resolved)
        )
        result.adjacent = neighbours
        # 省这一级是核对的 —— "没匹配上"不等于"没有任何信息"。把最深的命中层级
        # 如实报出去，模型才知道该在"省已确认为浙江省"的基础上找城市，
        # 而不是重新问一遍省份
        result.level = "province"
        result.note = (
            f"地点库里「{province_name}」下没有「{city}」。candidates 按 "
            "同省 → 相邻省/州 → 该国主要城市 分层给出（scope 字段标明层级），"
            "请从中挑地理上最近的那个，用它的 value 作为规范写法。"
        )
        return result
    result.city = city_name
    result.level = "city"

    if not district:
        result.matched = True
        return result
    result.matched = _match_district(result, district)
    if not result.matched:
        result.candidates = _dedup(
            [
                {"scope": "same_region", "value": item, "city": item.rsplit(" ", 1)[-1]}
                for item in _district_values(result)
            ]
        )
        result.note = f"地点库里「{result.canonical}」下没有「{district}」，candidates 是它的区/县。"
    return result


def _district_values(result: PlaceLookupResult) -> list[str]:
    districts = _district_index().get((result.province, result.city), {})
    return [f"{result.country} {result.province} {result.city} {name}" for name in districts.values()]


def _match_district(result: PlaceLookupResult, district: str, *, strict: bool = False) -> bool:
    """区/县核对。命中就写进结果。``strict=False`` 时不命中也不改 ``matched``。"""
    key = _loose(district)
    districts = _district_index().get((result.province, result.city))
    if districts is None:
        # 直辖市：区挂在省这一级
        value = _regions().get(result.province)
        if isinstance(value, list):
            districts = {_loose(d): d for d in value}
    if districts and key in districts:
        result.district = districts[key]
        return True
    if strict:
        return not district
    return False


# --------------------------------------------------------------------------- #
# 拆词
# --------------------------------------------------------------------------- #
def split_place(text: str | None) -> list[str]:
    """把 ``"中国 浙江省 杭州市"`` 拆成 ``["中国", "浙江省", "杭州市"]``。"""
    if not text:
        return []
    return [part for part in re.split(r"[\s\u3000,，、/]+", text.strip()) if part]


def check_place(text: str | None) -> PlaceLookupResult:
    """核对一句"用户原话"形态的地点（允许只写国家 / 只写城市）。"""
    parts = split_place(text)
    if not parts:
        return PlaceLookupResult(matched=False, note="地点是空的：请先向用户问清楚。")

    if len(parts) == 1:
        only = parts[0]
        if _country_keys().get(_alias_key(only)):
            return lookup(country=only)
        return lookup(city=only)

    if len(parts) == 2:
        if _country_keys().get(_alias_key(parts[0])):
            return lookup(country=parts[0], province=parts[1])
        # "浙江省 杭州市"：没有国家，交给反推
        return lookup(province=parts[0], city=parts[1])

    return lookup(country=parts[0], province=parts[1], city=parts[2], district=parts[3] if len(parts) > 3 else None)


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
class PlaceLookupParams(BaseModel):
    country: str = Field("", description="国家/地区，如「中国」「美国」。不知道就留空。")
    province: str = Field("", description="省/州，如「浙江省」「加利福尼亚州」。")
    city: str = Field("", description="城市，如「杭州市」「旧金山」。")
    district: str = Field("", description="区/县，如「西湖区」。可不填。")
    raw: str = Field(
        "",
        description="整串地点原话，如「中国 浙江省 杭州市」。填了这个就不用填上面几项。",
    )


@skill(
    name=xjx.TOOL_PLACE_LOOKUP,
    display_name="地点核对",
    description=(
        "把用户给出的地点核成地点库里的规范写法，**在向心鉴学提交报告之前必须先调用**。"
        "输入国家/省/市/区（或一整串地点原话 raw）。"
        "命中时返回 canonical（规范写法），直接用它填 current_place / birth_place。"
        "没命中时返回分层候选 candidates（scope = same_region 同省 / adjacent 相邻省州 / "
        "country_major 该国主要城市），请从中挑地理上最近的一个再核对一次；"
        "实在核不上就问用户，**不要自己编地名**。"
    ),
    params_model=PlaceLookupParams,
    category="life",
    permission_level="safe",
    timeout=10.0,
    tags=["心鉴学", "地点"],
)
class PlaceLookupSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> Any:
        if not xjx.may_use_tools(ctx.assistant_id):
            raise SkillExecutionError(
                "地点核对只为 Soulmate（Soulmate专用）与 Love Buddy / Relation Buddy"
                "（人际关系运营）开放：当前搭子不在归属名单里，无法使用。"
            )

        raw = str(params.get("raw") or "").strip()
        country = str(params.get("country") or "").strip()
        province = str(params.get("province") or "").strip()
        city = str(params.get("city") or "").strip()
        district = str(params.get("district") or "").strip()

        if raw and not (country or province or city or district):
            result = check_place(raw)
        elif not (country or province or city or district):
            raise SkillExecutionError("请至少给出国家、省/州或城市中的一项。")
        else:
            result = lookup(country or None, province or None, city or None, district or None)

        payload = result.to_dict()
        payload["next_step"] = _next_step(result)
        ctx.logger.info(
            "地点核对：in=%s → matched=%s level=%s",
            raw or "/".join(p for p in (country, province, city) if p),
            result.matched,
            result.level,
        )
        return json.dumps(payload, ensure_ascii=False, indent=1)


def _next_step(result: PlaceLookupResult) -> str:
    if result.matched:
        return (
            f"核对通过：请用「{result.display()}」作为规范写法填写 current_place / "
            "birth_place（不要改写、不要加区号），然后调用报告工具提交。"
        )
    if result.candidates:
        return (
            "核对未通过：请从 candidates 里挑地理上最近的一个，用它的 value 作为规范写法；"
            "若都不对，请向用户确认更细的地点。"
        )
    return "核对未通过：请向用户补全或确认地点写法，不要自己编地名。"

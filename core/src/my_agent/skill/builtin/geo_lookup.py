





































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





_SUFFIXES = (
    "特别行政区", "自治区", "特别市", "地区", "新区",
    "省", "市", "区", "县", "州", "盟", "旗",
)


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




CHINA = "中国"


def _norm(text: str) -> str:

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

    key = _norm(text or "")
    for _ in range(2):  
        for suffix in _SUFFIXES:
            if key.endswith(suffix) and len(key) > len(suffix):
                key = key[: -len(suffix)]
                break
        else:
            break
    return key


def _alias_key(text: str | None) -> str:

    raw = (text or "").strip().upper()
    if raw in _US_STATE_ABBR:
        return _loose(_US_STATE_ABBR[raw])
    return _loose(text)





@lru_cache(maxsize=1)
def _regions() -> dict[str, Any]:

    return load_json("geo", "regions.json")


@lru_cache(maxsize=1)
def _country_regions() -> dict[str, dict[str, list[str]]]:

    return load_json("geo", "countries_regions.json")


@lru_cache(maxsize=1)
def _adjacency() -> dict[str, dict[str, list[str]]]:
    return load_json("geo", "adjacency.json")


@lru_cache(maxsize=1)
def _country_keys() -> dict[str, str]:

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
    if isinstance(value, list):  
        return {"": list(value)}
    return {}


@lru_cache(maxsize=1)
def _city_index() -> dict[str, list[tuple[str, str]]]:

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

    major: dict[str, list[str]] = {}
    for province, value in _regions().items():
        cities = list(value) if isinstance(value, dict) else []
        major[province] = cities[:4] or [province]
    for country, regions in _country_regions().items():
        for region, cities in regions.items():
            major[f"{country}|{region}"] = cities[:4]
    return major


def _provinces_of(country: str) -> dict[str, str]:






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

    return country == CHINA and isinstance(_regions().get(region), list)





_MAX_CANDIDATES = 60


@dataclass
class PlaceLookupResult:


    matched: bool
    level: str = "none"  
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

        parts: list[str] = []
        for item in (self.country, self.province, self.city):
            if item and item not in parts:
                parts.append(item)
        return " ".join(parts)

    def display(self) -> str:

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





def resolve_country(country: str | None, province: str | None, city: str | None) -> str | None:

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

    resolved = resolve_country(country, province, city)
    if not resolved:
        return PlaceLookupResult(
            matched=False,
            note=(
                "地点库里没有这个国家/地区。可以让用户补成「国家 + 省/州 + 城市」，"
                "也可以把原话直接提交（服务端会自己识别）；只是别自己编一个国家名。"
            ),
        )

    result = PlaceLookupResult(matched=False, country=resolved, country_known=True)
    provinces = _provinces_of(resolved)
    if not provinces:
        
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
            f"地点库里找不到城市「{city}」。available 是该国的一级行政区，可作参考；"
            "也可以把用户原话原样提交，服务端会自己识别。"
        )
        return result

    province_name = provinces.get(_alias_key(province)) or provinces.get(_loose(province))
    if not province_name:
        
        
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
        
        
        
        result.level = "province"
        result.note = (
            f"地点库里「{province_name}」下没有「{city}」（例如它可能是个县级市，挂在别的市/地区下面，"
            "库里按城市查不到）。candidates 按同省 → 相邻省/州 → 该国主要城市 分层给出（scope 标明层级），"
            "**只作参考**：可以原样提交用户写法，也可以从中挑一个最接近的并如实说明改用了哪里。"
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

    key = _loose(district)
    districts = _district_index().get((result.province, result.city))
    if districts is None:
        
        value = _regions().get(result.province)
        if isinstance(value, list):
            districts = {_loose(d): d for d in value}
    if districts and key in districts:
        result.district = districts[key]
        return True
    if strict:
        return not district
    return False





def split_place(text: str | None) -> list[str]:

    if not text:
        return []
    return [part for part in re.split(r"[\s\u3000,，、/]+", text.strip()) if part]


def check_place(text: str | None) -> PlaceLookupResult:

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
        
        return lookup(province=parts[0], city=parts[1])

    return lookup(country=parts[0], province=parts[1], city=parts[2], district=parts[3] if len(parts) > 3 else None)





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
        "把用户给出的地点核成地点库里的规范写法（**建议做，但不是提交前的关卡**）。"
        "输入国家/省/市/区（或一整串地点原话 raw）。"
        "命中时返回 canonical（规范写法），可以照抄；**没命中也不影响提交** —— "
        "用户原话原样交给报告工具即可，服务端自己会做地理识别。"
        "没命中时还会返回分层候选 candidates（scope = same_region 同省 / adjacent 相邻省州 / "
        "country_major 该国主要城市），**只作参考**：只在用户想把写法改得更规范时才挑一个最接近的，"
        "并如实说明改用了哪里；不要擅自把用户的出生地换成另一个城市，也不要自己编地名。"
    ),
    params_model=PlaceLookupParams,
    category="life",
    permission_level="safe",
    timeout=10.0,
    tags=["心鉴学", "地点"],
)
class PlaceLookupSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> Any:
        
        if not xjx.may_use_tool(ctx.assistant_id, xjx.TOOL_PLACE_LOOKUP):
            raise SkillExecutionError(
                "地点核对只为心鉴学专属技能的归属搭子开放"
                "（Soulmate专用 / 人际关系运营 / Fortune telling Buddy）："
                "当前搭子不在归属名单里，无法使用。"
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
            f"核对通过：可以用「{result.display()}」作为规范写法填写 current_place / "
            "birth_place（也可以保留用户原话，服务端会自己识别），然后提交。"
        )
    if result.candidates:
        return (
            "核对未通过（**这只是建议，不是拦截**）：可以把用户原话原样提交给报告工具，"
            "服务端会自己识别。只有当用户希望写得更规范时，才从 candidates 里挑一个最接近的，"
            "并如实说明「改用了附近的地点」。**不要**在用户没确认的情况下把他的出生地换成另一个城市。"
        )
    return (
        "核对未通过（**这只是建议，不是拦截**）：可以原样提交用户给的写法；"
        "若用户愿意补全，再问清国家 / 省州 / 城市。**不要自己编地名**。"
    )

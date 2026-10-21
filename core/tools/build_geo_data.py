



























from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SRC_DIR = Path(r"D:\win版客户端开发\心鉴学-地点库")
OUT_DIR = Path(__file__).resolve().parents[1] / "src" / "my_agent" / "resources" / "geo"











PROVINCE_ADJACENCY: dict[str, list[str]] = {
    "北京市": ["河北省", "天津市"],
    "天津市": ["北京市", "河北省"],
    "河北省": ["北京市", "天津市", "辽宁省", "内蒙古自治区", "山西省", "河南省", "山东省"],
    "山西省": ["河北省", "内蒙古自治区", "陕西省", "河南省"],
    "内蒙古自治区": [
        "黑龙江省",
        "吉林省",
        "辽宁省",
        "河北省",
        "山西省",
        "陕西省",
        "宁夏回族自治区",
        "甘肃省",
    ],
    "辽宁省": ["吉林省", "内蒙古自治区", "河北省"],
    "吉林省": ["黑龙江省", "内蒙古自治区", "辽宁省"],
    "黑龙江省": ["吉林省", "内蒙古自治区"],
    "上海市": ["江苏省", "浙江省"],
    "江苏省": ["山东省", "安徽省", "浙江省", "上海市"],
    "浙江省": ["上海市", "江苏省", "安徽省", "江西省", "福建省"],
    "安徽省": ["江苏省", "浙江省", "江西省", "湖北省", "河南省", "山东省"],
    "福建省": ["浙江省", "江西省", "广东省"],
    "江西省": ["安徽省", "浙江省", "福建省", "广东省", "湖南省", "湖北省"],
    "山东省": ["河北省", "河南省", "安徽省", "江苏省"],
    "河南省": ["河北省", "山西省", "陕西省", "湖北省", "安徽省", "山东省"],
    "湖北省": ["河南省", "安徽省", "江西省", "湖南省", "重庆市", "陕西省"],
    "湖南省": ["湖北省", "江西省", "广东省", "广西壮族自治区", "贵州省", "重庆市"],
    "广东省": ["福建省", "江西省", "湖南省", "广西壮族自治区", "香港特别行政区", "澳门特别行政区"],
    "广西壮族自治区": ["广东省", "湖南省", "贵州省", "云南省"],
    "海南省": [],
    "重庆市": ["湖北省", "湖南省", "贵州省", "四川省", "陕西省"],
    "四川省": ["重庆市", "贵州省", "云南省", "西藏自治区", "青海省", "甘肃省", "陕西省"],
    "贵州省": ["重庆市", "湖南省", "广西壮族自治区", "云南省", "四川省"],
    "云南省": ["西藏自治区", "四川省", "贵州省", "广西壮族自治区"],
    "西藏自治区": ["新疆维吾尔自治区", "青海省", "四川省", "云南省"],
    "陕西省": [
        "山西省",
        "河南省",
        "湖北省",
        "重庆市",
        "四川省",
        "甘肃省",
        "宁夏回族自治区",
        "内蒙古自治区",
    ],
    "甘肃省": ["内蒙古自治区", "宁夏回族自治区", "陕西省", "四川省", "青海省", "新疆维吾尔自治区"],
    "青海省": ["甘肃省", "四川省", "西藏自治区", "新疆维吾尔自治区"],
    "宁夏回族自治区": ["内蒙古自治区", "陕西省", "甘肃省"],
    "新疆维吾尔自治区": ["甘肃省", "青海省", "西藏自治区"],
    "台湾省": [],
    "香港特别行政区": ["广东省"],
    "澳门特别行政区": ["广东省"],
}








COUNTRY_ADJACENCY: dict[str, list[str]] = {
    "中国": [
        "韩国",
        "朝鲜",
        "蒙古",
        "俄罗斯",
        "哈萨克斯坦",
        "吉尔吉斯斯坦",
        "塔吉克斯坦",
        "阿富汗",
        "巴基斯坦",
        "印度",
        "尼泊尔",
        "不丹",
        "缅甸",
        "老挝",
        "越南",
    ],
    "美国": ["加拿大", "墨西哥"],
    "加拿大": ["美国"],
    "墨西哥": ["美国", "危地马拉", "伯利兹"],
    "英国": ["爱尔兰"],
    "爱尔兰": ["英国"],
    "法国": ["德国", "比利时", "卢森堡", "瑞士", "意大利", "西班牙", "安道尔", "摩纳哥"],
    "德国": [
        "丹麦",
        "波兰",
        "捷克",
        "奥地利",
        "瑞士",
        "法国",
        "卢森堡",
        "比利时",
        "荷兰",
    ],
    "意大利": ["法国", "瑞士", "奥地利", "斯洛文尼亚", "圣马力诺", "梵蒂冈"],
    "西班牙": ["法国", "安道尔", "葡萄牙"],
    "葡萄牙": ["西班牙"],
    "荷兰": ["德国", "比利时"],
    "比利时": ["法国", "卢森堡", "德国", "荷兰"],
    "瑞士": ["法国", "德国", "奥地利", "意大利", "列支敦士登"],
    "奥地利": ["德国", "捷克", "斯洛伐克", "匈牙利", "斯洛文尼亚", "意大利", "瑞士", "列支敦士登"],
    "日本": [],
    "韩国": ["朝鲜", "中国"],
    "朝鲜": ["韩国", "中国", "俄罗斯"],
    "俄罗斯": ["朝鲜", "中国", "蒙古", "哈萨克斯坦", "白俄罗斯", "乌克兰", "格鲁吉亚", "阿塞拜疆"],
    "澳大利亚": [],
    "新西兰": [],
    "新加坡": ["马来西亚"],
    "马来西亚": ["新加坡", "泰国", "印度尼西亚", "文莱"],
    "泰国": ["马来西亚", "缅甸", "老挝", "柬埔寨"],
    "越南": ["中国", "老挝", "柬埔寨"],
    "老挝": ["中国", "越南", "缅甸", "泰国", "柬埔寨"],
    "柬埔寨": ["越南", "老挝", "泰国"],
    "缅甸": ["中国", "老挝", "泰国", "印度", "孟加拉国"],
    "印度": ["中国", "尼泊尔", "不丹", "孟加拉国", "缅甸", "巴基斯坦"],
    "印度尼西亚": ["马来西亚", "巴布亚新几内亚", "东帝汶"],
    "菲律宾": [],
    "阿联酋": ["沙特阿拉伯", "阿曼"],
    "沙特阿拉伯": ["阿联酋", "阿曼", "也门", "约旦", "伊拉克", "科威特", "卡塔尔"],
    "以色列": ["黎巴嫩", "叙利亚", "约旦", "埃及"],
    "埃及": ["以色列", "苏丹", "利比亚"],
    "南非": ["纳米比亚", "博茨瓦纳", "津巴布韦", "莫桑比克", "斯威士兰", "莱索托"],
    "巴西": ["阿根廷", "乌拉圭", "巴拉圭", "玻利维亚", "秘鲁", "哥伦比亚", "委内瑞拉", "圭亚那", "苏里南"],
    "阿根廷": ["巴西", "乌拉圭", "巴拉圭", "玻利维亚", "智利"],
    "智利": ["阿根廷", "玻利维亚", "秘鲁"],
    "秘鲁": ["巴西", "玻利维亚", "智利", "厄瓜多尔", "哥伦比亚"],
    "墨西哥_": [],  
    "台湾": [],
    "香港": ["中国"],
    "澳门": ["中国"],
}


def strip_wrapper(text: str) -> str:






    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    start = min(
        (i for i in (text.find("{"), text.find("[")) if i >= 0),
        default=-1,
    )
    if start < 0:
        raise ValueError("找不到数据体的起始位置")

    depth = 0
    in_string = False
    escaped = False
    end = -1
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end <= start:
        raise ValueError("数据体的括号没有配对")
    body = text[start : end + 1]
    
    body = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', body)
    
    body = re.sub(r",(\s*[}\]])", r"\1", body)
    return body


def load_js(path: Path):
    return json.loads(strip_wrapper(path.read_text(encoding="utf-8")))


def close_and_verify(
    pairs: dict[str, list[str]],
    label: str,
    known: set[str],
    *,
    close: bool,
) -> dict[str, list[str]]:







    if close:
        for source, targets in list(pairs.items()):
            for target in targets:
                pairs.setdefault(target, [])
                if source not in pairs[target]:
                    pairs[target].append(source)

    problems: list[str] = []
    for source, targets in pairs.items():
        if source not in known:
            problems.append(f"{label}: 邻接表的键「{source}」不在数据里")
        for target in sorted(set(targets)):
            if target not in known:
                problems.append(f"{label}: 「{source}」的邻居「{target}」不在数据里")
                continue
            if source not in pairs.get(target, []):
                problems.append(f"{label}: 「{source}」→「{target}」不对称")
    if problems:
        for item in problems:
            print(f"  [x] {item}", file=sys.stderr)
        raise SystemExit(f"{label}邻接表校验失败（{len(problems)} 处）")

    return {key: sorted(set(value)) for key, value in sorted(pairs.items())}


def main() -> None:
    if not SRC_DIR.is_dir():
        raise SystemExit(f"找不到地点库源目录：{SRC_DIR}")

    countries = load_js(SRC_DIR / "countries-data.js")
    country_regions = load_js(SRC_DIR / "countries-regions.js")
    regions = load_js(SRC_DIR / "regions-data.js")
    cities = load_js(SRC_DIR / "全国城市表.js")

    
    known_countries = {item["zh"] for item in countries}
    unknown = sorted(set(country_regions) - known_countries)
    if unknown:
        print(f"  ! countries-regions 里有 {len(unknown)} 个国家不在国家表里：{unknown}")

    province_adj = close_and_verify(PROVINCE_ADJACENCY, "省级", set(regions), close=False)
    
    country_adj = {
        k: list(v) for k, v in COUNTRY_ADJACENCY.items() if not k.endswith("_")
    }
    country_adj = close_and_verify(country_adj, "国家级", known_countries, close=True)

    missing_adj = sorted(set(country_regions) - set(country_adj))
    if missing_adj:
        print(f"  ! 这些国家有省/市数据但没登记邻接（核到时直接落到「该国主要城市」）：{missing_adj}")

    adjacency = {"provinces": province_adj, "countries": country_adj}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = {
        "countries.json": countries,
        "countries_regions.json": country_regions,
        "regions.json": regions,
        "cities.json": cities,
        "adjacency.json": adjacency,
    }
    for name, payload in outputs.items():
        target = OUT_DIR / name
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"  [ok] {name}  {target.stat().st_size / 1024:.1f} KB")

    print(
        f"完成：{len(countries)} 个国家、{len(regions)} 个省级行政区、"
        f"{len(country_regions)} 个国家的省/市数据、"
        f"{len(country_adj)} 个国家登记了邻接"
    )


if __name__ == "__main__":
    main()

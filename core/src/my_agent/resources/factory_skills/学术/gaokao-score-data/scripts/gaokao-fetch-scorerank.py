#!/usr/bin/env python3














import argparse
import bisect
import json
import sys
import urllib.request
import urllib.parse
import urllib.error


BASE_URL = "https://gaokao.search.qq.com/skills_data"
TYPE = "score_range"
SOURCE = "open_tB0fU5wP"


def fetch_data(year: str, place: str, classify: str, read_key: str, retry_times=1) -> list:

    url_prefix = f"{BASE_URL}?type={TYPE}&from={SOURCE}&title={urllib.parse.quote('高考;一分一段表')}"

    if year != "" and year is not None:
        url_prefix += f"&year={year}"

    if place != "" and place is not None:
        url_prefix += f"&place={urllib.parse.quote(place)}"

    if classify != "" and classify is not None:
        url_prefix += f"&classify={urllib.parse.quote(classify)}"

    url = url_prefix

    print("读取数据:", url, file=sys.stderr)

    

    for _ in range(retry_times):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                result = json.loads(raw)
                if result.get("status") != 0:
                    print("接口返回异常。 MSG = {}".format(result.get("message", "")), file=sys.stderr)
                    return []
                return result.get("data", []).get("score_range_res", [])
        except urllib.error.URLError as e:
            print(json.dumps({"error": f"网络请求失败: {str(e)}"}, ensure_ascii=False), file=sys.stderr)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"JSON 解析失败: {str(e)}"}, ensure_ascii=False), file=sys.stderr)

    return []


def filter_data(records: list, unwanted_keys: list = None) -> list:
    filtered = []
    for item in records:
        if unwanted_keys and len(unwanted_keys) > 0:
            item = {k: v for k, v in item.items() if k not in unwanted_keys}
        filtered.append(item)
    return filtered


def _parse_score(score_str: str) -> int:





    if "-" in score_str:
        return int(score_str.split("-")[0])
    return int(score_str)


def _build_index(detail: list) -> tuple:









    
    valid = []
    for item in detail:
        try:
            valid.append((item, _parse_score(item["返回的查询分数"]), int(item["排名位次"])))
        except (KeyError, ValueError, TypeError):
            continue

    
    valid_rev = list(reversed(valid))
    scores     = [v[1] for v in valid_rev]
    total_nums = [v[2] for v in valid_rev]
    detail_rev = [v[0] for v in valid_rev]
    return scores, total_nums, detail_rev


def _make_result(record: dict, item: dict, user_in: int) -> dict:
    return {
        "年份"                      : record["查询分数线年份"],
        "地区"                       : record["适用地区"],
        "选科类别"                          : record["选科类别"],
        "返回的查询分数"                        : item["返回的查询分数"],
        "同分人数"                   : item["同分人数"],
        "排名位次"  : item["排名位次"],
        "用户输入分数/排名" : user_in,
    }


def query_by_score(records: list, score_list: list) -> list:









    rst = []
    for record in records:
        detail = record.get("查询数据", [])
        if not detail:
            continue

        
        scores, _, detail_rev = _build_index(detail)

        
        for score in score_list:
            
            
            idx = bisect.bisect_right(scores, score) - 1
            if idx < 0:
                idx = 0

            item = detail_rev[idx]
            item_score = _parse_score(item["返回的查询分数"])

            
            if item_score == score:
                rst.append(_make_result(record, item, score))

            
            
            elif "-" in item["返回的查询分数"]:
                rst.append(_make_result(record, item, score))

            
            elif score < item_score:
                rst.append(_make_result(record, item, score))

    return rst


def query_by_rank(records: list, rank_list: list) -> list:










    rst = []
    for record in records:
        detail = record.get("查询数据", [])
        if not detail:
            continue

        
        
        total_nums = []
        for item in detail:
            try:
                total_nums.append(int(item["排名位次"]))
            except (KeyError, ValueError, TypeError):
                total_nums.append(0)

        
        for rank in rank_list:
            
            
            idx = bisect.bisect_left(total_nums, rank)
            if idx >= len(detail):
                idx = len(detail) - 1

            rst.append(_make_result(record, detail[idx], rank))

    return rst

place_all_list = [
    "北京",
    "天津",
    "河北",
    "山西",
    "内蒙古",
    "辽宁",
    "吉林",
    "黑龙江",
    "上海",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "广西",
    "海南",
    "重庆",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "宁夏"
]


def main():
    parser = argparse.ArgumentParser(description="高考地区分数线查询")
    parser.add_argument("--place",    default=None, nargs="*", help="省份名称，如：福建、广东")
    parser.add_argument("--year",     default=None, nargs="*", help="年份列表，如：2024 2023")
    parser.add_argument("--classify", default=None, nargs="*", help="选科列表，如：历史 物理 文科 理科")
    parser.add_argument("--score",  default=None, nargs="*", help="按分数查询：返回该分数的人数和省排名")
    parser.add_argument("--rank",    default=None, nargs="*", help="按位次查询：返回该位次对应的分数区间")
    parser.add_argument("--ip",     default=None, help="按位次查询：返回该位次对应的分数区间")

    args, unknown = parser.parse_known_args()
    if unknown:
        print(f"忽略未知参数: {unknown}", file=sys.stderr)

    if args.place is None:
        if args.ip is None:
            args.place = ["北京"]
        else:
            args.place = [args.ip]

    if not isinstance(args.place, list):
        args.place = [args.place]

    if args.year is None:
        args.year = ["2026"]

    if not isinstance(args.year, list):
        args.year = [args.year]

    if not isinstance(args.classify, list):
        args.classify = [args.classify]

    print(args)

    records_list = []

    place_list = []

    args.year = list(set(args.year))

    for p in args.place:
        if p == "全省":
            place_list.extend(place_all_list)
        place_list.append(p)

    for place in place_list:
        for year in args.year:
            for classify in args.classify:
                records  = fetch_data(year, place, classify, read_key="lingxi_doc")
                records_list.extend(records)

    unwanted_keys = [
        "url", "title", "year_all", "location", "year_select", "item_key", "classify_select"
    ]

    rnt_data = filter_data(records_list, unwanted_keys)

    print("接口返回结果：")
    result = None
    if args.score is not None:
        score = args.score
        if not isinstance(args.score, list):
            score = [score]
        try:
            score = [int(s) for s in score if s]
            result = query_by_score(rnt_data, score)
        except ValueError:
            pass

    
    if args.rank is not None:
        rank = args.rank
        if not isinstance(args.rank, list):
            rank = [rank]
        try:
            rank = [int(r) for r in rank if r]
            result = query_by_rank(rnt_data, rank)
        except ValueError:
            pass

    if args.score is None and args.rank is None:
        result = query_by_score(rnt_data, [600, 500, 400, 300])
        for item in result:
            item.pop("用户输入分数/排名", None)



    if result and len(result) != 0:
        for item in result:
            item.pop("查询数据", None)
        rnt_data = result

    print(json.dumps(rnt_data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

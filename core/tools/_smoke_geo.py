"""临时冒烟：地点核对各级路径（跑完即删）。"""

import importlib
import sys

sys.path.insert(0, "src")
geo = importlib.import_module("my_agent.skill.builtin.geo_lookup")

CASES = [
    dict(country="中国", province="浙江", city="杭州市"),
    dict(country="中国", province="浙江省", city="杭州市"),
    dict(country="中国", province="浙江", city="杭洲"),
    dict(country="中国", city="杭州"),
    dict(country="中国", province="北京", city="北京", district="海淀区"),
    dict(country="美国", province="加州", city="旧金山"),
    dict(country="美国", province="加利福尼亚", city="洛杉矶"),
    dict(country="美国", province="纽约州", city="纽约"),
    dict(country="法国", province="巴黎", city="巴黎"),
    dict(country="火星", province="x", city="y"),
]
for case in CASES:
    result = geo.lookup(**case)
    print(
        f"{str(case):<58} matched={result.matched} lvl={result.level} canon={repr(result.canonical)} disp={repr(result.display())} cand={len(result.candidates)} adj={len(result.adjacent)} avail={len(result.available)} note={result.note[:44]}"
    )

print()
for raw in ["浙江省 杭州市", "杭州", "纽约", "中国 浙江省 杭州市", "美国 加利福尼亚州 洛杉矶", ""]:
    got = geo.check_place(raw)
    print(f"{repr(raw):<30} -> {got.matched} {repr(got.canonical)} {got.note[:56]}")

print()
print("same_region sample:", geo.lookup(country="中国", province="浙江", city="杭洲").candidates[:3])
print("adjacent names:", geo.lookup(country="中国", province="浙江", city="杭洲").adjacent)

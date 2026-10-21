#!/usr/bin/env python3
# -*- coding: utf-8 -*-



































import argparse, json, math, os, sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
from spots_db import CITIES
import geo, autolayout
from fetch_tiles import stitch

TARGET_W = {'overview': 1536, 'day': 1792}
ZOOM_MIN, ZOOM_MAX = 12, 16


def pick_zoom(lon0, lon1, target_w):
    span = lon1 - lon0
    z = math.log2(target_w * 360.0 / (span * 256.0))
    return int(min(ZOOM_MAX, max(ZOOM_MIN, round(z))))


def bbox_for(coords, pad=0.12, min_pad=0.002):
    lons = [c[0] for c in coords]; lats = [c[1] for c in coords]
    lon0, lon1 = min(lons), max(lons)
    lat0, lat1 = min(lats), max(lats)
    dx = max((lon1 - lon0) * pad, min_pad)
    dy = max((lat1 - lat0) * pad, min_pad * 0.8)
    return lon0 - dx, lat0 - dy, lon1 + dx, lat1 + dy


def resolve_spots(city, plan):


    db = CITIES.get(city, {})
    all_spots = []
    for d in plan['days']:
        for s in d['spots']:
            if isinstance(s, str):
                v = db.get(s)
                if not v:
                    raise SystemExit(f'[planner] 城市 {city} 无景点「{s}」，请检查 spots_db 或改用对象写法')
                all_spots.append({"name": s, "lon": v[0], "lat": v[1], "tag": v[2], "pay": v[3],
                                  "icon": v[4], "desc": v[5], "query": v[6], "custom": False})
            else:
                all_spots.append({"name": s["name"], "lon": s["lon"], "lat": s["lat"],
                                  "desc": s.get("desc", ""), "tag": s.get("tag", ""), "pay": s.get("pay", False),
                                  "icon": s.get("icon", "📍"), "query": s.get("query", ""), "custom": True})
    return all_spots


def fetch_map(bbox, zoom, out_path, meta_path, cache_dir, reuse=False):
    if reuse and os.path.exists(meta_path):
        m = json.load(open(meta_path))
        if m.get('zoom') == zoom and m.get('bbox') and \
           max(abs(a - b) for a, b in zip(m['bbox'], bbox)) < 1e-4:
            return m
    meta = stitch(bbox[0], bbox[1], bbox[2], bbox[3], zoom, out_path, cache_dir)
    meta['zoom'] = zoom
    meta['bbox'] = bbox
    json.dump(meta, open(meta_path, 'w'))
    return meta


def merge_overview_labels(spots, merge_map):

    if not merge_map:
        return spots
    out = []
    for s in spots:
        for src, merged in merge_map.items():
            if s['name'] == src:
                s['name'] = merged
        out.append(s)
    return out


def build_overview(plan, outdir, cache, reuse=False):
    city = plan['city']
    ov = plan.get('overview', {})
    exclude = set(ov.get('exclude', []))   
    spots = resolve_spots(city, plan)
    spots = [s for s in spots if s['name'] not in exclude]
    coords = [(s['lon'], s['lat']) for s in spots]
    bbox = ov.get('bbox') or bbox_for(coords)
    zoom = ov.get('zoom') or pick_zoom(bbox[0], bbox[2], TARGET_W['overview'])
    bm = os.path.join(outdir, 'basemap_overview.png')
    meta_path = os.path.join(outdir, 'origin.json')
    meta = fetch_map(bbox, zoom, bm, meta_path, cache, reuse)
    mw, mh = meta['width'], meta['height']

    
    day_of = {}
    for i, d in enumerate(plan['days'], 1):
        for s in d['spots']:
            day_of[s if isinstance(s, str) else s['name']] = i
    px = {}
    for s in spots:
        x, y = geo.to_pixels(s['lon'], s['lat'], meta)
        px[s['name']] = (x, y)

    
    zones = []
    zone_labels = []
    by_day = {}
    for s in spots:
        by_day.setdefault(day_of[s['name']], []).append(px[s['name']])
    for day in sorted(by_day):
        pts = by_day[day]
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        rx = min(max((max(xs) - min(xs)) / 2 * 1.35, 120), mw * 0.45)
        ry = min(max((max(ys) - min(ys)) / 2 * 1.35, 90), mh * 0.45)
        zones.append({"cx": round(cx), "cy": round(cy), "rx": round(rx), "ry": round(ry),
                      "day": day, "label_dx": round(cx), "label_dy": round(cy - ry - 32),
                      "label": f"Day{day}"})
        zone_labels.append([round(cx), round(cy - ry - 32), round(cx + 60), round(cy - ry - 4)])

    
    ndays = len(plan['days'])
    legend_box = [mw - 322, 22, mw - 18, 22 + 60 + 42 * ndays]
    corner = plan.get('overview', {}).get('corner')
    corner_box = [mw - 160, mh - 240, mw - 20, mh - 130] if corner else None
    occupied = [legend_box] + ([corner_box] if corner_box else []) + zone_labels
    ov_spots = []
    for s in spots:
        x, y = px[s['name']]
        ov_spots.append({"x": x, "y": y, "name": s['name'], "desc": s['desc'],
                         "tag": s['tag'], "pay": s['pay'], "cls": day_of[s['name']], "icon": s['icon']})
    ov_spots = merge_overview_labels(ov_spots, plan.get('overview', {}).get('merge'))
    placed, unresolved = autolayout.layout('map', ov_spots, mw, mh, occupied=occupied)

    
    legend = []
    for d in plan['days']:
        legend.append({"day": d['day'], "title": f"Day{d['day']}（{d['sub']}）", "desc": d.get('legend_desc', '')})

    spec = {
        "kind": "map", "title": ov.get('title', f"{city}景点分布图"),
        "subtitle": ov.get('subtitle', '按板块就近安排 · 少跑路'),
        "basemap": "basemap_overview.png", "map_w": mw, "map_h": mh,
        "zones": zones, "spots": placed, "legend": legend,
    }
    if corner:
        spec['corner'] = corner
    if ov.get('note'):
        spec['note'] = ov['note']
    json.dump(spec, open(os.path.join(outdir, 'map_spec.json'), 'w'), ensure_ascii=False, indent=1)
    print(f'[planner] overview: {bm} {mw}x{mh} zoom={zoom} unresolved={unresolved}')
    return unresolved


def build_day(plan, d, outdir, cache, reuse=False):
    city = plan['city']
    db = CITIES.get(city, {})
    spots = []
    for s in d['spots']:
        if isinstance(s, str):
            v = db[s]
            spots.append({"name": s, "lon": v[0], "lat": v[1], "desc": v[5], "tag": v[2], "icon": v[4]})
        else:
            spots.append({"name": s["name"], "lon": s["lon"], "lat": s["lat"],
                          "desc": s.get("desc", ""), "tag": s.get("tag", ""), "icon": s.get("icon", "📍")})
    coords = [(s['lon'], s['lat']) for s in spots]
    bbox = bbox_for(coords)
    zoom = pick_zoom(bbox[0], bbox[2], TARGET_W['day'])
    daydir = os.path.join(outdir, 'daymaps')
    os.makedirs(daydir, exist_ok=True)
    bm = os.path.join(daydir, f'basemap_day{d["day"]}.png')
    meta_path = os.path.join(daydir, f'origin_day{d["day"]}.json')
    meta = fetch_map(bbox, zoom, bm, meta_path, cache, reuse)
    mw, mh = meta['width'], meta['height']
    px = [(geo.to_pixels(s['lon'], s['lat'], meta)) for s in spots]

    
    tip_w = min(320, int(mw * 0.42))
    tip_h = 120 + 34 * len(d.get('tips', {}).get('lines', []))
    corners = [(8, max(40, mh - tip_h - 120)), (8, 60), (mw - tip_w - 8, 60), (mw - tip_w - 8, mh - tip_h - 120)]
    
    d_spots = [{"x": x, "y": y, "name": s['name'], "desc": s['desc']} for (x, y), s in zip(px, spots)]
    placed_s, un_s = autolayout.layout('spot', d_spots, mw, mh, occupied=[])
    spot_boxes = [autolayout.box_of('spot', s['x'], s['y'], s.get('pos', 'b'), s.get('dx', 0), s.get('dy', 0),
                                    s['name'], s.get('desc', '')) for s in placed_s]
    
    best_corner = corners[0]; best_score = None
    for (cx, cy) in corners:
        tb = (cx, cy, cx + tip_w, cy + tip_h)
        sc = sum(1 for b in spot_boxes if autolayout.overlaps(b, tb))
        if best_score is None or sc < best_score:
            best_score, best_corner = sc, (cx, cy)
    tips = None
    if d.get('tips'):
        tips = {"x": best_corner[0], "y": best_corner[1], "w": tip_w,
                "title": d['tips']['title'], "lines": d['tips']['lines']}
    tip_box = (tips['x'], tips['y'], tips['x'] + tip_w, tips['y'] + tip_h) if tips else None
    occupied = [tip_box] if tip_box else []

    
    transits = []
    for t in d.get('transits', []):
        ia = next(i for i, s in enumerate(spots) if s['name'] == t['a'])
        ib = next(i for i, s in enumerate(spots) if s['name'] == t['b'])
        x1, y1 = px[ia]; x2, y2 = px[ib]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        dx, dy = x2 - x1, y2 - y1
        ln = math.hypot(dx, dy) or 1
        off = 34
        tx, ty = mx - dy / ln * off, my + dx / ln * off
        transits.append({"x": round(tx), "y": round(ty), "name": t['text'], "text": t['text']})
    placed_t, un_t = autolayout.layout_trans(transits, mw, mh, occupied=spot_boxes + occupied)
    trans_out = [{"x": t['x'], "y": t['y'], "text": t['name']} for t in placed_t]

    
    route = [[list(p) for p in px]]
    for (ia, ib) in d.get('dash', []):
        route.append(([list(px[ia]), list(px[ib])], "14 10"))

    
    for i, s in enumerate(placed_s):
        s['num'] = i + 1

    spec = {
        "title": d.get('title', f"{city} DAY {d['day']} 路线"),
        "subtitle": d.get('sub', ''), "day": d['day'],
        "basemap": f"basemap_day{d['day']}.png", "map_w": mw, "map_h": mh,
        "route": route, "spots": placed_s, "transits": trans_out,
        "footer": d.get('footer') or ' → '.join(s['name'] for s in spots),
    }
    if tips:
        spec['tips'] = tips
    json.dump(spec, open(os.path.join(outdir, f'day{d["day"]}_spec.json'), 'w'), ensure_ascii=False, indent=1)
    print(f'[planner] day{d["day"]}: {bm} {mw}x{mh} zoom={zoom} unresolved={un_s + un_t}')
    return un_s + un_t


def build_cards(plan, outdir):
    city = plan['city']
    db = CITIES.get(city, {})
    cols = []
    for d in plan['days']:
        spots = []
        for s in d['spots']:
            if isinstance(s, str):
                v = db[s]
                spots.append({"name": s, "desc": f"{v[5]} · {v[2]}", "icon": v[4], "query": v[6]})
            else:
                spots.append({"name": s["name"], "desc": s.get("desc", ""), "icon": s.get("icon", "📍"), "query": s.get("query", "")})
        nodes = []
        via_map = {}
        for t in d.get('transits', []):
            via_map[(t['a'], t['b'])] = t['text']
        for i, s in enumerate(spots):
            via = ''
            if i > 0:
                prev = spots[i - 1]['name']
                via = via_map.get((prev, s['name']), '步行')
            nodes.append({"name": s['name'], "desc": s['desc'], "photo": s['name'], "via": via, "emoji": s['icon']})
        cols.append({"day": d['day'], "date": d.get('date', ''), "sub": d.get('sub', ''),
                     "nodes": nodes, "summary": d.get('summary', '')})
    t = plan.get('title', {})
    photos = {}
    for d in plan['days']:
        for s in d['spots']:
            if isinstance(s, str):
                photos[s] = os.path.join('photos', f"{s}.jpg")
    spec = {
        "kind": "cards",
        "title_prefix": city,
        "title_hl": t.get('hl', f"{len(plan['days'])}天{len(plan['days'])-1}晚"),
        "title_suffix": t.get('suffix', ''),
        "headline": t.get('headline', ''),
        "cols": cols,
        "photos": photos,
        "credit": "📸 图片来源：Wikimedia Commons（CC协议）｜ 底图：高德地图",
    }
    json.dump(spec, open(os.path.join(outdir, 'cards_spec.json'), 'w'), ensure_ascii=False, indent=1)

    
    queries = {}
    for d in plan['days']:
        for s in d['spots']:
            if isinstance(s, str):
                v = db[s]
                if v[6]:
                    queries[s] = v[6]
            else:
                if s.get('query'):
                    queries[s['name']] = s['query']
    json.dump(queries, open(os.path.join(outdir, 'photo_queries.json'), 'w'), ensure_ascii=False, indent=1)
    print(f'[planner] cards_spec + photo_queries ({len(queries)} queries)')


def build_docx_content(plan, outdir):
    city = plan['city']
    db = CITIES.get(city, {})
    t = plan.get('title', {})
    days = len(plan['days'])
    dates = plan.get('dates', [])
    date_range = f"{dates[0]} - {dates[-1]}" if dates else ''
    itinerary = []
    daymaps = []
    for d in plan['days']:
        lines = []
        for s in d['spots']:
            if isinstance(s, str):
                v = db[s]
                lines.append(f"{s}：{v[5]}（{v[2]}）")
            else:
                lines.append(f"{s['name']}：{s.get('desc','')}")
        itinerary.append({"h2": f"Day{d['day']} · {d.get('date','')} {d.get('sub','')}", "lines": lines})
        daymaps.append({"h2": f"Day{d['day']} · {d.get('date','')} {d.get('sub','')}",
                        "img": f"day{d['day']}.jpg"})

    
    stays = plan.get('stays') or []
    if stays:
        stay_section = {"type": "table", "title": "四、住宿推荐（具体酒店 / 民宿）",
                        "headers": ["推荐住宿", "特点 / 位置", "参考价", "预订渠道"],
                        "rows": [[s.get('name',''), s.get('desc',''), s.get('price',''),
                                  s.get('book','携程 / 美团 / 飞猪 / 去哪儿')] for s in stays],
                        "widths": [2000, 2800, 1800, 2426],
                        "note": "※ 价格为估算，端午/节假日溢价明显，以预订平台实时为准；建议全程不换店，两间双床/亲子房提前 15-30 天订。"}
    else:
        stay_section = {"type": "table", "title": "四、住宿推荐（片区对比）",
                        "headers": ["片区", "优势", "适合人群", "参考价（双床/亲子）"],
                        "rows": [["", "", "", ""], ["", "", "", ""], ["", "", "", ""]],
                        "widths": [1600, 2400, 2400, 2626], "note": ""}

    
    tr = plan.get('transport') or {}
    groups = [
        {"h2": "市内交通", "headers": ["方式", "参考价", "备注"], "rows": [["", "", ""]], "widths": [1500, 1800, 5726]},
    ]
    rail_rows = [["", "", "", "", ""]] if not (tr.get('rail')) else \
        [[x.get('no',''), f"{x.get('dep','')} - {x.get('arr','')}", x.get('dur',''),
          x.get('price',''), x.get('note','')] for x in tr['rail']]
    flight_rows = [["", "", "", "", ""]] if not (tr.get('flight')) else \
        [[x.get('no',''), f"{x.get('dep','')} - {x.get('arr','')}", x.get('dur',''),
          x.get('price',''), x.get('note','')] for x in tr['flight']]
    hdrs = ["车次 / 航班", "出发 - 到达", "历时", "参考价", "备注"]
    wdts = [1300, 2200, 1300, 1900, 2326]
    from_city = tr.get('from', '出发地')
    big_groups = []
    if tr.get('rail') or tr.get('flight'):
        big_groups = [{"h2": f"高铁 · {from_city} → {city}", "headers": hdrs, "rows": rail_rows, "widths": wdts}]
        if tr.get('flight'):
            big_groups.append({"h2": f"航班 · {from_city} → {city}", "headers": hdrs, "rows": flight_rows, "widths": wdts})
    else:
        big_groups = [{"h2": "大交通", "headers": ["方式", "到达站", "备注"], "rows": [["", "", ""]], "widths": [1100, 2900, 5026]}]
    groups = big_groups + groups

    content = {
        "out": f"{city}{len(plan['days'])}天{len(plan['days'])-1}晚攻略.docx",
        "images_dir": "jpg",
        "cover": {
            "city": city, "title": f"{days}天{days-1}晚 · {t.get('suffix','旅行攻略')}",
            "dates": date_range, "people": "", "budget": "",
            "theme": "", "stay": "",
        },
        "sections": [
            {"type": "cards", "title": "一、路线总览卡片", "img": "cards.jpg",
             "caption": "每天怎么走，一眼看懂。节点间为交通方式。"},
            {"type": "overview", "title": "二、景点分布总地图", "img": "overview_map.jpg",
             "caption": ""},
            {"type": "daymaps", "title": "三、每日路线图", "days": daymaps},
            stay_section,
            {"type": "tables", "title": "五、交通明细", "groups": groups},
            {"type": "itinerary", "title": "六、逐日详细行程", "days": itinerary},
            {"type": "table", "title": "七、预算分解", "intro": "",
             "headers": ["项目", "说明", "预估"],
             "rows": [["住宿", "", ""], ["餐饮", "", ""], ["市内交通", "", ""], ["门票", "", ""], ["合计", "", ""]],
             "widths": [1600, 4000, 3426], "note": "注：以上为估算，价格波动以实际预订为准。"},
            {"type": "checklist", "title": "八、打包清单", "items": [
                "身份证 / 证件", "防晒 / 雨具", "充电宝", "常用药（肠胃 / 感冒 / 创可贴）", "运动鞋", "少量现金"]},
            {"type": "list", "title": "九、本地文化与注意事项", "items": [
                f"{city}出行提示待补充。"]},
            {"type": "list", "title": "十、行前准备时间线", "items": [
                "提前 30 天：订往返大交通。", "提前 15 天：订酒店。",
                "提前 7 天：预约热门场馆 / 购票。", "提前 1 天：打包行李。"],
            },
        ],
        "notes": [
            "※ 本攻略中门票价格、预约政策、酒店价格为估算，节假日波动大，请在出行前 1–2 周通过官方渠道复核。",
            "底图 © 高德地图 ｜ 照片 © Wikimedia Commons（CC 协议）",
        ],
    }
    json.dump(content, open(os.path.join(outdir, 'docx_content.json'), 'w'), ensure_ascii=False, indent=1)
    print('[planner] docx_content.json 骨架已生成，AI 补文案')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('plan', help='plan.json')
    ap.add_argument('--out', default='guide_out')
    ap.add_argument('--cache', default='tiles')
    ap.add_argument('--reuse-basemaps', action='store_true', help='底图已存在则跳过拉取（迭代调布局用）')
    a = ap.parse_args()
    plan = json.load(open(a.plan))
    outdir = a.out
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(a.cache, exist_ok=True)
    reuse = a.reuse_basemaps
    un_all = build_overview(plan, outdir, a.cache, reuse)
    for d in plan['days']:
        un_all += build_day(plan, d, outdir, a.cache, reuse)
    build_cards(plan, outdir)
    build_docx_content(plan, outdir)
    if un_all:
        print(f'[planner] ⚠ 未避让成功（密集区需 AI 处理）: {un_all}')
    else:
        print('[planner] 全部标签避让成功')


if __name__ == '__main__':
    main()

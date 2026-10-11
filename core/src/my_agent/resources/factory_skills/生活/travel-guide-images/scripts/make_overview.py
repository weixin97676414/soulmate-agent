#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""总览图生成：A) 分区总地图（参考小红书"地图总览"） B) 路线卡片图（参考小红书"吃货路线"）。

用法:
  python3 make_overview.py spec.json out.html

spec JSON:
{
  "kind": "map" | "cards",

  // kind=map 时:
  "title": "重庆4天3晚·景点分布图",
  "subtitle": "按板块就近安排 · 少跑路",
  "basemap": "basemap_z13.png", "map_w": 1536, "map_h": 1280,
  "zones": [   // 分区虚线圈
    {"cx":1125,"cy":615,"rx":170,"ry":110,"day":1,"label_dx":1248,"label_dy":512,"label":"Day1"}
  ],
  "spots": [   // 图钉+标签；cls 用 day 数字（颜色）或 "hub"（枢纽绿）
    {"x":1095,"y":586,"name":"洪崖洞","desc":"绝美夜景","tag":"免费·需预约","pay":false,
     "cls":1,"pos":"t","dx":0,"dy":-6,"icon":"🍜"}
  ],
  "legend": [  // 右侧图例
    {"day":1,"title":"Day1（红圈·渝中核心）","desc":"解放碑/洪崖洞/索道——步行可达"}
  ],
  "corner": {"arrow":"↘","text":"Day3 武隆方向"},   // 图外目的地指示（可选）
  "note": "备注：……",                               // 底部注释（可选）

  // kind=cards 时:
  "title_prefix": "重庆", "title_hl": "4天3晚", "title_suffix": "保姆级路线",
  "headline": "住宿选解放碑 · 轻轨+打车组合出行 · 国庆记得提前预约！",
  "cols": [   // 每列一天
    {"day":1,"date":"10.3","sub":"解放碑 · 索道过江 · 洪崖洞夜景",
     "nodes":[{"name":"解放碑","desc":"市中心地标 · 免费","photo":"p_jiefangbei","via":"步行5分钟"}],
     "summary":"🍲 晚餐：防空洞火锅"}
  ],
  "photos": {"p_jiefangbei": "/abs/path/photo.jpg"},   // 本地照片路径（自动转 base64）
  "credit": "📸 图片来源：Wikimedia Commons（CC协议）｜ 底图：高德地图"
}
"""
import base64, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xhs_style import COMMON_CSS, LABEL_JS, DAY_COLORS, SOFT, HUB, esc


def b64img(path):
    ext = 'png' if path.lower().endswith('.png') else 'jpeg'
    return f'data:image/{ext};base64,' + base64.b64encode(open(path, 'rb').read()).decode()


def render_map(spec):
    mw, mh = spec['map_w'], spec['map_h']
    els = []
    for z in spec.get('zones', []):
        c = DAY_COLORS.get(z['day'], '#E74C3C')
        els.append(f'<div class="zone" style="left:{z["cx"]-z["rx"]}px;top:{z["cy"]-z["ry"]}px;'
                   f'width:{z["rx"]*2}px;height:{z["ry"]*2}px;border-color:{c};'
                   f'background:{c}14"></div>')
        if z.get('label'):
            els.append(f'<div class="daytag" style="left:{z["label_dx"]}px;top:{z["label_dy"]}px;'
                       f'color:{c}">{esc(z["label"])}</div>')
    for s in spec.get('spots', []):
        c = HUB if s.get('cls') == 'hub' else DAY_COLORS.get(s.get('cls', 1), '#E74C3C')
        els.append(f'<div class="pin" style="left:{s["x"]}px;top:{s["y"]}px">'
                   f'<div class="icon" style="background:{c}"><span>{s.get("icon","📍")}</span></div></div>')
        tag = ''
        if s.get('tag'):
            tag = f'<span class="tagchip{" pay" if s.get("pay") else ""}">{esc(s["tag"])}</span>'
        els.append(f'<div class="lbl" data-x="{s["x"]}" data-y="{s["y"]}" data-pos="{s.get("pos","b")}" '
                   f'data-dx="{s.get("dx",0)}" data-dy="{s.get("dy",0)}">'
                   f'{esc(s["name"])}<small>{esc(s.get("desc",""))}</small>{tag}</div>')
    legend = ''
    if spec.get('legend'):
        items = ''.join(
            f'<div class="item"><div class="dot" style="background:{DAY_COLORS.get(i["day"],"#E74C3C")}"></div>'
            f'<div><b>{esc(i["title"])}</b><small>{esc(i.get("desc",""))}</small></div></div>'
            for i in spec['legend'])
        legend = f'<div class="legend" style="right:18px;top:22px"><h3>📌 路线分区说明</h3>{items}</div>'
    corner = ''
    if spec.get('corner'):
        c = spec['corner']
        corner = (f'<div class="corner" style="right:30px;bottom:130px">'
                  f'<div class="arrow" style="color:#F39C12">{esc(c["arrow"])}</div>'
                  f'<div class="txt">{c["text"]}</div></div>')
    note = ''
    if spec.get('note'):
        note = f'<div class="note">{spec["note"]}</div>'
    bg = b64img(spec['basemap'])
    return f'''<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><style>{COMMON_CSS}</style></head><body>
<div class="page" style="width:{mw}px;height:{mh}px;background:url('{bg}') no-repeat left top">
  {''.join(els)}
</div>
<div class="maptitle">{esc(spec['title'])}</div>
<div class="mapsub">{esc(spec.get('subtitle',''))}</div>
{legend}{corner}{note}
<script>{LABEL_JS}</script>
</body></html>'''


CARDS_CSS = """
.page { width:1560px; padding:34px 30px 26px; background:#FFF6EE; }
.header { text-align:center; margin-bottom:26px; }
.header h1 { font-size:52px; font-weight:800; color:#C0392B; letter-spacing:3px; }
.header h1 em { font-style:normal; background:#FFD966; border-radius:8px; padding:0 14px; color:#7A3E00; }
.header p { font-size:21px; color:#8a6d3b; margin-top:8px; font-weight:600; }
.cols { display:flex; gap:22px; }
.col { flex:1; background:#fff; border-radius:18px; overflow:hidden; box-shadow:0 4px 16px rgba(0,0,0,.12); }
.col .day-head { padding:12px 0; text-align:center; color:#fff; }
.col .day-head .d { font-size:26px; font-weight:800; letter-spacing:1px; }
.col .day-head .s { font-size:15px; font-weight:600; opacity:.95; margin-top:2px; }
.node { display:flex; gap:10px; padding:10px 14px 4px; align-items:center; }
.node img, .node .emoji { width:66px; height:66px; border-radius:50%; object-fit:cover; flex:none;
        border:3px solid #fff; box-shadow:0 2px 6px rgba(0,0,0,.25); }
.node .emoji { display:flex; align-items:center; justify-content:center; font-size:26px; }
.node .info b { font-size:18px; color:#2C2C2C; }
.node .info small { display:block; font-size:12.5px; color:#999; margin-top:2px; }
.arrow { text-align:center; padding:3px 0; font-size:13.5px; font-weight:600; }
.col .sum { margin:10px 14px 14px; padding:8px 10px; border-radius:10px; font-size:13.5px; font-weight:600; text-align:center; }
.footer { text-align:center; margin-top:20px; font-size:15px; color:#8a6d3b; }
"""


def render_cards(spec):
    photos = {k: b64img(v) for k, v in spec.get('photos', {}).items()}
    cols = []
    for c in spec['cols']:
        day = c['day']
        color = DAY_COLORS.get(day, '#E74C3C')
        soft = SOFT.get(day, '#FDEDEC')
        h = (f'<div class="col"><div class="day-head" style="background:{color}">'
             f'<div class="d">DAY {day} · {esc(c.get("date",""))}</div>'
             f'<div class="s">{esc(c.get("sub",""))}</div></div>')
        nodes = c['nodes']
        for i, n in enumerate(nodes):
            if n.get('photo') and n['photo'] in photos:
                media = f'<img src="{photos[n["photo"]]}">'
            else:
                media = f'<div class="emoji" style="background:{soft}">{n.get("emoji","📍")}</div>'
            h += (f'<div class="node">{media}<div class="info"><b>{esc(n["name"])}</b>'
                  f'<small>{esc(n.get("desc",""))}</small></div></div>')
            if i < len(nodes) - 1:
                h += f'<div class="arrow" style="color:{color}">↓ {esc(nodes[i+1].get("via",""))}</div>'
        h += f'<div class="sum" style="background:{soft};color:{color}">{esc(c.get("summary",""))}</div></div>'
        cols.append(h)
    return f'''<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><style>{COMMON_CSS}{CARDS_CSS}</style></head><body>
<div class="page">
  <div class="header">
    <h1>{esc(spec['title_prefix'])}<em>{esc(spec['title_hl'])}</em>{esc(spec['title_suffix'])}</h1>
    <p>{esc(spec.get('headline',''))}</p>
  </div>
  <div class="cols">{''.join(cols)}</div>
  <div class="footer">{esc(spec.get('credit',''))}</div>
</div>
</body></html>'''


if __name__ == '__main__':
    spec_path = os.path.abspath(sys.argv[1])
    spec = json.load(open(spec_path))
    spec_dir = os.path.dirname(spec_path)
    # basemap / photos 若相对，则相对于 spec.json 所在目录解析
    if spec.get('basemap') and not os.path.isabs(spec['basemap']):
        spec['basemap'] = os.path.normpath(os.path.join(spec_dir, spec['basemap']))
    if spec.get('photos'):
        spec['photos'] = {
            k: (v if os.path.isabs(v) else os.path.normpath(os.path.join(spec_dir, v)))
            for k, v in spec['photos'].items()
        }
    html = render_map(spec) if spec.get('kind') == 'map' else render_cards(spec)
    open(sys.argv[2], 'w').write(html)
    if spec.get('kind') == 'map':
        print('written', sys.argv[2], 'window-size:', f"{spec['map_w']},{spec['map_h']}")
    else:
        print('written', sys.argv[2], 'window-size: 1560,~1100 (cards; 截图后裁底部空白)')

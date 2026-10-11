#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日路线图生成：读 spec JSON，输出 HTML（供 render_html.sh 截图）。

用法:
  python3 make_day_map.py spec.json out.html

spec JSON 结构:
{
  "title": "重庆 DAY 1 路线",
  "subtitle": "解放碑 · 索道过江 · 洪崖洞夜景",
  "day": 1,                      // 决定主题色（1红 2紫 3橙 4绿 5蓝）
  "basemap": "basemap_day1.png", // 与 out.html 同目录的底图
  "map_w": 768, "map_h": 1024,   // 底图原始像素尺寸
  "route": [                      // 当天游览顺序的像素坐标链（画箭头用）
    [[380,483],[505,534],[465,499],[570,768]],
    [[[566,710],[398,404]], "14 10"]   // 元组第二元素=虚线样式（可选）
  ],
  "spots": [                      // 景点标签
    {"x":380,"y":483,"name":"解放碑 → 八一路好吃街","desc":"市中心地标 · 免费",
     "pos":"l","dx":-14,"dy":-14, "num":1}
    // pos: b下 t上 l左 r右; num 给该点画编号圈（白底彩边）
  ],
  "transits": [                   // 交通标注胶囊
    {"x":418,"y":492,"text":"🚶步行8分钟"}
  ],
  "tips": {"x":8,"y":880,"w":300,"title":"💡 Tips","lines":["...","..."]},
  "footer": "解放碑 → 八一路 → 白象居 → 长江索道 → 洪崖洞夜景"
}

注意: 页面宽高已按 map_w/map_h + 96 标题栏 + 84 底栏写死，
      截图时 window-size 用 map_w,96+map_h+84。
"""
import base64, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xhs_style import COMMON_CSS, LABEL_JS, DAY_COLORS, arrows_svg, esc


def b64img(path):
    """把底图内嵌成 base64 data URI，避免截图时相对路径失效。"""
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    ext = 'png' if path.lower().endswith('.png') else 'jpeg'
    return f"data:image/{ext};base64," + base64.b64encode(open(path, 'rb').read()).decode()


def render(spec):
    color = DAY_COLORS.get(spec.get('day', 1), '#E74C3C')
    mw, mh = spec['map_w'], spec['map_h']
    spots, nums = [], []
    for s in spec.get('spots', []):
        spots.append(
            f'<div class="spot" data-x="{s["x"]}" data-y="{s["y"]}" data-pos="{s.get("pos","b")}" '
            f'data-dx="{s.get("dx",0)}" data-dy="{s.get("dy",0)}">'
            f'<b>{esc(s["name"])}</b><small>{esc(s.get("desc",""))}</small></div>')
        if s.get('num'):
            nums.append(f'<div class="num" style="left:{s["x"]}px;top:{s["y"]}px;'
                        f'border:3px solid {color};color:{color}">{s["num"]}</div>')
    trans = ''.join(
        f'<div class="trans" style="left:{t["x"]}px;top:{t["y"]}px;color:{color}">{esc(t["text"])}</div>'
        for t in spec.get('transits', []))
    tip = ''
    if spec.get('tips'):
        t = spec['tips']
        lis = ''.join(f'<p>{esc(l)}</p>' for l in t['lines'])
        tip = (f'<div class="tip" style="left:{t["x"]}px;top:{t["y"]}px;width:{t["w"]}px">'
               f'<h4>{esc(t["title"])}</h4>{lis}</div>')
    route = [tuple(x) if isinstance(x, list) and len(x) == 2 and isinstance(x[1], str) else x
             for x in spec.get('route', [])]
    svg = arrows_svg(route, color)
    bg = b64img(spec['basemap'])
    total_h = 96 + mh + 84
    return f'''<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><style>{COMMON_CSS}
  .banner {{ background:linear-gradient(135deg,{color},{color}CC); }}
  .foot {{ background:linear-gradient(135deg,{color}DD,{color}); }}
  .mapbox {{ width:{mw}px; height:{mh}px; background:url('{bg}') no-repeat left top; }}
</style></head><body>
<div class="page" style="width:{mw}px;height:{total_h}px">
  <div class="banner"><h1>{esc(spec['title'])}</h1><span class="sub">{esc(spec.get('subtitle',''))}</span></div>
  <div class="mapbox">{svg}{''.join(spots)}{''.join(nums)}{trans}{tip}</div>
  <div class="foot"><span>{esc(spec.get('footer',''))}</span></div>
</div>
<script>{LABEL_JS}</script>
</body></html>'''


if __name__ == '__main__':
    spec_path = os.path.abspath(sys.argv[1])
    spec = json.load(open(spec_path))
    spec_dir = os.path.dirname(spec_path)
    # basemap 若相对，则相对于 spec.json 所在目录解析
    bm = spec['basemap']
    if not os.path.isabs(bm):
        bm = os.path.normpath(os.path.join(spec_dir, bm))
    spec['basemap'] = bm
    open(sys.argv[2], 'w').write(render(spec))
    print('written', sys.argv[2], 'window-size:', f"{spec['map_w']},{96+spec['map_h']+84}")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

















DAY_COLORS = {
    1: '#E74C3C',   
    2: '#8E44AD',   
    3: '#E67E22',   
    4: '#27AE60',   
    5: '#2980B9',   
}
SOFT = {
    1: '#FDEDEC', 2: '#F4ECF7', 3: '#FDF2E9', 4: '#E9F7EF', 5: '#EAF2F8',
}
HUB = '#27AE60'

COMMON_CSS = """
* { margin:0; padding:0; box-sizing:border-box; font-family:"PingFang SC","Microsoft YaHei",sans-serif; }
body { background:#FFF6EE; }
/* ---- 地图页骨架 ---- */
.page { position:relative; overflow:hidden; background:#FFF6EE; }
.banner { position:absolute; top:0; left:0; right:0; height:96px; z-index:20;
          display:flex; align-items:center; justify-content:center; gap:14px; }
.banner h1 { font-size:42px; font-weight:800; color:#fff; letter-spacing:3px; }
.banner .sub { font-size:20px; color:rgba(255,255,255,.92); font-weight:600; }
.mapbox { position:absolute; top:96px; left:0; z-index:1; }
.mapbox svg.arrows { position:absolute; inset:0; z-index:2; pointer-events:none; }
.num { position:absolute; z-index:6; width:38px; height:38px; border-radius:50%;
       background:#fff; display:flex; align-items:center; justify-content:center;
       font-size:19px; font-weight:800; transform:translate(-50%,-50%);
       box-shadow:0 2px 8px rgba(0,0,0,.35); }
.spot { position:absolute; z-index:5; background:#FFFBEF; border:2.5px solid #E8912D;
        border-radius:50px; padding:4px 16px; text-align:center;
        box-shadow:0 3px 8px rgba(0,0,0,.28); white-space:nowrap; }
.spot b { font-size:19px; color:#3D2B1F; }
.spot small { display:block; font-size:12.5px; color:#8a6d3b; font-weight:500; }
.trans { position:absolute; z-index:4; font-size:16px; font-weight:700;
         padding:1px 10px; background:rgba(255,255,255,.88); border-radius:14px;
         box-shadow:0 1px 4px rgba(0,0,0,.2); }
.tip { position:absolute; z-index:10; background:#EAF4FC; border-left:6px solid #2980B9;
       border-radius:0 12px 12px 0; padding:10px 14px; box-shadow:0 3px 10px rgba(0,0,0,.2); }
.tip h4 { font-size:17px; color:#1A5276; margin-bottom:5px; }
.tip p { font-size:14px; color:#2C3E50; line-height:1.6; }
.foot { position:absolute; bottom:0; left:0; right:0; height:84px; z-index:20;
        display:flex; align-items:center; justify-content:center; }
.foot span { font-size:21px; font-weight:700; color:#fff; letter-spacing:1px; }
/* ---- 总图专属 ---- */
.zone { position:absolute; border:4.5px dashed; border-radius:50%; pointer-events:none; opacity:.9; }
.daytag { position:absolute; font-size:56px; font-weight:800; opacity:.95; z-index:3;
        text-shadow:0 2px 12px #fff, 0 0 30px #fff, 0 0 30px #fff; letter-spacing:1px; }
.pin { position:absolute; transform:translate(-50%,-100%); z-index:5; }
.pin .icon { width:36px; height:36px; border-radius:50% 50% 50% 0; transform:rotate(-45deg);
        display:flex; align-items:center; justify-content:center;
        border:2.5px solid #fff; box-shadow:0 2px 6px rgba(0,0,0,.35); }
.pin .icon span { transform:rotate(45deg); font-size:16px; }
.lbl { position:absolute; z-index:6; background:#FFFBEF; border:2px solid #F0B429; border-radius:9px;
       padding:2px 9px; font-size:17px; font-weight:700; color:#3D2B1F;
       box-shadow:0 2px 5px rgba(0,0,0,.25); white-space:nowrap; text-align:center; }
.lbl small { display:block; font-size:11.5px; font-weight:500; color:#8a6d3b; }
.tagchip { display:inline-block; font-size:12px; font-weight:700; border-radius:5px;
           padding:0 6px; margin-top:1px; color:#fff; background:#2C2C2C; }
.tagchip.pay { background:#C0392B; }
.maptitle { position:absolute; top:22px; left:50%; transform:translateX(-50%); z-index:10;
         font-size:46px; font-weight:800; color:#C0392B; letter-spacing:2px;
         text-shadow:0 2px 12px #fff, 0 0 30px #fff; }
.mapsub { position:absolute; top:86px; left:50%; transform:translateX(-50%); z-index:10;
         font-size:20px; color:#5D4037; background:rgba(255,246,238,.92);
         border-radius:20px; padding:4px 22px; border:1.5px solid #F0B429; }
.legend { position:absolute; z-index:10; width:335px;
          background:rgba(255,251,242,.95); border:2px solid #F0B429; border-radius:14px;
          padding:12px 16px; box-shadow:0 4px 14px rgba(0,0,0,.25); }
.legend h3 { font-size:19px; color:#C0392B; margin-bottom:8px; }
.legend .item { display:flex; gap:8px; margin:7px 0; font-size:14.5px; color:#3D2B1F; align-items:flex-start; }
.legend .dot { width:15px; height:15px; border-radius:50%; flex:none; margin-top:3px;
               border:2px solid #fff; box-shadow:0 1px 3px rgba(0,0,0,.3); }
.legend small { display:block; color:#8a6d3b; font-size:12px; }
.note { position:absolute; bottom:0; left:0; right:0; z-index:10;
        background:linear-gradient(transparent, rgba(255,246,238,.97) 30%);
        padding:30px 22px 12px; font-size:15.5px; color:#5D4037; line-height:1.65; }
.note b { color:#C0392B; }
.corner { position:absolute; z-index:8; text-align:center; }
.corner .arrow { font-size:40px; font-weight:800; }
.corner .txt { background:#FEF3E2; border:2px dashed #F39C12; border-radius:10px;
               padding:5px 14px; font-size:15px; font-weight:700; color:#B4690E; }
"""


LABEL_JS = """
document.querySelectorAll('.spot,.lbl').forEach(el => {
  const x = +el.dataset.x, y = +el.dataset.y, pos = el.dataset.pos || 'b',
        dx = +el.dataset.dx||0, dy = +el.dataset.dy||0;
  const w = el.offsetWidth, h = el.offsetHeight;
  let lx, ly;
  if (pos==='b') { lx=x-w/2; ly=y+26; }
  else if (pos==='t') { lx=x-w/2; ly=y-h-26; }
  else if (pos==='l') { lx=x-w-24; ly=y-h/2; }
  else { lx=x+24; ly=y-h/2; }
  el.style.left=(lx+dx)+'px'; el.style.top=(ly+dy)+'px';
});
"""


def arrow_path(x1, y1, x2, y2, bend=0.18):
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = x2 - x1, y2 - y1
    cx, cy = mx - dy * bend, my + dx * bend
    return f"M {x1} {y1} Q {cx} {cy} {x2} {y2}"


def arrows_svg(chains, color, w=5):

    paths = []
    for ch in chains:
        if isinstance(ch, tuple):
            pts, dash = ch
        else:
            pts, dash = ch, None
        for i in range(len(pts) - 1):
            d = arrow_path(*pts[i], *pts[i + 1])
            dd = f' stroke-dasharray="{dash}"' if dash else ''
            paths.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}"'
                         f' stroke-linecap="round" marker-end="url(#arr)"{dd}/>')
    return (f'<svg class="arrows" width="100%" height="100%"><defs><marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{color}"/></marker></defs>' + ''.join(paths) + '</svg>')


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

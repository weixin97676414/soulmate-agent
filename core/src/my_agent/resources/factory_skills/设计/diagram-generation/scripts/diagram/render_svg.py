# -*- coding: utf-8 -*-
"""graph.json -> SVG（自研布局 + 自渲染，零第三方依赖）。

用于 PPT / 邮件 / 文档等只读展示场景。需要可编辑请用 gen_drawio.py。
用法: python render_svg.py graph.json -o out.svg
"""
import argparse
import os
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_graph import load, layout, style_of, FONT, TEXT_COLOR  # noqa: E402

LINE = "#4C4C4C"


def esc_xml(t):
    return escape(str(t or ""))


def render(g):
    lay = layout(g)
    nodes, groups, edges = lay["nodes"], lay["groups"], lay["edges"]
    meta = g.get("meta") or {}
    nm = {n["id"]: n for n in g["nodes"]}
    title_h = 34
    W = lay["width"]
    H = lay["height"] + title_h

    o = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
         'viewBox="0 0 %d %d" font-family="%s, sans-serif">'
         % (W, H, W, H, FONT)]
    o.append('  <defs>')
    for mid, color in (("arrow", LINE), ("arrowG", "#82B366")):
        o.append('    <marker id="%s" markerWidth="10" markerHeight="8" '
                 'refX="9" refY="4" orient="auto" markerUnits="userSpaceOnUse">'
                 % mid)
        o.append('      <path d="M0,0 L10,4 L0,8 z" fill="%s" />' % color)
        o.append('    </marker>')
    o.append('  </defs>')
    o.append('  <rect width="%d" height="%d" fill="#FFFFFF" />' % (W, H))
    if meta.get("title"):
        o.append('  <text x="%d" y="26" font-size="16" font-weight="bold" '
                 'fill="%s">%s</text>'
                 % (24, TEXT_COLOR, esc_xml(meta["title"])))
    o.append('  <g transform="translate(0,%d)">' % title_h)

    # 分组
    for gid, box in groups.items():
        o.append('  <rect x="%d" y="%d" width="%d" height="%d" rx="8" '
                 'fill="#FFFFFF" stroke="#999999" stroke-width="1" '
                 'stroke-dasharray="8 4" />'
                 % (box["x"], box["y"], box["w"], box["h"]))
        o.append('  <text x="%d" y="%d" font-size="12" font-weight="bold" '
                 'fill="#666666">%s</text>'
                 % (box["x"] + 12, box["y"] + 18, esc_xml(box["label"])))

    # 边
    for e in edges:
        pts = " ".join("%.1f,%.1f" % p for p in e["points"])
        dash = ' stroke-dasharray="8 4"' if e["dashed"] else ""
        mk = ' marker-end="url(#%s)"' % ("arrowG" if e["width"] > 1.5 else "arrow") \
            if e["arrow"] else ""
        o.append('  <polyline points="%s" fill="none" stroke="%s" '
                 'stroke-width="%s"%s%s />'
                 % (pts, "#82B366" if e["width"] > 1.5 else LINE,
                    e["width"], dash, mk))
        if e["label"]:
            tw = len(e["label"]) * 7 + 10
            o.append('  <rect x="%.1f" y="%.1f" width="%d" height="16" '
                     'fill="#FFFFFF" />'
                     % (e["lx"] - tw / 2, e["ly"] - 8, tw))
            o.append('  <text x="%.1f" y="%.1f" font-size="10" fill="%s" '
                     'text-anchor="middle">%s</text>'
                     % (e["lx"], e["ly"] + 4, TEXT_COLOR, esc_xml(e["label"])))

    # 节点
    for nid, d in nodes.items():
        src = nm.get(nid) or {}
        shape, fill, stroke, _, _, radius = d.get("shape"), d["fill"], d["stroke"], \
            None, None, d.get("radius", 0)
        shape = style_of(src)[0]
        x, y, w, h = d["x"], d["y"], d["w"], d["h"]
        dash = ' stroke-dasharray="8 4"' if src.get("type") == "external" else ""
        common = 'fill="%s" stroke="%s" stroke-width="1.5"%s' % (fill, stroke, dash)
        cx, cy = x + w / 2, y + h / 2
        if shape == "ellipse":
            o.append('  <ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" %s />'
                     % (cx, cy, w / 2, h / 2, common))
        elif shape == "diamond":
            o.append('  <polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f" %s />'
                     % (cx, y, x + w, cy, cx, y + h, x, cy, common))
        elif shape == "cylinder":
            r = min(12, h / 5)
            o.append('  <path d="M %.1f,%.1f L %.1f,%.1f A %.1f,%.1f 0 0 0 '
                     '%.1f,%.1f L %.1f,%.1f" %s />'
                     % (x, y + r, x, y + h - r, w / 2, r, x + w, y + h - r,
                        x + w, y + r, common))
            o.append('  <ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" %s />'
                     % (cx, y + r, w / 2, r, common))
        else:
            o.append('  <rect x="%d" y="%d" width="%d" height="%d" rx="%d" %s />'
                     % (x, y, w, h, radius, common))

        lines = d.get("lines") or []
        lh = 16
        ty = cy - (len(lines) - 1) * lh / 2 + 5
        for i, ln in enumerate(lines):
            o.append('  <text x="%.1f" y="%.1f" font-size="12" fill="%s" '
                     'text-anchor="middle">%s</text>'
                     % (cx, ty + i * lh, TEXT_COLOR, esc_xml(ln)))

    o.append('  </g>')
    o.append('</svg>')
    return "\n".join(o) + "\n", W, H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("graph")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    g = load(a.graph)
    svg, W, H = render(g)
    d = os.path.dirname(os.path.abspath(a.out))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(svg)
    print("SVG 已生成：%s（%dx%d，%.1f KB）"
          % (a.out, W, H, len(svg.encode("utf-8")) / 1024))
    print("  转 PNG：drawio 桌面版导出，或 npx @mermaid-js/mermaid-cli（见 export-guide.md）")


if __name__ == "__main__":
    main()

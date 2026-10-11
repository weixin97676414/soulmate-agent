# -*- coding: utf-8 -*-
"""graph.json -> .drawio（mxGraph XML）。

生成的图元带完整样式，在 drawio / diagrams.net / VS Code Draw.io 插件中打开后
可直接拖拽节点、改连线、改配色。分组用 swimlane 表达系统边界。

用法: python gen_drawio.py graph.json -o out.drawio
"""
import argparse
import hashlib
import os
import sys
from xml.sax.saxutils import escape, quoteattr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_graph import load, layout, style_of, edge_style, FONT  # noqa: E402

SHAPE_STYLE = {
    # drawio arcSize 是圆角占短边的百分比：默认圆角矩形约 10，胶囊为 50
    "rect":     lambda r: ("rounded=1;arcSize=%d;" % (50 if r >= 16 else int(r * 1.5))
                           if r else "rounded=0;"),
    "ellipse":  lambda r: "ellipse;",
    "diamond":  lambda r: "rhombus;",
    "cylinder": lambda r: ("shape=cylinder3;boundedLbl=1;backgroundOutline=1;"
                           "size=14;"),
    "note":     lambda r: ("shape=note;backgroundOutline=1;darkOpacity=0.05;"
                           "align=left;verticalAlign=top;spacingLeft=6;"),
}


def node_style(node):
    shape, fill, stroke, _, _, radius = style_of(node)
    base = SHAPE_STYLE.get(shape, SHAPE_STYLE["rect"])(radius)
    s = base + "whiteSpace=wrap;html=1;"
    s += "fillColor=%s;strokeColor=%s;" % (fill, stroke)
    s += "fontFamily=%s;fontSize=12;fontColor=#1F2933;" % FONT
    if shape not in ("note",):
        s += "align=center;verticalAlign=middle;"
    if node.get("type") == "external":
        s += "dashed=1;dashPattern=8 4;"
    return s


def _port(pts, kind):
    """按首尾线段的实际走向推断出/入端口，避免横向连线的端口被写死成上下。"""
    if len(pts) < 2:
        return ""
    if kind == "exit":
        a, b = pts[0], pts[1]
    else:
        a, b = pts[-2], pts[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) >= abs(dy):
        return ("exitX=%d;exitY=0.5;exitDx=0;exitDy=0;" % (1 if dx > 0 else 0)
                if kind == "exit" else
                "entryX=%d;entryY=0.5;entryDx=0;entryDy=0;" % (0 if dx > 0 else 1))
    return ("exitX=0.5;exitY=%d;exitDx=0;exitDy=0;" % (1 if dy > 0 else 0)
            if kind == "exit" else
            "entryX=0.5;entryY=%d;entryDx=0;entryDy=0;" % (0 if dy > 0 else 1))


def edge_style_str(edge, direction):
    dashed, arrow, width = edge_style(edge)
    s = "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;jumpStyle=arc;"
    s += "endArrow=%s;endFill=%d;" % ("blockThin" if arrow else "none",
                                      1 if arrow else 0)
    if dashed:
        s += "dashed=1;dashPattern=8 4;"
    s += "strokeWidth=%s;" % width
    s += "fontFamily=%s;fontSize=10;fontColor=#1F2933;" % FONT
    if edge.get("type") == "data":
        s += "strokeColor=#82B366;"
    elif edge.get("type") == "inherit":
        s += "endArrow=block;endFill=0;"
    return s


def build(g):
    lay = layout(g)
    nodes, groups, edges = lay["nodes"], lay["groups"], lay["edges"]
    meta = g.get("meta") or {}
    direction = lay["direction"]

    nm = {n["id"]: n for n in g["nodes"]}
    em = {e["id"]: e for e in g["edges"]}
    gm = {x["id"]: x for x in g["groups"]}

    # 节点 -> 所属分组（取最内层）
    parent_of = {}
    for n in g["nodes"]:
        parent_of[n["id"]] = n.get("group") or "1"

    out = ['<mxfile host="app.diagrams.net" type="device" version="24.0.0">']
    # 用确定性摘要而非内置 hash()——后者带随机种子，会导致同一模型每次生成的
    # diagram id 都不同，产物无法 diff、不可复现
    did = "vg-" + hashlib.md5(
        (meta.get("title") or "diagram").encode("utf-8")).hexdigest()[:8]
    out.append('  <diagram id="%s" name=%s>'
               % (did, quoteattr(meta.get("title") or "Diagram")))
    out.append('    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" '
               'guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
               'page="1" pageScale="1" pageWidth="%d" pageHeight="%d" '
               'math="0" shadow="0">'
               % (max(850, lay["width"]), max(1100, lay["height"])))
    out.append('      <root>')
    out.append('        <mxCell id="0" />')
    out.append('        <mxCell id="1" parent="0" />')

    # 分组（swimlane）
    for gid, box in groups.items():
        src = gm.get(gid) or {}
        st = ("swimlane;whiteSpace=wrap;html=1;startSize=%d;horizontal=1;"
              "fillColor=#FFFFFF;strokeColor=#999999;dashed=1;dashPattern=8 4;"
              "swimlaneFillColor=#FFFFFF;fontFamily=%s;fontSize=12;"
              "fontStyle=1;fontColor=#1F2933;align=center;verticalAlign=middle;"
              % (26, FONT))
        out.append('        <mxCell id=%s value=%s style=%s vertex="1" parent="%s">'
                   % (quoteattr(gid), quoteattr(box["label"]), quoteattr(st), "1"))
        out.append('          <mxGeometry x="%d" y="%d" width="%d" height="%d" '
                   'as="geometry" />' % (box["x"], box["y"], box["w"], box["h"]))
        out.append('        </mxCell>')

    # 节点（坐标转为相对父容器）
    for nid, d in nodes.items():
        src = nm.get(nid) or {}
        pid = parent_of.get(nid, "1")
        ox, oy = 0, 0
        if pid in groups:
            ox, oy = groups[pid]["x"], groups[pid]["y"]
        label = "&#10;".join(escape(x) for x in (d.get("lines") or [src.get("label") or ""]))
        out.append('        <mxCell id=%s value=%s style=%s vertex="1" parent=%s>'
                   % (quoteattr(nid), quoteattr(label),
                      quoteattr(node_style(src)), quoteattr(pid)))
        out.append('          <mxGeometry x="%d" y="%d" width="%d" height="%d" '
                   'as="geometry" />' % (d["x"] - ox, d["y"] - oy, d["w"], d["h"]))
        out.append('        </mxCell>')

    # 边
    for e in edges:
        src = em.get(e["id"]) or {}
        ex = _port(e["points"], "exit")
        en = _port(e["points"], "entry")
        out.append('        <mxCell id=%s value=%s style=%s edge="1" parent="1" '
                   'source=%s target=%s>'
                   % (quoteattr(e["id"]), quoteattr(escape(e["label"])),
                      quoteattr(edge_style_str(src, direction) + ex + en),
                      quoteattr(src.get("source") or ""),
                      quoteattr(src.get("target") or "")))
        out.append('          <mxGeometry relative="1" as="geometry" />')
        out.append('        </mxCell>')

    out.append('      </root>')
    out.append('    </mxGraphModel>')
    out.append('  </diagram>')
    out.append('</mxfile>')
    return "\n".join(out) + "\n", lay


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("graph")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    g = load(a.graph)
    xml, lay = build(g)
    d = os.path.dirname(os.path.abspath(a.out))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(xml)
    print("drawio 已生成：%s" % a.out)
    print("  节点 %d / 连线 %d / 分组 %d | 画布 %dx%d"
          % (len(lay["nodes"]), len(lay["edges"]), len(lay["groups"]),
             lay["width"], lay["height"]))
    print("  打开方式：draw.io 网页版 / 桌面版 / VS Code Draw.io 插件")


if __name__ == "__main__":
    main()

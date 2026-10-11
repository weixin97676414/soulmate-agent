# -*- coding: utf-8 -*-
"""graph.json -> .excalidraw（Excalidraw 原生 JSON）。

关键点：文字以独立 text 元素绑定到容器的 containerId / boundElements，
否则打开后只看到空框没有字。手绘风（roughness=1），适合方案评审。

用法: python gen_excalidraw.py graph.json -o out.excalidraw
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_graph import load, layout, style_of, edge_style, text_width  # noqa: E402


def seed_of(key):
    return int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16) % (2 ** 31)


def base(el_id, etype, x, y, w, h, stroke, bg, extra=None):
    d = {
        "id": el_id, "type": etype, "x": round(x, 1), "y": round(y, 1),
        "width": round(w, 1), "height": round(h, 1), "angle": 0,
        "strokeColor": stroke, "backgroundColor": bg, "fillStyle": "solid",
        "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1,
        "opacity": 100, "groupIds": [], "frameId": None, "roundness": None,
        "seed": seed_of(el_id), "version": 1, "versionNonce": seed_of(el_id + "v"),
        "isDeleted": False, "boundElements": [], "updated": 1, "link": None,
        "locked": False,
    }
    if extra:
        d.update(extra)
    return d


def build(g):
    lay = layout(g)
    nodes, groups, edges = lay["nodes"], lay["groups"], lay["edges"]
    nm = {n["id"]: n for n in g["nodes"]}
    em = {e["id"]: e for e in g["edges"]}
    elements = []

    # 分组：虚线矩形 + 标题文本
    for gid, box in groups.items():
        tid = gid + "_t"
        elements.append(base(gid, "rectangle", box["x"], box["y"],
                             box["w"], box["h"], "#999999", "transparent",
                             {"strokeStyle": "dashed", "strokeWidth": 1,
                              "roundness": {"type": 3},
                              "boundElements": [{"id": tid, "type": "text"}]}))
        # 标题绑定到框体（verticalAlign=top 贴顶），拖动分组时标题跟随
        elements.append(base(tid, "text",
                             box["x"] + 10, box["y"] + 6,
                             text_width(box["label"], 12) + 8, 20,
                             "#666666", "transparent",
                             {"text": box["label"], "originalText": box["label"],
                              "fontSize": 12, "fontFamily": 2,
                              "textAlign": "left", "verticalAlign": "top",
                              "containerId": gid, "lineHeight": 1.25}))

    # 节点
    for nid, d in nodes.items():
        src = nm.get(nid) or {}
        shape, fill, stroke, _, _, radius = style_of(src)
        etype = {"ellipse": "ellipse", "diamond": "diamond",
                 "cylinder": "rectangle"}.get(shape, "rectangle")
        extra = {"roundness": {"type": 3} if (shape == "rect" and radius) else None}
        if src.get("type") == "external":
            extra["strokeStyle"] = "dashed"
        el = base(nid, etype, d["x"], d["y"], d["w"], d["h"], stroke, fill, extra)
        tid = nid + "_t"
        el["boundElements"].append({"id": tid, "type": "text"})
        elements.append(el)

        lines = d.get("lines") or [src.get("label") or ""]
        text = "\n".join(lines)
        lh = 18
        elements.append(base(tid, "text",
                             d["x"] + 8, d["y"] + d["h"] / 2 - len(lines) * lh / 2,
                             d["w"] - 16, len(lines) * lh,
                             "#1F2933", "transparent",
                             {"text": text, "originalText": text,
                              "fontSize": 16, "fontFamily": 2,
                              "textAlign": "center", "verticalAlign": "middle",
                              "containerId": nid, "lineHeight": 1.25}))

    # 连线
    for e in edges:
        src = em.get(e["id"]) or {}
        dashed, arrow, width = edge_style(e)
        pts = e["points"]
        x0, y0 = pts[0]
        rel = [[round(p[0] - x0, 1), round(p[1] - y0, 1)] for p in pts]
        w = max(p[0] for p in rel) - min(p[0] for p in rel)
        h = max(p[1] for p in rel) - min(p[1] for p in rel)
        extra = {
            "points": rel,
            "startBinding": ({"elementId": src.get("source"), "focus": 0, "gap": 4}
                             if src.get("source") else None),
            "endBinding": ({"elementId": src.get("target"), "focus": 0, "gap": 4}
                           if src.get("target") else None),
            "startArrowhead": None,
            "endArrowhead": "arrow" if arrow else None,
            "strokeWidth": 1 if width <= 1.5 else 2,
        }
        if dashed:
            extra["strokeStyle"] = "dashed"
        elements.append(base(e["id"], "arrow", x0, y0, w, h,
                             "#4C4C4C", "transparent", extra))
        if e["label"]:
            lw = text_width(e["label"], 11) + 10
            elements.append(base(e["id"] + "_t", "text",
                                 e["lx"] - lw / 2, e["ly"] - 9, lw, 16,
                                 "#1F2933", "#FFFFFF",
                                 {"text": e["label"], "originalText": e["label"],
                                  "fontSize": 11, "fontFamily": 2,
                                  "textAlign": "center", "verticalAlign": "middle",
                                  "containerId": None, "lineHeight": 1.25}))

    doc = {
        "type": "excalidraw", "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {"gridSize": None, "viewBackgroundColor": "#FFFFFF"},
        "files": {},
    }
    return doc, lay


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("graph")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    g = load(a.graph)
    doc, lay = build(g)
    d = os.path.dirname(os.path.abspath(a.out))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print("Excalidraw 已生成：%s" % a.out)
    print("  图元 %d 个（节点 %d / 连线 %d / 文本 %d） | 画布 %dx%d"
          % (len(doc["elements"]), len(lay["nodes"]), len(lay["edges"]),
             len(doc["elements"]) - len(lay["nodes"]) - len(lay["edges"])
             - len(lay["groups"]), lay["width"], lay["height"]))
    print("  打开方式：excalidraw.com → Open → 选择本文件")


if __name__ == "__main__":
    main()

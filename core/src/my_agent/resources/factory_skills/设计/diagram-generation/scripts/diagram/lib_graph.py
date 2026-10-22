# -*- coding: utf-8 -*-









import json
import os
import re



TEXT_COLOR = "#1F2933"
GROUP_STROKE = "#999999"
CANVAS_BG = "#FFFFFF"
FONT = "Microsoft YaHei"



STYLE = {
    "actor":     ("ellipse",  "#F5F5F5", "#666666", 120, 60, 0),
    "gateway":   ("rect",     "#DCE9F7", "#3F6FA8", 160, 60, 12),
    "service":   ("rect",     "#DAE8FC", "#6C8EBF", 160, 60, 8),
    "component": ("rect",     "#DCE9F7", "#3F6FA8", 160, 60, 2),
    "container": ("rect",     "#DAE8FC", "#6C8EBF", 160, 60, 8),
    "db":        ("cylinder", "#D5E8D4", "#82B366", 140, 70, 0),
    "cache":     ("cylinder", "#FFE6CC", "#D79B00", 140, 70, 0),
    "queue":     ("rect",     "#E1D5E7", "#9673A6", 160, 44, 4),
    "external":  ("rect",     "#F5F5F5", "#666666", 160, 60, 4),
    "process":   ("rect",     "#DAE8FC", "#6C8EBF", 160, 60, 6),
    "decision":  ("diamond",  "#FFF2CC", "#D6B656", 150, 70, 0),
    "start":     ("rect",     "#E8E8E8", "#666666", 100, 40, 20),
    "end":       ("rect",     "#E8E8E8", "#666666", 100, 40, 20),
    "entity":    ("rect",     "#DAE8FC", "#6C8EBF", 170, 60, 2),
    "attribute": ("ellipse",  "#FAFAFA", "#999999", 110, 44, 0),
    "state":     ("rect",     "#DAE8FC", "#6C8EBF", 150, 56, 14),
    "note":      ("note",     "#FFF2CC", "#D6B656", 160, 60, 0),
}

DEFAULT_STYLE = STYLE["component"]
VALID_TYPES = set(STYLE)
GRAPH_TYPES = {"architecture", "flowchart", "er", "sequence", "state", "c4"}


EDGE_STYLE = {
    "sync":    (False, True,  1.5),
    "async":   (True,  True,  1.5),
    "data":    (False, True,  2.0),
    "return":  (True,  False, 1.2),
    "assoc":   (False, True,  1.5),
    "inherit": (False, True,  1.5),
    "flow":    (False, True,  1.5),
}
DEFAULT_EDGE = EDGE_STYLE["sync"]

PAD_X, PAD_Y = 60, 84          
GROUP_PAD = 26                 
GROUP_HEAD = 26                
MARGIN = 44                    
MAX_LABEL = 12                 


def style_of(node):
    return STYLE.get(node.get("type") or "", DEFAULT_STYLE)


def edge_style(edge):
    return EDGE_STYLE.get(edge.get("type") or "", DEFAULT_EDGE)


def text_width(text, size):

    w = 0.0
    for ch in text:
        w += size if ord(ch) > 0x2E80 else size * 0.55
    return w


def wrap_text(text, size, max_px):

    if text_width(text, size) <= max_px:
        return [text]
    lines, cur = [], ""
    for ch in text:
        if text_width(cur + ch, size) > max_px and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines[:3]


def node_size(node):

    _, _, _, w, h, _ = style_of(node)
    label = (node.get("label") or "").strip()
    need = text_width(label, 12) + 28
    if need > w:
        w = int(need) + 8
    return w, h




def load(path):
    with open(path, "r", encoding="utf-8") as f:
        g = json.load(f)
    g.setdefault("meta", {})
    g.setdefault("groups", [])
    g.setdefault("nodes", [])
    g.setdefault("edges", [])
    return g


def index_of(g):
    return ({n["id"]: n for n in g["nodes"]},
            {e["id"]: e for e in g["edges"]},
            {x["id"]: x for x in g["groups"]})




def assign_layers(g):

    nodes, edges, _ = g["nodes"], g["edges"], g["groups"]
    ids = [n["id"] for n in nodes]
    given = {n["id"]: n.get("layer") for n in nodes if isinstance(n.get("layer"), int)}
    if len(given) == len(ids):
        return given

    succ = {i: [] for i in ids}
    pred = {i: [] for i in ids}
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in succ and t in pred and s != t:
            succ[s].append(t)
            pred[t].append(s)

    layer = {}
    indeg = {i: len(pred[i]) for i in ids}
    queue = [i for i in ids if indeg[i] == 0] or list(ids)
    for i in queue:
        layer[i] = given.get(i, 0)
    done = 0
    while queue and done < len(ids) * 4:
        cur = queue.pop(0)
        done += 1
        for t in succ[cur]:
            layer[t] = max(layer.get(t, given.get(t, 0)),
                           layer.get(cur, 0) + 1)
            indeg[t] -= 1
            if indeg[t] == 0:
                queue.append(t)
    for i in ids:                                   
        layer.setdefault(i, given.get(i, 0))
    return layer


def barycenter_pass(order, layer, edges, reverse=False):

    keys = sorted(order)
    seq = keys[1:] if not reverse else list(reversed(keys))[:-1]
    pos = {}
    for k in keys:
        pos.update({nid: i for i, nid in enumerate(order[k])})
    for _ in range(2):
        for k in seq:
            prev = order[k - 1] if not reverse else order[k + 1]
            ppos = {nid: i for i, nid in enumerate(prev)}
            scored = []
            for nid in order[k]:
                neigh = [e["source"] if not reverse else e["target"]
                         for e in edges
                         if (e.get("target") == nid if not reverse
                             else e.get("source") == nid)]
                vals = [ppos[x] for x in neigh if x in ppos]
                scored.append((sum(vals) / len(vals) if vals else pos[nid], nid))
            scored.sort()
            order[k] = [n for _, n in scored]
            pos.update({n: i for i, n in enumerate(order[k])})
    return order




def layout(g):







    nodes, edges, groups = g["nodes"], g["edges"], g["groups"]
    gtype = (g.get("meta") or {}).get("graph_type")
    direction = (g.get("meta") or {}).get("direction") or "TB"
    if gtype == "sequence":
        return _layout_sequence(g)
    if gtype == "er":
        return _layout_er(g)

    layer = assign_layers(g)
    order = {}
    for i, n in enumerate(nodes):
        order.setdefault(layer.get(n["id"], 0), []).append((i, n["id"]))
    order = {k: [n for _, n in sorted(v)] for k, v in order.items()}
    order = barycenter_pass(order, layer, edges)

    sizes = {n["id"]: node_size(n) for n in nodes}
    out_nodes = {}
    if direction == "LR":
        xs, cursor = {}, MARGIN
        for k in sorted(order):
            xs[k] = cursor
            cursor += max(sizes[n][0] for n in order[k]) + PAD_X
        total_h = max(sum(sizes[n][1] for n in order[k]) +
                      PAD_Y * (len(order[k]) - 1) for k in order)
        for k, ids in order.items():
            h = sum(sizes[n][1] for n in ids) + PAD_Y * (len(ids) - 1)
            y = MARGIN + (total_h - h) / 2
            for nid in ids:
                w, hh = sizes[nid]
                out_nodes[nid] = {"x": xs[k], "y": y, "w": w, "h": hh}
                y += hh + PAD_Y
    else:
        ys, cursor = {}, MARGIN
        for k in sorted(order):
            ys[k] = cursor
            cursor += max(sizes[n][1] for n in order[k]) + PAD_Y
        total_w = max(sum(sizes[n][0] for n in order[k]) +
                      PAD_X * (len(order[k]) - 1) for k in order)
        for k, ids in order.items():
            w = sum(sizes[n][0] for n in ids) + PAD_X * (len(ids) - 1)
            x = MARGIN + (total_w - w) / 2
            for nid in ids:
                nw, nh = sizes[nid]
                out_nodes[nid] = {"x": x, "y": ys[k], "w": nw, "h": nh}
                x += nw + PAD_X

    for n in nodes:
        d = out_nodes.get(n["id"])
        if not d:
            continue
        shape, fill, stroke, _, _, radius = style_of(n)
        d.update(shape=shape, fill=fill, stroke=stroke, radius=radius,
                 lines=wrap_text((n.get("label") or ""), 12, max(40, d["w"] - 20)))

    out_groups = _group_boxes(g, out_nodes, sizes, direction)
    out_edges = _route_edges(g, out_nodes, direction)
    w, h = _canvas(out_nodes, out_groups)
    return {"nodes": out_nodes, "groups": out_groups, "edges": out_edges,
            "width": w, "height": h, "direction": direction}


def _group_boxes(g, out_nodes, sizes, direction):

    res = {}
    gmap = {x["id"]: x for x in g["groups"]}
    members = {}
    for n in g["nodes"]:
        gid = n.get("group")
        if gid:
            members.setdefault(gid, []).append(n["id"])
    for gid, ids in members.items():
        boxes = [out_nodes[i] for i in ids if i in out_nodes]
        if not boxes:
            continue
        x0 = min(b["x"] for b in boxes)
        y0 = min(b["y"] for b in boxes)
        x1 = max(b["x"] + b["w"] for b in boxes)
        y1 = max(b["y"] + b["h"] for b in boxes)
        res[gid] = {"x": x0 - GROUP_PAD, "y": y0 - GROUP_PAD - GROUP_HEAD,
                    "w": x1 - x0 + GROUP_PAD * 2,
                    "h": y1 - y0 + GROUP_PAD * 2 + GROUP_HEAD,
                    "label": (gmap.get(gid) or {}).get("label") or gid}
    return res


def _route_edges(g, out_nodes, direction):

    res = []
    for e in g["edges"]:
        s, t = out_nodes.get(e.get("source")), out_nodes.get(e.get("target"))
        if not s or not t:
            continue
        dashed, arrow, width = edge_style(e)
        if direction == "LR":
            p1 = (s["x"] + s["w"], s["y"] + s["h"] / 2)
            p2 = (t["x"], t["y"] + t["h"] / 2)
            if abs(p1[1] - p2[1]) < 1:
                pts = [p1, p2]
            else:
                mx = (p1[0] + p2[0]) / 2
                pts = [p1, (mx, p1[1]), (mx, p2[1]), p2]
        else:
            p1 = (s["x"] + s["w"] / 2, s["y"] + s["h"])
            p2 = (t["x"] + t["w"] / 2, t["y"])
            if abs(p1[0] - p2[0]) < 1:
                pts = [p1, p2]
            else:
                my = (p1[1] + p2[1]) / 2
                pts = [p1, (p1[0], my), (p2[0], my), p2]
        lx = sum(p[0] for p in pts) / len(pts)
        ly = sum(p[1] for p in pts) / len(pts) - 6
        res.append({"id": e.get("id"), "points": pts,
                    "label": e.get("label") or "", "dashed": dashed,
                    "arrow": arrow, "width": width, "lx": lx, "ly": ly})
    return res


def _layout_sequence(g):

    actors = [n for n in g["nodes"]]
    msgs = sorted([e for e in g["edges"]], key=lambda e: e.get("seq", 999))
    out_nodes, x = {}, MARGIN
    TOP, GAP = 150, 240
    for n in actors:
        w, h = node_size(n)
        out_nodes[n["id"]] = {"x": x, "y": MARGIN, "w": w, "h": h}
        x += w + GAP
    actor_x = {nid: d["x"] + d["w"] / 2 for nid, d in out_nodes.items()}
    for n in actors:
        d = out_nodes[n["id"]]
        shape, fill, stroke, _, _, radius = style_of(n)
        d.update(shape=shape, fill=fill, stroke=stroke, radius=radius,
                 lines=wrap_text(n.get("label") or "", 12, max(40, d["w"] - 20)))

    out_edges = []
    STEP = 52
    for i, e in enumerate(msgs):
        s, t = e.get("source"), e.get("target")
        if s not in actor_x or t not in actor_x:
            continue
        y = TOP + i * STEP
        xs, xt = actor_x[s], actor_x[t]
        dashed, arrow, width = edge_style(e)
        if s == t:                                   
            pts = [(xs, y), (xs + 46, y), (xs + 46, y + 26), (xs, y + 26)]
            out_edges.append({"id": e["id"], "points": pts,
                              "label": e.get("label") or "", "dashed": dashed,
                              "arrow": arrow, "width": width,
                              "lx": xs + 56, "ly": y + 13})
            continue
        pts = [(xs, y), (xt, y)]
        out_edges.append({"id": e["id"], "points": pts,
                          "label": e.get("label") or "", "dashed": dashed,
                          "arrow": arrow, "width": width,
                          "lx": (xs + xt) / 2, "ly": y - 7})
    w = max(d["x"] + d["w"] for d in out_nodes.values()) + MARGIN
    h = TOP + len(msgs) * STEP + MARGIN
    return {"nodes": out_nodes, "groups": {}, "edges": out_edges,
            "width": w, "height": h, "direction": "TB"}


def _layout_er(g):

    ents = [n for n in g["nodes"] if (n.get("type") or "entity") != "attribute"]
    per_col = max(1, (len(ents) + 1) // 2)
    out_nodes = {}
    for i, n in enumerate(ents):
        w, h = node_size(n)
        col, row = i // per_col, i % per_col
        x = MARGIN + col * (max(node_size(m)[0] for m in ents) + 170)
        y = MARGIN + row * (h + 60)
        out_nodes[n["id"]] = {"x": x, "y": y, "w": w, "h": h}
    for n in ents:
        d = out_nodes[n["id"]]
        shape, fill, stroke, _, _, radius = style_of(n)
        d.update(shape=shape, fill=fill, stroke=stroke, radius=radius,
                 lines=wrap_text(n.get("label") or "", 12, max(40, d["w"] - 20)))
    out_edges = []
    for e in g["edges"]:
        s, t = out_nodes.get(e.get("source")), out_nodes.get(e.get("target"))
        if not s or not t:
            continue
        dashed, arrow, width = edge_style(e)
        same_col = abs((s["x"] + s["w"] / 2) - (t["x"] + t["w"] / 2)) < 1
        if same_col:
            p1 = (s["x"] + s["w"] / 2, s["y"] + s["h"])
            p2 = (t["x"] + t["w"] / 2, t["y"])
            pts = [p1, p2] if abs(p1[0] - p2[0]) < 1 else [
                p1, (p1[0], (p1[1] + p2[1]) / 2), (p2[0], (p1[1] + p2[1]) / 2), p2]
            lx, ly = (p1[0] + p2[0]) / 2 + 8, (p1[1] + p2[1]) / 2
        else:
            p1 = (s["x"] + s["w"], s["y"] + s["h"] / 2)
            p2 = (t["x"], t["y"] + t["h"] / 2)
            pts = [p1, p2]
            lx, ly = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 - 7
        out_edges.append({"id": e["id"], "points": pts,
                          "label": e.get("label") or "", "dashed": dashed,
                          "arrow": arrow, "width": width, "lx": lx, "ly": ly})
    w = max(d["x"] + d["w"] for d in out_nodes.values()) + MARGIN
    h = max(d["y"] + d["h"] for d in out_nodes.values()) + MARGIN
    return {"nodes": out_nodes, "groups": {}, "edges": out_edges,
            "width": w, "height": h, "direction": "TB"}


def _canvas(out_nodes, out_groups):
    w = h = 0
    for d in out_nodes.values():
        w = max(w, d["x"] + d["w"])
        h = max(h, d["y"] + d["h"])
    for d in out_groups.values():
        w = max(w, d["x"] + d["w"])
        h = max(h, d["y"] + d["h"])
    return int(w + MARGIN), int(h + MARGIN)


def dump_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

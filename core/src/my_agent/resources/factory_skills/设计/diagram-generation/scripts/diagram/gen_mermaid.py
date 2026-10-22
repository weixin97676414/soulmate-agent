# -*- coding: utf-8 -*-





import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_graph import load, style_of  


MMD_SHAPE = {
    "actor":     ("((", "))"),
    "gateway":   ("{{", "}}"),
    "service":   ("(", ")"),
    "component": ("[", "]"),
    "container": ("(", ")"),
    "db":        ("[(", ")]"),
    "cache":     ("[(", ")]"),
    "queue":     ("[", "]"),
    "external":  ("[", "]"),
    "process":   ("[", "]"),
    "decision":  ("{", "}"),
    "start":     ("([", "])"),
    "end":       ("([", "])"),
    "entity":    ("[", "]"),
    "attribute": ("((", "))"),
    "state":     ("(", ")"),
    "note":      ("[", "]"),
}
MMD_EDGE = {
    "sync": "-->", "async": "-.->", "data": "==>", "return": "-.->",
    "assoc": "-->", "inherit": "-->", "flow": "-->",
}



CARD_MMD = {
    "1:1": "||--||", "1:N": "||--o{", "1:n": "||--o{",
    "N:1": "}|--||", "n:1": "}|--||",
    "N:M": "}|--|{", "n:m": "}|--|{", "M:N": "}|--|{",
}


def esc(t):
    return (t or "").replace('"', "'").replace("\n", " ")


def er_name(n):

    lb = (n.get("label") or "").strip()
    if lb and lb.isascii() and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", lb):
        return lb, False
    return n.get("id"), True


def to_mermaid(g):
    meta = g.get("meta") or {}
    gtype = meta.get("graph_type")
    direction = meta.get("direction") or "TB"
    nodes = {n["id"]: n for n in g["nodes"]}
    L = []
    if gtype == "sequence":
        L.append("sequenceDiagram")
        for n in g["nodes"]:
            kw = "actor" if n.get("type") == "actor" else "participant"
            L.append("    %s %s as %s" % (kw, n["id"], esc(n.get("label") or "")))
        for e in sorted(g["edges"], key=lambda x: x.get("seq", 999)):
            arrow = "-->>" if (e.get("type") or "sync") == "sync" else "-->>"
            if e.get("type") == "async":
                L.append("    %s -) %s: %s" % (e["source"], e["target"],
                                               esc(e.get("label") or "")))
            elif e.get("type") == "return":
                
                L.append("    %s -->> %s: %s" % (e["source"], e["target"],
                                                 esc(e.get("label") or "")))
            else:
                L.append("    %s %s %s: %s" % (e["source"], arrow, e["target"],
                                               esc(e.get("label") or "")))
        return "\n".join(L) + "\n"

    if gtype == "er":
        alias = {}
        body = []
        for n in g["nodes"]:
            name, aliased = er_name(n)
            if aliased:
                alias[name] = n.get("label") or name
            body.append("    %s {" % name)
            for a in (n.get("attrs") or []):
                body.append("        %s %s" % (a.get("type", "string"),
                                               a.get("name", "")))
            body.append("    }")
        for e in g["edges"]:
            s, _ = er_name(nodes.get(e["source"], {"id": e["source"]}))
            t, _ = er_name(nodes.get(e["target"], {"id": e["target"]}))
            card = (e.get("label") or "1:N").strip()
            sym = CARD_MMD.get(card, CARD_MMD.get(card.upper(), "||--o{"))
            body.append('    %s %s %s : "%s"' % (s, sym, t, esc(e.get("desc") or "")))
        L.append("erDiagram")
        if alias:
            
            L.append("%% 实体名对照（Mermaid 实体名不支持中文，此处用 id 代替）：")
            for k, v in alias.items():
                L.append("%%   {} = {}".format(k, v))
        L.extend(body)
        return "\n".join(L) + "\n"

    if gtype == "state":
        L.append("stateDiagram-v2")
        for n in g["nodes"]:
            L.append("    %s : %s" % (n["id"], esc(n.get("label") or "")))
        for e in g["edges"]:
            L.append("    %s --> %s : %s" % (e["source"], e["target"],
                                             esc(e.get("label") or "")))
        return "\n".join(L) + "\n"

    
    L.append("flowchart %s" % direction)
    gm = {x["id"]: x for x in g["groups"]}
    in_group = {n["id"]: n.get("group") for n in g["nodes"]}
    emitted = set()

    def render_node(n):
        if n["id"] in emitted:
            return
        emitted.add(n["id"])
        lb, rb = MMD_SHAPE.get(n.get("type") or "component", ("[", "]"))
        L.append("    %s%s\"%s\"%s" % (n["id"], lb, esc(n.get("label") or ""), rb))

    for gid, gx in gm.items():
        L.append("    subgraph %s[\"%s\"]" % (gid, esc(gx.get("label") or gid)))
        for n in g["nodes"]:
            if in_group.get(n["id"]) == gid:
                render_node(n)
        L.append("    end")
    for n in g["nodes"]:
        render_node(n)
    for e in g["edges"]:
        arrow = MMD_EDGE.get(e.get("type") or "sync", "-->")
        lb = esc(e.get("label") or "")
        if lb:
            L.append("    %s %s|%s| %s" % (e["source"], arrow, lb, e["target"]))
        else:
            L.append("    %s %s %s" % (e["source"], arrow, e["target"]))
    
    for n in g["nodes"]:
        if n.get("type") == "external":
            L.append("    style %s stroke-dasharray: 5 5" % n["id"])
    return "\n".join(L) + "\n"


def to_plantuml(g):
    meta = g.get("meta") or {}
    gtype = meta.get("graph_type")
    nodes = {n["id"]: n for n in g["nodes"]}
    L = ["@startuml", "' 由统一图模型 graph.json 生成",
         "skinparam defaultFontName Microsoft YaHei",
         "skinparam shadowing false", ""]
    if gtype == "sequence":
        for n in g["nodes"]:
            kw = "actor" if n.get("type") == "actor" else "participant"
            L.append("%s \"%s\" as %s" % (kw, esc(n.get("label") or ""), n["id"]))
        L.append("")
        for e in sorted(g["edges"], key=lambda x: x.get("seq", 999)):
            ar = "->" if (e.get("type") or "sync") != "return" else "-->"
            L.append("%s %s %s : %s" % (e["source"], ar, e["target"],
                                        esc(e.get("label") or "")))
    elif gtype == "er":
        L.append("!theme plain")
        for n in g["nodes"]:
            L.append("entity \"%s\" as %s {" % (esc(n.get("label") or ""), n["id"]))
            for a in (n.get("attrs") or []):
                L.append("  %s : %s" % (a.get("name", ""), a.get("type", "string")))
            L.append("}")
        for e in g["edges"]:
            card = (e.get("label") or "1:N").strip()
            lft, rgt = card.split(":", 1) if ":" in card else ("1", card)
            L.append('%s "%s" -- "%s" %s : %s'
                     % (e["source"], lft.strip(), rgt.strip(), e["target"],
                        esc(e.get("desc") or "")))
    elif gtype == "state":
        L.append("[*] --> %s" % next((n["id"] for n in g["nodes"]
                                      if "init" in n["id"].lower()),
                                     g["nodes"][0]["id"] if g["nodes"] else ""))
        for e in g["edges"]:
            L.append("%s --> %s : %s" % (e["source"], e["target"],
                                         esc(e.get("label") or "")))
        for n in g["nodes"]:
            if "final" in n["id"].lower() or n.get("type") == "end":
                L.append("%s --> [*]" % n["id"])
    elif gtype == "flowchart":
        L.append("' 说明：PlantUML 活动图对复杂嵌套分支表达有限，")
        L.append("' 完整分支结构请以 drawio / Mermaid 产物为准")
        L.append("start")
        for n in g["nodes"]:
            if n.get("type") in ("start", "end"):
                continue
            if n.get("type") == "decision":
                outs = [e for e in g["edges"] if e.get("source") == n["id"]]
                L.append("if (%s) then (%s)" % (esc(n.get("label") or ""),
                                                esc(outs[0].get("label") or "yes")
                                                if outs else "yes"))
                for e in outs:
                    tgt = nodes.get(e.get("target"), {})
                    L.append("  : %s" % esc(tgt.get("label") or ""))
                L.append("else (%s)" % (esc(outs[1].get("label") or "no")
                                        if len(outs) > 1 else "no"))
            else:
                L.append(":%s" % esc(n.get("label") or ""))
        L.append("stop")
    else:
        for x in g["groups"]:
            L.append("package \"%s\" {" % esc(x.get("label") or x["id"]))
            for n in g["nodes"]:
                if n.get("group") == x["id"]:
                    L.append("  component \"%s\" as %s"
                             % (esc(n.get("label") or ""), n["id"]))
            L.append("}")
        for n in g["nodes"]:
            if not n.get("group"):
                L.append("component \"%s\" as %s" % (esc(n.get("label") or ""), n["id"]))
        L.append("")
        for e in g["edges"]:
            ar = "..>" if (e.get("type") or "sync") == "async" else "-->"
            L.append("%s %s %s : %s" % (e["source"], ar, e["target"],
                                        esc(e.get("label") or "")))
    L.append("")
    L.append("@enduml")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("graph")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--format", choices=["mermaid", "plantuml"], default="mermaid")
    a = ap.parse_args()
    g = load(a.graph)
    text = to_mermaid(g) if a.format == "mermaid" else to_plantuml(g)
    d = os.path.dirname(os.path.abspath(a.out))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text)
    print("%s 已生成：%s（%d 行）"
          % (a.format, a.out, text.count("\n")))
    print("  嵌入 Markdown：用 ```mermaid 代码块包裹即可渲染")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-






import json
import os
import re
import sys
import unicodedata

MATERIALS_SCHEMA = "demo-materials/v1"
OUTLINE_SCHEMA = "demo-outline/v1"


ROLES = ("封面", "背景", "痛点", "方案", "能力", "价值", "案例", "路线", "保障", "收尾")


ROLE_MINUTES = {"封面": 0.5, "背景": 1.5, "痛点": 2, "方案": 3, "能力": 4,
                "价值": 2, "案例": 3, "路线": 2, "保障": 1.5, "收尾": 1}

NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")
HEADING_MD = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)")
HEADING_CN = re.compile(r"^\s*第[一二三四五六七八九十百零〇\d]+[条章节部分篇]\s*(.*)$")
HEADING_NUM = re.compile(r"^\s*(\d+(?:\.\d+)*)[、.．]\s*(\S.*)$")
HEADING_ALPHA = re.compile(r"^\s*[（(]?([一二三四五六七八九十]+|[A-Z])[)）、]\s*(\S.*)$")
BULLET = re.compile(r"^\s*[-*·•]\s+")




def die(msg, code=1):
    sys.stderr.write("[ERROR] %s\n" % msg)
    sys.exit(code)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def norm(s):

    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[，。；：、！？,.;:!?\"'“”‘’（）()\[\]【】{}《》<>·…—\-_/\\|~`*#]+", "", s)
    return s


def ngrams(s, n=2):
    s = norm(s)
    if len(s) < n:
        return {s} if s else set()
    return set(s[i:i + n] for i in range(len(s) - n + 1))


def similarity(a, b):
    ga, gb = ngrams(a), ngrams(b)
    if not ga or not gb:
        return 0.0
    inter = len(ga & gb)
    return inter / min(len(ga), len(gb)) if min(len(ga), len(gb)) else 0.0




def is_heading(line):







    s = (line or "").strip()
    if not s:
        return None
    m = HEADING_MD.match(line)
    if m:
        return m.group(1).strip()
    if s[-1] in "。：；，、！？.!?,;:":
        return None
    if len(s) > 30:
        return None
    m = HEADING_CN.match(line)
    if m:
        return s
    m = HEADING_NUM.match(line)
    if m:
        return m.group(2).strip()
    m = HEADING_ALPHA.match(line)
    if m:
        return m.group(2).strip()
    return None


def slice_text(text, source, min_len=8):




    lines = text.splitlines()
    items = []
    cur_sec = ""
    buf = []
    order = 0

    def flush():
        nonlocal buf
        body = "\n".join(x for x in buf if x.strip()).strip()
        buf = []
        if len(norm(body)) < min_len:
            return
        order_local = len(items)
        items.append({
            "source": source,
            "section": cur_sec or ("片段%d" % (order_local + 1)),
            "text": body,
        })

    for ln in lines:
        if not ln.strip():
            flush()
            continue
        h = is_heading(ln)
        if h:
            flush()
            cur_sec = h
            continue
        buf.append(ln.rstrip())
    flush()
    return items


def split_long(items, max_chars=300):




    out = []
    for it in items:
        text = it.get("text", "") or ""
        if len(text) <= max_chars:
            out.append(it)
            continue
        buf, idx = "", 1
        for seg in re.split(r"(?<=[。；！？\n])", text):
            if not seg.strip():
                continue
            if len(buf) + len(seg) > max_chars and buf:
                out.append({"source": it.get("source", ""),
                            "section": "%s（%d）" % (it.get("section", ""), idx),
                            "text": buf.strip(),
                            "tags": it.get("tags", [])})
                idx += 1
                buf = ""
            buf += seg
        if buf.strip():
            out.append({"source": it.get("source", ""),
                        "section": "%s（%d）" % (it.get("section", ""), idx),
                        "text": buf.strip(),
                        "tags": it.get("tags", [])})
    return out


def docx_paragraphs(path):

    try:
        import docx  
    except ImportError:
        die("未安装 python-docx，无法解析 .docx。请先在隔离环境执行：pip install python-docx")
    from docx import Document
    d = Document(path)
    return [(p.style.name or "", p.text or "") for p in d.paragraphs]


def read_docx_sections(path):

    items = []
    cur_sec = ""
    buf = []

    def flush():
        nonlocal buf
        body = "\n".join(x for x in buf if x.strip()).strip()
        buf = []
        if len(norm(body)) < 8:
            return
        items.append({"source": os.path.basename(path), "section": cur_sec or "正文",
                      "text": body})

    for style, text in docx_paragraphs(path):
        if not text.strip():
            flush()
            continue
        if str(style).lower().startswith(("heading", "title")):
            flush()
            cur_sec = text.strip()
            continue
        if is_heading(text) and len(text.strip()) <= 40:
            flush()
            cur_sec = is_heading(text)
            continue
        buf.append(text.strip())
    flush()
    return items


TEXT_EXT = (".md", ".markdown", ".txt", ".text")


def collect_files(path):

    if os.path.isfile(path):
        return [path]
    out = []
    for root, _dirs, files in os.walk(path):
        for fn in sorted(files):
            if fn.startswith("~$") or fn.startswith("."):
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext in TEXT_EXT or ext == ".docx":
                out.append(os.path.join(root, fn))
    return sorted(out)


def build_materials(paths):

    raw = []
    for p in paths:
        for f in collect_files(p):
            ext = os.path.splitext(f)[1].lower()
            name = os.path.basename(f)
            if ext == ".docx":
                raw.extend(read_docx_sections(f))
            else:
                with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                    raw.extend(slice_text(fh.read(), name))
    return raw


def make_materials(raw, source_name=""):

    mats = []
    for i, r in enumerate(raw, 1):
        mats.append({
            "id": "S-%d" % i,
            "source": r.get("source", ""),
            "section": r.get("section", ""),
            "text": r.get("text", "").strip(),
            "tags": r.get("tags", []),
        })
    return {
        "schema": MATERIALS_SCHEMA,
        "name": source_name or "素材库",
        "total": len(mats),
        "materials": mats,
    }


def find_quote(mats, quote):

    nq = norm(quote)
    if not nq:
        return []
    hits = []
    for m in mats:
        if nq in norm(m.get("text", "")):
            hits.append(m["id"])
    if hits:
        return hits
    
    parts = [p for p in re.split(r"[。；;！？!?\n]", quote) if len(norm(p)) >= 6]
    if parts:
        for m in mats:
            nt = norm(m.get("text", ""))
            if all(norm(p) in nt for p in parts):
                hits.append(m["id"])
    return hits


def material_index(mats):
    return {m["id"]: m for m in mats}




DEFAULT_PAGES = [
    {"role": "封面", "title": "开场", "goal": "交代主题与价值主张，让听众立刻知道要听什么"},
    {"role": "背景", "title": "业务背景与现状", "goal": "说明行业与公司现状，建立共识"},
    {"role": "痛点", "title": "当前面临的核心问题", "goal": "点出痛点，激发改变动机"},
    {"role": "方案", "title": "整体方案概览", "goal": "一句话讲清方案是什么、怎么解决"},
    {"role": "能力", "title": "核心能力详解", "goal": "展开关键能力，配合场景说明"},
    {"role": "价值", "title": "预期价值与收益", "goal": "量化收益，回答\"对我有什么好处\""},
    {"role": "案例", "title": "落地案例与验证", "goal": "用事实增强可信度"},
    {"role": "路线", "title": "实施路线与计划", "goal": "说明分几步、多久见效"},
    {"role": "保障", "title": "风险与保障机制", "goal": "主动回应顾虑"},
    {"role": "收尾", "title": "总结与行动倡议", "goal": "收束主线，明确下一步"},
]


def empty_outline(name="", audience="", goal="", duration=30):
    return {
        "schema": OUTLINE_SCHEMA,
        "meta": {
            "name": name or "对外演示材料",
            "audience": audience,
            "goal": goal,
            "duration_min": duration,
            "created_at": "",
            "edited_by": "",
            "edit_note": "",
        },
        "pages": [],
    }


def iter_points(outline):
    for p in outline.get("pages", []):
        for t in p.get("points", []):
            yield p, t

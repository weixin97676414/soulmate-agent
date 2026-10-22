#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公众号爆款封面工坊 · 工具脚本（本地运行）

子命令：
  preview  生成自包含 HTML 方案册（注入 covers 数据 + 拷贝图片到 assets/）
  compose  用 Pillow 将中文标题清晰合成到视觉底图的「标题安全区」
  check    校验封面尺寸/比例，给出缩略识别度与安全区建议

所有能力均为本地/内置运行。
需要 Pillow 时（compose/check）：在托管环境执行  pip install pillow
"""

import os
import re
import sys
import json
import shutil
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
REF_DIR = os.path.join(os.path.dirname(HERE), "references")
TEMPLATE = os.path.join(REF_DIR, "cover_preview_template.html")


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------
def _die(msg, code=1):
    print("❌ " + msg, file=sys.stderr)
    sys.exit(code)


def _read_json(path_or_stdin):
    if path_or_stdin == "-":
        return json.load(sys.stdin)
    with open(path_or_stdin, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 子命令：preview
# ---------------------------------------------------------------------------
def cmd_preview(args):
    if not os.path.exists(TEMPLATE):
        _die("未找到模板: %s" % TEMPLATE)
    data = _read_json(args.input)
    items = data.get("items", [])
    theme = data.get("theme", "封面方案")

    out_path = args.output or ("./封面方案_%s.html" % theme)
    out_path = os.path.abspath(out_path)
    out_dir = os.path.dirname(out_path)
    assets_dir = os.path.join(out_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    def _localize(field):
        val = item.get(field, "")
        if not val:
            return ""
        src = val if os.path.isabs(val) else os.path.join(out_dir, val)
        if not os.path.exists(src):
            return val  # 远程 URL 等原样保留
        base = os.path.basename(src)
        name, ext = os.path.splitext(base)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        ext = ext or ".png"
        dst = os.path.join(assets_dir, "%s_%s%s" % (field, safe, ext))
        shutil.copy2(src, dst)
        return "assets/" + os.path.basename(dst)

    for item in items:
        item["base"] = _localize("base")
        item["final"] = _localize("final")

    payload = {
        "theme": theme,
        "generatedAt": data.get("generatedAt", ""),
        "count": len(items),
        "items": items,
    }
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        html = f.read()
    html = re.sub(r"var __COVER_DATA__ = \{.*?\};",
                  "var __COVER_DATA__ = " + json.dumps(payload, ensure_ascii=False) + ";",
                  html, count=1, flags=re.S)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("✓ 方案册已生成: %s" % out_path)
    print("✓ 共 %d 套方案，图片已拷贝到 assets/" % len(items))


# ---------------------------------------------------------------------------
# 字体探测（CJK）
# ---------------------------------------------------------------------------
def _cjk_font_candidates():
    env = os.environ.get("GZH_COVER_FONT")
    if env and os.path.exists(env):
        return [env]
    cands = []
    if sys.platform.startswith("win"):
        base = "C:/Windows/Fonts"
        cands = [
            os.path.join(base, "msyhbd.ttc"),
            os.path.join(base, "msyh.ttc"),
            os.path.join(base, "simhei.ttf"),
            os.path.join(base, "simsun.ttc"),
        ]
    elif sys.platform == "darwin":
        cands = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
    else:  # linux
        cands = [
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    return [c for c in cands if os.path.exists(c)]


def _load_font(size, bold=False):
    try:
        from PIL import ImageFont
    except Exception:
        return None
    cands = _cjk_font_candidates()
    # 优先 Bold 变体
    if bold:
        bold_cands = [c for c in cands if ("bold" in c.lower() or "bd" in c.lower() or "hei" in c.lower())]
        cands = bold_cands + cands
    for c in cands:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 子命令：compose（标题精排）
# ---------------------------------------------------------------------------
def _wrap_text(draw, text, font, max_width):
    lines = []
    cur = ""
    for ch in text:
        test = cur + ch
        try:
            fits = draw.textlength(test, font=font) <= max_width
        except Exception:
            fits = len(test) * size * 0.6 <= max_width
        if fits:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def _is_light(hexcolor):
    h = hexcolor.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return lum > 150


def _fit_layout(draw, w, h, title, subtitle, pos, max_lines=2):
    """
    在底部（或顶部）安全区内自适配合适字号与位置。
    返回 dict，包含所有排版图元参数。
    """
    region_ratio = 0.46 if pos != "top" else 0.38
    region_h = int(h * region_ratio)
    pad_x = int(w * 0.05)
    max_text_w = w - 2 * pad_x
    pad_bottom = int(h * 0.04)

    best = None
    max_size = int(w * 0.085)
    min_size = int(w * 0.05)

    for size in range(max_size, min_size - 1, -2):
        tfont = _load_font(size, bold=True)
        if not tfont:
            continue
        lines = _wrap_text(draw, title, tfont, max_text_w)
        if len(lines) > max_lines:
            continue
        line_h = int(size * 1.22)
        block_h = line_h * len(lines)

        sub_size = max(16, int(size * 0.5)) if subtitle else 0
        sub_h = int(sub_size * 1.35) if subtitle else 0
        sfont = _load_font(sub_size, bold=False) if subtitle else None

        bar_h = max(5, int(size * 0.16))
        # 间距：标题-色条 10px；色条-副标题 10px；副标题-区域底 pad_bottom
        gaps = 10 + (10 if subtitle else 0)
        total_h = block_h + bar_h + sub_h + gaps + pad_bottom

        if total_h <= region_h:
            best = {
                "size": size,
                "tfont": tfont,
                "lines": lines,
                "line_h": line_h,
                "block_h": block_h,
                "sub_size": sub_size,
                "sfont": sfont,
                "sub_h": sub_h,
                "bar_h": bar_h,
                "pad_x": pad_x,
                "pad_bottom": pad_bottom,
            }
            break

    if best is None:
        # 兜底：最小字号
        size = min_size
        tfont = _load_font(size, bold=True) or _load_font(size, bold=False)
        lines = _wrap_text(draw, title, tfont, max_text_w)[:max_lines]
        best = {
            "size": size,
            "tfont": tfont,
            "lines": lines,
            "line_h": int(size * 1.22),
            "block_h": int(size * 1.22) * len(lines),
            "sub_size": int(size * 0.5) if subtitle else 0,
            "sfont": _load_font(int(size * 0.5), bold=False) if subtitle else None,
            "sub_h": int(int(size * 0.5) * 1.35) if subtitle else 0,
            "bar_h": max(4, int(size * 0.16)),
            "pad_x": pad_x,
            "pad_bottom": pad_bottom,
        }

    # 计算 Y 坐标（从底往上堆叠）
    b = best
    if pos == "top":
        title_top = int(h * 0.14)
        title_bottom = title_top + b["block_h"]
    else:
        title_bottom = h - b["pad_bottom"]
        title_top = title_bottom - b["block_h"]
    b["title_top"] = title_top

    b["bar_bottom"] = title_top - 10
    b["bar_top"] = b["bar_bottom"] - b["bar_h"]
    if subtitle and b["sfont"]:
        b["sub_bottom"] = b["bar_top"] - 10
        b["sub_top"] = b["sub_bottom"] - b["sub_h"]
    else:
        b["sub_top"] = b["sub_bottom"] = 0

    return b


def cmd_compose(args):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        _die("需要 Pillow：请在托管环境执行  pip install pillow  后重试（compose 依赖它做标题精排）。\n"
             "若无法安装，可降级为「纯标题排版 HTML 封面」方案。")

    if not os.path.exists(args.base):
        _die("底图不存在: %s" % args.base)
    img = Image.open(args.base).convert("RGBA")
    w, h = img.size
    pos = args.position

    title = args.title or ""
    subtitle = args.subtitle or ""
    tag = args.tag or ""

    # 安全区高度
    region_ratio = 0.46 if pos != "top" else 0.38
    region_h = int(h * region_ratio)
    if pos == "top":
        region_top, region_bottom = 0, region_h
    else:
        region_top, region_bottom = h - region_h, h

    title_color = args.title_color
    light_title = _is_light(title_color)
    scrim_color = (0, 0, 0) if light_title else (255, 255, 255)
    max_alpha = 150 if light_title else 170

    # 渐变蒙版
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(region_top, region_bottom):
        t = (y - region_top) / max(1, region_bottom - region_top - 1)
        alpha = int(max_alpha * (t if pos != "top" else (1 - t)))
        od.line([(0, y), (w, y)], fill=scrim_color + (alpha,))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # 标签（角标）
    tag_size = max(18, int(w * 0.028))
    gfont = _load_font(tag_size, bold=True)
    if tag and gfont:
        tg = draw.textlength(tag, font=gfont) + tag_size * 0.9
        ty = int(h * 0.05)
        tx = int(w * 0.05)
        draw.rectangle([tx, ty, tx + tg, ty + tag_size * 1.45], fill=args.accent)
        draw.text((tx + tag_size * 0.35, ty + tag_size * 0.22), tag, font=gfont, fill="#ffffff")

    if not title:
        out = args.out or (_add_suffix(args.base, "_cover"))
        img.convert("RGB").save(out)
        print("✓ 已输出（无标题）: %s" % out)
        return

    layout = _fit_layout(draw, w, h, title, subtitle, pos)

    # 副标题
    if subtitle and layout["sfont"]:
        stroke = max(1, int(layout["sub_size"] * 0.04))
        draw.text((layout["pad_x"], layout["sub_top"]), subtitle,
                  font=layout["sfont"], fill=title_color,
                  stroke_width=stroke, stroke_fill=scrim_color)

    # 强调色条（分隔副标题与主标题）
    accent_w = int(w * 0.10)
    draw.rectangle([
        layout["pad_x"], layout["bar_top"],
        layout["pad_x"] + accent_w, layout["bar_bottom"]
    ], fill=args.accent)

    # 主标题
    stroke = max(1, int(layout["size"] * 0.03))
    y = layout["title_top"]
    for ln in layout["lines"]:
        draw.text((layout["pad_x"], y), ln, font=layout["tfont"],
                  fill=title_color, stroke_width=stroke, stroke_fill=scrim_color)
        y += layout["line_h"]

    out = args.out or (_add_suffix(args.base, "_cover"))
    img.convert("RGB").save(out)
    print("✓ 标题精排完成: %s" % out)
    print("  标题: %s | 字号: %d | 行数: %d | 位置: %s | 安全区: %s" %
          (title, layout["size"], len(layout["lines"]), pos,
           "底部 1/3" if pos != "top" else "顶部"))


def _add_suffix(path, suffix):
    root, ext = os.path.splitext(path)
    return root + suffix + (ext or ".png")


# ---------------------------------------------------------------------------
# 子命令：check（自检）
# ---------------------------------------------------------------------------
def cmd_check(args):
    try:
        from PIL import Image
    except Exception:
        _die("需要 Pillow：pip install pillow")
    targets = {
        "900x383": (900, 383),
        "1080x1080": (1080, 1080),
        "1080x1350": (1080, 1350),
    }
    want = None
    if args.target:
        want = tuple(int(x) for x in args.target.lower().split("x"))
    results = []
    for p in args.images:
        if not os.path.exists(p):
            results.append({"file": p, "ok": False, "note": "文件不存在"})
            continue
        im = Image.open(p)
        w, h = im.size
        ratio = round(w / h, 3)
        match = (w, h) in targets.values()
        rec = {"file": p, "width": w, "height": h, "ratio": ratio,
               "matchKnown": match}
        if want:
            rec["matchTarget"] = (w, h) == want
        tips = []
        if min(w, h) < 300:
            tips.append("分辨率偏低，缩略可能糊")
        if not (0.4 < ratio < 3.0):
            tips.append("宽高比异常")
        rec["tips"] = tips
        results.append(rec)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            status = "✓" if r.get("matchKnown") else "⚠"
            print("%s %s  %dx%d  比例%.3f" % (status, r["file"], r["width"], r["height"], r["ratio"]))
            for t in r.get("tips", []):
                print("   - %s" % t)
    print("\n已知标准尺寸: 900x383(主封面 2.35:1) / 1080x1080(方图) / 1080x1350(朋友圈)")
    print("标题安全区建议：主体居中偏上，标题落底部1/3，缩至108px仍可辨。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="公众号爆款封面工坊工具")
    sub = ap.add_subparsers(dest="cmd")

    p_p = sub.add_parser("preview", help="生成 HTML 方案册")
    p_p.add_argument("--input", required=True, help="方案 JSON（文件或 - 表示 stdin）")
    p_p.add_argument("--output", default=None, help="输出 HTML 路径")
    p_p.set_defaults(func=cmd_preview)

    p_c = sub.add_parser("compose", help="标题精排合成")
    p_c.add_argument("--base", required=True, help="视觉底图路径")
    p_c.add_argument("--title", default="", help="主标题")
    p_c.add_argument("--subtitle", default="", help="副标题")
    p_c.add_argument("--tag", default="", help="栏目标签（角标）")
    p_c.add_argument("--out", default=None, help="输出路径")
    p_c.add_argument("--position", default="bottom", choices=["bottom", "top"])
    p_c.add_argument("--title-color", default="#ffffff", help="标题颜色(十六进制)")
    p_c.add_argument("--accent", default="#ff6a3d", help="强调色(角标/色条)")
    p_c.add_argument("--font-size", type=int, default=0, help="主标题字号(0=自适应)")
    p_c.set_defaults(func=cmd_compose)

    p_k = sub.add_parser("check", help="尺寸/安全区自检")
    p_k.add_argument("--images", nargs="+", required=True, help="图片路径")
    p_k.add_argument("--target", default=None, help="期望尺寸 如 900x383")
    p_k.add_argument("--json", action="store_true")
    p_k.set_defaults(func=cmd_check)

    args = ap.parse_args()
    if not getattr(args, "cmd", None):
        ap.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()

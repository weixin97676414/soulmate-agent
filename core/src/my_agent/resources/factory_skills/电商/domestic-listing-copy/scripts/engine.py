#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# © 三咨澳金（北京）科技有限公司 @2026 AI智造局. 保留所有权利。
"""
详情页文案工厂 · 引擎 v2.0.0（纯标准库）
子命令: generate / score / check / profile / selftest
- generate: 输入商品资料 → 模块化详情页文案（痛点/卖点/证明/场景/信任/逼单/FAQ）
- score:    文案质量评分（模块完整度/卖点数/违禁-free/长度）
- check:    违禁词扫描
- profile:  深度感知 — 商品档案演化
引擎读取 references/ 下知识库；无网络、零第三方依赖。
"""
import os, sys, json, argparse

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COPYRIGHT_BANNER = "© 三咨澳金（北京）科技有限公司 @2026 AI智造局. 保留所有权利。"
GENERATED_BY_STAMP = "「由三咨澳金（北京）科技有限公司  @2026 AI智造局 生成 ©」"

def load_json(name):
    with open(os.path.join(SKILL_DIR, "references", name), encoding="utf-8") as f:
        return json.load(f)

SP_BANK = load_json("selling-points.json")
TEMPLATES = load_json("copy-templates.json")
BANNED = load_json("banned-words.json")

PLATFORMS = TEMPLATES["platforms"]
MODULE_ORDER = TEMPLATES["modules"]
PAIN_DEFAULTS = {
    "服饰": "尺码不准、色差大、洗两次就变形",
    "数码": "续航虚标、用俩月卡顿、售后找不到人",
    "家居": "味道大、用料糙、和图片差太多",
    "美妆": "过敏、假货、宣传效果名不副实",
    "食品": "临期、口感差、配料表看不懂",
}
DEFAULT_PAINS = ["货不对板", "质量不稳", "售后无门"]


def _load_product(product):
    if isinstance(product, str):
        product = json.loads(product)
    return product


def extract_selling_points(product):
    """从商品属性/关键词/标题匹配卖点库，返回 [(label, text), ...]"""
    blob = " ".join([
        product.get("title", ""),
        product.get("category", ""),
        " ".join(product.get("attrs", {}).values()),
        " ".join(product.get("keywords", [])),
    ])
    blob_low = blob.lower()
    points = []
    for cat in SP_BANK["categories"]:
        hit = next((t for t in cat["triggers"] if t.lower() in blob_low), None)
        if hit:
            text = cat["template"].format(hot=hit)
            points.append((cat["label"], text))
    if not points:
        points.append(("综合优势", "聚焦真实使用场景，把每一分预算花在刀刃上。"))
    return points


def check_banned(text):
    found_hard = [w for w in BANNED["hard"] if w in text]
    found_soft = [w for w in BANNED["soft_warn"] if w in text]
    return found_hard, found_soft


def build_modules(product):
    platform = product.get("platform", "taobao")
    cfg = PLATFORMS.get(platform, PLATFORMS["taobao"])
    name = product.get("title", product.get("name", "本商品"))
    cat = product.get("category", "")
    pain_default = PAIN_DEFAULTS.get(cat, "、".join(DEFAULT_PAINS))
    points = extract_selling_points(product)
    sp_text = "；".join(f"{l}：{t}" for l, t in points[:3])

    emo = "🔥" if cfg.get("emoji") else ""
    modules = {}
    modules["痛点引入"] = cfg["pain"].format(name=name, pain_default=pain_default)
    modules["核心卖点"] = f"三大理由选它：{sp_text}"
    attrs = product.get("attrs", {})
    if attrs:
        spec = "；".join(f"{k}：{v}" for k, v in list(attrs.items())[:6])
        modules["参数证明"] = f"硬核参数一眼懂：{spec}。"
    else:
        modules["参数证明"] = f"{name}关键指标清晰标注，下单前心里有数。"
    scene = product.get("scene", "日常通勤/居家/送礼都能hold住")
    modules["场景故事"] = f"想象一下：{scene}，{name}刚好派上用场{emo}。"
    modules["信任背书"] = f"支持七天无理由+运费险，正品保障，售后有人管。"
    modules["逼单话术"] = cfg["urgency"]
    faqs = TEMPLATES["faq_pool"][:3]
    modules["FAQ"] = "\n".join(f"Q：{f['q']}\nA：{f['a']}" for f in faqs)
    return modules, points


def score_copy(modules):
    present = [m for m in MODULE_ORDER if modules.get(m)]
    completeness = len(present) / len(MODULE_ORDER)
    full = "\n".join(modules.values())
    hard, soft = check_banned(full)
    sp_count = sum(1 for m in modules if "卖点" in m)
    length_ok = 200 <= len(full) <= 2000
    score = 60 * completeness + 15 * (1 if length_ok else 0) + 15 * (1 if not hard else 0) + 10 * (1 if sp_count >= 1 else 0)
    return round(min(score, 100), 1), {"modules": len(present), "banned_hard": hard, "banned_soft": soft, "length_ok": length_ok}


def a2a_event(product, modules, platform):
    full = "\n".join(modules.values())
    hard, soft = check_banned(full)
    return {
        "event": "detail_page.ready",
        "version": "2.0.0",
        "source": "ecom-detail-copy",
        "payload": {
            "product": product.get("title", product.get("name", "")),
            "platform": platform,
            "modules": list(modules.keys()),
            "banned_free": not hard,
            "banned_hard": hard,
        },
    }


def profile_path():
    return os.path.join(SKILL_DIR, "assets", "product-profile.json")


def load_profile():
    p = profile_path()
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return {"products": {}, "used_count": 0, "tone_pref": {}, "category_pref": {}}


def save_profile(pf):
    with open(profile_path(), "w", encoding="utf-8") as f:
        json.dump(pf, f, ensure_ascii=False, indent=2)


def evolve_profile(product, platform):
    pf = load_profile()
    pf["used_count"] = pf.get("used_count", 0) + 1
    c = product.get("category", "其他")
    pf["category_pref"][c] = pf["category_pref"].get(c, 0) + 1
    pf["tone_pref"][platform] = pf["tone_pref"].get(platform, 0) + 1
    title = product.get("title", product.get("name", ""))
    pf["products"][title] = pf["products"].get(title, 0) + 1
    save_profile(pf)
    return pf


def cmd_generate(args):
    product = _load_product(args.product)
    platform = product.get("platform", "taobao")
    modules, points = build_modules(product)
    pf = evolve_profile(product, platform)
    evt = a2a_event(product, modules, platform)
    out = {
        "product": product.get("title", product.get("name", "")),
        "platform": platform,
        "selling_points": [{"label": l, "text": t} for l, t in points],
        "modules": modules,
        "score": score_copy(modules)[0],
        "profile_used_count": pf["used_count"],
        "a2a_event": evt,
        "signature": GENERATED_BY_STAMP,
    }
    rendered = "\n".join(f"【{m}】\n{modules[m]}" for m in MODULE_ORDER if modules.get(m))
    rendered = rendered + "\n" + GENERATED_BY_STAMP
    out["rendered"] = rendered
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_score(args):
    modules = _load_product(args.copy) if args.copy else {}
    if not modules and args.text:
        modules = {"核心卖点": args.text}
    s, detail = score_copy(modules)
    print(json.dumps({"score": s, "detail": detail}, ensure_ascii=False, indent=2))


def cmd_check(args):
    hard, soft = check_banned(args.text)
    print(json.dumps({"banned_hard": hard, "banned_soft": soft, "clean": not hard}, ensure_ascii=False, indent=2))


def cmd_profile(args):
    pf = load_profile()
    print(json.dumps(pf, ensure_ascii=False, indent=2))


# ---------- 自检 ----------
def selftest():
    ok, total = 0, 0
    def chk(name, cond):
        nonlocal ok, total
        total += 1
        ok += 1 if cond else 0
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")

    demo = {"title": "纯棉宽松短袖T恤", "category": "服饰", "platform": "taobao",
            "attrs": {"材质": "纯棉", "版型": "宽松"}, "keywords": ["透气", "亲肤"], "scene": "夏天通勤"}
    modules, points = build_modules(demo)
    chk("用例1 七模块齐备", all(modules.get(m) for m in MODULE_ORDER))
    chk("用例2 卖点提取命中(纯棉→材质)", any("材质" in l for l, _ in points))
    full = "\n".join(modules.values())
    hard, _ = check_banned(full)
    chk("用例3 默认文案无硬违禁词", not hard)
    # 平台语气差异
    d_dy = build_modules({**demo, "platform": "douyin"})[0]
    d_tb = build_modules({**demo, "platform": "taobao"})[0]
    chk("用例4 抖音语气含emoji/淘宝无", ("🔥" in d_dy["逼单话术"]) and ("🔥" not in d_tb["逼单话术"]))
    # 违禁检测
    h, _ = check_banned("本产品是行业第一，100%有效")
    chk("用例5 违禁词识别(第一/100%)", "第一" in h and "100%" in h)
    # 深度感知演化
    p0 = load_profile()["used_count"]
    evolve_profile(demo, "taobao")
    p1 = load_profile()["used_count"]
    chk("用例6 档案二次演化(used_count+1)", p1 == p0 + 1)
    # A2A 结构
    evt = a2a_event(demo, modules, "taobao")
    chk("用例7 A2A事件含version2.0与banned_free", evt["version"] == "2.0.0" and "banned_free" in evt["payload"])
    # 评分边界
    s_low, _ = score_copy({"核心卖点": "短"})
    s_full, _ = score_copy(modules)
    chk("用例8 完整文案评分>残缺文案", s_full > s_low)
    # 清理档案保持交付干净
    try:
        os.remove(profile_path())
    except Exception:
        pass
    print(f"\n详情页文案工厂 selftest: {ok}/{total} PASS")
    return ok == total


def main():
    ap = argparse.ArgumentParser(description="详情页文案工厂 v2.0.0")
    sub = ap.add_subparsers(dest="cmd")
    g = sub.add_parser("generate"); g.add_argument("--product", required=True); g.set_defaults(func=cmd_generate)
    s = sub.add_parser("score"); s.add_argument("--copy", default=None); s.add_argument("--text", default=None); s.set_defaults(func=cmd_score)
    c = sub.add_parser("check"); c.add_argument("--text", required=True); c.set_defaults(func=cmd_check)
    p = sub.add_parser("profile"); p.set_defaults(func=cmd_profile)
    st = sub.add_parser("selftest"); st.set_defaults(func=lambda a: selftest())
    args = ap.parse_args()
    if not args.cmd:
        ap.print_help(); sys.exit(1)
    ok = args.func(args)
    if args.cmd == "selftest":
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

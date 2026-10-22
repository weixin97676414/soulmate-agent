#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标签自动避让（复刻 xhs_style.py 的 LABEL_JS 公式，保证与浏览器一致）。

两种 label 尺寸（浏览器实测，2x 截图下的 CSS px）:
  - kind='map'（总图 .lbl）: font 17px + small 11.5px, padding 2px 9px, h≈72
  - kind='spot'（每日图 .spot）: font 19px + small 12.5px, padding 4px 16px, h≈72
  - kind='trans'（交通胶囊）: font 16px, padding 1px 10px, h≈32

中文宽度估算（与浏览器实测误差 <6px）: 全角=fs, 半角=fs*0.55。

用法:
  生成布局: autolayout.py --task layout.json --out placed.json
  仅质检:   autolayout.py --check placed_spec.json [--kind spot]
"""
import argparse, json

# ---------- 文本度量 ----------
def text_w(s, fs):
    """估算单行文本像素宽：全角=fs，半角=fs*0.55。"""
    w = 0.0
    for ch in s:
        if ch in ' \t':
            w += fs * 0.5
        elif ord(ch) > 0x2E80:  # CJK / 全角
            w += fs
        else:
            w += fs * 0.55
    return w

KINDS = {
    'map':   dict(fs=17.0, sfs=11.5, padx=9,  pady=2,  h=72.0),   # 总图 .lbl（实测）
    'spot':  dict(fs=19.0, sfs=12.5, padx=16, pady=4,  h=55.0),   # 每日图 .spot（实测）
    'trans': dict(fs=16.0, sfs=0,    padx=10, pady=1,  h=28.0),   # 交通胶囊 .trans（实测）
}

def box_of(kind, x, y, pos, dx, dy, name, desc=''):
    """复刻 LABEL_JS: pos b下 t上 l左 r右；返回 (l,t,r,b) 包围盒。"""
    k = KINDS[kind]
    w = max(text_w(name, k['fs']), text_w(desc, k['sfs']) if desc else 0) + 2 * k['padx']
    h = k['h']
    if pos == 'b':
        lx, ly = x - w / 2, y + 26
    elif pos == 't':
        lx, ly = x - w / 2, y - h - 26
    elif pos == 'l':
        lx, ly = x - w - 24, y - h / 2
    else:  # r
        lx, ly = x + 24, y - h / 2
    return (lx + dx, ly + dy, lx + dx + w, ly + dy + h)

def overlaps(a, b, ox=4, oy=4):
    """与浏览器判定一致：x/y 重叠都 > 阈值才算撞。"""
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    return ix > ox and iy > oy

# ---------- 布局 ----------
def default_pos(x, y, map_w, map_h):
    """按四象限选默认 pos：靠近哪边就把标签放哪边，减少出界。"""
    if x < map_w * 0.4:
        return 'r'
    if x > map_w * 0.6:
        return 'l'
    if y < map_h * 0.4:
        return 'b'
    return 't'

_POS_ORDER = ['b', 't', 'l', 'r']

def layout(kind, spots, map_w, map_h, occupied=(), max_nudge=24, step=6):
    """贪心避让。每个 spot 依次尝试 pos 顺序 + dx/dy 微调，选第一个不重叠且在界内的。
    返回 (placed_spots, unresolved)。unresolved 交 AI 兜底。"""
    placed_boxes = [tuple(r) for r in occupied]
    placed = []
    unresolved = []
    k = KINDS[kind]
    for s in spots:
        name = s['name']; desc = s.get('desc', '')
        x, y = s['x'], s['y']
        pref = s.get('pos') or default_pos(x, y, map_w, map_h)
        pos_order = [pref] + [p for p in _POS_ORDER if p != pref]
        cands = [(0, 0)]
        for rng in range(step, max_nudge + 1, step):
            cands += [(rng, 0), (-rng, 0), (0, rng), (0, -rng)]
        chosen = None  # (pos, dx, dy) 不碰撞候选
        fallback = None; fallback_score = None  # 全碰撞时选重叠最小
        for pos in pos_order:
            for dx, dy in cands:
                b = box_of(kind, x, y, pos, dx, dy, name, desc)
                if b[0] < 0 or b[1] < 0 or b[2] > map_w or b[3] > map_h:
                    continue
                score = 0; collide = False
                for pb in placed_boxes:
                    if overlaps(b, pb):
                        collide = True
                        score += (min(b[2], pb[2]) - max(b[0], pb[0])) * (min(b[3], pb[3]) - max(b[1], pb[1]))
                if not collide:
                    chosen = (pos, dx, dy)
                    break
                if fallback_score is None or score < fallback_score:
                    fallback_score = score
                    fallback = (pos, dx, dy)
            if chosen:
                break
        if chosen is None:
            chosen = fallback if fallback is not None else ('b', 0, 0)
            if fallback is None:
                unresolved.append(name)
        out = dict(s)
        out['pos'] = chosen[0]; out['dx'] = chosen[1]; out['dy'] = chosen[2]
        placed_boxes.append(box_of(kind, x, y, chosen[0], chosen[1], chosen[2], name, desc))
        placed.append(out)
    return placed, unresolved

def trans_box(x, y, text):
    """交通胶囊 .trans 是 left:x 左锚定（非居中），宽=文本+2*padx，高=28。"""
    w = text_w(text, KINDS['trans']['fs']) + 2 * KINDS['trans']['padx']
    return (x, y, x + w, y + KINDS['trans']['h'])


def layout_trans(transits, map_w, map_h, occupied=(), max_nudge=24, step=6):
    """交通胶囊避让：左锚定 box，直接输出最终 (x,y)。occupied 通常=景点标签框+Tips。"""
    placed_boxes = [tuple(r) for r in occupied]
    placed = []
    unresolved = []
    cands = [(0, 0)]
    for rng in range(step, max_nudge + 1, step):
        cands += [(rng, 0), (-rng, 0), (0, rng), (0, -rng)]
    for t in transits:
        x, y = t['x'], t['y']
        chosen = None; fallback = None; fallback_score = None
        for dx, dy in cands:
            b = trans_box(x + dx, y + dy, t['text'])
            if b[0] < 0 or b[1] < 0 or b[2] > map_w or b[3] > map_h:
                continue
            score = 0; collide = False
            for pb in placed_boxes:
                if overlaps(b, pb):
                    collide = True
                    score += (min(b[2], pb[2]) - max(b[0], pb[0])) * (min(b[3], pb[3]) - max(b[1], pb[1]))
            if not collide:
                chosen = (dx, dy); break
            if fallback_score is None or score < fallback_score:
                fallback_score = score; fallback = (dx, dy)
        if chosen is None:
            chosen = fallback if fallback is not None else (0, 0)
            if fallback is None:
                unresolved.append(t.get('text', '?'))
        out = dict(t)
        out['x'] = x + chosen[0]; out['y'] = y + chosen[1]
        placed_boxes.append(trans_box(out['x'], out['y'], t['text']))
        placed.append(out)
    return placed, unresolved


def check(kind, spots, map_w, map_h, occupied=()):
    """质检：返回重叠对列表 [(nameA, nameB)]。"""
    boxes = []
    for s in spots:
        boxes.append((s.get('name', '?'), box_of(kind, s['x'], s['y'], s.get('pos', 'b'),
                                                 s.get('dx', 0), s.get('dy', 0),
                                                 s.get('name', ''), s.get('desc', ''))))
    hits = []
    allb = boxes + [('__occupied%d' % i, tuple(r)) for i, r in enumerate(occupied)]
    for i in range(len(allb)):
        for j in range(i + 1, len(allb)):
            n1, b1 = allb[i]; n2, b2 = allb[j]
            if overlaps(b1, b2):
                hits.append((n1, n2))
    return hits

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', help='布局任务 JSON')
    ap.add_argument('--out', help='输出 JSON')
    ap.add_argument('--check', help='质检已有 spec JSON')
    ap.add_argument('--kind', default='spot', choices=['map', 'spot', 'trans'])
    a = ap.parse_args()
    if a.check:
        spec = json.load(open(a.check))
        kind = a.kind
        hits = check(kind, spec['spots'], spec.get('map_w', 1536), spec.get('map_h', 1024),
                     spec.get('occupied', ()))
        print(json.dumps({"overlaps": hits}, ensure_ascii=False, indent=1))
        return
    task = json.load(open(a.task))
    kind = a.kind
    placed, unresolved = layout(kind, task['spots'], task['map_w'], task['map_h'],
                                occupied=task.get('occupied', ()))
    out = dict(task)
    out['spots'] = placed
    out['unresolved'] = unresolved
    if a.out:
        json.dump(out, open(a.out, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({"unresolved": unresolved}, ensure_ascii=False, indent=1))

if __name__ == '__main__':
    main()

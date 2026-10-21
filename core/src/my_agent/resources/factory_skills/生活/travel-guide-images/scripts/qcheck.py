#!/usr/bin/env python3
# -*- coding: utf-8 -*-












import argparse, json, glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autolayout
from autolayout import check as layout_check

BLANK_RATIO = 0.98


def sample_stats(png):
    import numpy as np
    from PIL import Image
    im = Image.open(png).convert('RGB')
    w, h = im.size
    im = im.resize((256, 256))
    a = np.asarray(im, dtype=np.uint16).reshape(-1, 3)
    
    q = (a // 16) * 16
    vals, counts = np.unique(q, axis=0, return_counts=True)
    top = float(counts.max() / len(q))
    return w, h, top, tuple(int(v) for v in a[0])


def qc_spec(path):

    issues = []
    spec = json.load(open(path))
    mw, mh = spec.get('map_w', 0), spec.get('map_h', 0)
    if spec.get('kind') == 'map':
        k = 'map'
    elif 'route' in spec:  
        k = 'spot'
    else:
        return []
    occupied = []
    if spec.get('tips'):
        t = spec['tips']
        occupied.append((t['x'], t['y'], t['x'] + t['w'], t['y'] + 130))
    hits = layout_check(k, spec.get('spots', []), mw, mh, occupied=occupied)
    for a, b in hits:
        if b.startswith('__occupied'):
            issues.append(('overlap', f'{os.path.basename(path)}: 标签「{a}」与 Tips 框重叠'))
        else:
            issues.append(('overlap', f'{os.path.basename(path)}: 标签「{a}」与「{b}」重叠'))
    
    spots = spec.get('spots', [])
    boxes = [autolayout.box_of(k, s['x'], s['y'], s.get('pos', 'b'), s.get('dx', 0), s.get('dy', 0),
                               s.get('name', ''), s.get('desc', '')) for s in spots]
    for t in spec.get('transits', []):
        tb = autolayout.trans_box(t['x'], t['y'], t['text'])
        for s, b in zip(spots, boxes):
            if autolayout.overlaps(b, tb):
                issues.append(('overlap', f'{os.path.basename(path)}: 交通「{t["text"]}」与标签「{s["name"]}」重叠'))
    return issues


def qc_img(path):
    issues = []
    try:
        w, h, top_ratio, _ = sample_stats(path)
    except Exception as e:
        return [('blank', f'{os.path.basename(path)}: 无法读取 ({e})')]
    if w < 100 or h < 100:
        issues.append(('size', f'{os.path.basename(path)}: 尺寸异常 {w}x{h}'))
    if top_ratio > BLANK_RATIO:
        issues.append(('blank', f'{os.path.basename(path)}: 疑似空白/白屏（{top_ratio:.0%} 像素同色）'))
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', help='攻略输出目录（自动发现 spec/png/docx）')
    ap.add_argument('--specs', nargs='*')
    ap.add_argument('--imgs', nargs='*')
    ap.add_argument('--docx')
    ap.add_argument('--min-docx-kb', type=int, default=300)
    a = ap.parse_args()
    specs, imgs, docx = a.specs or [], a.imgs or [], [a.docx] if a.docx else []
    if a.out:
        d = a.out
        specs += sorted(glob.glob(os.path.join(d, '*_spec.json')))
        imgs += sorted(glob.glob(os.path.join(d, '*.png'))) + sorted(glob.glob(os.path.join(d, 'daymaps', '*.png')))
        docx += sorted(glob.glob(os.path.join(d, '*.docx')))
    issues = []
    for s in specs:
        issues += qc_spec(s)
    for i in imgs:
        issues += qc_img(i)
    for f in docx:
        kb = os.path.getsize(f) // 1024
        if kb < a.min_docx_kb:
            issues.append(('size', f'{os.path.basename(f)}: docx 仅 {kb}KB（<{a.min_docx_kb}KB，疑似缺图）'))
    if not issues:
        print('QC PASS ✅ 无重叠 / 无空白 / 尺寸正常')
        return 0
    for tag, msg in issues:
        print(f'[{tag}] {msg}')
    print(f'QC FAIL ⚠ {len(issues)} 项待处理')
    return 1


if __name__ == '__main__':
    sys.exit(main())

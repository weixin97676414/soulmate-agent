#!/usr/bin/env python3
# -*- coding: utf-8 -*-






import sys
import numpy as np
from PIL import Image


def to_jpg(src, dst, quality=84):
    Image.open(src).convert('RGB').save(dst, 'JPEG', quality=quality)


def hex2rgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i+2], 16) for i in (0, 2, 4)])


def trim_bottom(path, bg='#FFF6EE', margin=60):
    im = Image.open(path)
    a = np.array(im.convert('RGB'))
    bgc = hex2rgb(bg)
    mask = (np.abs(a.astype(int) - bgc).sum(axis=2) > 40)
    rows = mask.any(axis=1)
    last = np.where(rows)[0].max() if rows.any() else a.shape[0] - 1
    im.crop((0, 0, im.width, min(im.height, last + margin))).save(path)
    print(f'trimmed to {im.width}x{min(im.height, last + margin)}')


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'to-jpg':
        to_jpg(sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 84)
        print('saved', sys.argv[3])
    elif cmd == 'trim-bottom':
        kw = {}
        for i in range(3, len(sys.argv) - 1, 2):
            k, v = sys.argv[i], sys.argv[i + 1]
            if k == '--bg': kw['bg'] = v
            if k == '--margin': kw['margin'] = int(v)
        trim_bottom(sys.argv[2], **kw)

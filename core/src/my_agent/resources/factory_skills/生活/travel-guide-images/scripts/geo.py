#!/usr/bin/env python3
# -*- coding: utf-8 -*-










import argparse, json, math


def lonlat_to_tile(lon, lat, z):
    x = (lon + 180) / 360 * (1 << z)
    phi = math.radians(lat)
    y = (1 - math.log(math.tan(phi) + 1 / math.cos(phi)) / math.pi) / 2 * (1 << z)
    return x, y


def to_pixels(lon, lat, meta):
    z = meta['zoom']
    xf, yf = lonlat_to_tile(lon, lat, z)
    return [round((xf - meta['tile_x0']) * 256, 1), round((yf - meta['tile_y0']) * 256, 1)]


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--meta', required=True)
    ap.add_argument('--spots', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    meta = json.load(open(a.meta))
    spots = json.load(open(a.spots))
    out = {name: to_pixels(lon, lat, meta) for name, (lon, lat) in spots.items()}
    json.dump(out, open(a.out, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False))

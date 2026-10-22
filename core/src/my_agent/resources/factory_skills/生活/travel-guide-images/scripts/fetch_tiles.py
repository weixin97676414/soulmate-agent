#!/usr/bin/env python3
# -*- coding: utf-8 -*-


















import argparse, json, math, os, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

HOSTS = ['webst02', 'webst03', 'webst04']
UA = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://ditu.amap.com/'}


def lonlat_to_tile(lon, lat, z):
    x = (lon + 180) / 360 * (1 << z)
    phi = math.radians(lat)
    y = (1 - math.log(math.tan(phi) + 1 / math.cos(phi)) / math.pi) / 2 * (1 << z)
    return x, y


def fetch_tile(style, tx, ty, z, cache_dir):
    ext = 'jpg' if style == 7 else 'png'
    fn = os.path.join(cache_dir, f'{z}s{style}', f'{tx}_{ty}.{ext}')
    if os.path.exists(fn):
        return fn
    os.makedirs(os.path.dirname(fn), exist_ok=True)
    for attempt in range(5):
        host = HOSTS[attempt % len(HOSTS)]
        try:
            url = f'https://{host}.is.autonavi.com/appmaptile?style={style}&x={tx}&y={ty}&z={z}'
            req = urllib.request.Request(url, headers=UA)
            d = urllib.request.urlopen(req, timeout=15).read()
            if len(d) < 200:  
                raise ValueError('tile too small')
            open(fn, 'wb').write(d)
            return fn
        except Exception:
            time.sleep(0.4 * (attempt + 1))
    return None


def stitch(lon0, lat0, lon1, lat1, z, out_path, cache_dir):
    from PIL import Image
    
    x0f, y0f = lonlat_to_tile(lon0, lat1, z)
    x1f, y1f = lonlat_to_tile(lon1, lat0, z)
    x0, y0, x1, y1 = int(x0f), int(y0f), int(x1f), int(y1f)
    W, H = (x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256
    
    jobs = [(s, tx, ty) for s in (7, 8)
            for tx in range(x0, x1 + 1) for ty in range(y0, y1 + 1)]
    results = {}
    def work(j):
        s, tx, ty = j
        return j, fetch_tile(s, tx, ty, z, cache_dir)
    with ThreadPoolExecutor(max_workers=6) as ex:
        for j, fn in ex.map(work, jobs):
            results[j] = fn
    base = Image.new('RGB', (W, H), (235, 235, 230))
    label = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    fails = 0
    for tx in range(x0, x1 + 1):
        for ty in range(y0, y1 + 1):
            f7 = results.get((7, tx, ty))
            if f7:
                base.paste(Image.open(f7).convert('RGB'), ((tx - x0) * 256, (ty - y0) * 256))
            else:
                fails += 1
            f8 = results.get((8, tx, ty))
            if f8:
                im8 = Image.open(f8).convert('RGBA')
                label.paste(im8, ((tx - x0) * 256, (ty - y0) * 256), im8)
    out = Image.alpha_composite(base.convert('RGBA'), label).convert('RGB')
    out.save(out_path)
    return {'zoom': z, 'tile_x0': x0, 'tile_y0': y0, 'width': W, 'height': H,
            'tile_x0f': x0f, 'tile_y0f': y0f, 'fails': fails}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--bbox', required=True, help='lon_min,lat_min,lon_max,lat_max')
    ap.add_argument('--zoom', type=int, required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--meta', default=None)
    ap.add_argument('--cache', default='/tmp/amap_tile_cache')
    a = ap.parse_args()
    lon0, lat0, lon1, lat1 = [float(v) for v in a.bbox.split(',')]
    meta = stitch(lon0, lat0, lon1, lat1, a.zoom, a.out, a.cache)
    if a.meta:
        json.dump(meta, open(a.meta, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False))

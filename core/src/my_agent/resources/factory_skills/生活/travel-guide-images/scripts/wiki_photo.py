#!/usr/bin/env python3
# -*- coding: utf-8 -*-












import argparse, json, os, sys, time, urllib.parse, urllib.request

UA = {'User-Agent': 'TravelGuideBot/1.0 (personal travel guide generation)'}
API = 'https://commons.wikimedia.org/w/api.php'


def search_thumb(query, width=640):
    params = {'action': 'query', 'generator': 'search', 'gsrsearch': query,
              'gsrnamespace': 6, 'gsrlimit': 6, 'prop': 'imageinfo',
              'iiprop': 'url|mime', 'iiurlwidth': width, 'format': 'json'}
    url = API + '?' + urllib.parse.urlencode(params)
    data = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read())
    for p in data.get('query', {}).get('pages', {}).values():
        info = (p.get('imageinfo') or [{}])[0]
        if info.get('mime', '').startswith('image/jpeg'):
            return p['title'], info.get('thumburl') or info.get('url')
    return None, None


def download(query, out, retries=3):
    title, thumb = search_thumb(query)
    if not thumb:
        print(f'NOTFOUND {query}')
        return False
    for i in range(retries):
        try:
            d = urllib.request.urlopen(urllib.request.Request(thumb, headers=UA), timeout=25).read()
            open(out, 'wb').write(d)
            print(f'OK {query} -> {out} ({len(d)//1024}KB) [{title}]')
            return True
        except Exception as e:
            print(f'retry {query}: {str(e)[:60]}')
            time.sleep(4 * (i + 1))
    return False


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('query', nargs='?')
    ap.add_argument('out', nargs='?')
    ap.add_argument('--batch', help='JSON: {"key": "search query", ...}')
    ap.add_argument('--dir', default='.')
    a = ap.parse_args()
    if a.batch:
        os.makedirs(a.dir, exist_ok=True)
        for k, q in json.load(open(a.batch)).items():
            download(q, os.path.join(a.dir, f'{k}.jpg'))
            time.sleep(1.5)
    else:
        sys.exit(0 if download(a.query, a.out) else 1)

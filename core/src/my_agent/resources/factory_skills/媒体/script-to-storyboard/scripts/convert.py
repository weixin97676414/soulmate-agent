#!/usr/bin/env python3
# -*- coding: utf-8 -*-


















import argparse
import csv
import json
import re
import sys


try:
    if sys.stdout.encoding and sys.stdout.encoding.lower().replace('-', '') not in ('utf8',):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


SHOT_TYPES = {
    '大特写': '大特写', '特写': '特写', '近景': '近景', '中近景': '中近景',
    '中景': '中景', '全景': '全景', '远景': '远景', '半身景': '中景',
}

ANGLE_TYPES = {
    '鸟瞰': '俯拍', '俯视': '俯拍', '俯拍': '俯拍', '顶拍': '俯拍',
    '仰视': '仰拍', '仰拍': '仰拍', '蚂蚁视角': '仰拍',
    '平视': '平拍', '平拍': '平拍',
    '斜拍': '斜拍', '侧拍': '侧拍', '过肩': '过肩', '航拍': '航拍',
}

CAMERA_MOVES = {
    '推镜头': '推镜头', '推镜': '推镜头', '推近': '推镜头', '推进': '推镜头',
    '拉镜头': '拉镜头', '拉远': '拉镜头', '拉镜': '拉镜头',
    '摇镜头': '摇镜头', '摇摄': '摇镜头',
    '跟镜头': '跟镜头', '跟拍': '跟镜头', '跟随': '跟镜头',
    '甩镜头': '甩镜头', '甩镜': '甩镜头',
    '移镜头': '移镜头', '横移': '移镜头', '平移': '移镜头',
    '升降': '升降', '环绕': '环绕', '俯冲': '俯冲', '穿梭': '穿梭',
    '慢镜头': '慢镜', '慢镜': '慢镜', '慢动作': '慢镜',
    '定格': '定格', '固定机位': '固定',
}

CAMERA_MOVES_SINGLE = [
    (r'推(?!开|动|门|倒|广|荐|测|理)', '推镜头'),
    (r'拉(?!开|动|门|上|下|手|扯|伸)', '拉镜头'),
    (r'摇(?!头|摆|晃|篮)', '摇镜头'),
    (r'跟(?!着|前|后|班)', '跟镜头'),
]


META_HEADING_KEYWORDS = (
    '概述', '简介', '说明', '总览', '摘要', '背景',
    '人物', '角色', '服装', '造型', '设定', '人设',
    '道具', '风格', '色调', '光影', '美术', '参考',
    '注意', '备注', '附录', '要求', '规范', '术语',
)


GENERIC_CHARS = {'有人', '无人', '每人', '某人', '个人', '人物', '人影', '人声', '人流'}

CHAR_STOPWORDS = ('照亮', '面对', '出现', '经过', '变成', '成为', '吸引', '没有',
                  '所有', '很多', '许多', '周围', '旁边', '附近', '以及', '然后')

CHAR_MAX_LEN = 8


SOUND_RULES = [
    (('海', '沙滩', '海岸', '浪', '潮'), '海浪声、背景音乐'),
    (('烟花', '爆竹', '爆炸'), '烟花爆炸声、背景音乐'),
    (('篝火', '火焰', '燃烧', '柴'), '木柴燃烧噼啪声、背景音乐'),
    (('鼓', '乐', '演奏', '弹', '唱', '舞蹈', '跳舞'), '鼓乐节奏、欢呼声'),
    (('雨',), '雨声、环境音'),
    (('风', '雪'), '风声、环境音'),
    (('街道', '城市', '车', '人群'), '城市环境音、背景音乐'),
    (('室内', '房间', '办公室', '教室'), '室内环境音、背景音乐'),
    (('森林', '山', '林'), '鸟鸣、风声、环境音'),
]


def _sorted_items(mapping):
    return sorted(mapping.items(), key=lambda kv: -len(kv[0]))



HEADING_RE = re.compile(r'^(#{1,6})\s*(.+?)\s*$')
HR_RE = re.compile(r'^\s*([-*_])\s*\1\s*\1[\s\-*_]*$')


def read_text(path):
    for enc in ('utf-8', 'utf-8-sig', 'gbk'):
        try:
            with open(path, 'r', encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    raise SystemExit('错误: 无法解码文件（已尝试 utf-8 / gbk）: %s' % path)


def clean_line(line):

    s = line.strip()
    s = re.sub(r'^\s*[-*+]\s+', '', s)          
    s = re.sub(r'^\s*\d+[.、]\s*', '', s)        
    s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)       
    s = re.sub(r'\*(.+?)\*', r'\1', s)           
    s = re.sub(r'`(.+?)`', r'\1', s)             
    s = re.sub(r'^\s*>+\s?', '', s)              
    return s.strip()


def split_blocks(text):

    blocks, cur = [], None
    for raw in text.split('\n'):
        line = raw.rstrip()
        if not line.strip():
            continue
        if HR_RE.match(line):
            continue
        m = HEADING_RE.match(line)
        if m:
            if cur and (cur['body'] or cur['title']):
                blocks.append(cur)
            title = m.group(2).strip()
            cur = {
                'level': len(m.group(1)),
                'title': title,
                'body': [],
                'meta': any(k in title for k in META_HEADING_KEYWORDS),
            }
            continue
        if cur is None:
            cur = {'level': 0, 'title': '', 'body': [], 'meta': False}
        c = clean_line(line)
        if c:
            cur['body'].append(c)
    if cur and (cur['body'] or cur['title']):
        blocks.append(cur)
    return blocks


SCENE_TITLE_RE = re.compile(
    r'^(?:场景\s*\d+|场次\s*\d+|第[一二三四五六七八九十百千万\d]+\s*[场幕镜]|\d+\s*[.、:：])'
)


def is_meta_block(b):



    if SCENE_TITLE_RE.match(b['title']):
        return False
    return b['meta'] or not b['body']


SHOT_SPLIT_RE = re.compile(r'(?:^|\s)(?:镜头|镜|Shot|shot)\s*(\d+)\s*[:：]?')


def split_shots(block):

    body = block['body']
    marks = [i for i, line in enumerate(body) if SHOT_SPLIT_RE.search(line)]
    if len(marks) >= 2:
        segs, start = [], marks[0]
        for m in marks[1:]:
            segs.append(body[start:m])
            start = m
        segs.append(body[start:])
        return [s for s in segs if s]
    return [body]



def detect(text, table):
    for kw, val in _sorted_items(table):
        if kw in text:
            return val
    return ''


def detect_camera(text):
    for kw, val in _sorted_items(CAMERA_MOVES):
        if kw in text:
            return val
    for pat, val in CAMERA_MOVES_SINGLE:
        if re.search(pat, text):
            return val
    return ''


GROUP_CHAR_RE = re.compile(
    
    r'((?:[0-9零一两三四五六七八九十百千万]+\s*多?\s*)?(?:名|个|位)?'
    r'[一-龥]{1,6}(?:人|者|师|员|众|兵|童|们))'
)

OVERVIEW_KEYWORDS = ('概述', '简介', '背景', '摘要', '总览', '梗概')
ALL_CHAR_RE = re.compile(r'(全体[一-龥]{1,8}|众人|群众)')
BRACKET_CHAR_RE = re.compile(r'【([^】]{1,20})】')
LINE_CHAR_RE = re.compile(r'^\s*([一-龥A-Za-z·]{1,8})\s*[：:]\s*\S')


def _collect(x, found):

    x = (x or '').strip()
    if not x or x in GENERIC_CHARS:
        return found
    if any(w in x for w in CHAR_STOPWORDS):
        return found
    if len(re.findall(r'[一-龥]', x)) > CHAR_MAX_LEN:
        return found
    if x not in found:
        found.append(x)
    return found


def extract_characters(text, manual=None):
    if manual:
        return [c.strip() for c in re.split(r'[,，、;；]', manual) if c.strip()]

    found = []
    add = lambda x: _collect(x, found)

    for m in BRACKET_CHAR_RE.finditer(text):
        add(m.group(1))
    for line in text.split('\n'):
        if INSTR_LINE_RE.match(line):   
            continue
        m = LINE_CHAR_RE.match(line)
        if m:
            add(m.group(1))
    for m in ALL_CHAR_RE.finditer(text):
        add(m.group(1))
    for m in GROUP_CHAR_RE.finditer(text):
        add(m.group(1))

    return found[:4]


CHAR_BLOCK_KEYWORDS = ('人物', '角色', '人设', '演员', '出场')

CHAR_BLOCK_EXCLUDE = ('服装', '造型', '道具', '细节', '外观', '服饰', '美术', '风格', '色调')


def global_characters(blocks):




    named, groups, shot_groups = [], [], []
    for b in blocks:
        body = '\n'.join(b['body'])
        if any(k in b['title'] for k in CHAR_BLOCK_KEYWORDS) \
                and not any(x in b['title'] for x in CHAR_BLOCK_EXCLUDE):
            for ln in b['body']:
                m = LINE_CHAR_RE.match(ln)
                if m:
                    _collect(m.group(1), named)
            continue
        if not is_meta_block(b):
            for x in GROUP_CHAR_RE.findall(body):
                _collect(x, shot_groups)
            continue
        if any(k in b['title'] for k in OVERVIEW_KEYWORDS):
            for x in GROUP_CHAR_RE.findall(body):
                _collect(x, groups)
    
    if not groups:
        groups = shot_groups
    out = named[:3]
    for g in groups:
        _collect(g, out)
    return out[:3]


def infer_sound(text):
    m = re.search(r'(?:音效|音乐|声音|配乐|声效)\s*[：:]\s*(.+)', text)
    if m:
        return m.group(1).strip()
    for keys, val in SOUND_RULES:
        if any(k in text for k in keys):
            return val
    return '背景音乐'


def scene_name(block):

    t = block['title']
    t = re.sub(r'^场景\s*\d+\s*[:：]?\s*', '', t)
    t = re.sub(r'^\d+\s*[.、]\s*', '', t)
    t = t.strip()
    if not t and block['body']:
        t = block['body'][0][:12]
    return t or '未标注'



INSTR_LINE_RE = re.compile(r'^\s*(?:音效|音乐|声音|配乐|声效|时长|duration)\s*[：:]', re.I)

SHOT_MARK_PREFIX_RE = re.compile(r'^\s*(?:镜头|镜|Shot|shot)\s*\d*\s*[：:，,]?\s*', re.I)


def strip_lead_shotwords(s):

    words = [k for k, _ in _sorted_items(SHOT_TYPES)] + [k for k, _ in _sorted_items(ANGLE_TYPES)]
    changed = True
    while changed:
        changed = False
        for kw in words:
            m = re.match(r'^%s\s*[，,、。；;]?\s*' % re.escape(kw), s)
            if m and len(s) > m.end():
                s = s[m.end():]
                changed = True
                break
    return s


def build_shots(blocks, default_duration=5, manual_chars=None):
    shots = []
    for b in blocks:
        if is_meta_block(b):
            continue
        scene = scene_name(b)
        for seg in split_shots(b):
            if not seg:
                continue
            
            raw = '\n'.join(seg)
            duration = default_duration
            m = re.search(r'(?:时长|duration)\s*[：:]?\s*(\d+(?:\.\d+)?)\s*(?:s|秒)?', raw, re.I)
            if m:
                duration = float(m.group(1))
                if duration.is_integer():
                    duration = int(duration)
            sound = infer_sound(raw)
            chars = extract_characters(raw, manual_chars)

            lines = [ln for ln in seg if not INSTR_LINE_RE.match(ln)]
            lines = [SHOT_MARK_PREFIX_RE.sub('', ln).strip() for ln in lines]
            lines = [re.sub(r'^【[^】]{1,20}】\s*', '', ln) for ln in lines]  
            lines = [ln for ln in lines if ln]
            if not lines:
                continue
            lines[0] = strip_lead_shotwords(lines[0])
            content = ' '.join(lines).strip()
            if not content:
                continue

            
            head = b['title']
            full = ' '.join(seg)
            shot_type = detect(head, SHOT_TYPES) or detect(full, SHOT_TYPES)
            angle = detect(head, ANGLE_TYPES) or detect(full, ANGLE_TYPES)
            camera = detect_camera(head) or detect_camera(full)
            shots.append({
                'shot_type': shot_type,
                'angle': angle,
                'camera_move': camera,
                'content': content,
                'characters': chars,
                'scene': scene,
                'sound': sound,
                'duration': duration,
            })

    if not manual_chars:
        fallback = global_characters(blocks)
        for s in shots:
            if not s['characters']:
                s['characters'] = list(fallback)
    return shots


def enhance_shots(shots):
    for i, s in enumerate(shots):
        if not s.get('shot_type'):
            if i == 0:
                s['shot_type'] = '远景'
            elif i == len(shots) - 1:
                s['shot_type'] = '全景'
            else:
                s['shot_type'] = '中景'
        if not s.get('angle'):
            s['angle'] = '平拍'
        s['characters_str'] = '、'.join(s.get('characters') or []) or '无'
    return shots


def camera_str(s):
    parts = [s.get('shot_type', ''), s.get('angle', '')]
    if s.get('camera_move'):
        parts.append(s['camera_move'])
    return '/'.join(p for p in parts if p)



def _w(s):

    return sum(2 if ord(c) > 0x2E80 else 1 for c in str(s))


def _pad(s, width, align='<'):
    s = str(s)
    gap = max(0, width - _w(s))
    if align == '^':
        left = gap // 2
        return ' ' * left + s + ' ' * (gap - left)
    return s + ' ' * gap if align == '<' else ' ' * gap + s


def _clip(s, width):
    s = str(s)
    if _w(s) <= width:
        return s
    out, acc = '', 0
    for c in s:
        cw = _w(c)
        if acc + cw > width - 2:
            break
        out += c
        acc += cw
    return out + '..'


def print_storyboard(shots):
    cols = [('镜号', 6), ('景别/角度/运镜', 22), ('画面内容', 36), ('出场人物', 16), ('场景', 14), ('音效', 20), ('时长', 6)]
    line = '=' * (sum(w for _, w in cols) + 12)
    print('\n' + line)
    print(''.join(_pad(t, w, '^') for t, w in cols))
    print(line)
    for s in shots:
        row = [
            _pad(s['shot_number'], 6, '^'),
            _pad(_clip(camera_str(s), 22), 22),
            _pad(_clip(s['content'], 36), 36),
            _pad(_clip(s['characters_str'], 16), 16),
            _pad(_clip(s['scene'], 14), 14),
            _pad(_clip(s['sound'], 20), 20),
            _pad('%gs' % s['duration'], 6, '^'),
        ]
        print(''.join(row))
    print(line + '\n')


def write_csv(shots, path):
    fields = ['镜号', '景别/拍摄角度', '画面内容', '出场人物', '场景', '音效', '时长(秒)']
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for s in shots:
            w.writerow({
                '镜号': s['shot_number'],
                '景别/拍摄角度': camera_str(s),
                '画面内容': s['content'],
                '出场人物': s['characters_str'],
                '场景': s['scene'],
                '音效': s['sound'],
                '时长(秒)': s['duration'],
            })
    return path


def write_md(shots, path, title=''):
    lines = ['# %s' % (title or '分镜表'), '',
             '| 镜号 | 景别/拍摄角度 | 画面内容 | 出场人物 | 场景 | 音效 | 时长 |',
             '|------|--------------|----------|---------|------|------|------|']
    for s in shots:
        row = [s['shot_number'], camera_str(s), s['content'].replace('|', '/'),
               s['characters_str'], s['scene'], s['sound'], '%gs' % s['duration']]
        lines.append('| ' + ' | '.join(row) + ' |')
    text = '\n'.join(lines) + '\n'
    if path == '-':
        print(text)
        return '-'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return path


def write_platform_json(shots, path, title='分镜表', script_id='', schema='ui'):







    if schema == 'pipeline':
        board = {
            'title': title,
            'scriptId': script_id,
            'shots': [
                {
                    'no': s['shot_number'],
                    'scene': s['scene'],
                    'shotType': s.get('shot_type', ''),
                    'cam': '/'.join(p for p in [s.get('angle', ''), s.get('camera_move', '')] if p),
                    'desc': s['content'],
                    'line': '',
                    'dur': '%gs' % s['duration'],
                    'imgPrompt': '',
                }
                for s in shots
            ],
        }
    else:
        board = {
            'title': title,
            'scriptId': script_id,
            'shots': [
                {
                    'no': s['shot_number'],
                    'scene': s['scene'],
                    'action': s['content'],
                    'duration': s['duration'],
                    'camera': camera_str(s),
                    'artRef': '',
                    'promptRef': '',
                    'note': '出场人物：%s｜音效：%s' % (s['characters_str'], s['sound']),
                }
                for s in shots
            ],
        }
    text = json.dumps(board, ensure_ascii=False, indent=2)
    if path == '-':
        print(text)
        return '-'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    return path


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('input')
    ap.add_argument('output', nargs='?', default='storyboard.csv')
    ap.add_argument('--format', choices=['csv', 'md', 'json'], default='csv')
    ap.add_argument('--schema', choices=['ui', 'pipeline'], default='ui',
                    help='json 格式下镜头字段方案：ui=后台编辑器字段，pipeline=流水线生成字段')
    ap.add_argument('--duration', type=float, default=5)
    ap.add_argument('--title', default='')
    ap.add_argument('--scriptId', default='')
    ap.add_argument('--characters', default='')
    a = ap.parse_args()

    text = read_text(a.input)
    blocks = split_blocks(text)
    shots = build_shots(blocks, a.duration, a.characters or None)
    if not shots:
        print('警告: 未能从剧本中解析出镜头信息')
        print('请确保剧本包含分块标题（如「### 场景1：开篇」）或镜头指示（如：特写、远景、推镜头）')
        sys.exit(1)
    for i, s in enumerate(shots, 1):
        s['shot_number'] = '%02d' % i
    enhance_shots(shots)

    title = a.title or (blocks[0]['title'] if blocks and blocks[0]['level'] == 1 else '')
    title = re.sub(r'^示例剧本[:：]?\s*', '', title).strip() or '分镜表'

    print_storyboard(shots)

    if a.format == 'csv':
        out = write_csv(shots, a.output)
    elif a.format == 'md':
        out = write_md(shots, a.output, title)
    else:
        out = write_platform_json(shots, a.output, title, a.scriptId, a.schema)
    print('分镜脚本已保存到: %s（%d 个镜头）' % (out, len(shots)))


if __name__ == '__main__':
    main()

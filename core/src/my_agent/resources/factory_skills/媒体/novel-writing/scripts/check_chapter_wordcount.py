#!/usr/bin/env python3
# -*- coding: utf-8 -*-





import io
import re
import sys
from pathlib import Path

if sys.platform == 'win32':
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PLATFORM_PRESETS = {
    'tomato': (2200, 2800, '番茄小说'),
    'qimao': (2200, 2800, '七猫免费小说'),
    'qidian': (3000, 4500, '起点中文网'),
    'zongheng': (3000, 4000, '纵横中文网'),
    'jjwxc': (2500, 4000, '晋江文学城'),
    'feilu': (3000, 5000, '飞卢小说网'),
    'douban': (3000, 6000, '豆瓣阅读'),
    'zhihu': (8000, 15000, '知乎盐选/短篇'),
    'generic': (2500, 3500, '通用网文'),
}


def count_chinese_words(text: str) -> int:

    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'~~(.*?)~~', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    return len(chinese_chars)


def extract_content_from_chapter(file_path: Path) -> str:

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    content_start = 0
    for i, line in enumerate(lines):
        if line.startswith('#') and '章' in line:
            content_start = i + 1
            break

    return '\n'.join(lines[content_start:])


def check_chapter(file_path: str, min_words: int, max_words: int) -> dict:

    path = Path(file_path)
    if not path.exists():
        return {
            'file': str(path),
            'exists': False,
            'word_count': 0,
            'status': 'error',
            'message': f'文件不存在: {file_path}',
        }

    main_content = extract_content_from_chapter(path)
    word_count = count_chinese_words(main_content)

    if word_count < min_words:
        status = 'short'
        message = f'字数: {word_count} (✗ 不足，需要至少 {min_words} 字)'
    elif word_count > max_words:
        status = 'long'
        message = f'字数: {word_count} (⚠️ 超标，建议精简至 {max_words} 字以内)'
    else:
        status = 'pass'
        message = f'字数: {word_count} (✓ 最佳区间 {min_words}-{max_words} 字)'

    return {
        'file': str(path),
        'exists': True,
        'word_count': word_count,
        'status': status,
        'message': message,
    }


def check_all_chapters(directory: str, pattern: str = '第*.md',
                       min_words: int = 2500, max_words: int = 3500) -> list:

    dir_path = Path(directory)
    if not dir_path.exists():
        print(f'错误: 目录不存在 - {directory}')
        return []

    chapter_files = sorted(dir_path.glob(pattern))
    return [check_chapter(str(f), min_words, max_words) for f in chapter_files]


def print_results(results: list, min_words: int, max_words: int, platform_label: str = ''):

    if not results:
        print('没有找到章节文件')
        return

    total_words = 0
    passed = short = long = error = 0

    title = f'{platform_label}章节字数检查报告' if platform_label else '章节字数检查报告'
    print('\n' + '=' * 60)
    print(title)
    print(f'最佳区间: {min_words}-{max_words} 字')
    print('=' * 60)

    for result in results:
        if not result['exists']:
            error += 1
            icon = '❌'
        elif result['status'] == 'pass':
            passed += 1
            icon = '✅'
            total_words += result['word_count']
        elif result['status'] == 'short':
            short += 1
            icon = '⚠️'
            total_words += result['word_count']
        elif result['status'] == 'long':
            long += 1
            icon = '📈'
            total_words += result['word_count']
        else:
            error += 1
            icon = '❌'

        print(f'\n{icon} {Path(result["file"]).name}')
        print(f'   {result["message"]}')

    print('\n' + '-' * 60)
    print(f'总计: {len(results)} 章 | {passed} 章达标 | {short} 章不足 | {long} 章超标 | 总字数: {total_words:,}')
    print('-' * 60)

    if short > 0:
        print(f'\n⚠️ 有 {short} 章内容不足 {min_words} 字，建议使用扩充技巧（参考 content-expansion.md）')
    if long > 0:
        print(f'\n📈 有 {long} 章内容超过 {max_words} 字，建议精简以提升完读率。')


def print_usage():
    print('用法:')
    print('  python check_chapter_wordcount.py <章节文件> [--platform <平台键>] [最小字数] [最大字数]')
    print('  python check_chapter_wordcount.py --all <目录> [--platform <平台键>] [最小字数] [最大字数]')
    print('')
    print('平台键 (--platform):')
    for key, (min_w, max_w, label) in PLATFORM_PRESETS.items():
        print(f'  {key:10s}  {label}  ({min_w}-{max_w} 字)')
    print('')
    print('示例:')
    print('  python check_chapter_wordcount.py novels/我的书/第01章.md --platform tomato')
    print('  python check_chapter_wordcount.py --all novels/我的书/ --platform qidian')


def parse_args(argv: list) -> dict:

    if len(argv) < 2:
        return {'error': 'usage'}

    platform_key = 'generic'
    min_words = None
    max_words = None
    mode = 'single'
    target = None

    args = argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '--all':
            mode = 'all'
            i += 1
            if i < len(args):
                target = args[i]
                i += 1
        elif arg == '--platform':
            i += 1
            if i < len(args):
                platform_key = args[i].lower()
                i += 1
        elif arg.startswith('--'):
            i += 1
        elif target is None:
            target = arg
            i += 1
        else:
            if min_words is None:
                min_words = int(arg)
            elif max_words is None:
                max_words = int(arg)
            i += 1

    if not target:
        return {'error': 'usage'}

    if platform_key not in PLATFORM_PRESETS:
        print(f'错误: 未知平台键 "{platform_key}"')
        print_usage()
        return {'error': 'bad_platform'}

    preset_min, preset_max, platform_label = PLATFORM_PRESETS[platform_key]
    min_words = min_words if min_words is not None else preset_min
    max_words = max_words if max_words is not None else preset_max

    return {
        'mode': mode,
        'target': target,
        'min_words': min_words,
        'max_words': max_words,
        'platform_label': platform_label,
    }


def main():
    parsed = parse_args(sys.argv)
    if parsed.get('error') == 'usage':
        print_usage()
        return
    if parsed.get('error'):
        return

    if parsed['mode'] == 'all':
        results = check_all_chapters(
            parsed['target'],
            min_words=parsed['min_words'],
            max_words=parsed['max_words'],
        )
    else:
        results = [check_chapter(parsed['target'], parsed['min_words'], parsed['max_words'])]

    print_results(
        results,
        parsed['min_words'],
        parsed['max_words'],
        parsed['platform_label'],
    )


if __name__ == '__main__':
    main()

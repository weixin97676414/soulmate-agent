#!/usr/bin/env python3














import sys
import os
import json
import re

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SCRIPTS_DIR = os.path.dirname(__file__)
PROJECT_DIR = os.path.dirname(SCRIPTS_DIR)
CONFIG_FILE = os.path.join(PROJECT_DIR, 'config', 'fallback-sources.json')


def parse_cookie_string(raw):

    if not raw or not raw.strip():
        raise ValueError('Cookie 字符串为空')

    cookies = {}
    
    raw = raw.strip().rstrip(';').strip()

    for part in raw.split(';'):
        part = part.strip()
        if '=' in part:
            key, _, value = part.partition('=')
            key = key.strip()
            value = value.strip()
            if key:
                cookies[key] = value

    if not cookies:
        raise ValueError('未能解析任何 Cookie，请检查格式是否正确')

    return cookies


def validate_cookies(cookies):

    required = ['z_c0', '_xsrf', 'd_c0']
    missing = [k for k in required if k not in cookies]

    important = ['_zap', 'q_c1', 'SESSIONID']
    missing_important = [k for k in important if k not in cookies]

    if missing:
        print(f'⚠️  缺少关键字段: {", ".join(missing)}')
        print('   如果缺少 z_c0，请确认复制的是 Request Headers 中的 Cookie')
        print('   （不是 document.cookie，后者不含 HTTPOnly 的 z_c0）')
        return False

    if missing_important:
        print(f'⚠️  缺少重要字段（可能不影响使用）: {", ".join(missing_important)}')

    return True


def save_cookies(cookies):

    config = {}

    
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)

    
    config['cookie'] = cookies

    
    config['auth'] = config.get('auth', {})
    config['auth']['priority'] = ['file_cookie', 'browser_profile', 'fallback_source']

    
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    return True


def verify_cookies(cookies):

    import urllib.request
    import ssl

    cookie_str = '; '.join(f'{k}={v}' for k, v in cookies.items())

    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        'https://www.zhihu.com/api/v4/me',
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Cookie': cookie_str,
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                name = data.get('name', '未知')
                user_id = data.get('id', '?')
                print(f'✅ Cookie 有效！用户: {name} (ID: {user_id})')
                return True
            else:
                print(f'⚠️  API 返回 HTTP {resp.status}，Cookie 可能无效')
                return False
    except Exception as e:
        print(f'⚠️  验证失败: {e}')
        print('   Cookie 已保存，但可能过期或无效')
        return False


def get_cookie_input():

    if len(sys.argv) >= 2:
        arg = sys.argv[1]
        if arg == '--file':
            if len(sys.argv) < 3:
                print('用法: save_cookie.py --file cookie.txt')
                sys.exit(1)
            with open(sys.argv[2], 'r', encoding='utf-8') as f:
                return f.read().strip()
        elif arg == '--paste':
            try:
                import subprocess
                result = subprocess.run(
                    ['powershell', '-command', 'Get-Clipboard'],
                    capture_output=True, text=True
                )
                return result.stdout.strip()
            except Exception:
                print('无法读取剪贴板，请直接粘贴 Cookie 字符串')
                return input().strip()
        else:
            return arg

    
    print('请粘贴 Cookie 字符串（从 DevTools Network 面板复制），按 Enter 结束：')
    return input().strip()


def main():
    print('知乎 Cookie 保存工具')
    print('─' * 50)

    try:
        raw = get_cookie_input()
    except (KeyboardInterrupt, EOFError):
        print('\n已取消')
        sys.exit(0)

    if not raw:
        print('❌ 未收到 Cookie 输入')
        sys.exit(1)

    
    preview = raw[:80] + ('...' if len(raw) > 80 else '')
    print(f'📋 收到 Cookie: {preview}')
    print()

    try:
        cookies = parse_cookie_string(raw)
    except ValueError as e:
        print(f'❌ 解析失败: {e}')
        sys.exit(1)

    print(f'📊 解析到 {len(cookies)} 个 Cookie 字段')
    for k in sorted(cookies.keys()):
        v = cookies[k]
        preview = v[:30] + '...' if len(v) > 30 else v
        print(f'   {k}: {preview}')
    print()

    
    if not validate_cookies(cookies):
        print('Cookie 可能不完整，是否继续保存？(y/n) ', end='')
        if input().strip().lower() != 'y':
            print('已取消')
            sys.exit(1)

    
    save_cookies(cookies)
    print(f'✅ 已保存到 {CONFIG_FILE}')
    print()

    
    print('正在验证...')
    verify_cookies(cookies)
    print()

    print('下一步: python scripts/save_to_db.py all')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
从 Quark 浏览器提取知乎 Cookie 并写入配置文件
Extract Zhihu cookies from Quark browser and save to config

需要: 暂关 Quark 浏览器 / Need: close Quark browser temporarily
"""

import json
import os
import sys
import sqlite3
import base64
import shutil

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from Crypto.Cipher import AES
import win32crypt

# 路径配置
QUARK_PROFILE = os.path.expandvars(r'%LOCALAPPDATA%\Quark\User Data')
COOKIE_DB = os.path.join(QUARK_PROFILE, 'Default', 'Network', 'Cookies')
LOCAL_STATE = os.path.join(QUARK_PROFILE, 'Local State')
CONFIG_FILE = os.path.join(os.path.dirname(__file__), '..', 'config', 'fallback-sources.json')

# 知乎需要的核心 cookie 字段
KEY_COOKIES = ['z_c0', '_xsrf', '_zap', 'd_c0', 'zhihu_session', 'tst', 'q_c1', 'tgw_l7_route']


def get_encryption_key():
    """从 Quark Local State 获取 AES 解密密钥"""
    with open(LOCAL_STATE, 'r', encoding='utf-8') as f:
        state = json.load(f)
    enc_key_b64 = state['os_crypt']['encrypted_key']
    enc_key = base64.b64decode(enc_key_b64)
    # 去掉 'DPAPI' 前缀 (5 bytes)
    enc_key = enc_key[5:]
    return win32crypt.CryptUnprotectData(enc_key, None, None, None, 0)[1]


def decrypt_value(encrypted_value, key):
    """解密 v10/v11 AES-GCM 加密的 cookie 值"""
    if len(encrypted_value) < 3:
        return None
    prefix = encrypted_value[:3]
    # v10/v11: b'v10' or b'v11'
    if prefix in (b'v10', b'v11'):
        nonce = encrypted_value[3:15]
        ciphertext = encrypted_value[15:-16]
        tag = encrypted_value[-16:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode('utf-8', errors='replace')
    # 旧格式: DPAPI 直接解密
    else:
        return win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1].decode('utf-8', errors='replace')


def extract_cookies():
    """提取所有 zhihu.com 域名下的 cookie"""
    # 复制数据库避免锁冲突
    tmp_db = os.path.join(os.environ['TEMP'], 'quark_cookies_extract.db')
    try:
        shutil.copy2(COOKIE_DB, tmp_db)
    except PermissionError:
        print("\n❌ 无法读取 Cookie 数据库！")
        print(f"   文件仍然被锁定: {COOKIE_DB}")
        print("   请确保所有浏览器进程已关闭。")
        return None

    print(f"[OK] 数据库已复制 ({os.path.getsize(tmp_db)} bytes)")

    key = get_encryption_key()
    print(f"[OK] 解密密钥已获取")

    conn = sqlite3.connect(tmp_db)
    conn.text_factory = bytes
    cursor = conn.cursor()
    cursor.execute(
        "SELECT host_key, name, encrypted_value, path FROM cookies WHERE host_key LIKE '%zhihu%'"
    )

    cookies = {}
    for host, name, enc_val, path in cursor.fetchall():
        try:
            value = decrypt_value(enc_val, key)
            name_str = name.decode()
            host_str = host.decode()
            cookies[name_str] = value
            short_val = value[:40] + '...' if len(value) > 40 else value
            print(f"  [{host_str}] {name_str} = {short_val}")
        except Exception as e:
            print(f"  ⚠️  {name.decode()} 解密失败: {e}")

    conn.close()
    os.unlink(tmp_db)
    return cookies


def update_config(cookies):
    """更新 fallback-sources.json 中的 cookie 配置"""
    # 读取现有配置
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    else:
        config = {}

    # 过滤出关键 cookie
    filtered = {}
    for k in KEY_COOKIES:
        if k in cookies:
            filtered[k] = cookies[k]
    # 也保留其他 zhihu 相关 cookie
    for k, v in cookies.items():
        if k not in filtered:
            filtered[k] = v

    config['cookie'] = filtered

    # 写入配置
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Cookie 已写入配置: {CONFIG_FILE}")
    return config


def test_cookie(cookies):
    """快速测试 cookie 是否有效"""
    import urllib.request
    cookie_str = '; '.join(f'{k}={v}' for k, v in cookies.items())

    req = urllib.request.Request(
        'https://www.zhihu.com/api/v4/me',
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Cookie': cookie_str
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if 'name' in data:
                print(f"\n✅ Cookie 有效! 当前登录: {data.get('name', '?')}")
                return True
            else:
                print(f"\n⚠️  Cookie 可能已过期: {data}")
                return False
    except Exception as e:
        print(f"\n⚠️  Cookie 验证失败: {e}")
        return False


def main():
    print("=" * 60)
    print("  知乎 Cookie 提取工具 (Quark 浏览器)")
    print("=" * 60)

    if not os.path.exists(COOKIE_DB):
        print(f"\n❌ 未找到 Quark cookie 数据库")
        print(f"   路径: {COOKIE_DB}")
        return

    cookies = extract_cookies()
    if not cookies:
        return

    print(f"\n共提取 {len(cookies)} 个 zhihu.com cookie")

    # 核心 cookie 检查
    print(f"\n核心 Cookie 状态:")
    for k in KEY_COOKIES:
        status = '✅' if k in cookies else '❌'
        print(f"  {status} {k}")

    # 写入配置
    update_config(cookies)

    # 测试 cookie
    test_cookie(cookies)

    print(f"\n" + "=" * 60)
    print(f"  完成! 现在可以重新打开夸克浏览器")
    print(f"  运行采集: python3 scripts/save_to_db.py 50")
    print(f"=" * 60)


if __name__ == '__main__':
    main()

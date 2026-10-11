#!/usr/bin/env python3
"""
采集并保存到数据库 - Collection & Save to Database

用法:
  python3 save_to_db.py [limit]              # 采集热榜 默认50条
  python3 save_to_db.py 30                   # 采集30条热榜
  python3 save_to_db.py 30 questions         # 采集30条"等你来答"问题
  python3 save_to_db.py 100 recommend        # 采集100条推荐问题
  python3 save_to_db.py 100 invited          # 采集100条邀请回答
  python3 save_to_db.py recommend 100        # 同上 (顺序兼容)
  python3 save_to_db.py all                  # 全部采集 (热榜+等你来答+推荐+邀请)
"""

import sys
import os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json
import subprocess
import time

sys.path.insert(0, os.path.dirname(__file__))
from db import init_database, save_articles, save_questions, log_fetch, now_ts

SCRIPTS_DIR = os.path.dirname(__file__)
PROJECT_DIR = os.path.dirname(SCRIPTS_DIR)
SNIPPETS_DIR = os.path.join(PROJECT_DIR, 'snippets')


def get_node():
    """获取可用的Node.js路径"""
    import shutil
    # 优先使用 managed node
    home = os.path.expanduser('~')
    for ver in ['22.12.0', '22.22.2']:
        node_path = os.path.join(home, '.skill-runtime', 'binaries', 'node', 'versions', ver, 'node.exe')
        if os.path.exists(node_path):
            return node_path
    # 尝试系统node
    node = shutil.which('node')
    if node:
        return node
    return 'node'


def parse_args():
    """解析命令行参数"""
    limit = 50
    mode = 'hot'
    modes_to_run = []

    if len(sys.argv) <= 1:
        return [{'mode': 'hot', 'limit': 50}]

    # 解析所有参数
    remaining = list(sys.argv[1:])

    # "all" 模式：全部采集
    if 'all' in remaining:
        return [
            {'mode': 'hot', 'limit': 50},
            {'mode': 'recommend', 'limit': 100},
            {'mode': 'invited', 'limit': 100},
        ]

    # 检查是否有明确模式
    mode_aliases = {
        'questions': 'questions', 'question': 'questions', 'q': 'questions',
        'recommend': 'recommend', 'recommended': 'recommend', 'rec': 'recommend',
        'invited': 'invited', 'invite': 'invited', 'inv': 'invited',
    }

    detected_mode = None
    detected_limit = None

    for arg in remaining:
        if arg in mode_aliases:
            detected_mode = mode_aliases[arg]
        else:
            try:
                detected_limit = int(arg)
            except ValueError:
                pass

    mode = detected_mode or 'hot'
    limit = detected_limit or (100 if mode in ('recommend', 'invited') else 50)

    return [{'mode': mode, 'limit': limit}]


def run_fetch(mode, limit, retry_count=2):
    """执行单次抓取任务，网络错误自动重试最多 retry_count 次"""
    started_at = now_ts()
    node = get_node()

    mode_labels = {
        'hot': '热榜',
        'questions': '等你来答',
        'recommend': '推荐问题',
        'invited': '邀请回答',
    }
    label = mode_labels.get(mode, mode)

    mode_hints = {
        'recommend': '如果返回数据为空，可能是登录已过期。重新扫码登录知乎后运行: node scripts/auto_cookie.js --headless',
        'invited': '如果返回数据为空，可能是登录已过期或最近没有收到邀请。',
    }

    for attempt in range(1, retry_count + 2):  # retry_count+1 次尝试
        if attempt > 1:
            wait = attempt * 3
            print(f"\n   🔄 第 {attempt} 次重试（等待 {wait} 秒）...")
            time.sleep(wait)

        print(f"\n{'='*60}")
        print(f"📡 {label} ({mode})  条数: {limit}")
        if attempt > 1:
            print(f"   重试: {attempt}/{retry_count + 1}")
        print(f"{'='*60}")

        try:
            # 根据模式选择 fetcher
            if mode in ('recommend', 'invited'):
                fetch_cmd = [
                    node, os.path.join(SNIPPETS_DIR, 'fetch-featured.js'),
                    mode, str(limit), '--json'
                ]
            elif mode == 'questions':
                fetch_cmd = [
                    node, os.path.join(SNIPPETS_DIR, 'fetch-questions.js'),
                    str(limit), '--json'
                ]
            else:
                fetch_cmd = [
                    node, os.path.join(SNIPPETS_DIR, 'fetch-hot.js'),
                    str(limit), '--json'
                ]

            result = subprocess.run(
                fetch_cmd, cwd=PROJECT_DIR,
                capture_output=True, text=True, timeout=180,
                encoding='utf-8', errors='replace'
            )

            # 解析 stderr 中的错误信息
            stderr_lower = result.stderr.lower() if result.stderr else ''

            if result.returncode != 0:
                if '401' in result.stderr or 'unauthorized' in stderr_lower or 'auth' in stderr_lower:
                    print(f"   ⚠️  登录已过期，需要重新获取 Cookie")
                    print(f"   💡 解决方法：关闭 Edge 后运行：")
                    print(f"      node scripts/auto_cookie.js --headless")
                    if mode in ('recommend', 'invited'):
                        print(f"      如果仍未解决，打开 https://www.zhihu.com 重新扫码登录")
                elif 'timeout' in stderr_lower or 'timed out' in stderr_lower or 'econnrefused' in stderr_lower or 'enotfound' in stderr_lower:
                    print(f"   ⚠️  网络连接失败，可能是网络不稳定或知乎接口暂时不可用")
                    if attempt <= retry_count:
                        continue  # 重试
                elif '403' in result.stderr or 'forbidden' in stderr_lower:
                    print(f"   ⚠️  请求被知乎拒绝（可能触发反爬机制）")
                    print(f"   💡 建议等待几分钟后再试")
                else:
                    print(f"   ⚠️  抓取出错")
                    if attempt <= retry_count:
                        continue  # 未知错误也重试

                finished_at = now_ts()
                log_fetch(source='zhihu', mode=mode, status='error',
                          error_message=result.stderr[:500],
                          started_at=started_at, finished_at=finished_at)
                return False

            # 直接解析整个 stdout 为 JSON
            output = result.stdout.strip()
            if not output:
                print(f"   ⚠️  未获取到任何数据")
                if mode in mode_hints:
                    print(f"   💡 {mode_hints[mode]}")
                finished_at = now_ts()
                log_fetch(source='zhihu', mode=mode, status='error',
                          error_message='No output from fetcher',
                          started_at=started_at, finished_at=finished_at)
                return False

            data = json.loads(output)

            meta = data.get('meta', {})
            items = data.get('data', [])

            auth_method = meta.get('auth_method', 'unknown')
            auth_labels = {
                'browser_profile': 'Edge浏览器自动提取',
                'file_cookie': '已保存的Cookie',
                'fallback_source': '公开备用源（无需登录）',
                'none': '无认证（仅热榜可用）',
            }
            auth_label = auth_labels.get(auth_method, auth_method)
            print(f"   认证方式: {auth_label}")
            print(f"   获取到 {len(items)} 条数据")

            if items:
                if mode in ('questions', 'recommend', 'invited'):
                    new_count, updated_count = save_questions(items)
                else:
                    article_type = meta.get('mode', 'hot')
                    new_count, updated_count = save_articles(items, article_type)
            else:
                new_count, updated_count = 0, 0
                if meta.get('error'):
                    print(f"   ⚠️  {meta['error']}")
                elif mode in mode_hints:
                    print(f"   💡 {mode_hints[mode]}")
                elif mode == 'hot':
                    print(f"   💡 热榜可能需要稍等片刻再试")

            finished_at = now_ts()

            log_fetch(
                source='zhihu', mode=mode,
                auth_method=meta.get('auth_method'),
                count=len(items), new_count=new_count, updated_count=updated_count,
                status='success' if items else 'warning',
                started_at=started_at, finished_at=finished_at
            )

            if items:
                print(f"   ✅ 完成! 获取 {len(items)} 条 | 新增 {new_count} | 更新 {updated_count}")
            else:
                print(f"   ⚠️ 未获取到新数据")
            return True

        except subprocess.TimeoutExpired:
            print(f"   ⚠️  请求超时（网络较慢或知乎接口繁忙）")
            if attempt <= retry_count:
                continue
            finished_at = now_ts()
            log_fetch(source='zhihu', mode=mode, status='error',
                      error_message='Timeout after 180s',
                      started_at=started_at, finished_at=finished_at)
            return False
        except json.JSONDecodeError:
            print(f"   ⚠️  返回数据格式异常（知乎接口可能临时变动）")
            if attempt <= retry_count:
                continue
            finished_at = now_ts()
            log_fetch(source='zhihu', mode=mode, status='error',
                      error_message='JSON parse error',
                      started_at=started_at, finished_at=finished_at)
            return False
        except Exception as e:
            print(f"   ⚠️  发生错误: {e}")
            if attempt <= retry_count:
                continue
            finished_at = now_ts()
            log_fetch(source='zhihu', mode=mode, status='error',
                      error_message=str(e)[:500],
                      started_at=started_at, finished_at=finished_at)
            return False



def main():
    tasks = parse_args()
    init_database()

    print(f"知乎数据采集 ({len(tasks)} 个任务)")
    print("-" * 40)

    success_count = 0
    for task in tasks:
        if run_fetch(task['mode'], task['limit']):
            success_count += 1

    print(f"\n{'='*60}")
    print(f"全部完成: {success_count}/{len(tasks)} 个任务成功")


if __name__ == '__main__':
    main()

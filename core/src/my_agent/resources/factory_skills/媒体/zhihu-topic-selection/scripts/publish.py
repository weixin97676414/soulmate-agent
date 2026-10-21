#!/usr/bin/env python3

















import sys
import os
import json
import re
import urllib.request
import subprocess
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))
SCRIPTS_DIR = os.path.dirname(__file__)
SNIPPETS_DIR = os.path.join(PROJECT_DIR, 'snippets')
DRAFTS_DIR = os.path.join(PROJECT_DIR, 'data', 'drafts')
CONFIG_FILE = os.path.join(PROJECT_DIR, 'config', 'fallback-sources.json')

sys.path.insert(0, SCRIPTS_DIR)
from content_writer import (
    get_topics, display_topics, select_topic_interactive,
    fetch_url_content, build_ai_prompt, save_draft, list_drafts,
    STYLES, CONTENT_TYPES
)


def get_node():

    import shutil
    home = os.path.expanduser('~')
    for ver in ['22.12.0', '22.22.2']:
        p = os.path.join(home, '.skill-runtime', 'binaries', 'node', 'versions', ver, 'node.exe')
        if os.path.exists(p):
            return p
    node = shutil.which('node')
    return node or 'node'


def check_cookie():

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        cookies = config.get('cookie', {})
        has_zc0 = bool(cookies.get('z_c0'))
        has_xsrf = bool(cookies.get('_xsrf'))
        return has_zc0 and has_xsrf
    except:
        return False


def refresh_cookie():

    print("\n📡 尝试从 Edge 浏览器自动获取 Cookie...")
    node = get_node()
    script = os.path.join(SCRIPTS_DIR, 'auto_cookie.js')

    try:
        result = subprocess.run(
            [node, script, '--headless', '--save-only'],
            cwd=PROJECT_DIR,
            capture_output=True, text=True,
            encoding='utf-8', errors='replace',
            timeout=30
        )
        return check_cookie()
    except:
        return False


def ai_generate(prompt_data):




    print("\n" + "=" * 60)
    print("  🤖 AI 正在生成内容...")

    system = prompt_data['system']
    prompt = prompt_data['prompt']

    
    print("  (提示词已准备，等待 AI 生成...)")
    print("=" * 60)

    return None, None  


def interactive_edit(title, body, content_type):

    while True:
        print(f"\n{'='*60}")
        print(f"  📝 内容预览")
        print(f"{'='*60}")

        if title:
            print(f"\n  标题: {title}")
            print(f"  {'─'*50}")

        
        preview = (body or '')[:300]
        print(f"  {preview}")
        if len(body or '') > 300:
            print(f"  ... (共 {len(body)} 字)")
        print(f"  {'─'*50}")

        print(f"\n  操作: [y]确认发布  [e]编辑  [v]查看全文  [q]取消")
        choice = input("  > ").strip().lower()

        if choice == 'y':
            return title, body
        elif choice == 'e':
            print("\n  编辑模式（输入新内容，输入 ---END 结束）")
            print("  修改标题（回车保持）:")
            new_title = input("  > ").strip()
            if new_title:
                title = new_title

            print("  修改正文（输入 ---END 结束）:")
            lines = []
            while True:
                line = input()
                if line.strip() == '---END':
                    break
                lines.append(line)
            if lines:
                body = '\n'.join(lines)

            
            save_draft(title, body, content_type,
                      {'title': title, 'type': 'edited'},
                      'custom', [])
            print(f"  ✅ 草稿已更新")
        elif choice == 'v':
            print(f"\n{'='*60}")
            if title:
                print(f"  {title}")
                print(f"  {'─'*50}")
            print(body)
            print(f"{'='*60}")
            input("  按 Enter 返回...")
        elif choice == 'q':
            return None, None


def launch_publisher(mode, draft_path, question_urls=None):

    node = get_node()
    script = os.path.join(SCRIPTS_DIR, 'publisher.js')

    cmd = [node, script, mode, '--draft', draft_path]
    if question_urls:
        cmd.extend(['--urls', ','.join(question_urls)])

    print(f"\n  启动发布工具: {' '.join(cmd[:5])}...")

    
    result = subprocess.run(cmd, cwd=PROJECT_DIR, timeout=300)

    return result.returncode == 0


def main():
    print("=" * 60)
    print("  知乎 AI 内容生成与发布工具 v1.0")
    print("=" * 60)

    
    args = sys.argv[1:]

    if '--list-drafts' in args:
        drafts = list_drafts()
        if not drafts:
            print("\n  📭 暂无草稿")
            return
        print(f"\n  📁 草稿列表 ({len(drafts)}个):")
        for d in drafts:
            title = (d.get('title') or d.get('topic', {}).get('title', '无标题'))[:40]
            ct = d.get('content_type', 'article')
            date = (d.get('created_at', '') or '')[:16]
            print(f"    [{date}] [{ct}] {title}")
        return

    if '--draft' in args and len(args) > args.index('--draft') + 1:
        
        draft_name = args[args.index('--draft') + 1]
        draft_path = None

        if draft_name == 'latest':
            drafts = list_drafts()
            if drafts:
                draft_path = os.path.join(DRAFTS_DIR, drafts[0]['_file'])
        else:
            draft_path = draft_name

        if not draft_path or not os.path.exists(draft_path):
            print(f"\n  ❌ 草稿不存在: {draft_name}")
            return

        with open(draft_path, 'r', encoding='utf-8') as f:
            draft = json.load(f)

        title = draft.get('title', '')
        body = draft.get('body', '')
        content_type = draft.get('content_type', 'article')

        if not body:
            print("\n  ❌ 草稿内容为空")
            return

        print(f"\n  ✅ 已加载草稿: {(title or '无标题')[:50]}")

        
        title, body = interactive_edit(title, body, content_type)
        if not body:
            print("  已取消")
            return

        
        save_draft(title, body, content_type,
                  draft.get('topic', {}), draft.get('style', 'professional'),
                  draft.get('references', []))

        
        question_urls = None
        if content_type == 'answer' and '--urls' in args:
            idx = args.index('--urls')
            if idx + 1 < len(args):
                question_urls = args[idx + 1].split(',')

        launch_publisher(content_type, draft_path, question_urls)
        return

    

    
    print("\n[前置] 检查认证状态")
    if not check_cookie():
        print("  ⚠️  Cookie 未配置或已过期")
        if refresh_cookie():
            print("  ✅ Cookie 已刷新")
        else:
            print("  💡 请先运行: node scripts/auto_cookie.js")
            return
    else:
        print("  ✅ Cookie 可用")

    
    quick = '--quick' in args

    print(f"\n{'='*60}")
    print(f"  选择发布模式")
    print(f"{'='*60}")
    print(f"  [1] 发布文章 (article)")
    print(f"  [2] 回答问题 (answer)")
    print(f"  [3] 只生成内容，不发布")

    mode_choice = input("  选择 [1]: ").strip() or '1'
    if mode_choice == '2':
        content_type = 'answer'
        publish_mode = 'answer'
    elif mode_choice == '3':
        content_type = 'article'
        publish_mode = None
    else:
        content_type = 'article'
        publish_mode = 'article'

    
    print(f"\n[1/5] 选择写作话题")
    topic_source = 'all' if not quick else 'recommend'
    topics = get_topics(topic_source, limit=30)
    topic = select_topic_interactive(topics)

    if not topic:
        print("  已取消")
        return

    print(f"\n  ✅ 话题: {topic['title'][:60]}")

    
    print(f"\n[2/5] 选择写作风格")
    style_map = {'1': 'professional', '2': 'conversational', '3': 'storytelling', '4': 'data_driven'}
    for k, v in STYLES.items():
        num = [n for n, sk in style_map.items() if sk == k][0]
        print(f"  [{num}] {v['name']}")
    style_choice = input("  选择 [1]: ").strip() or '1'
    style = style_map.get(style_choice, 'professional')
    print(f"  ✅ 风格: {STYLES[style]['name']}")

    
    print(f"\n[3/5] 添加参考资料（回车跳过）")
    refs = []
    while True:
        ref = input("  粘贴链接或文本（回车跳过）: ").strip()
        if not ref:
            break
        if ref.startswith('http'):
            content = fetch_url_content(ref)
            if not content.startswith('[无法'):
                refs.append(f"[来源: {ref}]\n{content}")
                print(f"  ✅ 已获取链接内容")
            else:
                print(f"  ⚠️  无法获取该链接")
        else:
            refs.append(ref)
            print(f"  ✅ 已添加 ({len(ref)}字)")

    if refs:
        print(f"  📎 已添加 {len(refs)} 份参考资料")

    
    print(f"\n[4/5] AI 生成内容")
    prompt_text = build_ai_prompt(topic, refs, style, content_type)

    
    prompt_file = os.path.join(DRAFTS_DIR, 'latest_prompt.json')
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    prompt_data = {
        'system': '''你是一位资深的知乎内容创作者，擅长多种写作风格。

请根据要求生成知乎内容。回复格式：
---TITLE---
标题（仅文章需要）
---TITLE---
---BODY---
正文（Markdown 格式）
---BODY---

如果是回答模式，跳过 TITLE 部分，直接输出 BODY。''',
        'prompt': prompt_text,
    }
    with open(prompt_file, 'w', encoding='utf-8') as f:
        json.dump(prompt_data, f, ensure_ascii=False, indent=2)

    
    print(f"\n  {'='*60}")
    print(f"  📋 AI 生成提示词")
    print(f"  {'='*60}")
    print(f"\n{prompt_text}")
    print(f"\n  {'='*60}")
    print(f"\n  提示词已保存到: {prompt_file}")
    print(f"\n  💡 请在对话中回复生成的标题和内容。")
    print(f"  回复格式:")
    print(f"  ---TITLE---")
    print(f"  你的标题")
    print(f"  ---TITLE---")
    print(f"  ---BODY---")
    print(f"  你的正文")
    print(f"  ---BODY---")

    
    print(f"\n[5/5] 等待内容输入...")
    print(f"  粘贴 AI 生成的内容（含 ---TITLE--- 和 ---BODY--- 标记）:")

    lines = []
    while True:
        try:
            line = input()
            if not line and lines and lines[-1] == '':
                break
            lines.append(line)
        except EOFError:
            break

    full = '\n'.join(lines)

    
    title_match = re.search(r'---TITLE---\s*\n(.*?)\n\s*---TITLE---', full, re.DOTALL)
    body_match = re.search(r'---BODY---\s*\n(.*?)\n\s*(?:---BODY---|$)', full, re.DOTALL)

    title = title_match.group(1).strip() if title_match else topic['title']
    body = body_match.group(1).strip() if body_match else full.strip()

    if not body:
        print("\n  ❌ 未检测到正文内容")
        return

    
    title, body = interactive_edit(title, body, content_type)
    if not body:
        print("  已取消")
        return

    
    draft_path = save_draft(title, body, content_type, topic, style, refs)
    print(f"\n  ✅ 草稿已保存: {draft_path}")

    
    if publish_mode:
        print(f"\n[发布] 准备发布到知乎...")

        question_urls = None
        if publish_mode == 'answer':
            
            print("  请输入要回答的问题URL（多个用逗号分隔）:")
            print("  或直接回车使用话题链接:")
            urls_input = input("  > ").strip()
            if urls_input:
                question_urls = [u.strip() for u in urls_input.split(',') if u.strip()]
            elif topic.get('url'):
                question_urls = [topic['url']]

        if publish_mode == 'article' or question_urls:
            launch_publisher(publish_mode, draft_path, question_urls)
        else:
            print("  ⚠️  未指定问题URL，跳过发布")
    else:
        print(f"\n  📝 内容已保存为草稿，可稍后发布")
        print(f"  发布命令: python publish.py --draft {os.path.basename(draft_path)}")


if __name__ == '__main__':
    main()

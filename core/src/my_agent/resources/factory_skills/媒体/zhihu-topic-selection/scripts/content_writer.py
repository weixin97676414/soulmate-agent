#!/usr/bin/env python3




















import sys
import os
import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))
from db import (init_database, query_articles, query_questions,
                today_str, get_db)

PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))
DRAFTS_DIR = os.path.join(PROJECT_DIR, 'data', 'drafts')


STYLES = {
    'professional': {
        'name': '专业深度',
        'tone': '专业、有深度、逻辑清晰，引用数据和案例支撑观点，避免口语化表达',
        'structure': '开头引出问题 → 中间分点论证 → 结尾总结升华',
        'length': '1500-3000字'
    },
    'conversational': {
        'name': '通俗易懂',
        'tone': '亲切自然、像朋友聊天、用简单的话解释复杂的事，适当使用知乎梗和表情',
        'structure': '开门见山 → 层层递进 → 互动结尾',
        'length': '800-1500字'
    },
    'storytelling': {
        'name': '故事叙述',
        'tone': '以个人经历开场，讲故事的方式带出观点，有情感有温度',
        'structure': '个人故事引入 → 提炼观点 → 扩展讨论 → 情感收尾',
        'length': '1000-2000字'
    },
    'data_driven': {
        'name': '数据论证',
        'tone': '理性客观、用数据和事实说话、图表化思维、条理分明',
        'structure': '数据呈现 → 分析解读 → 结论建议',
        'length': '1200-2500字'
    }
}


CONTENT_TYPES = {
    'article': '知乎文章（独立发布，含标题和封面）',
    'answer': '问题回答（针对具体问题，直接切入）'
}


def get_topics(source='all', limit=20):

    init_database()
    topics = []

    if source in ('hot', 'all'):
        articles = query_articles(fetch_date=None, article_type='hot', limit=limit)
        for a in articles:
            topics.append({
                'type': 'hot',
                'label': '🔥 热榜',
                'title': a.get('title', ''),
                'url': a.get('url', ''),
                'heat': a.get('heat', 0),
                'summary': a.get('summary', '')[:100]
            })

    if source in ('recommend', 'all'):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM questions WHERE source='recommend' ORDER BY follower_count DESC LIMIT ?", (limit,))
        for r in c.fetchall():
            q = dict(r)
            topics.append({
                'type': 'recommend',
                'label': '💡 推荐问题',
                'title': q.get('title', ''),
                'url': q.get('url', ''),
                'follower_count': q.get('follower_count', 0),
                'answer_count': q.get('answer_count', 0),
                'recommend_reason': q.get('recommend_reason', '')
            })
        conn.close()

    if source in ('invited', 'all'):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM questions WHERE source='invited' ORDER BY follower_count DESC LIMIT ?", (limit,))
        for r in c.fetchall():
            q = dict(r)
            topics.append({
                'type': 'invited',
                'label': '📨 邀请回答',
                'title': q.get('title', ''),
                'url': q.get('url', ''),
                'follower_count': q.get('follower_count', 0),
                'answer_count': q.get('answer_count', 0)
            })
        conn.close()

    return topics


def fetch_url_content(url):

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode('utf-8', errors='replace')
            
            clean = re.sub(r'<[^>]+>', ' ', content)
            clean = re.sub(r'\s+', ' ', clean)
            return clean[:5000]
    except Exception as e:
        return f"[无法获取: {e}]"


def display_topics(topics, page=0, per_page=10):

    start = page * per_page
    end = start + per_page
    chunk = topics[start:end]

    print(f"\n{'='*70}")
    print(f"  📋 可选话题 ({start+1}-{min(end,len(topics))} / 共{len(topics)}个)")
    print(f"{'='*70}")

    for i, t in enumerate(chunk):
        idx = start + i + 1
        title = (t['title'] or '无标题')[:55]
        detail = ''
        if t['type'] == 'hot':
            h = t.get('heat', 0)
            detail = f"热度 {h/10000:.1f}W" if h > 10000 else f"热度 {h}"
        elif t.get('follower_count'):
            detail = f"{t['follower_count']}关注 {t.get('answer_count',0)}回答"

        print(f"  [{idx:>3}] {t['label']} | {title}")
        print(f"        {detail}")
        if t.get('recommend_reason'):
            print(f"        💬 {t['recommend_reason'][:50]}")
        print()

    return len(chunk)


def select_topic_interactive(topics):

    page = 0
    per_page = 5

    while True:
        displayed = display_topics(topics, page, per_page)
        total_pages = (len(topics) + per_page - 1) // per_page

        print(f"  输入编号选择话题 | n=下一页 p=上一页 q=退出")
        if displayed < per_page:
            print(f"  或者直接输入自定义话题")

        choice = input("  > ").strip()

        if choice.lower() == 'q':
            return None
        elif choice.lower() == 'n' and page < total_pages - 1:
            page += 1
        elif choice.lower() == 'p' and page > 0:
            page -= 1
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(topics):
                return topics[idx]
        elif choice:
            
            return {'type': 'custom', 'label': '✏️ 自定义', 'title': choice, 'url': ''}

        if not choice.isdigit() and not choice:
            continue


def build_ai_prompt(topic, refs, style, content_type):

    style_config = STYLES.get(style, STYLES['conversational'])
    is_answer = content_type == 'answer'

    prompt_parts = []

    
    prompt_parts.append(f"**话题/问题**: {topic['title']}")
    if topic.get('url'):
        prompt_parts.append(f"**链接**: {topic['url']}")

    
    if is_answer:
        prompt_parts.append(f"**内容类型**: 知乎问题回答（直接回答问题，不需要单独标题）")
    else:
        prompt_parts.append(f"**内容类型**: 知乎文章（需要吸引人的标题和完整正文）")

    
    prompt_parts.append(f"**写作风格**: {style_config['name']}")
    prompt_parts.append(f"**语气要求**: {style_config['tone']}")
    prompt_parts.append(f"**结构建议**: {style_config['structure']}")
    prompt_parts.append(f"**参考长度**: {style_config['length']}")

    
    if refs:
        prompt_parts.append(f"\n**参考资料**:")
        for i, ref in enumerate(refs):
            prompt_parts.append(f"  {i+1}. {ref[:2000]}")

    prompt_parts.append(f"\n**要求**:")
    prompt_parts.append(f"- 开头要吸引人，符合知乎社区氛围")
    prompt_parts.append(f"- 内容有观点、有论据，避免泛泛而谈")
    prompt_parts.append(f"- 可以适当使用知乎常见的排版方式（小标题、加粗、引用等）")
    prompt_parts.append(f"- 结尾要有互动感，引导读者评论讨论")
    if is_answer:
        prompt_parts.append(f"- 直接回答问题，不需要'谢邀'之类的客套开头")
    else:
        prompt_parts.append(f"- 提供3个备选标题供选择")

    return '\n'.join(prompt_parts)


def generate_content(prompt):

    
    

    system_msg = '''你是一位资深的知乎内容创作者，擅长各种写作风格。

请根据以下要求生成一篇知乎内容。回复格式:

如果是文章(article)，请用以下格式回复:
---TITLE---
选定的标题
---TITLE---
---BODY---
正文内容（Markdown格式）
---BODY---

如果是回答(answer)，直接回复正文:
---BODY---
正文内容（Markdown格式）
---BODY---'''

    return {
        'system': system_msg,
        'prompt': prompt,
        'type': 'ai_request'  
    }


def save_draft(title, body, content_type, topic_info, style, refs):

    os.makedirs(DRAFTS_DIR, exist_ok=True)

    ts = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')
    safe_title = re.sub(r'[^\w\s-]', '', title or 'draft')[:30]
    filename = f'{ts}_{safe_title}.json'

    draft = {
        'title': title,
        'body': body,
        'content_type': content_type,
        'topic': topic_info,
        'style': style,
        'references': refs,
        'created_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
        'status': 'draft'
    }

    path = os.path.join(DRAFTS_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)

    return path


def list_drafts():

    if not os.path.exists(DRAFTS_DIR):
        return []

    drafts = []
    for f in sorted(os.listdir(DRAFTS_DIR), reverse=True):
        if f.endswith('.json'):
            path = os.path.join(DRAFTS_DIR, f)
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    d = json.load(fh)
                d['_file'] = f
                drafts.append(d)
            except:
                pass
    return drafts


def main():
    print("=" * 60)
    print("  知乎 AI 内容写作工具 v1.0")
    print("=" * 60)

    
    args = sys.argv[1:]
    topic_source = 'all'
    custom_topic = None
    ref_urls = []
    style = 'professional'
    content_type = 'article'

    i = 0
    while i < len(args):
        if args[i] == '--from' and i + 1 < len(args):
            if args[i+1] in ('hot', 'recommend', 'invited', 'all'):
                topic_source = args[i+1]
                i += 1
        elif args[i] == '--topic' and i + 1 < len(args):
            custom_topic = args[i+1]
            i += 1
        elif args[i] == '--ref' and i + 1 < len(args):
            ref_urls = [u.strip() for u in args[i+1].split(',') if u.strip()]
            i += 1
        elif args[i] == '--style' and i + 1 < len(args):
            if args[i+1] in STYLES:
                style = args[i+1]
                i += 1
        elif args[i] == '--type' and i + 1 < len(args):
            if args[i+1] in CONTENT_TYPES:
                content_type = args[i+1]
                i += 1
        i += 1

    
    print("\n[1/4] 选择写作话题")
    topic = None

    if custom_topic:
        topic = {'type': 'custom', 'label': '✏️ 自定义', 'title': custom_topic, 'url': ''}
        print(f"  ✅ 使用自定义话题: {custom_topic}")
    else:
        topics = get_topics(topic_source, limit=20)
        if not topics:
            print("  ⚠️  数据库中没有话题数据，请先运行 save_to_db.py 采集数据")
            print("  使用自定义话题模式...")
            custom = input("  请输入话题: ").strip()
            if custom:
                topic = {'type': 'custom', 'label': '✏️ 自定义', 'title': custom, 'url': ''}

        if not topic:
            topic = select_topic_interactive(topics)

    if not topic:
        print("  ❌ 未选择话题，退出")
        return

    print(f"\n  已选择: {topic['title'][:60]}")

    
    print("\n[2/4] 设置写作参数")

    
    print(f"\n  内容类型:")
    for k, v in CONTENT_TYPES.items():
        mark = ' ◀' if k == content_type else ''
        print(f"    [{k}] {v}{mark}")
    ct = input(f"  选择 [{content_type}]: ").strip()
    if ct in CONTENT_TYPES:
        content_type = ct

    
    print(f"\n  写作风格:")
    for k, v in STYLES.items():
        mark = ' ◀' if k == style else ''
        print(f"    [{k}] {v['name']} - {v['tone'][:40]}...{mark}")
    st = input(f"  选择 [{style}]: ").strip()
    if st in STYLES:
        style = st

    print(f"\n  ✅ 类型: {CONTENT_TYPES[content_type]} | 风格: {STYLES[style]['name']}")

    
    print("\n[3/4] 添加参考资料（可选，直接回车跳过）")

    refs = []
    if ref_urls:
        print("  正在获取参考链接内容...")
        for url in ref_urls:
            content = fetch_url_content(url)
            if not content.startswith('[无法'):
                refs.append(f"[来源: {url}]\n{content}")
                print(f"  ✅ {url}")
            else:
                print(f"  ⚠️  {url} - 无法获取")
    else:
        while True:
            ref = input("  粘贴链接/文本（或回车跳过）: ").strip()
            if not ref:
                break
            if ref.startswith('http'):
                content = fetch_url_content(ref)
                if not content.startswith('[无法'):
                    refs.append(f"[来源: {ref}]\n{content}")
                    print(f"  ✅ 已获取: {ref}")
                else:
                    print(f"  ⚠️  无法获取该链接")
            else:
                refs.append(ref)
                print(f"  ✅ 已添加文本 ({len(ref)}字)")

    if refs:
        print(f"  📎 共 {len(refs)} 份参考资料")

    
    print("\n[4/4] 准备 AI 生成...")
    prompt = build_ai_prompt(topic, refs, style, content_type)
    result = generate_content(prompt)

    
    prompt_file = os.path.join(DRAFTS_DIR, 'latest_prompt.json')
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    with open(prompt_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"""
{'='*60}
  ✅ 写作参数已准备好!

  话题: {topic['title'][:50]}
  类型: {CONTENT_TYPES[content_type]}
  风格: {STYLES[style]['name']}
  参考资料: {len(refs)} 份
  提示词已保存: {prompt_file}

  下一步:
    python publish.py --draft latest   # 生成内容并发布
{'='*60}
""")

    
    print("---PROMPT_START---")
    print(result['system'])
    print("\n---\n")
    print(result['prompt'])
    print("---PROMPT_END---")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3














import sys
import os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))
from db import (query_articles, query_stats, query_logs, query_questions,
                today_str, init_database, get_db)


SOURCE_LABELS = {
    'waiting': '等你来答',
    'invited': '邀请回答',
    'recommend': '推荐问题',
    'hot': '热榜',
}


def print_separator(title=None):
    if title:
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}")
    else:
        print(f"{'='*70}")


def format_heat(h):

    if h is None:
        return '-'
    if h >= 10000000:
        return f"{h/10000000:.1f}kW"
    if h >= 10000:
        return f"{h/10000:.1f}W"
    return str(h)


def format_count(n):

    if n is None:
        return '-'
    if n >= 10000:
        return f"{n/10000:.1f}W"
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(n)


def print_articles(articles):

    for item in articles:
        rank = item.get('rank', '-')
        heat = format_heat(item.get('heat'))
        title = (item.get('title', '') or '')[:60]
        url = (item.get('url', '') or '')[:50]
        print(f"  #{rank:>3}  {heat:>8}  {title}")
        if len(articles) <= 10:
            print(f"       {url}")
    print(f"  --- 共 {len(articles)} 条 ---")


def print_questions_list(questions, verbose=False):

    for item in questions:
        title = (item.get('title', '') or '')[:60]
        answers = format_count(item.get('answer_count', 0))
        followers = format_count(item.get('follower_count', 0))
        views = format_count(item.get('view_count', 0))
        source = SOURCE_LABELS.get(item.get('source', ''), item.get('source', '-'))
        question_time = item.get('question_time', '') or ''
        reason = (item.get('recommend_reason', '') or '')[:40]

        
        if question_time and len(question_time) >= 10:
            time_str = question_time[:10]
        else:
            time_str = '-'

        
        print(f"  [{source}] {title}")
        meta_parts = [f"👁 {views}"]
        if answers: meta_parts.append(f"💬 {answers}答")
        if followers: meta_parts.append(f"👥 {followers}关")
        if time_str: meta_parts.append(f"🕐 {time_str}")
        print(f"       {'  '.join(meta_parts)}")

        
        if reason and verbose:
            print(f"       💡 推荐: {reason}")

        
        if len(questions) <= 5:
            url = (item.get('url', '') or '')[:70]
            print(f"       🔗 {url}")

        
        tags = (item.get('tags', '') or '')
        if tags and verbose:
            print(f"       🏷 {tags}")

    print(f"  --- 共 {len(questions)} 条 ---")


def print_logs(logs):

    for log in logs:
        source = log.get('source', '-')
        mode = log.get('mode', '-')
        auth = log.get('auth_method', '-') or '-'
        count = log.get('count', 0)
        new_c = log.get('new_count', 0)
        status = log.get('status', '-')
        started = log.get('started_at', 0)
        duration = log.get('duration_ms', 0)

        
        from datetime import datetime, timezone, timedelta
        TZ = timezone(timedelta(hours=8))
        ts = datetime.fromtimestamp(started, TZ).strftime('%m-%d %H:%M') if started else '-'

        mode_label = SOURCE_LABELS.get(mode, mode)
        icon = 'OK' if status == 'success' else 'ERR'
        print(f"  [{icon}] {ts}  {mode_label:>8}  {auth:>15}  {new_c:>3}新/{count:>3}总  {duration}ms")

    print(f"  --- 共 {len(logs)} 条 ---")


def query_questions_by_source(fetch_date=None, source=None, keyword=None, limit=200):

    conn = get_db()
    cursor = conn.cursor()

    conditions = []
    params = {}

    if fetch_date:
        conditions.append("fetch_date = :fetch_date")
        params['fetch_date'] = fetch_date

    if source:
        conditions.append("source = :source")
        params['source'] = source

    if keyword:
        conditions.append("title LIKE :keyword")
        params['keyword'] = f'%{keyword}%'

    where = ' AND '.join(conditions) if conditions else '1=1'
    query = f"SELECT * FROM questions WHERE {where} ORDER BY fetch_date DESC, follower_count DESC LIMIT :limit"
    params['limit'] = limit

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def main():
    init_database()

    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 query.py today              # 查看今天的热榜")
        print("  python3 query.py date 2026-03-15    # 查看指定日期")
        print("  python3 query.py stats 7            # 查看最近N天统计")
        print("  python3 query.py logs               # 查看抓取日志")
        print("  python3 query.py questions          # 查看今日问题")
        print("  python3 query.py questions recommend # 只看推荐问题")
        print("  python3 query.py questions invited   # 只看邀请回答")
        print("  python3 query.py questions -v       # 详细模式")
        print("  python3 query.py all                # 查看全部")
        return

    cmd = sys.argv[1]
    verbose = '-v' in sys.argv or '--verbose' in sys.argv

    if cmd == 'today':
        articles = query_articles(fetch_date=today_str())
        print_separator(f"今日热榜 ({today_str()})")
        print_articles(articles)

    elif cmd == 'date':
        date_str = sys.argv[2] if len(sys.argv) > 2 else today_str()
        articles = query_articles(fetch_date=date_str)
        print_separator(f"热榜 ({date_str})")
        print_articles(articles)

    elif cmd == 'stats':
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        stats = query_stats(days)
        print_separator(f"最近{days}天统计")
        for row in stats:
            print(f"  {row['fetch_date']}  {row['article_type']:>6}  {row['cnt']:>4} 条")
        print(f"  --- 共 {len(stats)} 行 ---")

    elif cmd == 'logs':
        logs = query_logs()
        print_separator("抓取日志")
        print_logs(logs)

    elif cmd in ('questions', 'question', 'q'):
        source_filter = None
        
        for i, arg in enumerate(sys.argv):
            if arg in ('recommend', 'recommended', 'invited', 'invite', 'waiting'):
                source_filter = 'invited' if arg in ('invited', 'invite') else arg
                if source_filter == 'recommended':
                    source_filter = 'recommend'

        if source_filter:
            questions = query_questions_by_source(fetch_date=today_str(), source=source_filter)
            label = SOURCE_LABELS.get(source_filter, source_filter)
            print_separator(f"今日{label} ({today_str()})")
        else:
            questions = query_questions(fetch_date=today_str())
            print_separator(f"今日问题列表 ({today_str()})")
        print_questions_list(questions, verbose=verbose)

    elif cmd == 'all':
        
        articles = query_articles(fetch_date=today_str())
        print_separator(f"今日热榜 ({today_str()})")
        print_articles(articles)
        
        questions = query_questions(fetch_date=today_str())
        print_separator(f"今日问题 ({today_str()})")
        print_questions_list(questions, verbose=verbose)
        
        logs = query_logs(10)
        print_separator("最近10条抓取日志")
        print_logs(logs)

        
        print_separator("问题来源分布")
        sources = {}
        for q in questions:
            s = q.get('source', 'other')
            sources[s] = sources.get(s, 0) + 1
        for s, c in sorted(sources.items(), key=lambda x: -x[1]):
            label = SOURCE_LABELS.get(s, s)
            print(f"  {label:>8}: {c:>4} 条")

    else:
        print(f"未知命令: {cmd}")


if __name__ == '__main__':
    main()

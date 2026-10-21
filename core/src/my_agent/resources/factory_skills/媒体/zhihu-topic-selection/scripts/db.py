#!/usr/bin/env python3





import sys
import sqlite3


if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass
import os
import json
import hashlib
from datetime import datetime, timezone, timedelta


TZ_BEIJING = timezone(timedelta(hours=8))


DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
DB_PATH = os.path.join(DB_DIR, 'zhihu.db')


def get_db():

    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate_questions_columns(cursor):

    try:
        cursor.execute("SELECT view_count FROM questions LIMIT 0")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE questions ADD COLUMN view_count INTEGER DEFAULT 0")
    try:
        cursor.execute("SELECT question_time FROM questions LIMIT 0")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE questions ADD COLUMN question_time TEXT")
    try:
        cursor.execute("SELECT recommend_reason FROM questions LIMIT 0")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE questions ADD COLUMN recommend_reason TEXT")


def init_database():

    conn = get_db()
    cursor = conn.cursor()

    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY,
            platform TEXT DEFAULT 'zhihu',
            article_type TEXT DEFAULT 'hot',
            rank INTEGER,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            heat INTEGER,
            author TEXT,
            summary TEXT,
            published_at INTEGER,
            fetched_at INTEGER,
            fetch_date TEXT,
            raw_data TEXT,
            UNIQUE(url, fetch_date)
        )
    ''')

    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY,
            platform TEXT DEFAULT 'zhihu',
            qid TEXT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            answer_count INTEGER DEFAULT 0,
            follower_count INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'waiting',
            tags TEXT,
            question_time TEXT,
            recommend_reason TEXT,
            fetched_at INTEGER,
            fetch_date TEXT,
            raw_data TEXT,
            UNIQUE(url, fetch_date)
        )
    ''')

    
    _migrate_questions_columns(cursor)

    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fetch_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            mode TEXT NOT NULL,
            auth_method TEXT,
            count INTEGER DEFAULT 0,
            new_count INTEGER DEFAULT 0,
            updated_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'success',
            error_message TEXT,
            started_at INTEGER,
            finished_at INTEGER,
            duration_ms INTEGER
        )
    ''')

    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(fetch_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_type ON articles(article_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_type_date ON articles(article_type, fetch_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_questions_date ON questions(fetch_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fetch_logs_date ON fetch_logs(started_at)')

    conn.commit()
    conn.close()
    return True


def url_to_id(url):

    return hashlib.sha256(url.encode()).hexdigest()[:32]


def now_ts():

    return int(datetime.now(TZ_BEIJING).timestamp())


def today_str():

    return datetime.now(TZ_BEIJING).strftime('%Y-%m-%d')




def save_articles(articles, article_type='hot'):

    conn = get_db()
    cursor = conn.cursor()
    new_count = 0
    updated_count = 0
    ts = now_ts()
    date_str = today_str()

    for item in articles:
        url = item.get('url', '')
        article_id = url_to_id(url)

        row = dict(item)
        row['id'] = article_id
        row['article_type'] = article_type
        row['platform'] = item.get('platform', 'zhihu')
        row['fetched_at'] = ts
        row['fetch_date'] = date_str
        row['summary'] = item.get('summary', '')
        row['author'] = item.get('author', '')
        row['published_at'] = item.get('published_at', 0)
        row['raw_data'] = item.get('raw_data', json.dumps(item, ensure_ascii=False))
        row['heat'] = item.get('heat', 0)
        row['rank'] = item.get('rank', 0)

        try:
            cursor.execute('''
                INSERT INTO articles (id, platform, article_type, rank, title, url, heat,
                      author, summary, published_at, fetched_at, fetch_date, raw_data)
                VALUES (:id, :platform, :article_type, :rank, :title, :url, :heat,
                        :author, :summary, :published_at, :fetched_at, :fetch_date, :raw_data)
            ''', row)
            new_count += 1
        except sqlite3.IntegrityError:
            
            cursor.execute('''
                UPDATE articles SET rank=:rank, title=:title, heat=:heat,
                       author=:author, summary=:summary, raw_data=:raw_data,
                       fetched_at=:fetched_at
                WHERE url=:url AND fetch_date=:fetch_date
            ''', row)
            updated_count += 1

    conn.commit()
    conn.close()
    return new_count, updated_count


def query_articles(fetch_date=None, article_type='hot', keyword=None, min_heat=None, limit=200):

    conn = get_db()
    cursor = conn.cursor()

    conditions = []
    params = {}

    if fetch_date:
        if isinstance(fetch_date, list) and len(fetch_date) == 2:
            conditions.append("fetch_date >= :date_from AND fetch_date <= :date_to")
            params['date_from'] = fetch_date[0]
            params['date_to'] = fetch_date[1]
        else:
            conditions.append("fetch_date = :fetch_date")
            params['fetch_date'] = fetch_date

    if article_type:
        conditions.append("article_type = :article_type")
        params['article_type'] = article_type

    if keyword:
        conditions.append("title LIKE :keyword")
        params['keyword'] = f'%{keyword}%'

    if min_heat is not None:
        conditions.append("heat >= :min_heat")
        params['min_heat'] = min_heat

    where = ' AND '.join(conditions) if conditions else '1=1'
    query = f"SELECT * FROM articles WHERE {where} ORDER BY fetch_date DESC, rank ASC LIMIT :limit"
    params['limit'] = limit

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def query_stats(days=7):

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT fetch_date, article_type, COUNT(*) as cnt
        FROM articles
        WHERE fetch_date >= date(:today, :offset_days)
        GROUP BY fetch_date, article_type
        ORDER BY fetch_date DESC
    ''', {'today': today_str(), 'offset_days': f'-{days} days'})
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows




def save_questions(questions):

    conn = get_db()
    cursor = conn.cursor()
    new_count = 0
    updated_count = 0
    ts = now_ts()
    date_str = today_str()

    for item in questions:
        url = item.get('url', '')
        qid = url_to_id(url)

        row = dict(item)
        row['id'] = qid
        row['platform'] = item.get('platform', 'zhihu')
        row['qid'] = item.get('qid', '')
        row['source'] = item.get('source', 'waiting')
        row['fetched_at'] = ts
        row['fetch_date'] = date_str
        row['answer_count'] = item.get('answer_count', 0)
        row['follower_count'] = item.get('follower_count', 0)
        row['view_count'] = item.get('view_count', 0)
        row['tags'] = item.get('tags', '')
        row['question_time'] = item.get('question_time', '')
        row['recommend_reason'] = item.get('recommend_reason', '')
        row['raw_data'] = item.get('raw_data', json.dumps(item, ensure_ascii=False))

        try:
            cursor.execute('''
                INSERT INTO questions (id, platform, qid, title, url, answer_count,
                      follower_count, view_count, source, tags, question_time,
                      recommend_reason, fetched_at, fetch_date, raw_data)
                VALUES (:id, :platform, :qid, :title, :url, :answer_count,
                        :follower_count, :view_count, :source, :tags, :question_time,
                        :recommend_reason, :fetched_at, :fetch_date, :raw_data)
            ''', row)
            new_count += 1
        except sqlite3.IntegrityError:
            cursor.execute('''
                UPDATE questions SET title=:title, answer_count=:answer_count,
                       follower_count=:follower_count, view_count=:view_count,
                       tags=:tags, question_time=:question_time,
                       recommend_reason=:recommend_reason, raw_data=:raw_data,
                       fetched_at=:fetched_at
                WHERE url=:url AND fetch_date=:fetch_date
            ''', row)
            updated_count += 1

    conn.commit()
    conn.close()
    return new_count, updated_count


def query_questions(fetch_date=None, keyword=None, limit=200):

    conn = get_db()
    cursor = conn.cursor()

    conditions = []
    params = {}

    if fetch_date:
        conditions.append("fetch_date = :fetch_date")
        params['fetch_date'] = fetch_date

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




def log_fetch(source, mode, auth_method=None, count=0, new_count=0, updated_count=0,
              status='success', error_message=None, started_at=None, finished_at=None):

    conn = get_db()
    cursor = conn.cursor()
    duration = (finished_at - started_at) * 1000 if (started_at and finished_at) else 0

    cursor.execute('''
        INSERT INTO fetch_logs (source, mode, auth_method, count, new_count, updated_count,
               status, error_message, started_at, finished_at, duration_ms)
        VALUES (:source, :mode, :auth_method, :count, :new_count, :updated_count,
                :status, :error_message, :started_at, :finished_at, :duration_ms)
    ''', {
        'source': source, 'mode': mode, 'auth_method': auth_method,
        'count': count, 'new_count': new_count, 'updated_count': updated_count,
        'status': status, 'error_message': error_message,
        'started_at': started_at, 'finished_at': finished_at,
        'duration_ms': duration
    })

    conn.commit()
    conn.close()


def query_logs(limit=50):

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM fetch_logs ORDER BY started_at DESC LIMIT :limit', {'limit': limit})
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


if __name__ == '__main__':
    init_database()
    print(f"数据库初始化完成: {DB_PATH}")

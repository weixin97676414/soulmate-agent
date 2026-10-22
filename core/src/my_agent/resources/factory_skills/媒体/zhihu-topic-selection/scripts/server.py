#!/usr/bin/env python3


















import sys
import os
import json
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

from db import init_database, query_articles, query_questions, today_str, get_db
from content_writer import build_ai_prompt, save_draft, list_drafts, fetch_url_content, STYLES

PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))
DRAFTS_DIR = os.path.join(PROJECT_DIR, 'data', 'drafts')
TASKS_DIR = os.path.join(DRAFTS_DIR, 'tasks')
CONFIG_FILE = os.path.join(PROJECT_DIR, 'config', 'fallback-sources.json')

TZ = timezone(timedelta(hours=8))


class APIHandler(BaseHTTPRequestHandler):


    def log_message(self, format, *args):

        print(f"  [{self.command}] {self.path}")

    def _set_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,DELETE,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self._set_cors()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        params = parse_qs(parsed.query)

        try:
            
            if path == '/api/topics':
                source = params.get('source', ['all'])[0]
                limit = int(params.get('limit', ['30'])[0])
                topics = self._get_topics(source, limit)
                self._json({'data': topics, 'count': len(topics)})

            
            elif path == '/api/drafts':
                drafts = list_drafts()
                result = []
                for d in drafts:
                    result.append({
                        'id': d.get('_file', ''),
                        'title': (d.get('title') or d.get('topic', {}).get('title', '无标题'))[:60],
                        'content_type': d.get('content_type', 'article'),
                        'style': d.get('style', 'professional'),
                        'status': d.get('status', 'draft'),
                        'created_at': d.get('created_at', ''),
                        'body_length': len(d.get('body', '')),
                    })
                self._json({'data': result, 'count': len(result)})

            
            elif path.startswith('/api/drafts/'):
                draft_id = path.split('/')[-1]
                draft_path = os.path.join(DRAFTS_DIR, draft_id)
                if os.path.exists(draft_path):
                    with open(draft_path, 'r', encoding='utf-8') as f:
                        draft = json.load(f)
                    draft['id'] = draft_id
                    self._json(draft)
                else:
                    self._json({'error': '草稿不存在'}, 404)

            
            elif path == '/api/cookie/status':
                cookie_ok = self._check_cookie()
                self._json({'available': cookie_ok})

            
            elif path == '/api/styles':
                result = {}
                for k, v in STYLES.items():
                    result[k] = {'name': v['name'], 'tone': v['tone'][:60]}
                self._json(result)

            
            elif path.startswith('/api/generate/'):
                task_id = path.split('/')[-1]
                task_path = os.path.join(TASKS_DIR, f'{task_id}.json')
                if os.path.exists(task_path):
                    with open(task_path, 'r', encoding='utf-8') as f:
                        task = json.load(f)
                    self._json(task)
                else:
                    self._json({'error': '任务不存在'}, 404)

            else:
                self._json({'error': 'not found'}, 404)

        except Exception as e:
            self._json({'error': str(e)}, 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        body = self._read_body()

        try:
            
            if path == '/api/generate':
                topic = body.get('topic', {})
                refs = body.get('refs', [])
                style = body.get('style', 'professional')
                content_type = body.get('content_type', 'article')

                if refs and isinstance(refs, list):
                    resolved_refs = []
                    for r in refs:
                        if r.startswith('http'):
                            content = fetch_url_content(r)
                            resolved_refs.append(f"[来源: {r}]\n{content}" if not content.startswith('[无法') else r)
                        else:
                            resolved_refs.append(r)
                    refs = resolved_refs

                prompt = build_ai_prompt(topic, refs, style, content_type)

                
                import uuid
                task_id = uuid.uuid4().hex[:12]
                os.makedirs(TASKS_DIR, exist_ok=True)

                task = {
                    'id': task_id,
                    'prompt': prompt,
                    'topic': topic.get('title', ''),
                    'style': style,
                    'content_type': content_type,
                    'refs': refs,
                    'status': 'awaiting_confirm',
                    'created_at': datetime.now(TZ).isoformat(),
                    'result_title': None,
                    'result_body': None,
                }
                with open(os.path.join(TASKS_DIR, f'{task_id}.json'), 'w', encoding='utf-8') as f:
                    json.dump(task, f, ensure_ascii=False, indent=2)

                self._json({
                    'task_id': task_id,
                    'status': 'awaiting_confirm',
                    'prompt': prompt,
                    'message': '指令已生成，请确认后开始写作'
                })

            
            elif path.startswith('/api/generate/') and path.endswith('/confirm'):
                task_id = path.split('/')[-2]  
                task_path = os.path.join(TASKS_DIR, f'{task_id}.json')
                if not os.path.exists(task_path):
                    self._json({'error': '任务不存在'}, 404)
                    return

                with open(task_path, 'r', encoding='utf-8') as f:
                    task = json.load(f)

                task['status'] = 'confirmed'
                with open(task_path, 'w', encoding='utf-8') as f:
                    json.dump(task, f, ensure_ascii=False, indent=2)

                
                current_file = os.path.join(TASKS_DIR, 'current.json')
                with open(current_file, 'w', encoding='utf-8') as f:
                    json.dump(task, f, ensure_ascii=False, indent=2)

                self._json({
                    'status': 'confirmed',
                    'message': '指令已确认，AI 正在生成内容...'
                })

            
            elif path.startswith('/api/generate/') and not path.endswith('/confirm'):
                task_id = path.split('/')[-1]
                task_path = os.path.join(TASKS_DIR, f'{task_id}.json')
                if os.path.exists(task_path):
                    with open(task_path, 'r', encoding='utf-8') as f:
                        task = json.load(f)
                    self._json(task)
                else:
                    self._json({'error': '任务不存在'}, 404)

            
            elif path == '/api/drafts':
                title = body.get('title', '')
                content = body.get('body', '')
                content_type = body.get('content_type', 'article')
                topic = body.get('topic', {})
                style = body.get('style', 'professional')
                refs = body.get('refs', [])

                if not content:
                    self._json({'error': '内容不能为空'}, 400)
                    return

                path = save_draft(title, content, content_type, topic, style, refs)
                self._json({'success': True, 'path': path})

            
            elif path == '/api/publish':
                draft_id = body.get('draft_id', '')
                mode = body.get('mode', 'article')
                urls = body.get('urls', [])

                
                import subprocess
                node = self._get_node()
                publisher_script = os.path.join(os.path.dirname(__file__), 'publisher.js')
                draft_path = os.path.join(DRAFTS_DIR, draft_id)

                if not os.path.exists(draft_path):
                    self._json({'error': '草稿不存在'}, 404)
                    return

                cmd = [node, publisher_script, mode, '--draft', draft_path]
                if urls:
                    cmd.extend(['--urls', ','.join(urls)])

                
                subprocess.Popen(cmd, cwd=PROJECT_DIR,
                               creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0)

                self._json({'success': True, 'message': '发布已启动，请在浏览器窗口中查看进度'})

            
            elif path == '/api/cookie/refresh':
                import subprocess
                node = self._get_node()
                cookie_script = os.path.join(os.path.dirname(__file__), 'auto_cookie.js')

                result = subprocess.run([node, cookie_script, '--headless', '--save-only'],
                                      cwd=PROJECT_DIR, capture_output=True, text=True,
                                      encoding='utf-8', errors='replace', timeout=30)
                cookie_ok = self._check_cookie()
                self._json({'success': cookie_ok, 'available': cookie_ok})

            else:
                self._json({'error': 'not found'}, 404)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._json({'error': str(e)}, 500)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')

        try:
            if path.startswith('/api/drafts/'):
                draft_id = path.split('/')[-1]
                draft_path = os.path.join(DRAFTS_DIR, draft_id)
                if os.path.exists(draft_path):
                    os.unlink(draft_path)
                    self._json({'success': True})
                else:
                    self._json({'error': '草稿不存在'}, 404)
        except Exception as e:
            self._json({'error': str(e)}, 500)

    def _get_topics(self, source, limit):

        init_database()
        topics = []

        if source in ('hot', 'all'):
            articles = query_articles(article_type='hot', limit=limit)
            for a in articles:
                topics.append({
                    'type': 'hot', 'label': '🔥 热榜',
                    'title': a.get('title', ''), 'url': a.get('url', ''),
                    'heat': a.get('heat', 0),
                    'summary': (a.get('summary', '') or '')[:100]
                })

        if source in ('recommend', 'all'):
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT * FROM questions WHERE source='recommend' ORDER BY follower_count DESC LIMIT ?", (limit,))
            for r in c.fetchall():
                q = dict(r)
                topics.append({
                    'type': 'recommend', 'label': '💡 推荐',
                    'title': q.get('title', ''), 'url': q.get('url', ''),
                    'followers': q.get('follower_count', 0),
                    'answers': q.get('answer_count', 0),
                    'reason': q.get('recommend_reason', '')
                })
            conn.close()

        if source in ('invited', 'all'):
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT * FROM questions WHERE source='invited' ORDER BY follower_count DESC LIMIT ?", (limit,))
            for r in c.fetchall():
                q = dict(r)
                topics.append({
                    'type': 'invited', 'label': '📨 邀请',
                    'title': q.get('title', ''), 'url': q.get('url', ''),
                    'followers': q.get('follower_count', 0),
                    'answers': q.get('answer_count', 0),
                })
            conn.close()

        return topics

    def _check_cookie(self):
        try:
            if not os.path.exists(CONFIG_FILE):
                return False
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            cookies = config.get('cookie', {})
            return bool(cookies.get('z_c0'))
        except:
            return False

    def _get_node(self):
        import shutil
        home = os.path.expanduser('~')
        for ver in ['22.12.0', '22.22.2']:
            p = os.path.join(home, '.skill-runtime', 'binaries', 'node', 'versions', ver, 'node.exe')
            if os.path.exists(p):
                return p
        return shutil.which('node') or 'node'


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765

    init_database()
    os.makedirs(DRAFTS_DIR, exist_ok=True)

    server = HTTPServer(('127.0.0.1', port), APIHandler)
    print(f'╔══════════════════════════════════════════════════╗')
    print(f'║  知乎工具 API 服务器                             ║')
    print(f'║  Zhihu Tools API Server                          ║')
    print(f'╠══════════════════════════════════════════════════╣')
    print(f'║  地址: http://127.0.0.1:{port}                    ║')
    print(f'║  API:  http://127.0.0.1:{port}/api/...             ║')
    print(f'╚══════════════════════════════════════════════════╝')
    print(f'  按 Ctrl+C 停止服务器')
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n  服务器已停止')
        server.shutdown()


if __name__ == '__main__':
    main()

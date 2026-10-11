#!/usr/bin/env python3
"""
HTML可视化报告生成器 - HTML Visualization Report Generator

功能:
  Date Filter - 选择具体日期或日期范围
  Keyword Search - 实时搜索标题
  Heat Filter - 按最小热度值筛选
  Ranking Display - Top 3 特殊颜色标识
  Data Stats - 实时显示筛选结果数量
  Questions - "等你来答"问题展示

用法:
  python3 generate_html.py
  python3 generate_html.py --open
"""

import sys
import os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json
import webbrowser

sys.path.insert(0, os.path.dirname(__file__))
from db import init_database, query_articles, query_questions, query_stats, query_logs, today_str, DB_PATH

SCRIPTS_DIR = os.path.dirname(__file__)
PROJECT_DIR = os.path.dirname(SCRIPTS_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, 'data')
OUTPUT_FILE = os.path.join(DATA_DIR, 'index.html')


def get_available_dates():
    """获取数据库中有数据的日期列表"""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT fetch_date FROM articles
        UNION
        SELECT DISTINCT fetch_date FROM questions
        ORDER BY fetch_date DESC
    ''')
    dates = [row['fetch_date'] for row in cursor.fetchall()]
    conn.close()
    return dates


def generate_html():
    """生成完整的HTML报告"""
    init_database()

    # 获取数据
    today = today_str()
    dates = get_available_dates()
    articles = query_articles(limit=500)
    questions = query_questions(limit=200)
    logs = query_logs(20)

    # JSON序列化
    dates_json = json.dumps(dates, ensure_ascii=False)
    articles_json = json.dumps(articles, ensure_ascii=False)
    questions_json = json.dumps(questions, ensure_ascii=False)
    logs_json = json.dumps(logs, ensure_ascii=False)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>知乎数据报告 - Zhihu Data Report</title>
<style>
/* ========== Reset & Base ========== */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB",
               "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
  background: #f5f7fa;
  color: #333;
  line-height: 1.6;
}}

/* ========== Header ========== */
.header {{
  background: linear-gradient(135deg, #0066ff 0%, #0052cc 100%);
  color: #fff;
  padding: 28px 40px;
  box-shadow: 0 2px 16px rgba(0,102,255,.18);
}}
.header h1 {{ font-size: 26px; font-weight: 700; letter-spacing: -.5px; }}
.header p {{ font-size: 13px; opacity: .75; margin-top: 4px; }}

/* ========== Container ========== */
.container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}

/* ========== Stats Bar ========== */
.stats-bar {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}}
.stat-card {{
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  text-align: center;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
}}
.stat-value {{ font-size: 32px; font-weight: 800; color: #0066ff; }}
.stat-label {{ font-size: 12px; color: #999; margin-top: 4px; text-transform: uppercase; letter-spacing: 1px; }}

/* ========== Tabs ========== */
.tabs {{ display: flex; gap: 0; margin-bottom: 24px; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
.tab-btn {{
  flex: 1; padding: 14px 20px; border: none; background: none; cursor: pointer;
  font-size: 14px; font-weight: 600; color: #999; transition: all .2s;
  border-bottom: 2px solid transparent;
}}
.tab-btn:hover {{ color: #555; }}
.tab-btn.active {{ color: #0066ff; border-bottom-color: #0066ff; background: #f0f5ff; }}

/* ========== Filters ========== */
.filters {{
  background: #fff; border-radius: 12px; padding: 16px 20px;
  margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.06);
  display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
}}
.filter-group {{ display: flex; align-items: center; gap: 6px; }}
.filter-group label {{ font-size: 12px; color: #666; white-space: nowrap; font-weight: 600; }}
.filter-group input, .filter-group select {{
  padding: 7px 12px; border: 1px solid #ddd; border-radius: 8px;
  font-size: 13px; outline: none; transition: border-color .2s;
}}
.filter-group input:focus, .filter-group select:focus {{ border-color: #0066ff; }}
.filter-group input {{ width: 180px; }}

.result-count {{
  margin-left: auto; font-size: 13px; color: #999; font-weight: 600;
  white-space: nowrap;
}}
.result-count strong {{ color: #0066ff; }}

/* ========== Items List ========== */
.items-list {{ display: flex; flex-direction: column; gap: 8px; }}

.item-card {{
  background: #fff; border-radius: 10px; padding: 16px 20px;
  display: flex; align-items: flex-start; gap: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,.05); transition: all .2s;
  border-left: 3px solid transparent;
}}
.item-card:hover {{ box-shadow: 0 4px 16px rgba(0,0,0,.1); transform: translateY(-1px); }}

/* Top 3 排名标识 */
.rank-badge {{
  flex-shrink: 0; width: 42px; height: 42px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; font-weight: 800; color: #aaa; background: #f0f0f0;
}}
.rank-1 {{ background: linear-gradient(135deg, #ff6b35, #f7931e); color: #fff; box-shadow: 0 2px 8px rgba(255,107,53,.3); }}
.rank-2 {{ background: linear-gradient(135deg, #a0a0a0, #808080); color: #fff; box-shadow: 0 2px 8px rgba(128,128,128,.3); }}
.rank-3 {{ background: linear-gradient(135deg, #cd7f32, #b8860b); color: #fff; box-shadow: 0 2px 8px rgba(205,127,50,.3); }}

.item-content {{ flex: 1; min-width: 0; }}
.item-title {{
  font-size: 15px; font-weight: 600; color: #222; margin-bottom: 6px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; line-height: 1.5;
}}
.item-title a {{ color: inherit; text-decoration: none; }}
.item-title a:hover {{ color: #0066ff; }}

.item-meta {{ display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: #999; }}

.heat-badge {{
  flex-shrink: 0; padding: 4px 12px; border-radius: 20px;
  font-size: 12px; font-weight: 700; color: #ff6b35; background: #fff5f0;
  white-space: nowrap;
}}

/* Questions card */
.question-card .item-card {{ border-left-color: #e8e8e8; }}

.question-tags {{
  display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px;
}}
.question-tag {{
  padding: 2px 10px; border-radius: 12px; font-size: 11px;
  background: #eef2ff; color: #5065d6;
}}

/* ========== Logs Section ========== */
.logs-section {{ margin-top: 32px; }}
.logs-section h2 {{ font-size: 18px; color: #333; margin-bottom: 12px; }}
.logs-table {{
  width: 100%; background: #fff; border-radius: 12px; overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
}}
.logs-table table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.logs-table th {{
  background: #f8f9fb; padding: 10px 14px; text-align: left;
  font-weight: 600; color: #666; font-size: 12px;
}}
.logs-table td {{ padding: 10px 14px; border-top: 1px solid #f0f0f0; }}
.log-badge {{
  padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 700;
}}
.log-badge-success {{ background: #e8f5e9; color: #2e7d32; }}
.log-badge-error {{ background: #ffebee; color: #c62828; }}

/* ========== Empty State ========== */
.empty-state {{
  text-align: center; padding: 60px 20px; color: #ccc;
}}
.empty-state .icon {{ font-size: 48px; margin-bottom: 12px; }}
.empty-state p {{ font-size: 14px; }}

/* ========== Responsive ========== */
@media (max-width: 768px) {{
  .header {{ padding: 20px; }}
  .header h1 {{ font-size: 20px; }}
  .container {{ padding: 12px; }}
  .filters {{ flex-direction: column; align-items: stretch; }}
  .filter-group input {{ width: 100%; }}
  .result-count {{ margin-left: 0; }}
}}
</style>
</head>
<body>

<div class="header">
  <h1>📊 知乎数据报告</h1>
  <p>Zhihu Data Report · 自动生成于 {today}</p>
</div>

<div class="container">
  <!-- Stats Bar -->
  <div class="stats-bar" id="statsBar"></div>

  <!-- Tabs -->
  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('hot')">🔥 热榜</button>
    <button class="tab-btn" onclick="switchTab('questions')">💬 问题列表</button>
    <button class="tab-btn" onclick="switchTab('logs')">📋 抓取日志</button>
  </div>

  <!-- Filters -->
  <div class="filters" id="filters"></div>

  <!-- Items List -->
  <div class="items-list" id="itemsList"></div>

  <!-- Empty State -->
  <div class="empty-state" id="emptyState" style="display:none">
    <div class="icon">📭</div>
    <p>暂无数据</p>
    <p style="font-size:12px;color:#bbb">运行 save_to_db.py 开始采集数据</p>
  </div>



<script>
// ============ Data ============
const ALL_ARTICLES = {articles_json};
const ALL_QUESTIONS = {questions_json};
const ALL_LOGS = {logs_json};
const ALL_DATES = {dates_json};

let currentTab = 'hot';

// ============ Utils ============
function formatHeat(h) {{
  if (!h) return '-';
  if (h >= 10000000) return (h/10000000).toFixed(1) + 'kW';
  if (h >= 10000) return (h/10000).toFixed(1) + 'W';
  return String(h);
}}

function formatTime(ts) {{
  if (!ts) return '-';
  const d = new Date(ts * 1000);
  const pad = n => String(n).padStart(2,'0');
  return `${{d.getFullYear()}}-${{pad(d.getMonth()+1)}}-${{pad(d.getDate())}} ${{pad(d.getHours())}}:${{pad(d.getMinutes())}}`;
}}

function getRankClass(rank) {{
  if (rank === 1) return 'rank-1';
  if (rank === 2) return 'rank-2';
  if (rank === 3) return 'rank-3';
  return '';
}}

// ============ Stats Bar ============
function renderStats() {{
  const totalArticles = ALL_ARTICLES.length;
  const totalQuestions = ALL_QUESTIONS.length;
  const totalLogs = ALL_LOGS.length;

  // 今日数据
  const today = new Date().toISOString().slice(0,10);
  const todayArticles = ALL_ARTICLES.filter(a => a.fetch_date === today).length;
  const todayQuestions = ALL_QUESTIONS.filter(q => q.fetch_date === today).length;
  const todayRecommend = ALL_QUESTIONS.filter(q => q.fetch_date === today && q.source === 'recommend').length;
  const todayInvited = ALL_QUESTIONS.filter(q => q.fetch_date === today && q.source === 'invited').length;

  // 最近日志成功率
  const recentLogs = ALL_LOGS.slice(0,10);
  const successCount = recentLogs.filter(l => l.status === 'success').length;
  const successRate = recentLogs.length > 0 ? Math.round(successCount / recentLogs.length * 100) : 0;

  document.getElementById('statsBar').innerHTML = `
    <div class="stat-card">
      <div class="stat-value">${{todayArticles}}</div>
      <div class="stat-label">今日热榜</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${{todayRecommend}}</div>
      <div class="stat-label">今日推荐</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${{todayInvited}}</div>
      <div class="stat-label">今日邀请</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${{todayQuestions}}</div>
      <div class="stat-label">问题总数</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${{successRate}}%</div>
      <div class="stat-label">最近成功率</div>
    </div>
  `;
}}

// ============ Tab Switching ============
function switchTab(tab) {{
  currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');

  document.getElementById('filters').style.display = 'flex';
  document.getElementById('itemsList').style.display = 'flex';
  renderFilters();
  applyFilters();
}}

// ============ Filters ============
function renderFilters() {{
  const filterDiv = document.getElementById('filters');

  if (currentTab === 'logs') {{
    filterDiv.innerHTML = `
      <div class="result-count">共 <strong>${{ALL_LOGS.length}}</strong> 条日志</div>
    `;
    return;
  }}

  const isHot = currentTab === 'hot';
  const allDates = [...new Set([
    ...ALL_ARTICLES.map(a => a.fetch_date),
    ...ALL_QUESTIONS.map(q => q.fetch_date)
  ])].sort().reverse();

  filterDiv.innerHTML = `
    <div class="filter-group">
      <label>📅 日期</label>
      <select id="filterDate" onchange="applyFilters()">
        <option value="">全部日期</option>
        ${{allDates.map(d => `<option value="${{d}}">${{d}}</option>`).join('')}}
      </select>
    </div>
    <div class="filter-group">
      <label>🔍 搜索</label>
      <input type="text" id="filterKeyword"
             placeholder="搜索标题关键词..."
             oninput="applyFilters()">
    </div>
    ${{!isHot ? `
    <div class="filter-group">
      <label>🏷 来源</label>
      <select id="filterSource" onchange="applyFilters()">
        <option value="">全部</option>
        <option value="recommend">推荐问题</option>
        <option value="invited">邀请回答</option>
        <option value="waiting">等你来答</option>
      </select>
    </div>
    ` : ''}}
    ${{isHot ? `
    <div class="filter-group">
      <label>🔥 最低热度</label>
      <select id="filterHeat" onchange="applyFilters()">
        <option value="0">不限</option>
        <option value="10000">1W+</option>
        <option value="50000">5W+</option>
        <option value="100000">10W+</option>
        <option value="500000">50W+</option>
        <option value="1000000">100W+</option>
      </select>
    </div>
    ` : ''}}
    <div class="result-count" id="resultCount">共 <strong>0</strong> 条</div>
  `;
}}

function applyFilters() {{
  if (currentTab === 'logs') {{
    renderLogs();
    return;
  }}

  const isHot = currentTab === 'hot';
  const dateFilter = document.getElementById('filterDate')?.value || '';
  const keywordFilter = (document.getElementById('filterKeyword')?.value || '').toLowerCase();
  const heatFilter = parseInt(document.getElementById('filterHeat')?.value || '0', 10);
  const sourceFilter = document.getElementById('filterSource')?.value || '';

  let data = isHot ? [...ALL_ARTICLES] : [...ALL_QUESTIONS];

  // Date filter
  if (dateFilter) {{
    data = data.filter(item => item.fetch_date === dateFilter);
  }}

  // Keyword filter
  if (keywordFilter) {{
    data = data.filter(item => (item.title || '').toLowerCase().includes(keywordFilter));
  }}

  // Heat filter (hot only)
  if (isHot && heatFilter > 0) {{
    data = data.filter(item => (item.heat || 0) >= heatFilter);
  }}

  // Source filter (questions only)
  if (!isHot && sourceFilter) {{
    data = data.filter(item => item.source === sourceFilter);
  }}

  // Sort
  if (isHot) {{
    data.sort((a, b) => (a.rank || 999) - (b.rank || 999));
  }} else {{
    data.sort((a, b) => (b.follower_count || 0) - (a.follower_count || 0));
  }}

  document.getElementById('resultCount').innerHTML = `共 <strong>${{data.length}}</strong> 条`;

  if (isHot) {{
    renderArticles(data);
  }} else {{
    renderQuestions(data);
  }}
}}

// ============ Render Articles ============
function renderArticles(articles) {{
  const list = document.getElementById('itemsList');
  const empty = document.getElementById('emptyState');

  if (articles.length === 0) {{
    list.innerHTML = '';
    empty.style.display = 'block';
    return;
  }}

  empty.style.display = 'none';
  list.innerHTML = articles.map(item => {{
    const rankClass = getRankClass(item.rank);
    const heat = formatHeat(item.heat);
    const url = item.url || '#';
    return `
    <div class="item-card">
      <div class="rank-badge ${{rankClass}}">${{item.rank || '-'}}</div>
      <div class="item-content">
        <div class="item-title">
          <a href="${{url}}" target="_blank" rel="noopener">${{item.title || '(无标题)'}}</a>
        </div>
        <div class="item-meta">
          ${{item.author ? `<span>✍️ ${{item.author}}</span>` : ''}}
          ${{item.fetch_date ? `<span>📅 ${{item.fetch_date}}</span>` : ''}}
        </div>
      </div>
      <div class="heat-badge">🔥 ${{heat}}</div>
    </div>
    `;
  }}).join('');
}}

// ============ Render Questions ============
function renderQuestions(questions) {{
  const list = document.getElementById('itemsList');
  const empty = document.getElementById('emptyState');

  if (questions.length === 0) {{
    list.innerHTML = '';
    empty.style.display = 'block';
    return;
  }}

  empty.style.display = 'none';

  function fmtCount(n) {{
    if (!n && n !== 0) return '-';
    if (n >= 10000) return (n/10000).toFixed(1) + 'W';
    if (n >= 1000) return (n/1000).toFixed(1) + 'K';
    return String(n);
  }}

  function getSourceIcon(source) {{
    if (source === 'invited') return '📨';
    if (source === 'waiting') return '⏳';
    if (source === 'recommend') return '💡';
    return '💬';
  }}

  function getSourceLabel(source) {{
    if (source === 'invited') return '邀请回答';
    if (source === 'waiting') return '等你来答';
    if (source === 'recommend') return '推荐问题';
    return source || '未知';
  }}

  function fmtTime(raw) {{
    if (!raw) return '';
    return String(raw).substring(0, 10);
  }}

  list.innerHTML = questions.map(item => {{
    const url = item.url || '#';
    const tags = (item.tags || '').split(',').filter(Boolean);
    const views = fmtCount(item.view_count);
    const answers = fmtCount(item.answer_count);
    const followers = fmtCount(item.follower_count);
    const qTime = fmtTime(item.question_time);
    const reason = (item.recommend_reason || '').substring(0, 80);
    const srcIcon = getSourceIcon(item.source);
    const srcLabel = getSourceLabel(item.source);

    return `
    <div class="item-card question-card">
      <div class="rank-badge" style="background:${{item.source === 'recommend' ? '#fff8e1' : '#eef2ff'}};">${{srcIcon}}</div>
      <div class="item-content">
        <div class="item-title">
          <a href="${{url}}" target="_blank" rel="noopener">${{item.title || '(无标题)'}}</a>
        </div>
        <div class="item-meta">
          <span>👁 ${{views}} 浏览</span>
          <span>💬 ${{answers}} 回答</span>
          <span>👥 ${{followers}} 关注</span>
          ${{qTime ? `<span>🕐 ${{qTime}}</span>` : ''}}
          <span style="font-weight:600;color:#5065d6;">${{srcLabel}}</span>
          <span>📅 ${{item.fetch_date || '-'}}</span>
        </div>
        ${{reason ? `<div style="margin-top:6px;font-size:12px;color:#999;line-height:1.5;">💡 ${{reason}}</div>` : ''}}
        ${{tags.length > 0 ? `<div class="question-tags">${{tags.map(t => `<span class="question-tag">${{t.trim()}}</span>`).join('')}}</div>` : ''}}
      </div>
    </div>
    `;
  }}).join('');
}}

// ============ Render Logs ============
function renderLogs() {{
  const list = document.getElementById('itemsList');
  const empty = document.getElementById('emptyState');

  if (ALL_LOGS.length === 0) {{
    list.innerHTML = '';
    empty.style.display = 'block';
    return;
  }}

  empty.style.display = 'none';

  list.innerHTML = `
    <div class="logs-table">
      <table>
        <thead>
          <tr>
            <th>时间</th>
            <th>模式</th>
            <th>认证方式</th>
            <th>数量</th>
            <th>状态</th>
            <th>耗时</th>
          </tr>
        </thead>
        <tbody>
          ${{ALL_LOGS.map(log => `
            <tr>
              <td>${{formatTime(log.started_at)}}</td>
              <td>${{log.mode === 'hot' ? '🔥 热榜' : log.mode === 'recommend' ? '💡 推荐' : log.mode === 'invited' ? '📨 邀请' : '💬 问题'}}</td>
              <td>${{log.auth_method || '-'}}</td>
              <td>${{log.new_count}}新/${{log.count}}总</td>
              <td><span class="log-badge ${{log.status === 'success' ? 'log-badge-success' : 'log-badge-error'}}">${{log.status === 'success' ? '成功' : '失败'}}</span></td>
              <td>${{log.duration_ms || '-'}}ms</td>
            </tr>
          `).join('')}}
        </tbody>
      </table>
    </div>
  `;
}}

// ============ Init ============
renderStats();
renderFilters();
applyFilters();
</script>

</body>
</html>'''

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    return OUTPUT_FILE


def main():
    print("正在生成HTML可视化报告...")

    output = generate_html()

    print(f"✅ HTML报告已生成!")
    print(f"   文件: {output}")
    print(f"")
    print(f"   在浏览器中打开: file:///{output.replace(chr(92), '/')}")

    if '--open' in sys.argv:
        webbrowser.open(f'file:///{output}')

    print(f"")
    print(f"💡 提示: 运行 save_to_db.py 采集数据后，刷新页面即可看到最新数据")


if __name__ == '__main__':
    main()

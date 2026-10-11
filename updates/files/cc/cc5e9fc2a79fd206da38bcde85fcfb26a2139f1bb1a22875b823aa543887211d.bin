#!/usr/bin/env python3
"""
看板生成器 — 根据工作流结果动态生成 dashboard.html
用法:
  python generate_dashboard.py --mode answer --date 2026-07-01
  python generate_dashboard.py --mode article --date 2026-07-01
  python generate_dashboard.py --mode both --date 2026-07-01
"""

import sys
import json
import os
import shutil
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = SKILL_DIR / "assets"
TEMPLATE_FILE = ASSETS_DIR / "dashboard_template.html"


def generate_dashboard(
    output_path: str,
    mode: str = "both",
    date_str: str = None,
    answer_data: dict = None,
    article_data: dict = None,
):
    """
    生成看板 HTML。

    Args:
        output_path: 输出文件路径
        mode: "answer" | "article" | "both"
        date_str: 日期字符串 YYYY-MM-DD
        answer_data: 回答工作流数据 {"stats": {...}, "questions": [...], "answers": [...]}
        article_data: 文章工作流数据 {"stats": {...}, "articles": [...], "backup_topics": [...]}
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    if not TEMPLATE_FILE.exists():
        print(f"[ERROR] 模板文件不存在: {TEMPLATE_FILE}")
        return False

    # 加载模板
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        template = f.read()

    # 默认数据
    if answer_data is None:
        answer_data = {
            "stats": {"recommend": 100, "invited": 100, "hot": 30, "matched": 0, "selected": 0},
            "questions": [],
        }

    if article_data is None:
        article_data = {
            "stats": {"directions": 0, "written": 0, "backup": 0, "words": 0},
            "articles": [],
            "backup_topics": [],
        }

    # 替换模板变量
    template = template.replace("{{DATE}}", date_str)
    template = template.replace("{{MODE}}", mode)

    # 统计数据
    for key, val in answer_data.get("stats", {}).items():
        template = template.replace(f"{{{{ANSWER_STATS_{key.upper()}}}}}", str(val))
    for key, val in article_data.get("stats", {}).items():
        template = template.replace(f"{{{{ARTICLE_STATS_{key.upper()}}}}}", str(val))

    # 问题列表
    questions_html = ""
    for i, q in enumerate(answer_data.get("questions", []), 1):
        questions_html += f"""
    <div class="q-card">
      <div class="q-header">
        <div style="display:flex;align-items:flex-start;gap:12px;flex:1">
          <div class="q-num">{i}</div>
          <div>
            <div class="q-title">{q.get('title', '')}</div>
            <div class="q-meta">
              <span>👁 {q.get('view_count', 0):,}</span>
              <span>👥 {q.get('follower_count', 0)}</span>
              <span>💬 {q.get('answer_count', 0)}</span>
              <span class="tag">{q.get('source', '')}</span>
            </div>
          </div>
        </div>
        <div class="publish-status status-done">✅ 草稿已保存</div>
      </div>
      <div class="q-url"><a href="{q.get('url', '#')}" target="_blank">{q.get('url', '')}</a></div>
      <button class="toggle-answer" onclick="toggleAnswer('a{i}')">查看生成回答 ▼</button>
      <div class="answer-preview" id="a{i}" style="display:none">{q.get('answer_preview', '等待生成...')}</div>
    </div>"""

    template = template.replace("{{QUESTIONS}}", questions_html)

    # 文章列表
    articles_html = ""
    for art in article_data.get("articles", []):
        articles_html += f"""
    <div class="q-card article-card">
      <div class="q-header">
        <div style="flex:1">
          <div class="q-title">{art.get('title', '')}</div>
          <div class="q-meta">
            <span class="tag tag-hot">🔥 热榜关联</span>
            <span class="tag tag-article">{art.get('tags', '')}</span>
            <span>📅 {art.get('date', '')}</span>
          </div>
        </div>
        <div class="publish-status status-done">✅ 草稿已保存</div>
      </div>
      <div class="q-url">
        知乎草稿：<a href="{art.get('draft_url', '#')}" target="_blank">{art.get('draft_url', '')}</a>
      </div>
      <button class="toggle-answer" onclick="toggleAnswer('art-{art.get('id', '0')}')">查看文章正文 ▼</button>
      <div class="article-full" id="art-{art.get('id', '0')}" style="display:none">{art.get('body_html', '')}</div>
    </div>"""

    template = template.replace("{{ARTICLES}}", articles_html)

    # 备选选题
    backup_html = ""
    for i, topic in enumerate(article_data.get("backup_topics", [])):
        backup_html += f'      <div class="backup-item"><strong>方向{i+2}</strong> — {topic.get("title", "")} | 热度源：{topic.get("source", "")}</div>\n'

    template = template.replace("{{BACKUP_TOPICS}}", backup_html)

    # 写入输出文件
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(template)

    print(f"✅ 看板已生成: {output_path}")
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="生成知乎内容创作看板")
    parser.add_argument("--output", default="dashboard.html", help="输出文件路径")
    parser.add_argument("--mode", default="both", choices=["answer", "article", "both"])
    parser.add_argument("--date", help="日期 (YYYY-MM-DD)")
    parser.add_argument("--data", help="JSON 数据文件路径")
    args = parser.parse_args()

    data = {}
    if args.data and os.path.exists(args.data):
        with open(args.data, "r", encoding="utf-8") as f:
            data = json.load(f)

    generate_dashboard(
        output_path=args.output,
        mode=args.mode,
        date_str=args.date,
        answer_data=data.get("answer"),
        article_data=data.get("article"),
    )

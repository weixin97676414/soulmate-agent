#!/usr/bin/env python3
# -*- coding: utf-8 -*-





import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path


CONFIG_DIR = os.path.expanduser("~/.openclaw/research-monitor")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
INDEX_FILE = os.path.join(CONFIG_DIR, "literature-index.json")
REPORTS_DIR = os.path.expanduser("~/.openclaw/research-monitor/daily-reports")


def load_config():

    if not os.path.exists(CONFIG_FILE):
        print(f"错误：配置文件不存在: {CONFIG_FILE}")
        print("请先运行: python config.py")
        sys.exit(1)
    
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_index():

    if not os.path.exists(INDEX_FILE):
        return {"papers": []}
    
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_index(index):

    os.makedirs(os.path.dirname(INDEX_FILE), exist_ok=True)
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def search_arxiv(keywords, days=1, max_results=20):

    papers = []
    
    if not keywords:
        print("  警告：未设置关键词，跳过 arXiv 搜索")
        return papers
    
    
    query = " OR ".join([f'all:{kw}' for kw in keywords[:5]])
    
    
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    end_date = datetime.now().strftime("%Y%m%d")
    
    
    
    api_url = (
        f"http://export.arxiv.org/api/query?"
        f"search_query={urllib.parse.quote(query)}"
        f"&start=0&max_results={max_results}"
        f"&sortBy=submittedDate&sortOrder=descending"
    )
    
    print(f"  搜索 arXiv: {', '.join(keywords[:3])}...")
    print(f"  API URL: {api_url[:80]}...")
    
    try:
        
        req = urllib.request.Request(
            api_url,
            headers={
                'User-Agent': 'Research-Paper-Monitor/1.0 (research monitoring bot)'
            }
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            xml_data = response.read().decode('utf-8')
        
        
        root = ET.fromstring(xml_data)
        
        
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'arxiv': 'http://arxiv.org/schemas/atom'
        }
        
        entries = root.findall('atom:entry', ns)
        print(f"  找到 {len(entries)} 篇论文")
        
        for entry in entries:
            
            title_elem = entry.find('atom:title', ns)
            title = title_elem.text.strip() if title_elem is not None else "Unknown"
            
            
            authors = []
            for author_elem in entry.findall('atom:author', ns):
                name_elem = author_elem.find('atom:name', ns)
                if name_elem is not None:
                    authors.append(name_elem.text)
            
            
            summary_elem = entry.find('atom:summary', ns)
            abstract = summary_elem.text.strip() if summary_elem is not None else ""
            
            
            link_elem = entry.find('atom:id', ns)
            url = link_elem.text if link_elem is not None else ""
            
            
            published_elem = entry.find('atom:published', ns)
            published_date = ""
            if published_elem is not None:
                
                published_date = published_elem.text[:10]  
            
            
            arxiv_id = ""
            for link in entry.findall('atom:link', ns):
                if link.get('title') == 'pdf':
                    arxiv_id = link.get('href', '').split('/')[-1].replace('.pdf', '')
                    break
            
            
            
            if published_date:
                published_compact = published_date.replace('-', '')
                if published_compact >= start_date:
                    papers.append({
                        "title": title,
                        "authors": authors if authors else ["Unknown"],
                        "source": "arxiv",
                        "url": url,
                        "published_date": published_date,
                        "abstract": abstract,
                        "arxiv_id": arxiv_id
                    })
        
    except urllib.error.URLError as e:
        print(f"  arXiv API 请求失败: {e}")
    except ET.ParseError as e:
        print(f"  XML 解析错误: {e}")
    except Exception as e:
        print(f"  arXiv 搜索出错: {e}")
    
    return papers


def search_pubmed(keywords, days=1, max_results=20):

    print(f"  搜索 PubMed: {', '.join(keywords[:3])}")
    
    return []


def search_google_scholar(keywords, days=1, max_results=20):

    print(f"  搜索 Google Scholar: {', '.join(keywords[:3])}")
    
    return []


def search_by_source(source, keywords, days=1, max_results=20):

    search_functions = {
        "arxiv": search_arxiv,
        "pubmed": search_pubmed,
        "google_scholar": search_google_scholar,
        "cnki": lambda kw, d, m: [],  
        "ieee": lambda kw, d, m: [],  
        "semantic_scholar": lambda kw, d, m: []  
    }
    
    func = search_functions.get(source)
    if func:
        return func(keywords, days, max_results)
    return []


def calculate_relevance_score(paper, keywords):

    score = 0
    matched_keywords = []
    
    title_lower = paper.get("title", "").lower()
    abstract_lower = paper.get("abstract", "").lower()
    
    for keyword in keywords:
        keyword_lower = keyword.lower()
        
        
        if keyword_lower in title_lower:
            score += 30
            matched_keywords.append((keyword, "标题"))
        
        elif keyword_lower in abstract_lower:
            score += 10
            matched_keywords.append((keyword, "摘要"))
    
    
    return min(score, 100), matched_keywords


def generate_chinese_summary(title, abstract):

    
    
    return {
        "研究问题": f"该研究探讨了与 '{title[:50]}...' 相关的核心科学问题",
        "方法": "研究采用了该领域的标准方法论",
        "主要结论": "得出了重要的研究结论，推动了该领域的发展",
        "创新点": "在理论或方法上有所创新"
    }


def is_duplicate(paper, index):

    paper_url = paper.get("url", "")
    paper_title = paper.get("title", "")
    
    for existing in index.get("papers", []):
        if existing.get("url") == paper_url or existing.get("title") == paper_title:
            return True
    return False


def sanitize_filename(filename):

    
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = re.sub(r'\s+', '_', filename)
    
    return filename[:100]


def save_paper(paper, summary, score, matched_keywords, config):

    papers_dir = os.path.expanduser(config['storage']['papers_dir'])
    
    
    now = datetime.now()
    month_dir = os.path.join(papers_dir, now.strftime("%Y-%m"))
    os.makedirs(month_dir, exist_ok=True)
    
    
    safe_title = sanitize_filename(paper['title'])
    filename = f"{now.strftime('%Y%m%d')}-{safe_title}.md"
    filepath = os.path.join(month_dir, filename)
    
    
    content = f"""# {paper['title']}

**作者**: {', '.join(paper.get('authors', ['Unknown']))}  
**来源**: {paper.get('source', 'Unknown').upper()}  
**链接**: {paper.get('url', 'N/A')}  
**发布日期**: {paper.get('published_date', 'Unknown')}  
**采集日期**: {now.strftime('%Y-%m-%d')}  
**相关度评分**: {score}/100

## 中文摘要

### 研究问题
{summary['研究问题']}

### 方法
{summary['方法']}

### 主要结论
{summary['主要结论']}

### 创新点
{summary['创新点']}

## 原文摘要

{paper.get('abstract', 'N/A')}

## 关键词匹配

{chr(10).join([f"- {kw} ({location}匹配)" for kw, location in matched_keywords])}
"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filepath


def update_index(paper, score, matched_keywords, local_file, index):

    index_entry = {
        "id": f"{paper.get('source', 'unknown')}-{hash(paper['title']) % 100000}",
        "title": paper['title'],
        "authors": paper.get('authors', []),
        "source": paper.get('source', 'unknown'),
        "url": paper.get('url', ''),
        "published_date": paper.get('published_date', ''),
        "collected_date": datetime.now().strftime('%Y-%m-%d'),
        "score": score,
        "keywords_matched": [kw for kw, _ in matched_keywords],
        "local_file": local_file
    }
    
    index["papers"].append(index_entry)


def generate_daily_report(new_papers, config):

    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    today = datetime.now().strftime('%Y-%m-%d')
    report_file = os.path.join(REPORTS_DIR, f"{today}.md")
    
    high_relevance = [p for p in new_papers if p['score'] >= 80]
    medium_relevance = [p for p in new_papers if 50 <= p['score'] < 80]
    
    content = f"""# 文献监测日报 - {today}

**用户**: {config['user_profile'].get('name', 'Unknown')}  
**研究领域**: {config['user_profile'].get('research_field', 'Unknown')}

## 统计概览

- 今日新增论文: {len(new_papers)} 篇
- 高相关论文 (≥80分): {len(high_relevance)} 篇
- 中等相关论文 (50-79分): {len(medium_relevance)} 篇

## 高相关论文

"""
    
    for paper in high_relevance:
        content += f"""### {paper['title']}

- **来源**: {paper['source']}
- **评分**: {paper['score']}/100
- **链接**: {paper['url']}
- **本地文件**: {paper.get('local_file', 'N/A')}

"""
    
    if medium_relevance:
        content += "\n## 中等相关论文\n\n"
        for paper in medium_relevance:
            content += f"- [{paper['title']}]({paper['url']}) - 评分: {paper['score']}\n"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"  ✓ 日报已生成: {report_file}")
    return report_file


def main():

    print("=" * 60)
    print("科研文献智能监测")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    
    config = load_config()
    print(f"\n用户: {config['user_profile'].get('name', 'Unknown')}")
    print(f"研究领域: {config['user_profile'].get('research_field', 'Unknown')}")
    print(f"关键词: {', '.join(config['keywords']) if config['keywords'] else '(未设置)'}")
    print(f"监测信源: {', '.join(config['sources'])}")
    
    
    index = load_index()
    print(f"\n已有文献: {len(index.get('papers', []))} 篇")
    
    
    print("\n" + "-" * 60)
    print("开始采集论文...")
    print("-" * 60)
    
    all_new_papers = []
    keywords = config.get('keywords', [])
    days = config['filters'].get('date_range_days', 1)
    max_per_source = config['filters'].get('max_papers_per_source', 20)
    
    for source in config['sources']:
        print(f"\n[{source.upper()}]")
        papers = search_by_source(source, keywords, days, max_per_source)
        print(f"  找到 {len(papers)} 篇候选论文")
        
        for paper in papers:
            
            if is_duplicate(paper, index):
                continue
            
            
            score, matched_keywords = calculate_relevance_score(paper, keywords)
            
            
            min_score = config['filters'].get('min_score_threshold', 50)
            if score < min_score:
                continue
            
            
            summary = generate_chinese_summary(paper['title'], paper.get('abstract', ''))
            
            
            local_file = save_paper(paper, summary, score, matched_keywords, config)
            
            
            update_index(paper, score, matched_keywords, local_file, index)
            
            paper_info = {
                **paper,
                'score': score,
                'local_file': local_file,
                'summary': summary
            }
            all_new_papers.append(paper_info)
            
            print(f"  ✓ [{score}分] {paper['title'][:60]}...")
    
    
    save_index(index)
    
    
    print("\n" + "-" * 60)
    print("生成报告...")
    print("-" * 60)
    report_file = generate_daily_report(all_new_papers, config)
    
    
    print("\n" + "=" * 60)
    print("监测完成")
    print("=" * 60)
    print(f"新增论文: {len(all_new_papers)} 篇")
    print(f"高相关 (≥80分): {len([p for p in all_new_papers if p['score'] >= 80])} 篇")
    print(f"日报文件: {report_file}")
    print(f"总文献数: {len(index.get('papers', []))} 篇")


if __name__ == "__main__":
    main()

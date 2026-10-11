---
name: paper-monitor
description: 定时监测 arXiv/PubMed/Semantic Scholar 等学术信源，按关键词去重评分、生成中文摘要、本地归档，产出日报/周报（本地）。触发：追踪最新论文、论文监测、文献日报/周报。
author: Soulmate Agent团队成员：岸
---

# 科研文献智能监测与摘要归档

## 适用场景

- 定时监测学术信源（arXiv、PubMed、Google Scholar、CNKI、IEEE Xplore、Semantic Scholar），按关注关键词采集最新论文。
- 根据关键词筛选高相关论文，生成中文摘要（问题/方法/结论/创新点）。
- 本地归档并支持检索。

## 步骤

1. **初始化配置**：`python scripts/research-monitor/config.py`（交互式设置研究领域、关键词、信源、过滤）。
2. **运行监测**：`python scripts/research-monitor/monitor.py`，执行完整流程：
   - 采集：用 `web_search` 检索各信源最新论文，按发布日期过滤（默认过去 24 小时），每信源最多 20 篇。
   - 去重：对比 `literature-index.json`，按 DOI 或标题跳过已记录论文。
   - 评分：关键词匹配 标题(权重 3) + 摘要(权重 1)；高相关 ≥80 / 中等 50–79 / 低相关 <50。
   - 摘要：仅对高/中相关论文生成中文摘要。
   - 归档：写入 `research-papers/YYYY-MM/YYYYMMDD-{title}.md`，更新索引，按领域分类。
   - 报告：生成本地日报。
3. **（可选）生成综述**：`python scripts/research-monitor/generate_digest.py --days 7 --output weekly-digest.md`。
4. **（可选）单信源检索**：`python scripts/research-monitor/search_papers.py --source arxiv --keywords "transformer" --days 7`。

## 输入输出

- 输入：配置文件 `~/.openclaw/research-monitor/config.json`（研究领域、关键词、信源、过滤阈值、存储路径）。
- 输出：`research-papers/` 归档 markdown、`literature-index.json` 索引、`daily-reports/YYYY-MM-DD.md` 日报。

## 配置示例

```json
{
  "user_profile": { "name": "张三", "institution": "某大学", "research_field": "人工智能" },
  "keywords": ["large language model", "reasoning", "AI safety", "multimodal"],
  "sources": ["arxiv", "pubmed", "google_scholar"],
  "filters": { "max_papers_per_source": 20, "min_score_threshold": 50, "date_range_days": 1 },
  "storage": { "papers_dir": "~/.openclaw/research-papers", "index_file": "~/.openclaw/research-monitor/literature-index.json" }
}
```

## 注意事项

- 本功能默认走 **arXiv 公开 API**（免费、无需注册、无 API Key）；Google Scholar 覆盖广但限流严格，CNKI 中文库需注意反爬。
- 脚本位于 `scripts/research-monitor/`；配置与数据默认落在 `~/.openclaw/research-monitor/`（可用配置覆盖）。
- 配置为交互式脚本，**未验证**在纯非交互环境下能否无人值守运行。
- 去重依赖索引被正确更新；重复采集先查 `literature-index.json`。
- 采集慢可减少信源数或降低每信源论文数；摘要质量差可补充领域背景。

## 可复用示例

```bash
# 首次
python scripts/research-monitor/config.py
# 日常监测
python scripts/research-monitor/monitor.py
# 周报
python scripts/research-monitor/generate_digest.py --days 7 --output weekly-digest.md
# 单次定向
python scripts/research-monitor/search_papers.py --source arxiv --keywords "transformer" --days 7
```

论文存储格式（`YYYY-MM/YYYYMMDD-title.md`）字段：标题、作者、来源、链接、发布日期、采集日期、相关度评分、摘要（研究问题/方法/主要结论/创新点）、原文摘要、关键词匹配。

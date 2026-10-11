---
name: paper-search
description: 多源论文检索（arXiv/PubMed/Semantic Scholar），导出 BibTeX/RIS/JSON/Markdown 引用列表并下载 PDF 全文。触发：找论文、检索文献、找相关文献/相关工作、要参考文献/引用列表、导出 BibTeX/RIS、下载文献。
author: Soulmate Agent团队成员：岸
---

# 论文检索与引用列表

## 适用场景

- 用户要"找论文""检索文献""搜索研究""找相关文献/相关工作"。
- 需要跨数据库检索：arXiv（物理/数学/CS/统计）、PubMed（生物医学）、Semantic Scholar（CS/交叉学科）。
- 需要生成参考文献：BibTeX、RIS、JSON、Markdown；需要下载 PDF 全文。

## 步骤

1. **确认范围**：主题关键词、子领域、侧重（综述 / 奠基性 / 最新）、时间范围。
2. **检索**：用统一脚本 `scripts/research.py <source> "<query>" [选项]`。
   - `source` 取值：`arxiv`、`pubmed`、`semantic`。
   - 多源交叉验证：同一主题分别跑多个 source，对比结果。
3. **筛选/去重**：保留高被引与较新版本；同一论文优先期刊/会议版而非预印本。
4. **输出引用列表**：字段统一为 **Authors. Title. Venue. Year. DOI/URL**，条目式。
5. **（可选）导出** BibTeX/RIS、下载 PDF；按需扩检（年份、venue、子主题）。

## 输入输出

- 输入：检索词（必填）；可选过滤（年份、作者、被引下限、分类、发表日期区间）。
- 输出：文本 / JSON / BibTeX / RIS / Markdown 结果；可选 PDF 文件与引用文件。

## 常用命令

```bash
# 环境（首次）：见 scripts/research-requirements.txt；建议虚拟环境
python -m venv venv && source venv/bin/activate
pip install -r scripts/research-requirements.txt

# 检索
python scripts/research.py arxiv "graph neural networks" --max-results 20
python scripts/research.py pubmed "covid vaccine" --publication-type "Clinical Trial"
python scripts/research.py semantic "transformers" --min-citations 100

# 导出
python scripts/research.py arxiv "deep learning" --format bibtex --output refs.bib
python scripts/research.py pubmed "gene editing" --format ris --output genes.ris
python scripts/research.py arxiv "topic" --format json --output results.json

# 下载全文
python scripts/research.py arxiv "attention mechanism" --download --max-results 10 --output-dir papers/
```

| 参数 | 说明 |
|------|------|
| `-n, --max-results` | 返回条数（默认 10，最大 100） |
| `-f, --format` | `text｜json｜bibtex｜ris｜markdown` |
| `-o, --output` | 保存到文件 |
| `--sort-by` | `relevance｜date｜citations` |
| `--year / --start-date / --end-date` | 时间过滤 |
| `--author` | 作者过滤 |
| `--min-citations` | 被引下限 |
| `--category` | arXiv 分类（如 `cs.AI`） |
| `--publication-type` / `--full-text` | PubMed 专用 |
| `--include-references` | Semantic Scholar 专用 |
| `--download` / `--output-dir` | 下载 PDF 及目录 |
| `--citations` / `--citation-format` | 抽取引用（bibtex/ris/json） |

## 注意事项

- **访问合规**：优先官方 API 与公开页面；**不要抓取**禁止自动化访问或需鉴权的站点。Google Scholar 无官方 API，仅可在用户提供导出结果或人工结果时使用，不要自动化。Scopus / Web of Science 为订阅服务，仅在用户提供 API key 或机构登录时纳入，否则注明"不可用"。
- **下载规范**：遵守速率限制，避免一次性批量下载；核对许可与机构访问政策，不要二次分发。
- 各库布尔语法不统一，没有跨库统一查询语法；检索结果可能与网页界面不同。
- 下载失败多因该论文无 PDF 或需订阅，属正常情况。
- 本功能依赖 `scripts/research.py`（本地脚本，非平台插件），首次使用需按依赖清单安装；不同 Python 环境可用性**未验证**。

## 可复用示例

**文献综述组合流程**

```bash
python scripts/research.py arxiv "graph neural networks" --max-results 20 --format json --output arxiv_gnn.json
python scripts/research.py semantic "graph neural networks" --max-results 20 --format json --output semantic_gnn.json
python scripts/research.py arxiv "graph neural networks" --format bibtex --output gnn_references.bib
python scripts/research.py arxiv "graph neural networks" --download --max-results 10 --output-dir papers/gnn/
```

**跟踪最新/高被引**

```bash
python scripts/research.py arxiv "large language models" --year 2023 --sort-by date --max-results 30
python scripts/research.py semantic "reinforcement learning" --min-citations 500 --sort-by citations
```

**输出示例（BibTeX）**

```bibtex
@article{vaswani2017attention,
  title={Attention Is All You Need},
  author={Vaswani, Ashish and Shazeer, Noam and ...},
  journal={arXiv preprint arXiv:1706.03762},
  year={2017}
}
```
